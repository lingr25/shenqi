#!/usr/bin/env python3
"""Merge LLM results for heuristic_default items + manual overrides of LLM 'drop' calls into deixis_keeps_20261022.json/.md."""
import json, collections
r = {json.loads(l)['id']: json.loads(l) for l in open('/workspace/deixis_llm_results.jsonl')}
OVR_OK = {"vod_wo_vod_b1_047/c01","vod_wo_vod_b1_058/c01","vod_wo_vod_b1_074/c01","vod_wo_vod_b1_124/c01","vod_wo_vod_b2_107/c01",
 "vod_wo_vod_b2_138/c02","vod_wo_vod_b2_165/c02","vod_wo_vod_b2_227/c01","vod_wo_vod_b2_350/c01","vod_wo_vod_b2_545/c01",
 "vod_wo_vod_b2_666/c01","vod_wo_vod_b2_672/c01","vod_wo_vod_b2_675/c02","vod_wo_vod_b2_689/c01","vod_wo_vod_b2_690/c01"}
d = json.load(open('/workspace/deixis_keeps_20261022.json'))
for x in d:
    if x['id'] in r:
        L = r[x['id']]; x['judged'] = 'llm(lingr-speed)'; x['llm_verdict'] = L['verdict']; x['llm_reason'] = L['reason']
        if L['verdict'] == 'drop' and x['id'] in OVR_OK:
            x['verdict'] = 'ok'; x['judged'] = 'llm+manual_override'
            x['reason'] = '人工复核：主体已命名或为通用机制术语，LLM 将“主体略泛”误当画面指涉'
        else:
            x['verdict'] = L['verdict']; x['reason'] = L['reason']
            if L['verdict'] == 'drop': x['judged'] = 'llm+manual_confirmed'
json.dump(d, open('/workspace/deixis_keeps_20261022.json', 'w'), ensure_ascii=False, indent=1)
c = collections.Counter((x['batch'], x['verdict']) for x in d); f = collections.Counter(x['batch'] for x in d)
tot = {'vod_b1': 181, 'vod_b2': 807}
md = ['# Deixis 扫描（全部 keep）2026-10-22 — final\n',
      '判定方式：预筛分数≥2 的 207 条人工逐条审读；其余 234 条用 lingr-speed 判定（结果在 /workspace/deixis_llm_results.jsonl），LLM 判 drop 的 36 条全部人工复核，其中 15 条改回 ok（主体已命名/通用术语）。\n',
      '| 批次 | keep总数 | 预筛命中 | drop | ok |', '|---|---|---|---|---|']
for b in ('vod_b1', 'vod_b2'): md.append(f'| {b} | {tot[b]} | {f[b]} | {c[(b,"drop")]} | {c[(b,"ok")]} |')
md.append('\n## drop 列表\n')
for x in d:
    if x['verdict'] == 'drop': md.append(f'- **{x["id"]}** [{x["judged"]}] — {x["claim"]}\n  - 引文：「{x["quote"][:200]}」\n  - 理由：{x["reason"]}')
md.append('\n## LLM 判 drop 但人工改回 ok\n')
for x in d:
    if x['judged'] == 'llm+manual_override': md.append(f'- {x["id"]} — {x["claim"][:90]}（LLM：{x["llm_reason"][:60]}）')
open('/workspace/deixis_keeps_20261022.md', 'w').write('\n'.join(md))
print(c)
