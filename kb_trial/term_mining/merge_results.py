# -*- coding: utf-8 -*-
"""Merge term-mining outputs into one ranked candidate list for human review.

Run from repo root:
    python kb_trial/term_mining/merge_results.py

Validates schema, dedupes (term, correction), sorts high->low confidence,
writes candidates.jsonl and prints stats. Every candidate still needs human
review before any corrector rule or glossary entry is written from it.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALID_KIND = {'asr_suspect', 'unknown_entity', 'slang'}
VALID_CONF = {'high', 'mid', 'low'}
RANK = {'high': 0, 'mid': 1, 'low': 2}


def main():
    tasks = sorted(HERE.glob('task_*.md'))
    outdir = HERE / 'out'
    errors, rows = [], []
    covered = set()
    for p in sorted(outdir.glob('out_*.jsonl')) if outdir.exists() else []:
        covered.add(p.stem.replace('out_', ''))
        for ln, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f'{p.name}:{ln} bad json {e}')
                continue
            for k in ('file', 'kind', 'term', 'ts', 'context', 'confidence'):
                if k not in r:
                    errors.append(f'{p.name}:{ln} missing {k}')
                    break
            else:
                if r['kind'] not in VALID_KIND or r['confidence'] not in VALID_CONF:
                    errors.append(f'{p.name}:{ln} bad kind/confidence')
                    continue
                rows.append(r)
    missing = [t.stem.replace('task_', '') for t in tasks if t.stem.replace('task_', '') not in covered]
    if missing:
        errors.append(f'{len(missing)} tasks without output: {missing[:5]}...')
    if errors:
        print('MERGE FAILED:')
        for e in errors[:30]:
            print(' ', e)
        return 1
    seen = {}
    for r in rows:
        key = (r['term'], r.get('correction'))
        if key not in seen or RANK[r['confidence']] < RANK[seen[key]['confidence']]:
            seen[key] = r
    dedup = sorted(seen.values(), key=lambda r: (RANK[r['confidence']], r['kind'], r['term']))
    out = HERE / 'candidates.jsonl'
    with open(out, 'w', encoding='utf-8') as f:
        for r in dedup:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'{len(rows)} raw -> {len(dedup)} deduped -> {out}')
    print('by kind:', dict(Counter(r['kind'] for r in dedup)))
    print('by confidence:', dict(Counter(r['confidence'] for r in dedup)))
    print('\nhigh-confidence candidates:')
    for r in dedup:
        if r['confidence'] == 'high':
            print(f"  [{r['kind']}] {r['term']} -> {r.get('correction')}  ({r['file']} {r['ts']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
