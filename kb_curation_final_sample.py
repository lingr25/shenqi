# -*- coding: utf-8 -*-
"""Draw the pre-delivery random resample from the shipped curation.

Writes kb_trial/curation/final_sample.json: a fixed-seed random draw from
kb_trial/curated_high_quality.json, each entry carrying its readable claim plus the
quotes its citations actually resolve to (transcript file + seconds, or the QQ window
spans). The point is to let a human check two separate things on real content rather
than on aggregate pass counts:

  * is the claim independently reusable as a mechanism statement?
  * does the attached quote support it?

The draw is seeded and the source hash is recorded, so the sample can be reproduced
and pinned to an exact build.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'

SEED = 20260920
SAMPLE_SIZE = 12
CURATED = TRIAL / 'curated_high_quality.json'
STATS = OUT / 'curated_stats.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def source_quotes(entry):
    out = []
    for c in entry.get('citations') or []:
        out.append(dict(
            citation_id=c.get('id'), status=c.get('status'),
            transcript_file=c.get('transcript_file'),
            window_id=c.get('window_id'),
            quotes=[dict(text=q.get('text'), t_start=q.get('t_start'), t_end=q.get('t_end'))
                    for q in (c.get('quotes') or [])],
        ))
    return out


def build(seed, size):
    curated = load(CURATED)
    entries = {e['id']: e for e in curated['entries']}
    rng = random.Random(seed)
    picked = sorted(rng.sample(sorted(entries), min(size, len(entries))))

    samples = []
    for eid in picked:
        e = entries[eid]
        samples.append(dict(
            entry_id=eid, claim=e['claim'],
            subject=e['subject'], condition=e['condition'], scope=e['scope'],
            category=e['category'], source_layer=e['source_layer'],
            review_status=e['review']['status'], review_reason=e['review']['reason'],
            semantic_review=e.get('semantic_review'),
            source_quotes=source_quotes(e),
        ))

    payload = dict(
        schema_version=1,
        seed=seed,
        sample_size=len(samples),
        drawn_from='kb_trial/curated_high_quality.json',
        drawn_from_entry_count=curated['entry_count'],
        drawn_from_sha256=load(STATS)['output_sha256'],
        note=('交付前随机复检样本。每条给出可读 claim 与实际引文（文件+秒 或 QQ 窗口片段），'
              '供人工核对「claim 是否是可独立用于 RAG 的机制」与「引文是否支持该 claim」两件事。'
              '这是抽样复检，不构成对全量的逐条担保。'),
        samples=samples,
    )
    (OUT / 'final_sample.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print('final_sample entries', len(samples), 'seed', seed,
          'from', payload['drawn_from_entry_count'],
          'sha256', payload['drawn_from_sha256'])
    for s in samples:
        print(' -', s['entry_id'], '|', s['claim'][:70])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--size', type=int, default=SAMPLE_SIZE)
    args = parser.parse_args()
    return build(args.seed, args.size)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
