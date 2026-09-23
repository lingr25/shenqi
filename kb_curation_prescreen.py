"""Local deterministic pre-screen for the curated high-quality layer.

Read-only over kb_trial/ and kb/. No API, no model scoring. Output is a candidate pool
plus per-rule flag evidence that a reviewing agent must then verify one by one against
the original subtitle / ASR / QQ evidence. Nothing here is an acceptance verdict;
kb_curation_rules.py decides what may ship.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'
QQ_CARDS_PATH = ROOT / 'qq_cards/cards.jsonl'


def load_qq_cards():
    """window_id -> card. The QQ track has no per-clip transcript file, so the card's
    source_spans are its only locatable evidence."""
    if not QQ_CARDS_PATH.exists():
        return None
    return {c['window_id']: c for c in (json.loads(l) for l in
                                        QQ_CARDS_PATH.read_text(encoding='utf-8').splitlines() if l.strip())}


QQ_CARDS = load_qq_cards()


REF = re.compile(r'(?:ctx=)?sub:BV[\w]+:\d+|BV[\w]+:p\d+:a\d+:[0-9a-f]{8}')
RULE_LINE = re.compile(r'^- (?P<body>.+?)\s*$')
SUFFIX = re.compile(
    r'\(主语:(?P<subject>.*?)(?:\s\|\s条件:(?P<condition>.*?))?'
    r'(?:\s\|\sscope:(?P<scope>.*?))?(?:\s\|\s证据:(?P<evidence>.*?))?\)\s*$')
PILOT_SUFFIX = re.compile(
    r'\s*\(主语:(?P<subject>.*?)(?:\s\|\s条件:(?P<condition>.*?))?'
    r'(?:\s\|\sscope:(?P<scope>.*?))?\)\s*$')
TAIL_ANNOT = re.compile(r'\s*\[(?:非通则|门控|实例)[^\]]*\]')
HEDGE = ('我怀疑', '不确定', '记不太清', '我记得', '我印象', '如果我没记错', '好像是',
         '大概吧', '也许', '不太确定', '说不定', '记不清', '我猜', '可能吧')
CHAT = ('哈哈哈', '笑死', '233', '谢了', '谢谢', '晚安', '早上好', '下播', '礼物', '投币', '三连',
        '充钱', '打钱', '来了来了')
SUPERLATIVE = ('最强', '必练', '优先级最高', '垃圾', '废物', '人权', '推荐练', '不值', '很值',
               '吊打', '无敌强')
NUMBER = re.compile(r'\d|[一二三四五六七八九十百零]+(?:帧|针|次|秒|格|倍|血|费|万|千)')
PLACEHOLDER = re.compile(r'^(未点名|未说明|待定|未知|待补|无|n/a|None)')
ASR_SUSPECT = ('镜像力', '维尼斯', '一针', '两针', '三针', '四针', '五针', '八针', '针)',
               '锁敌', '动画制', '素心', '童真', '紫兰', '小克', '海默针')
FRAGMENT_END = ('的', '是', '在', '了', '和', '与', '或', '而', '就', '也', '都', '很')


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def sections(text):
    out, current = {}, None
    for line in text.splitlines():
        if line.startswith('## '):
            current = line[3:].strip()
            out.setdefault(current, [])
            continue
        if current:
            out[current].append(line)
    return out


def parse_rule(body, with_suffix=True):
    m = (SUFFIX.search(body) or PILOT_SUFFIX.search(body)) if with_suffix else None
    fields, claim = {}, body
    if m:
        claim = body[:m.start()].strip()
        for key in ('subject', 'condition', 'scope', 'evidence'):
            if m.group(key):
                fields[key] = m.group(key).strip()
    claim = TAIL_ANNOT.sub('', claim).strip()
    return claim, fields, REF.findall(body)


def flags_for(claim, fields, refs, doc, with_suffix):
    layers = doc.get('source_layers') or []
    flags = []
    if with_suffix:
        if not fields.get('subject'):
            flags.append('no_subject_suffix')
        elif PLACEHOLDER.match(fields['subject']):
            flags.append('subject_placeholder')
        if not fields.get('scope'):
            flags.append('no_scope_suffix')
        if not fields.get('condition'):
            flags.append('no_condition')
        if not refs:
            flags.append('no_citation')
        if not any(r.startswith('BV') for r in refs):
            flags.append('no_atom_citation')
    if any(h in claim for h in HEDGE):
        flags.append('hedge_or_memory')
    if any(c in claim for c in CHAT):
        flags.append('chit_chat')
    if any(s in claim for s in SUPERLATIVE):
        flags.append('opinion_lexicon')
    if NUMBER.search(claim):
        flags.append('contains_number')
    if 'asr' in layers:
        flags.append('asr_layer')
    if 'official' not in layers:
        flags.append('no_official_layer')
    if any(s in claim for s in ASR_SUSPECT):
        flags.append('asr_suspect_word')
    if not claim or len(claim) < 4:
        flags.append('too_short')
    if claim.endswith(FRAGMENT_END):
        flags.append('fragment_tail')
    return flags


def qq_span_evidence(doc_id, src=None):
    """Return sanitized QQ evidence for a doc, or None.

    QQ windows/canonical cards are not VOD clips, so they carry no BV atom id. Their
    real provenance is qq_cards/cards.jsonl: source message ids plus the literal message
    spans. Those spans are ordinary group members talking, so the shipped citation keeps
    only the span text plus the window id and message count -- never a QQ number, nick
    name or any per-person identifier.

    qq_atom rows are single claims carved out of a window, so they resolve to the same
    window's spans rather than being treated as sourceless.
    """
    cards = QQ_CARDS
    if cards is None:
        return None
    key = doc_id.split(':', 1)[1]
    if key not in cards and src and src.get('window_id'):
        key = src['window_id']
    card = cards.get(key)
    if not card:
        return None
    spans = [re.sub(r'\s+', ' ', s).strip() for s in (card.get('source_spans') or []) if s and s.strip()]
    if not spans:
        return None
    return {
        'kind': 'qq_span',
        'window_id': key,
        'as_of': card.get('as_of'),
        'n_source_msgs': len(card.get('source_msg_ids') or spans),
        'spans': spans,
    }


def vod_evidence_citations(evidence):
    """Convert a doc's inline evidence list into citation refs.

    Some VOD docs (pilot_evidence, vod_atom, vod_cluster) do not carry a BV atom id in
    their text; their evidence is an explicit list of {file, t, text} transcript entries.
    That is fully locatable evidence, so it is normalised into the same citation shape the
    atom path produces rather than being discarded for lacking an atom id.
    """
    out = []
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        f, t = e.get('file'), e.get('t')
        if f and t is not None:
            out.append({'file': f, 't_start': t, 'text': e.get('text') or '',
                        'layer': e.get('layer')})
    return out


def build_pool():
    docs = load_jsonl(TRIAL / 'docs.jsonl')
    mech = [d for d in docs if d.get('mode') == 'mechanism']
    prod = {d['id']: d for d in load_jsonl(ROOT / 'kb/docs.jsonl')}
    audit = {d['id']: d for d in load_jsonl(ROOT / 'kb/quality_audit_v2.jsonl')}
    for d in load_jsonl(ROOT / 'kb/quality_audit.jsonl'):
        audit.setdefault(d['id'], d)
    rows = []
    for d in mech:
        text = d.get('text') or ''
        sec = sections(text)
        p, a = prod.get(d['id']) or {}, audit.get(d['id']) or {}
        base = {
            'doc_id': d['id'],
            'doc_type': d['doc_type'],
            'category': d.get('category'),
            'track': d.get('track'),
            'source_layers': d.get('source_layers'),
            'affirmative_rule_idx': d.get('affirmative_rule_idx'),
            'demoted_rule_idx': d.get('demoted_rule_idx'),
            'gated_rules': d.get('gated_rules'),
            'scope_doc': d.get('scope'),
            'confidence': d.get('confidence'),
            'claim_type': d.get('claim_type') or p.get('claim_type'),
            'issue_status': d.get('issue_status'),
            'novelty': d.get('novelty'),
            'audit_kind': p.get('audit_kind') or a.get('kind'),
            'audit_verdict': a.get('verdict'),
            'audit_subject_ok': a.get('subject_ok'),
            'audit_reason': a.get('reason'),
            'review_human': (d.get('review') or {}).get('human'),
            'doc_subject': d.get('subject'),
            'context_incomplete': d.get('context_incomplete'),
            'provenance_file': (d.get('provenance') or {}).get('file'),
            'recorded_ym': d.get('recorded_ym'),
            'qq_evidence': qq_span_evidence(d['id'], d.get('source')) if 'qq' in (d.get('source_layers') or []) else None,
            'inline_evidence': vod_evidence_citations(d.get('evidence')),
        }
        emitted = False
        if '规则' in sec:
            for i, line in enumerate(sec['规则']):
                m = RULE_LINE.match(line)
                if not m:
                    continue
                claim, fields, refs = parse_rule(m['body'], True)
                row = dict(base, rule_idx=i, claim=claim, suffix_subject=fields.get('subject'),
                           suffix_condition=fields.get('condition'), suffix_scope=fields.get('scope'),
                           citation_refs=refs, render_mode='rubric_rule')
                row['flags'] = flags_for(claim, fields, refs, d, True)
                rows.append(row)
                emitted = True
        if not emitted and text.strip():
            first = text.splitlines()[0].strip()
            bullets = [ln for ln in text.splitlines() if ln.startswith('- ')]
            claims = bullets if first.startswith('#') and bullets else [first]
            for i, line in enumerate(claims):
                raw = line[2:] if line.startswith('- ') else line
                claim, fields, refs = parse_rule(raw, False)
                row = dict(base, rule_idx=i, claim=claim, suffix_subject=None,
                           suffix_condition=None, suffix_scope=None, citation_refs=refs,
                           render_mode='closed_form')
                row['flags'] = flags_for(claim, fields, refs, d, False)
                rows.append(row)
    return rows, mech


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows, mech = build_pool()
    doc_ids = {r['doc_id'] for r in rows}
    stats = {
        'mechanism_docs': len(mech),
        'mechanism_docs_with_candidates': len(doc_ids),
        'rule_candidates': len(rows),
        'by_doc_type': dict(Counter(r['doc_type'] for r in rows).most_common()),
        'by_category': dict(Counter(r['category'] for r in rows).most_common()),
        'by_track': dict(Counter(r['track'] for r in rows).most_common()),
        'by_source_layer': dict(Counter('+'.join(r['source_layers']) for r in rows).most_common()),
        'by_flag': dict(Counter(f for r in rows for f in r['flags']).most_common()),
        'by_audit_kind': dict(Counter(str(r['audit_kind']) for r in rows).most_common()),
        'by_review_human': dict(Counter(str(r['review_human']) for r in rows).most_common()),
        'numeric_candidates': sum('contains_number' in r['flags'] for r in rows),
        'asr_candidates': sum('asr_layer' in r['flags'] for r in rows),
    }
    (OUT / 'candidates.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'prescreen_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
