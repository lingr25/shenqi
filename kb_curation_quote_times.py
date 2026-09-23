# -*- coding: utf-8 -*-
"""Calibrate citation quote times against the actual transcript lines.

The upstream `t_start` is a WINDOW start (the review packet's context window), so the
quote text often begins 5-35 seconds after it. That is not wrong, but shipping only the
window start makes the quote look mis-timed.

This script, for every citation quote that can be located verbatim in its transcript:

  * keeps the upstream value under `t_start` / `t_start_upstream` (nothing is lost), and
  * adds the ACTUAL line time as `t_start_line` / `t_line_label`.

Quotes that cannot be located verbatim are left untouched and counted.

Idempotent: re-running does not change the output.
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'


def load_timed(path):
    timed = []
    for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
        m = re.match(r'\[(\d+:\d+(?::\d+)?)\]\s*(.*)', line)
        if m:
            t = 0
            for n in m.group(1).split(':'):
                t = t * 60 + int(n)
            timed.append((t, m.group(2), m.group(1)))
    return timed


def main():
    cur = json.loads(CURATED.read_text(encoding='utf-8'))
    cache = {}
    stats = Counter()
    for e in cur['entries']:
        for c in e.get('citations', []):
            f = c.get('transcript_file')
            if not f or not (ROOT / f).exists():
                continue
            if f not in cache:
                cache[f] = load_timed(f)
            timed = cache[f]
            for q in c.get('quotes', []):
                body = (q.get('text') or '').strip()
                if not body:
                    continue
                ts = q.get('t_start')
                # window-labelled quotes already carry their own [MM:SS]
                if body.startswith('['):
                    m = re.match(r'\[(\d+:\d+(?::\d+)?)\]', body)
                    if m:
                        lab = m.group(1)
                        t = 0
                        for n in lab.split(':'):
                            t = t * 60 + int(n)
                        body2 = body[len(m.group(0)):].strip()
                        hit = [y for y in timed if body2 and body2[:20] in y[1]]
                        if hit:
                            q['t_line_label'] = hit[0][2]
                            q['t_start_line'] = hit[0][0]
                            stats['window_located'] += 1
                        else:
                            q['t_line_label'] = lab
                            q['t_start_line'] = t
                            stats['window_selflabelled'] += 1
                    continue
                hit = [y for y in timed if body in y[1]]
                if not hit:
                    stats['unlocated'] += 1
                    continue
                line_t, _, line_lab = hit[0]
                q['t_start_upstream'] = ts
                q['t_start_line'] = line_t
                q['t_line_label'] = line_lab
                if ts is not None and line_t != ts:
                    stats['recalibrated'] += 1
                else:
                    stats['already_exact'] += 1
    CURATED.write_text(json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=False) + '\n',
                       encoding='utf-8')
    print(json.dumps(dict(stats), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
