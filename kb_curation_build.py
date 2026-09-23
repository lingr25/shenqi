"""Build kb_trial/curated_high_quality.json - the curated, externally usable layer.

The output is a single JSON object (not JSONL) with a schema_version and an entries
array, so an external model can consume it directly. Each entry carries its own
subject / condition / scope / citations / source files and timestamps, the source layer,
and the review status with its reason.

The builder never overwrites the full trial artifacts and never touches kb/.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import kb_curation_rules as R
import kb_curation_qq_expansion_loader as EXPANSION_LOADER
from entity_corrector import correct_text

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'
CURATED = TRIAL / 'curated_high_quality.json'
REF_ATOM = re.compile(r'BV[\w]+:p\d+:a\d+:[0-9a-f]{8}')
REF_SUB = re.compile(r'(?:ctx=)?sub:(BV[\w]+):(\d+)')
LAYER_LABEL = {'official': '官方AI字幕', 'asr': '云端ASR重转写(无官方字幕分P)',
               'qq': 'QQ群聊',
               'asr+official': '官方AI字幕+云端ASR重转写',
               'official+asr': '官方AI字幕+云端ASR重转写', 'unknown': '来源未知'}
QQ_NUMBER = re.compile(r'(?<!\d)\d{6,12}(?!\d)')
SCHEMA_VERSION = R.SCHEMA_VERSION


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence_index():
    return {e['id']: e for e in load_jsonl(TRIAL / 'evidence.jsonl')}


# LLM 章节标题（knowledge_pilot/*.chapters.json，经 atoms → evidence → citations 一路带入）
# 是派生元数据而非逐字引文，可安全订正；ASR 讹写归一在此登记。
CHAPTER_REPAIRS = {
    '四种移动逻辑与鼠传送的事件结算顺序': '四种移动逻辑与黍传送的事件结算顺序',
    '纳斯提回转修正及传染对群相互减伤机制推导': '缇缇沉睡传染与起床爆炸机制推导',
}


def citation_objects(row, evidence):
    """Resolve each citation to a locatable object with file, timestamp and quote.

    Three provenance shapes resolve here, none privileged over the others: VOD clip atoms,
    VOD inline transcript evidence, and QQ spans. QQ spans are emitted with their window id
    and literal message text only -- message ids and any per-person identifier stay out.
    """
    out = []
    for ref in row['citation_refs']:
        item = evidence.get(ref)
        if item is None:
            out.append({'id': ref, 'status': 'unresolved'})
            continue
        entry = {'id': ref, 'status': item['status'],
                 'source_layers': item['source_layers']}
        if item['status'] == 'resolved_atom':
            clips = (item.get('evidence') or {}).get('clips') or []
            source = item.get('source') or {}
            stem = source.get('bvid_stem') or Path(item.get('transcript_file') or '').stem
            entry.update({
                'transcript_file': item.get('transcript_file'),
                'bvid_stem': source.get('bvid_stem'),
                'recorded_at': source.get('recorded_at'),
                'speaker': source.get('speaker'),
                'chapter': CHAPTER_REPAIRS.get(source.get('chapter'), source.get('chapter')),
                'quotes': [{'text': correct_text(c.get('quote') or '', stem), 't_start': c.get('t_start'), 't_end': c.get('t_end')}
                           for c in clips],
                # the upstream atom quote is itself a normalised derivative; expose it so
                # traceability can be graded without re-reading production files
                '_upstream_quote': correct_text(clips[0].get('quote') or '', stem) if clips else None,
            })
        elif item['status'] == 'resolved_timestamp_window':
            stem = Path(item.get('file') or '').stem
            entry.update({
                'transcript_file': item.get('file'),
                'requested_second': item.get('requested_second'),
                'quotes': [{'text': correct_text(item.get('quote_line') or '', stem), 't_start': item.get('requested_second'),
                            't_end': None}],
            })
        out.append(entry)
    for ev in (row.get('inline_evidence') or []):
        if not (ev.get('file') and ev.get('text')):
            continue
        # inline_evidence 存的是抽取当时的逐字稿文本；纠错规则更新后逐字稿会变，
        # 此处用同一套 correct_text 把存量引文同步到当前逐字稿口径，保持逐字可追溯
        stem = Path(ev['file']).stem
        out.append({
            'id': f"inline:{ev['file']}@{ev['t_start']}", 'status': 'resolved_inline_evidence',
            'source_layers': ['official'] if ev.get('layer') == 'official_txt' else ['asr'],
            'transcript_file': ev['file'],
            'quotes': [{'text': correct_text(ev['text'], stem), 't_start': ev['t_start'], 't_end': None}],
        })
    qq = row.get('qq_evidence')
    if qq and qq.get('spans'):
        out.append({
            'id': f"qq:{qq['window_id']}", 'status': 'resolved_qq_span',
            'source_layers': ['qq'], 'track': 'qq_chat',
            'window_id': qq['window_id'], 'as_of': qq.get('as_of'),
            'n_source_msgs': qq.get('n_source_msgs'),
            'quotes': [{'text': t, 't_start': None, 't_end': None} for t in qq['spans']],
            'note': 'QQ 群聊原文片段，已脱敏：仅保留消息文本与窗口标识，不含群号、QQ 号或昵称',
        })
    return out


def dedupe_claims(entries):
    """Collapse rules with identical normalised text, keeping every origin recorded.

    Deduplication must not erase provenance: the dropped copy is retained under
    ``also_from`` on the surviving entry so an approved card's rule stays traceable.
    """
    rank = {'user_verified': 3, 'agent_verified': 2, 'auto_screened': 1}
    best, order = {}, []
    for e in entries:
        key = R.normalise(e['claim'])
        if key not in best:
            best[key] = e
            order.append(key)
        elif rank[e['review']['status']] > rank[best[key]['review']['status']]:
            e['also_from'] = best[key].get('also_from', []) + [best[key]['origin']]
            best[key] = e
        else:
            best[key].setdefault('also_from', []).append(e['origin'])
    return [best[k] for k in order]


def load_qq_overlay(path):
    """Load the per-entry QQ re-derivation, keyed by curated entry id.

    QQ rule sentences shipped upstream were frequently window TITLES rather than mechanism
    statements ("嘲讽机制数值与仇恨异常表现"), while subject/condition/scope sat unfilled.
    The overlay states the mechanism the spans actually carry, with its subject and
    applicability stated. It is authored by `kb_curation_evidence_close.py`, which derives
    it from the spans in `curation/qq_worklist.json`; every record is diffable, and a record
    left out means the spans cannot settle the claim, so that entry must not ship.
    """
    if not path.exists():
        raise SystemExit('QQ overlay missing: %s (run kb_curation_evidence_close.py)' % path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    return {r['entry_id']: r for r in payload['records']}


def load_semantic_review(path):
    """Load the per-entry semantic review, keyed by curated entry id.

    This is a claim-level semantic pass only: it decides whether a claim is an
    independently reusable mechanism, and it must not be merged into review.status,
    which records evidence review. The two are reported side by side.
    """
    if not path.exists():
        return None, {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload, {r['entry_id']: r for r in payload['records']}


def build_entries(decisions, evidence, verifications, semantic=None, qq_overlay=None):
    semantic = semantic or {}
    qq_overlay = qq_overlay or {}
    entries = []
    dropped = []
    for row in decisions:
        if row['decision'] != 'accept':
            continue
        doc_id, idx = row['doc_id'], row['rule_idx']
        key = (doc_id, idx)
        entry_id = f'{doc_id}#r{idx}'
        sem = semantic.get(entry_id)
        if sem and sem['verdict'] == 'drop':
            dropped.append({'id': entry_id, 'info_value': sem['info_value'],
                            'reason': sem['reason']})
            continue
        citations = citation_objects(row, evidence)
        source_files = sorted({c.get('transcript_file') for c in citations if c.get('transcript_file')})
        layers = [l for l in row['source_layers']]
        qq_track = any(c.get('status') == 'resolved_qq_span' for c in citations)
        entry = {
            'id': entry_id,
            'claim': row['claim'],
            # Field contract: an absent value is stated, never left as a bare null. A reader
            # must be able to tell "the source did not name it" from "we did not extract it".
            'subject': row['suffix_subject'] or '未标注',
            'condition': row['suffix_condition'] or '未标注',
            'scope': row['suffix_scope'] or '未标注',
            'category': row['category'],
            'recorded_ym': row.get('recorded_ym'),
            'source_layer': 'QQ群聊' if qq_track else LAYER_LABEL.get(
                '+'.join(sorted(set(layers))), '+'.join(layers)),
            'source_layers': layers,
            'track': row['track'],
            'citations': citations,
            'source_files': source_files,
            'origin': {
                'trial_doc_id': doc_id,
                'trial_rule_idx': idx,
                'trial_manifest_outputs': 'kb_trial/docs.jsonl',
                'upstream_record': row.get('provenance_file'),
                'card_section': '规则',
            },
            'review': {
                'status': row['review_status'],
                'reason': row['review_note'],
                'not_authoritative': True,
            },
            'conflict_policy': ('no automatic precedence: where sources disagree, all sides '
                                'must be shown and the disagreement left standing for a human '
                                'to resolve; nothing is auto-adjudicated by source layer'),
            'disclaimer': '草稿层条目：本层是草稿，不是官方发布；数值与机制结论在用于生产前'
                          '应回看引文所指时刻的原片。上游授权与公开范围由项目负责人决定。',
        }
        if qq_track:
            entry['disclaimer'] += (' QQ 轨条目的唯一来源是群聊片段（已脱敏，不含群号与个人标识）；'
                                    '本层不对来源分层设自动优先级，与录播轨条目产生分歧时按 '
                                    'conflict_policy 并列呈现、留待人工判断。')
            ov = qq_overlay.get(entry_id)
            if ov:
                # A window title must never ship as a mechanism sentence: replace it with
                # the mechanism the spans carry, and state subject/condition/scope. The
                # evidence-review stage runs after this one and judges the new claim itself,
                # so start it from a neutral status rather than an inherited verdict.
                if entry['claim'] != ov['claim_from']:
                    raise SystemExit('QQ overlay claim mismatch for %s: have %r want %r'
                                     % (entry_id, entry['claim'], ov['claim_from']))
                entry['claim'] = ov['claim']
                entry['subject'] = ov['subject']
                entry['condition'] = ov['condition']
                entry['scope'] = ov['scope']
                entry['claim_derivation'] = {
                    'source': 'kb_trial/curation/qq_claim_overlay.json',
                    'rule_idx': idx,
                    'from': ov['claim_from'],
                    'to': ov['claim'],
                    'note': ov['note'],
                }
                entry['review']['status'] = 'auto_screened'
        v = verifications.get(key)
        if v:
            entry['review']['verification'] = v['reason']
        if sem:
            entry['semantic_review'] = {
                'verdict': sem['verdict'],
                'support': sem['support'],
                'info_value': sem['info_value'],
                'reason': sem['reason'],
                'reviewer_type': sem['reviewer_type'],
            }
        entries.append(entry)
    return entries, dropped


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    decisions = load_jsonl(OUT / 'decisions.jsonl')
    evidence = evidence_index()
    verifications = {}
    vpath = OUT / 'agent_verifications.json'
    if vpath.exists():
        for v in json.loads(vpath.read_text(encoding='utf-8'))['verifications']:
            verifications[(v['doc_id'], v['rule_idx'])] = v
    sem_payload, semantic = load_semantic_review(OUT / 'semantic_review.json')
    qq_overlay = load_qq_overlay(OUT / 'qq_claim_overlay.json')
    entries, dropped = build_entries(decisions, evidence, verifications, semantic, qq_overlay)
    entries_before = len(entries)
    entries = dedupe_claims(entries)
    entries.sort(key=lambda e: e['id'])

    # Phase-2 QQ expansion: approved manifest entries are appended here, after the upstream
    # decision pipeline and outside dedupe_claims, so they can neither be collapsed into nor
    # rewrite an existing entry. The loader is inert until the manifest is actually approved.
    expansion_entries, expansion_report = EXPANSION_LOADER.load_expansion_entries(
        existing_ids=[e['id'] for e in entries])
    if expansion_report['failures']:
        raise SystemExit('QQ expansion manifest failed re-verification: %s'
                         % expansion_report['failures'][:5])

    # Phase-3 b3 batch: same append-only path, separate manifest and separate frozen
    # materials (workorders_b3/ + reviews_b3/ + audit_decisions_b3.json). Its own gate is
    # the manifest status, so it too stays inert until that manifest is approved.
    cfg_b3 = EXPANSION_LOADER.BATCHES['b3']
    b3_entries, b3_report = EXPANSION_LOADER.load_expansion_entries(
        workorders=cfg_b3['workorders'], reviews=cfg_b3['reviews'],
        audit_path=cfg_b3['audit_path'], batch='b3',
        existing_ids=[e['id'] for e in entries] + [e['id'] for e in expansion_entries])
    if b3_report['failures']:
        raise SystemExit('QQ expansion b3 manifest failed re-verification: %s'
                         % b3_report['failures'][:5])

    # Phase-4 b4 batch: same append-only path, separate manifest and separate frozen materials
    # (workorders_b4/ + reviews_b4/ + audit_decisions_b4.json). Same manifest-status gate.
    cfg_b4 = EXPANSION_LOADER.BATCHES['b4']
    b4_entries, b4_report = EXPANSION_LOADER.load_expansion_entries(
        workorders=cfg_b4['workorders'], reviews=cfg_b4['reviews'],
        audit_path=cfg_b4['audit_path'], batch='b4',
        existing_ids=[e['id'] for e in entries] + [e['id'] for e in expansion_entries] +
                     [e['id'] for e in b3_entries])
    if b4_report['failures']:
        raise SystemExit('QQ expansion b4 manifest failed re-verification: %s'
                         % b4_report['failures'][:5])

    entries = entries + expansion_entries + b3_entries + b4_entries
    payload = {
        'schema_version': SCHEMA_VERSION,
        'name': '神祇读神奇 机制讲堂 甄选高质量规则',
        'status': 'draft_curated',
        'release_note': '本地甄选草稿层；不是官方发布，也不宣称绝对无错。'
                        '是否对外发布由项目负责人决定，本文件不构成发布许可判断。'
                        '条目来源为录播官方 AI 字幕、缺官方字幕分P的云端 ASR 重转写与 QQ 群聊；'
                        '各条实际来源见 source_layer 与 citations[].transcript_file，'
                        '引用前须核该条证据落在哪一层。未混入本次甄选之外的检索层。',
        'entry_count': len(entries),
        'entry_count_before_semantic_review': entries_before,
        'semantic_review_note': (
            'entries 已应用语义内审：claim 不是可独立用于检索的明确机制的条目已剔除，'
            '逐条判定与被剔原因见 kb_trial/curation/semantic_review.json（含被剔条目）。'
            '语义内审是 claim 层的单代理判定，不等于证据核听；两者分列于 '
            'semantic_review 与 review.status。'),
        'semantic_review_counts': sem_payload['counts'] if sem_payload else None,
        'removed_by_semantic_review': {
            'count': len(dropped),
            'by_info_value': dict(Counter(d['info_value'] for d in dropped).most_common()),
        },
        'qq_expansion_manifest': {
            'source': 'kb_trial/curation/qq_expansion/approved_manifest.json',
            'manifest_status': expansion_report['manifest_status'],
            'appended': expansion_report['loaded'],
            'entry_ids': expansion_report['entry_ids'],
            'note': '阶段二 80 窗试批的增量条目：来源为 QQ 群聊片段，只追加不改写既有条目。'
                    'manifest 未经批准时 appended=0，正式文件保持原有条数。'
                    '逐条裁定见 curation/qq_expansion/audit_decisions.json。',
            'skipped_reason': expansion_report['skipped_reason'],
        },
        'review_status_legend': {
            'user_verified': '用户明确认可("优秀")的整卡继承到其未被改写的明确规则句；见 reason',
            'agent_verified': '代理逐条读取原始引文/邻窗/QQ span 后确认该规则句有源可依',
            'auto_screened': '通过了语义内审与确定性闸门，但该条的引文未被逐条核听；不等于已证实',
            'coverage': '证据审核（review.status）只覆盖部分条目；未注明 agent_verified 的条目未经逐条证据核听。',
        },
        'field_legend': {
            'claim': '规则句正文',
            'claim_derivation': 'QQ 轨条目专有：本条 claim 由 `curation/qq_claim_overlay.json` '
                                '依据窗口 span 重写（原值为上游窗口标题）。from/to 与理由见该记录；'
                                'VOD 轨条目不设该字段。',
            'subject': '主语（"未标注"表示来源未点名具体对象，不是我们没提取）',
            'condition': '触发条件（"未标注"表示来源未给条件）',
            'scope': 'universal=可复用通则；instance/example=单次实例或例题；"未标注"表示来源未界定',
            'citations': '引文；含字幕/ASR 文件与秒，或 QQ 群聊已脱敏片段',
            'source_layer': '来源层；官方AI字幕 / 云端ASR重转写(无官方字幕分P) / QQ群聊。'
                            '云端ASR重转写的权威性低于官方字幕轨，引用前见 CURATED_OVERVIEW.md §4',
            'review.status': '证据审核状态；见 review_status_legend',
            'semantic_review': '语义内审：verdict(keep/drop) / support(引文是否支持) / '
                               'info_value(是否可复用机制) / reason / reviewer_type=agent。'
                               '该字段只判定 claim 语义，不冒充证据审核。',
        },
        'entries': entries,
    }
    # The b3 summary block is written only once the batch has actually been appended, so an
    # unapproved (inert) manifest leaves the shipped file byte-identical instead of adding a
    # metadata key that describes a merge which did not happen.
    if b3_report['loaded']:
        payload['qq_expansion_manifest_b3'] = {
            'source': 'kb_trial/curation/qq_expansion/%s' % cfg_b3['manifest_label'],
            'manifest_status': b3_report['manifest_status'],
            'appended': b3_report['loaded'],
            'entry_ids': b3_report['entry_ids'],
            'note': '阶段三 b3 批（260 窗）的增量条目：来源为 QQ 群聊片段，只追加不改写既有条目。'
                    'manifest 未经批准时 appended=0，正式文件保持原有条数。'
                    '逐条裁定见 curation/qq_expansion/audit_decisions_b3.json。',
            'skipped_reason': b3_report['skipped_reason'],
        }
    # Same rule for b4: the summary block appears only once the batch is actually appended.
    if b4_report['loaded']:
        payload['qq_expansion_manifest_b4'] = {
            'source': 'kb_trial/curation/qq_expansion/%s' % cfg_b4['manifest_label'],
            'manifest_status': b4_report['manifest_status'],
            'appended': b4_report['loaded'],
            'entry_ids': b4_report['entry_ids'],
            'note': '阶段四 b4 批（441 窗）的增量条目：来源为 QQ 群聊片段，只追加不改写既有条目。'
                    'manifest 未经批准时 appended=0，正式文件保持原有条数。'
                    '逐条裁定见 curation/qq_expansion/audit_decisions_b4.json，'
                    '父对 28 条存疑的裁决见该文件与 manifest 的 parent_ruling。',
            'skipped_reason': b4_report['skipped_reason'],
        }
    CURATED.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + '\n',
                       encoding='utf-8')
    stats = {
        'entries': len(entries),
        'entries_before_dedupe': entries_before,
        'entries_before_semantic_review': payload['entry_count_before_semantic_review'],
        'removed_by_semantic_review': payload['removed_by_semantic_review'],
        'by_review_status': dict(Counter(e['review']['status'] for e in entries)),
        'by_source_layer': dict(Counter(e['source_layer'] for e in entries)),
        'by_category': dict(Counter(e['category'] for e in entries).most_common()),
        'by_scope': dict(Counter(str(e['scope']) for e in entries).most_common()),
        'source_docs': len({e['origin']['trial_doc_id'] for e in entries}),
        'by_track': dict(Counter(e['track'] for e in entries).most_common()),
        'qq_entries': sum(1 for e in entries
                          if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])),
        'qq_expansion_appended': expansion_report['loaded'],
        'output_sha256': sha256(CURATED),
    }
    (OUT / 'curated_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')

    # Evidence-review stage runs as part of the build chain so the shipped file keeps its
    # `evidence_review` blocks and derived-text repairs; validate() rebuilds via this script
    # and would otherwise revert them.
    if not os.environ.get('KB_CURATION_SKIP_EVIDENCE'):
        for script in ('kb_curation_evidence_apply.py', 'kb_curation_quote_times.py'):
            rc = subprocess.run([sys.executable, script], cwd=ROOT,
                                stdout=subprocess.DEVNULL).returncode
            if rc != 0:
                raise SystemExit('%s failed with code %d' % (script, rc))
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
