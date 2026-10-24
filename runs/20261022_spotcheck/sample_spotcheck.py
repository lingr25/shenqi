#!/usr/bin/env python3
"""Read-only spot-check sampler for vod_b1/vod_b2 review outputs. SEED=20261022."""
import json, glob, random, re, os
SEED = 20261022
ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
VE = os.path.join(ROOT, 'kb_trial/curation/vod_expansion')
QUOTA = {'vod_b2': (15, 10), 'vod_b1': (5, 5)}

def load_tx(src):
    lines = []
    for ln in open(os.path.join(ROOT, src), encoding='utf-8'):
        m = re.match(r'\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)', ln.strip())
        if m: lines.append(((int(m.group(1) or 0)*60+int(m.group(2)))*60+int(m.group(3)), m.group(4)))
        elif ln.strip(): lines.append((None, ln.strip()))
    return lines

def ctx(src, t0, t1, pad=15):
    try: L = load_tx(src)
    except Exception as e: return [f'(transcript unreadable: {e})']
    return [f'[{t}s] {x}' for t, x in L if t is not None and t0 - pad <= t <= t1 + pad]

out = {}
for b, (nk, nr) in QUOTA.items():
    keeps, rejs = [], []
    for f in sorted(glob.glob(f'{VE}/reviews_{b}/*.json')):
        r = json.load(open(f)); wo = json.load(open(f'{VE}/workorders_{b}/{r["workorder_id"]}.json'))
        cands = {c['local_id']: c for c in wo['candidates']}
        for c in r.get('claims', []):
            keeps.append(dict(kind='keep', wo=r['workorder_id'], stem=r['stem'], src=wo['source_file'], item=c, cand=cands.get(c['local_id'])))
        for c in r.get('excluded', []):
            if c.get('verdict') == 'reject':
                rejs.append(dict(kind='reject', wo=r['workorder_id'], stem=r['stem'], src=wo['source_file'], item=c, cand=cands.get(c['local_id'])))
    rng = random.Random(f'{SEED}-{b}')
    sel = rng.sample(keeps, nk) + rng.sample(rejs, nr)
    for s in sel:
        ev = s['item'].get('evidence') or [{'t_start': e['start'], 't_end': e['end'], 'text': e['quote']} for e in (s['cand'] or {}).get('evidence', [])]
        s['evidence'] = ev
        if ev: s['context'] = ctx(s['src'], min(e['t_start'] for e in ev), max(e['t_end'] for e in ev))
    out[b] = dict(n_keep=len(keeps), n_reject=len(rejs), sample=sel)
json.dump(out, open('/workspace/spotcheck_sample_raw.json', 'w'), ensure_ascii=False, indent=1)
for b, v in out.items(): print(b, v['n_keep'], v['n_reject'])

# --- render markdown (judgments in /tmp/j.json, written by hand after reading transcripts) ---
J = json.load(open('/tmp/j.json')) if os.path.exists('/tmp/j.json') else {}
md = [f'# VOD 审读抽查 2026-10-22\n\n随机种子：`random.Random(f"{SEED}-{{batch}}")`，SEED={SEED}。脚本：runs/20261022_spotcheck/sample_spotcheck.py（未跟踪）。\n',
      '注：仓库中只有 approved_manifest_vod_b1.json，**没有 vod_b2 的 manifest 文件**；vod_b2 直接从 reviews_vod_b2/*.json 抽样（keep 807 / reject 324，与总数一致）。\n']
n = 0
for b, v in out.items():
    md.append(f'\n## {b}（总体 keep {v["n_keep"]} / reject {v["n_reject"]}）\n')
    for s in v['sample']:
        n += 1; i = s['item']; j = J.get(str(n), ['?', ''])
        bv, p = s['stem'].split('_')[:2]
        md.append(f'### {n}. [{s["kind"]}] {s["wo"]}/{i["local_id"]} — {bv} {p}\n')
        md.append(f'- **Claim**：{i.get("claim") or i.get("topic")}')
        if s['cand']: md.append(f'- **原候选**：{s["cand"].get("proposition")}')
        for e in s['evidence']: md.append(f'- **引文** [{e["t_start"]}s]：「{e["text"]}」')
        md.append(f'- **审读理由**：{i.get("reason")}' + (f'（failed: {",".join(i["failed_gates"])}）' if i.get('failed_gates') else ''))
        md.append(f'- **抽查判断**：**{j[0]}** — {j[1]}')
        if s.get('context'): md.append('<details><summary>逐字稿上下文</summary>\n\n```\n' + '\n'.join(s['context']) + '\n```\n</details>')
        md.append('')
open('/workspace/spotcheck_vod_20261022.md', 'w').write('\n'.join(md))
