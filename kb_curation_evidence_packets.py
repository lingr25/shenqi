# -*- coding: utf-8 -*-
"""Emit readable evidence-review packets, ~40 entries per batch.

Turns evidence_review_worklist.jsonl into plain-text packets a reviewer can read start
to finish. One packet per batch; each entry shows the claim, its field values, and for
every citation the full source window with the exact source file and line time, so the
reviewer can rule on whether the source supports the OBJECT, CONDITION, CAUSALITY and any
NUMBER in the claim -- not merely whether the topic matches.

Read-only. Writing verdicts is kb_curation_evidence_apply.py's job.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial' / 'curation'
WORKLIST = OUT / 'evidence_review_worklist.jsonl'
PACKETS = OUT / 'evidence_packets'

TS = re.compile(r'\[\d{1,2}:\d{2}(?::\d{2})?\]')


def hms(s):
    if s is None:
        return '?'
    s = int(s)
    return '%02d:%02d:%02d' % (s // 3600, s % 3600 // 60, s % 60)


def load_worklist():
    return [json.loads(l) for l in WORKLIST.read_text(encoding='utf-8').splitlines() if l.strip()]


def render(rec):
    out = []
    out.append('=' * 78)
    out.append('ENTRY %s' % rec['entry_id'])
    out.append('  claim    : %s' % rec['claim'])
    out.append('  subject  : %s' % rec['subject'])
    out.append('  condition: %s' % rec['condition'])
    out.append('  scope    : %s' % rec['scope'])
    out.append('  category : %s | track: %s | layer: %s | recorded: %s' % (
        rec['category'], rec['track'], rec['source_layer'], rec.get('recorded_ym')))
    for i, c in enumerate(rec['citations'], 1):
        out.append('  --- citation %d/%d: %s' % (i, len(rec['citations']), c['citation_id']))
        out.append('      status=%s file=%s' % (c['status'], c.get('transcript_file')))
        if c.get('chapter'):
            out.append('      chapter=%s' % c['chapter'])
        for q in c['quotes']:
            out.append('      quote  : %s   [%s-%s]' % (
                q.get('text'), hms(q.get('t_start')), hms(q.get('t_end'))))
        wf = c.get('window_file')
        if wf:
            out.append('      SOURCE WINDOW (%s):' % wf)
            for line in (c.get('window') or []):
                out.append('        %s' % line[:230])
        else:
            out.append('      SOURCE WINDOW: <none resolved>')
    out.append('')
    return '\n'.join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch-size', type=int, default=40)
    p.add_argument('--only', type=int, help='render just this batch number (1-based)')
    a = p.parse_args()

    recs = load_worklist()
    PACKETS.mkdir(parents=True, exist_ok=True)
    for f in PACKETS.glob('batch_*.txt'):
        f.unlink()

    batches = [recs[i:i + a.batch_size] for i in range(0, len(recs), a.batch_size)]
    index = []
    for n, batch in enumerate(batches, 1):
        if a.only and n != a.only:
            continue
        text = '\n'.join(render(r) for r in batch)
        path = PACKETS / ('batch_%02d.txt' % n)
        path.write_text(text, encoding='utf-8')
        index.append({'batch': n, 'file': str(path.relative_to(ROOT)),
                      'entry_ids': [r['entry_id'] for r in batch],
                      'chars': len(text)})
        print('batch %02d: %d entries, %d chars -> %s' % (n, len(batch), len(text), path.name))

    if not a.only:
        (OUT / 'evidence_packets_index.json').write_text(
            json.dumps({'batch_size': a.batch_size, 'total_entries': len(recs),
                        'batches': index}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('total entries:', len(recs), '| batches:', len(batches))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
