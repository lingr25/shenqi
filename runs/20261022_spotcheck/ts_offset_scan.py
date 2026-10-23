#!/usr/bin/env python3
"""Check candidate evidence timestamps vs transcript_window lines; and whether review evidence uses corrected times."""
import json, glob, re, os, collections
VE = os.path.join(os.path.dirname(__file__), '../../kb_trial/curation/vod_expansion')
norm = lambda s: re.sub(r'\s+', '', s)
res = collections.Counter(); aff = []
for b in ('vod_b1', 'vod_b2'):
    for f in sorted(glob.glob(f'{VE}/workorders_{b}/vod_wo_*.json')):
        w = json.load(open(f)); tw = w['transcript_window']
        rv = f'{VE}/reviews_{b}/{w["workorder_id"]}.json'; r = json.load(open(rv)) if os.path.exists(rv) else {}
        rev_t = {norm(e['text'])[:12]: e['t_start'] for c in r.get('claims', []) for e in c.get('evidence', [])}
        offs = []
        for c in w['candidates']:
            for e in c['evidence']:
                q = norm(e['quote'])[:12]
                hit = [x['t'] for x in tw if q and q in norm(x['text'])]
                if not hit: res[(b, 'quote_not_in_window')] += 1; continue
                d = min(hit, key=lambda t: abs(t - e['start'])) - e['start']
                offs.append(d)
                if abs(d) > 5:
                    rt = rev_t.get(q); res[(b, 'offset_quote')] += 1
                    res[(b, 'review_kept' if rt is not None else 'no_review_evidence')] += 1
                    if rt is not None: res[(b, 'review_corrected' if abs(rt - (e['start'] + d)) <= 5 else 'review_still_wrong')] += 1
                else: res[(b, 'ok_quote')] += 1
        if any(abs(d) > 5 for d in offs):
            aff.append((b, w['workorder_id'], w['stem'], sorted(set(offs))[:3]))
print(res)
c = collections.Counter(a[0] for a in aff); print('affected workorders', c)
print(collections.Counter((a[0], a[2]) for a in aff).most_common(15))
json.dump(aff, open('/tmp/ts_aff.json', 'w'))
