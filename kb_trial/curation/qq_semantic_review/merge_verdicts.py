# -*- coding: utf-8 -*-
"""Merge and validate qq semantic-review verdicts from all batch outputs.

Run from repo root after every out_NN.jsonl is in place:
    python kb_trial/curation/qq_semantic_review/merge_verdicts.py

Checks: every batch covered, every input id answered exactly once, schema sane.
Writes qq_semantic_verdicts.jsonl (consolidated) and prints the stats you need
before deciding what to feed back into the curation pipeline.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALID_VERDICTS = {'keep', 'demote', 'reject'}
VALID_INFO = {'mechanism', 'question', 'trivia'}


def main():
    batches = sorted(HERE.glob('batch_*.jsonl'))
    outs = {p.stem.replace('out_', ''): p for p in (HERE / 'out').glob('out_*.jsonl')}
    errors, verdicts = [], {}
    for bp in batches:
        nn = bp.stem.replace('batch_', '')
        inputs = [json.loads(l) for l in bp.read_text(encoding='utf-8').splitlines() if l.strip()]
        if nn not in outs:
            errors.append(f'batch {nn}: no out file')
            continue
        seen = set()
        for ln, line in enumerate(outs[nn].read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                v = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f'batch {nn} line {ln}: bad json {e}')
                continue
            vid = v.get('id')
            if v.get('verdict') not in VALID_VERDICTS:
                errors.append(f'batch {nn} line {ln} ({vid}): bad verdict {v.get("verdict")}')
            if v.get('info_value') not in VALID_INFO:
                errors.append(f'batch {nn} line {ln} ({vid}): bad info_value {v.get("info_value")}')
            if v.get('verdict') in ('demote', 'reject') and not v.get('reason'):
                errors.append(f'batch {nn} line {ln} ({vid}): {v.get("verdict")} without reason')
            if vid in verdicts:
                errors.append(f'batch {nn} line {ln}: duplicate id {vid}')
            verdicts[vid] = v
            seen.add(vid)
        missing = {r['id'] for r in inputs} - seen
        if missing:
            errors.append(f'batch {nn}: {len(missing)} unanswered, e.g. {sorted(missing)[:3]}')
    if errors:
        print('MERGE FAILED:')
        for e in errors[:40]:
            print(' ', e)
        return 1
    out = HERE / 'qq_semantic_verdicts.jsonl'
    with open(out, 'w', encoding='utf-8') as f:
        for vid in sorted(verdicts):
            f.write(json.dumps(verdicts[vid], ensure_ascii=False) + '\n')
    vc = Counter(v['verdict'] for v in verdicts.values())
    ic = Counter(v['info_value'] for v in verdicts.values())
    print(f'merged {len(verdicts)} verdicts -> {out}')
    print('verdicts:', dict(vc))
    print('info_value:', dict(ic))
    print('\ndemote/reject (人审候选):')
    for vid, v in verdicts.items():
        if v['verdict'] != 'keep':
            print(f"  [{v['verdict']}] {vid}: {v.get('reason','')}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
