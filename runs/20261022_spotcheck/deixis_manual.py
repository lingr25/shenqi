#!/usr/bin/env python3
"""Manual deixis verdicts (LLM gateway returned HTTP 401 token_invalid at ~12:05 JST; judged by hand instead).
Items with prefilter score>=2 (n=208) were read and judged; score<=1 (single deictic word in quote only) default 'ok' (heuristic, not hand-read)."""
import json
items = json.load(open('/tmp/dx_items.json'))
DROP = {
 "vod_wo_vod_b1_016/c01": "“本例录播演示关卡”未命名，鱼/牌子靠“这里这个”指画面",
 "vod_wo_vod_b1_001/c01": "顶上/底下影子的0/2/3/4帧只能看画面对应",
 "vod_wo_vod_b1_019/c01": "“在这前面站”方向依赖画面",
 "vod_wo_vod_b1_032/c02": "“这俩/他俩”的242/245读数依赖画面",
 "vod_wo_vod_b1_018/c01": "“这个才是80/这俩”单例画面读数",
 "vod_wo_vod_b1_029/c02": "“从上到下321”对应位置依赖画面",
 "vod_wo_vod_b1_042/c01": "“演示中的这个两波次关卡”未命名",
 "vod_wo_vod_b1_011/c02": "“这个出生之后十帧”所指单位靠画面",
 "vod_wo_vod_b1_110/c01": "“红门右侧一列”未说明关卡，“这里左转”靠画面",
 "vod_wo_vod_b2_069/c02": "“该演示中”碰撞箱0.1/0.3边距由“从这里到这里”读出",
 "vod_wo_vod_b2_131/c01": "白板例题中2/3号敌人位置靠画面",
 "vod_wo_vod_b2_131/c02": "同上，4号受力方向靠画面",
 "vod_wo_vod_b2_108/c02": "“这边十这边一”白板方向靠画面",
 "vod_wo_vod_b2_204/c02": "1/2/3号仇恨档位位置靠画面",
 "vod_wo_vod_b2_462/c01": "某条2896伤害记录，所指测试靠画面",
 "vod_wo_vod_b2_463/c01": "某条2510伤害记录，同上",
 "vod_wo_vod_b2_489/c01": "“这俩位置不同/这个不在同一格”靠画面",
 "vod_wo_vod_b2_552/c02": "“该关卡流程中”未命名，治疗回血点靠画面",
 "vod_wo_vod_b2_419/c01": "“这里还有个路径点”位置靠画面",
 "vod_wo_vod_b2_611/c01": "“活动第四关右下角”未说明是哪个活动",
 "vod_wo_vod_b2_642/c02": "“该处40秒和50秒的波次”靠画面",
 "vod_wo_vod_b2_343/c02": "“该毒雾图”未命名",
 "vod_wo_vod_b2_681/c01": "13帧下16帧撤，所依托的实验画面未交代",
 "vod_wo_vod_b2_752/c02": "“当前讨论的关卡”未命名",
}
out = []
for i in items:
    v = 'drop' if i['id'] in DROP else 'ok'
    out.append(dict(batch=i['batch'], id=i['id'], stem=i['stem'], claim=i['claim'], quote=i['quote'], prefilter_score=i['score'],
                    judged='hand' if i['score'] >= 2 else 'heuristic_default', verdict=v,
                    reason=DROP.get(i['id'], '主体/条件已自包含，引文中的指示词为口头禅或可由上下文还原' if i['score'] >= 2 else '仅引文含单个指示词，未逐条人工复核，默认ok')))
json.dump(out, open('/workspace/deixis_keeps_20261022.json', 'w'), ensure_ascii=False, indent=1)
from collections import Counter
c = Counter((o['batch'], o['verdict']) for o in out); f = Counter(o['batch'] for o in out); h = Counter(o['batch'] for o in out if o['judged']=='hand')
md = ['# Deixis 扫描（全部 keep）2026-10-22\n', 'LLM 网关在运行中返回 HTTP 401 token_invalid，已改为人工判定：prefilter 分数≥2 的条目逐条人工审读；分数≤1（仅引文含单个指示词）默认 ok、未逐条复核。\n',
      '| 批次 | keep总数 | 预筛命中 | 人工判定 | drop |', '|---|---|---|---|---|']
tot = {'vod_b1': 181, 'vod_b2': 807}
for b in ('vod_b1', 'vod_b2'): md.append(f'| {b} | {tot[b]} | {f[b]} | {h[b]} | {c[(b,"drop")]} |')
md.append('\n## drop 列表\n')
for o in out:
    if o['verdict'] == 'drop': md.append(f'- **{o["id"]}** — {o["claim"]}\n  - 引文：「{o["quote"][:200]}」\n  - 理由：{o["reason"]}')
md.append('\n## 人工判 ok（节选前 30）\n')
for o in [o for o in out if o['verdict']=='ok' and o['judged']=='hand'][:30]:
    md.append(f'- {o["id"]} — {o["claim"][:80]}')
open('/workspace/deixis_keeps_20261022.md', 'w').write('\n'.join(md))
print(c, f, h)
