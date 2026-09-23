# -*- coding: utf-8 -*-
"""Build the per-entry evidence-review worklist for the whole shipped set.

Emits kb_trial/curation/evidence_review_worklist.jsonl: one line per shipped entry,
carrying the claim, its field values, and -- for every citation -- the FULL source text
that the citation resolves to, plus the surrounding transcript window so a reviewer can
judge object / condition / causality / numbers against what was actually said.

This script makes no acceptance decision. It only assembles what must be read.
Reuses kb_curation_evidence.Evidence so each transcript file is read once and cached,
which is what makes a 600+ entry read-through practical.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kb_curation_evidence import Evidence  # noqa: E402

TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'
CURATED = TRIAL / 'curated_high_quality.json'
VERDICTS = OUT / 'evidence_verdicts.jsonl'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]


def citation_material(ev, c):
    """Everything the source says for one citation: resolved quotes + a wide window."""
    out = {'citation_id': c.get('id'), 'status': c.get('status'),
           'transcript_file': c.get('transcript_file'), 'window_id': c.get('window_id'),
           'chapter': c.get('chapter'), 'quotes': []}
    for q in (c.get('quotes') or []):
        out['quotes'].append({'text': q.get('text'), 't_start': q.get('t_start'),
                              't_end': q.get('t_end')})
    cid = c.get('id') or ''
    f = c.get('transcript_file')
    if cid.startswith('ctx=sub:'):
        parts = cid.split(':')
        sec = None
        if len(parts) >= 4:
            try:
                sec = int(parts[3])
            except ValueError:
                sec = None
        elif len(parts) == 3:
            try:
                sec = int(parts[2])
            except ValueError:
                sec = None
        if sec is not None and f:
            stem = Path(f).stem
            w = ev.window(stem, sec, before=3, after=3)
            out['window_file'] = w.get('file')
            out['window'] = [l.strip() for l in w.get('lines') or []]
        else:
            out['window_file'] = None
            out['window'] = []
    elif cid.startswith('inline:'):
        # inline:<file>@<second>
        m = re.search(r'@(\d+)\s*$', cid)
        sec = int(m.group(1)) if m else None
        if f and sec is not None:
            stem = Path(f).stem
            w = ev.window(stem, sec, before=3, after=3)
            out['window_file'] = w.get('file')
            out['window'] = [l.strip() for l in w.get('lines') or []]
        else:
            out['window_file'] = None
            out['window'] = []
    else:
        row = ev.lookup(cid, before=3, after=3)
        if row.get('found'):
            out['resolved'] = {'quotes': row.get('quotes'), 'source': row.get('source')}
            w = row.get('window') or {}
            out['window_file'] = w.get('file')
            out['window'] = [l.strip() for l in w.get('lines') or []]
        else:
            out['resolved'] = None
    return out


def build(limit=None, only_unruled=True, out_path=None):
    """Assemble the worklist for entries this stage has not yet ruled on.

    The selector is deliberately NOT review.status. The QQ track reaches the shipped set
    as agent_verified (it cleared the eligibility gate in kb_curation_decide.py), so a
    worklist keyed on auto_screened silently omitted all 11 QQ entries -- they never got a
    verdict here, and the apply stage fell through to an 'inherited' block that claimed a
    review which had never happened. Scope is therefore "no verdict in VERDICTS yet".
    """
    ev = Evidence()
    cur = load(CURATED)
    entries = cur['entries']
    if only_unruled:
        have_verdict = {r['entry_id'] for r in load_jsonl(VERDICTS)} if VERDICTS.exists() else set()
        entries = [e for e in entries if e['id'] not in have_verdict]
    if limit:
        entries = entries[:limit]

    path = Path(out_path) if out_path else OUT / 'evidence_review_worklist.jsonl'
    with path.open('w', encoding='utf-8') as fh:
        for e in entries:
            rec = {
                'entry_id': e['id'],
                'claim': e['claim'],
                'subject': e['subject'], 'condition': e['condition'], 'scope': e['scope'],
                'category': e['category'], 'track': e['track'],
                'source_layer': e['source_layer'], 'recorded_ym': e.get('recorded_ym'),
                'review_status': e['review']['status'],
                'origin': e.get('origin'),
                'citations': [citation_material(ev, c) for c in e['citations']],
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print('worklist entries:', len(entries), '->', path)
    print('transcript files cached:', len(ev.transcripts))
    return len(entries)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--limit', type=int)
    p.add_argument('--all', action='store_true',
                   help='include entries that already have a verdict (full re-list)')
    p.add_argument('--out')
    a = p.parse_args()
    return build(a.limit, not a.all, a.out)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
