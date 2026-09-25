# -*- coding: utf-8 -*-
"""Export qq_expansion entries from the curated KB into review batches.

Deterministic, no network. Run from repo root:
    python kb_trial/curation/qq_semantic_review/export_batches.py

Writes batch_01.jsonl ... batch_NN.jsonl (30 entries each) next to this file.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BATCH_SIZE = 30


def main():
    d = json.loads((ROOT / 'curated_high_quality.json').read_text(encoding='utf-8'))
    rows = []
    for e in d['entries']:
        if not e['id'].startswith('qq_expansion:'):
            continue
        quotes = []
        for c in (e.get('citations') or []):
            for q in (c.get('quotes') or []):
                quotes.append(q.get('text', ''))
        rows.append({
            'id': e['id'],
            'category': e.get('category'),
            'claim': e.get('claim'),
            'subject': e.get('subject'),
            'condition': e.get('condition'),
            'review_status': (e.get('review') or {}).get('status'),
            'quotes': quotes[:4],
        })
    for old in HERE.glob('batch_*.jsonl'):
        old.unlink()
    n_batches = 0
    for i in range(0, len(rows), BATCH_SIZE):
        n_batches += 1
        with open(HERE / f'batch_{n_batches:02d}.jsonl', 'w', encoding='utf-8') as f:
            for r in rows[i:i + BATCH_SIZE]:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'exported {len(rows)} entries into {n_batches} batches in {HERE}')


if __name__ == '__main__':
    main()
