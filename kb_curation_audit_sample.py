"""Fixed-seed audit sample: 30 accepts and 30 rejects with their own evidence attached.

This exists so the shipped set can be spot-checked without trusting the gate code. The
sample is drawn with a pinned seed, so the same 60 rules come out on every machine, and
every row carries the evidence needed to judge it by hand: the claim, the citation(s) with
file and second, the review status, and the rejection reason for the rejects.

Read-only over the curation outputs. No API.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial/curation'
CURATED = ROOT / 'kb_trial/curated_high_quality.json'
SEED = 20260920
N = 30


def load_evidence_index():
    path = ROOT / 'kb_trial/evidence.jsonl'
    idx = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            e = json.loads(line)
            idx[e['id']] = e
    return idx


def atom_quote(evidence, ref):
    """Locate the raw quote text for a VOD atom ref, for hand-checking."""
    item = evidence.get(ref)
    if not item:
        return None
    if item['status'] == 'resolved_atom':
        clips = (item.get('evidence') or {}).get('clips') or []
        return {'file': item.get('transcript_file'),
                'quotes': [{'text': c.get('quote'), 't_start': c.get('t_start')} for c in clips]}
    return {'file': item.get('file'), 'second': item.get('requested_second'),
            'quotes': [{'text': item.get('quote_line'), 't_start': item.get('requested_second')}]}


def accept_rows(curated, evidence):
    rows = []
    for e in curated['entries']:
        cits = []
        for c in e['citations']:
            ref = c.get('id') or ''
            raw = atom_quote(evidence, ref) if ref.startswith('BV') else None
            cits.append({
                'id': ref, 'status': c.get('status'),
                'transcript_file': c.get('transcript_file'),
                'window_id': c.get('window_id'),
                'quotes': [{'text': q.get('text'), 't_start': q.get('t_start')}
                           for q in (c.get('quotes') or [])],
                'raw_source': raw,
            })
        rows.append({
            'entry_id': e['id'],
            'claim': e['claim'],
            'subject': e.get('subject'),
            'condition': e.get('condition'),
            'category': e.get('category'),
            'source_layer': e.get('source_layer'),
            'track': e.get('track'),
            'review_status': e['review']['status'],
            'review_reason': e['review']['reason'],
            'citations': cits,
        })
    return rows


def reject_rows():
    rows = []
    for line in (OUT / 'decisions.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r['decision'] != 'reject':
            continue
        rows.append({
            'doc_id': r['doc_id'],
            'rule_idx': r['rule_idx'],
            'claim': r['claim'],
            'category': r.get('category'),
            'track': r.get('track'),
            'doc_type': r['doc_type'],
            'source_layers': r.get('source_layers'),
            'render_mode': r.get('render_mode'),
            'reject_reason': r.get('reject_reason'),
            'citation_refs': r.get('citation_refs'),
            'inline_evidence': r.get('inline_evidence'),
            'qq_evidence': r.get('qq_evidence'),
            'flags': r.get('flags'),
        })
    return rows


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    evidence = load_evidence_index()
    curated = json.loads(CURATED.read_text(encoding='utf-8'))
    acc, rej = accept_rows(curated, evidence), reject_rows()
    rng = random.Random(SEED)
    acc_s = rng.sample(sorted(acc, key=lambda r: r['entry_id']), min(N, len(acc)))
    rej_s = rng.sample(sorted(rej, key=lambda r: (r['doc_id'], r['rule_idx'])), min(N, len(rej)))
    payload = {
        'seed': SEED, 'sample_size': N,
        'population': {'accepts': len(acc), 'rejects': len(rej)},
        'note': '固定 seed 抽样，供父代理逐条核对；accept 行含引文与原始来源，reject 行含拒收原因。',
        'accept_sample': acc_s,
        'reject_sample': rej_s,
    }
    (OUT / 'audit_sample.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'seed': SEED, 'accepts_in_sample': len(acc_s), 'rejects_in_sample': len(rej_s),
                      'population': payload['population'],
                      'path': str((OUT / 'audit_sample.json').relative_to(ROOT))},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
