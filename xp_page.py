# -*- coding: utf-8 -*-
"""把 xp_data.json 渲染成自包含 HTML 看板（无外部依赖，双击即开）。

输入:  qq_info/xp_data.json（由 xp_rank.py 生成）
输出:  qq_info/xp_report.html（仅含昵称，不含 QQ 号；qq_info/ 已被 gitignore 保护）
"""
import html
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("qq_info/xp_data.json", encoding="utf-8"))
E = html.escape

mentions = d["op_mention"]
affection = dict(d["op_affection"])
fans = d["op_fans"]
rate = dict(d["love_rate"])
risky = set(d["risky"])
per_speaker = d["per_speaker"]

def bar(val, vmax, color="var(--accent)"):
    pct = 100 * val / vmax if vmax else 0
    return f'<div class="bar"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div>'

def medal(i):
    return ["🥇", "🥈", "🥉"][i] if i < 3 else f'<span class="rk">{i + 1}</span>'

# ---------- 各区块 ----------
sec = []

# 0. 官宣单推墙
ops_decl = [x for x in d["declared"] if x["canon"]]
ppl_decl = [x for x in d["declared"] if not x["canon"]]
rows = "".join(
    f'<div class="chip op"><b>{E(x["nick"])}</b><span class="arr">单推</span>'
    f'<b class="tgt">{E(x["canon"])}</b><i>{x["count"]}条</i></div>'
    for x in sorted(ops_decl, key=lambda x: -x["count"]))
rows2 = "".join(
    f'<div class="chip ppl"><b>{E(x["nick"])}</b><span class="arr">单推</span>'
    f'<b class="tgt">{E(x["target"])}</b><i>{x["count"]}条</i></div>'
    for x in sorted(ppl_decl, key=lambda x: -x["count"]))
sec.append(f"""
<h2>🏛️ 官宣单推墙 <small>把本命写进群名片的勇士们</small></h2>
<h3>推干员的</h3><div class="chips">{rows}</div>
<h3>推……群友的？<small>这个群不对劲</small></h3><div class="chips">{rows2}</div>""")

# 1. 热度榜 TOP30
top = mentions[:30]
vmax = top[0][1]
lis = "".join(
    f'<div class="row"><span class="medal">{medal(i)}</span><span class="name">{E(op)}</span>'
    f'{bar(c, vmax)}<span class="val">{c}<i>{fans.get(op, 0)}人聊过</i></span></div>'
    for i, (op, c) in enumerate(top))
sec.append(f'<h2>🔥 全群干员热度榜 TOP30</h2><div class="chart">{lis}</div>')

# 2. 真爱榜 TOP20
love = [(op, c) for op, c in d["op_affection"][:20]]
vmax = love[0][1] if love else 1
lis = "".join(
    f'<div class="row"><span class="medal">{medal(i)}</span>'
    f'<span class="name">{E(op)}{" <sup title=语境受限词,口径偏高>*</sup>" if op in risky else ""}</span>'
    f'{bar(c, vmax, "var(--pink)")}'
    f'<span class="val">{c}<i>真爱率 {rate.get(op, 0):.0%}</i></span></div>'
    for i, (op, c) in enumerate(love))
sec.append(f"""<h2>💘 真爱榜 TOP20 <small>老婆/喜欢/满潜/我推 等明示爱语境</small></h2>
<div class="chart">{lis}</div>""")

# 3. 单推浓度榜
lis = "".join(
    f'<div class="row"><span class="medal">{medal(i)}</span><span class="name nick">{E(s["nick"])}</span>'
    f'<span class="tgt">{E(s["op"])}</span>'
    f'{bar(s["rate"], 1, "var(--green)")}'
    f'<span class="val">{s["rate"]:.0%}<i>{s["cnt"]}/{s["total"]}次示爱</i></span></div>'
    for i, s in enumerate(d["stan"][:15]))
sec.append(f'<h2>🎯 单推浓度榜 <small>个人示爱最集中的干员（示爱总数≥5）</small></h2><div class="chart">{lis}</div>')

# 4. 花心榜 + 话痨榜 两栏
pb = "".join(
    f'<div class="row"><span class="medal">{medal(i)}</span><span class="name nick">{E(p["nick"])}</span>'
    f'{bar(p["n"], d["playboy"][0]["n"], "var(--purple)")}'
    f'<span class="val">{p["n"]}位<i>最爱：{E("、".join(t for t, _ in p["tops"][:3]))}</i></span></div>'
    for i, p in enumerate(d["playboy"][:10]))
ct = "".join(
    f'<div class="row"><span class="medal">{medal(i)}</span><span class="name nick">{E(c["nick"])}</span>'
    f'{bar(c["msgs"], d["chatty"][0]["msgs"], "var(--blue)")}'
    f'<span class="val">{c["msgs"]}<i>{c["ops"]}个干员</i></span></div>'
    for i, c in enumerate(d["chatty"][:10]))
sec.append(f"""<div class="cols">
<div><h2>🃏 花心榜 <small>示爱过的不同干员最多</small></h2><div class="chart">{pb}</div></div>
<div><h2>💬 话痨榜 TOP10</h2><div class="chart">{ct}</div></div></div>""")

# 5. 逐月热点
mv = max(c for mo in d["monthly"] for _, c in mo["tops"])
blocks = ""
for mo in d["monthly"]:
    bars = "".join(
        f'<div class="mrow"><span class="mop">{E(op)}</span>'
        f'{bar(c, mv, ["var(--accent)", "var(--pink)", "var(--blue)"][j])}'
        f'<span class="mval">{c}</span></div>'
        for j, (op, c) in enumerate(mo["tops"]))
    blocks += f'<div class="month"><h4>{E(mo["month"])}</h4>{bars}</div>'
sec.append(f'<h2>📈 逐月热点 <small>每月讨论量 TOP3，对应版本节奏</small></h2><div class="months">{blocks}</div>')

# 6. XP 名片
cards = ""
active = sorted(((n, v) for n, v in per_speaker.items() if v["msgs"] >= 100),
                key=lambda x: -x[1]["msgs"])
for n, v in active:
    m3 = " ".join(f'<span class="tag">{E(op)}<i>{c}</i></span>' for op, c in v["mention"][:3])
    a3 = (" ".join(f'<span class="tag love">{E(op)}<i>{c}</i></span>' for op, c in v["affection"][:3])
          or '<span class="tag none">强度党，不谈感情</span>')
    cards += f"""<div class="card"><div class="chead"><b>{E(n)}</b><span>{v["msgs"]}条</span></div>
<div class="cline">常聊 {m3 or '<span class="tag none">-</span>'}</div>
<div class="cline">示爱 {a3}</div></div>"""
sec.append(f'<h2>🪪 活跃群友 XP 名片 <small>发言≥100，共{len(active)}位</small></h2><div class="cards">{cards}</div>')

total_msgs = sum(v["msgs"] for v in per_speaker.values())
page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>桃大将军粉丝群 · XP 观察报告</title>
<style>
:root{{--bg:#0e1014;--panel:#171b22;--line:#262d38;--fg:#e6e9ef;--dim:#8b94a3;
--accent:#f0b429;--pink:#f06292;--green:#4fc38a;--blue:#5aa9e6;--purple:#a98fe0}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font-family:"Microsoft YaHei","PingFang SC",sans-serif;
max-width:1060px;margin:0 auto;padding:32px 20px 80px}}
header{{border:1px solid var(--line);border-radius:14px;padding:28px 32px;margin-bottom:28px;
background:linear-gradient(135deg,#1a1f2b,#141821);position:relative;overflow:hidden}}
header::after{{content:"アークナイツ";position:absolute;right:-10px;bottom:-22px;font-size:64px;
color:#ffffff08;font-weight:700;letter-spacing:4px}}
h1{{font-size:26px;margin-bottom:10px}}
h1 span{{color:var(--accent)}}
.meta{{color:var(--dim);font-size:13px;line-height:1.8}}
h2{{font-size:19px;margin:38px 0 14px;padding-left:12px;border-left:4px solid var(--accent)}}
h2 small{{color:var(--dim);font-size:12px;font-weight:400;margin-left:8px}}
h3{{font-size:14px;color:var(--dim);margin:12px 0 8px}}
h3 small{{font-size:11px;margin-left:6px}}
.chart,.cards,.chips,.months{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}}
.row{{display:flex;align-items:center;gap:10px;padding:5px 0}}
.medal{{width:30px;text-align:center;font-size:14px;flex:none}}
.rk{{color:var(--dim);font-size:12px}}
.name{{width:96px;flex:none;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.name.nick{{width:180px}}
.tgt{{width:70px;flex:none;font-size:13px;color:var(--accent)}}
.bar{{flex:1;height:14px;background:#0a0c10;border-radius:7px;overflow:hidden}}
.fill{{height:100%;border-radius:7px;min-width:2px}}
.val{{width:120px;flex:none;text-align:right;font-size:13px}}
.val i{{display:block;font-style:normal;color:var(--dim);font-size:11px}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;padding:12px}}
.chip{{border:1px solid var(--line);border-radius:20px;padding:6px 14px;font-size:13px;
display:flex;gap:6px;align-items:center}}
.chip.op{{border-color:#f0b42944}}
.chip.ppl{{border-color:#a98fe044}}
.chip .arr{{color:var(--dim);font-size:11px}}
.chip .tgt{{color:var(--accent)}}
.chip.ppl .tgt{{color:var(--purple)}}
.chip i{{font-style:normal;color:var(--dim);font-size:11px}}
.months{{display:flex;gap:14px;flex-wrap:wrap}}
.month{{flex:1;min-width:160px}}
.month h4{{color:var(--dim);font-size:13px;margin-bottom:8px}}
.mrow{{display:flex;align-items:center;gap:8px;padding:3px 0}}
.mop{{width:56px;flex:none;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mval{{width:36px;flex:none;text-align:right;font-size:12px;color:var(--dim)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}}
.card{{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:#12161d}}
.chead{{display:flex;justify-content:space-between;margin-bottom:6px}}
.chead b{{font-size:14px}}
.chead span{{color:var(--dim);font-size:12px}}
.cline{{font-size:12px;color:var(--dim);padding:2px 0}}
.tag{{display:inline-block;background:#1d232e;border-radius:4px;padding:1px 7px;margin:1px 3px 1px 0;
font-size:12px;color:var(--fg)}}
.tag i{{font-style:normal;color:var(--accent);margin-left:4px;font-size:11px}}
.tag.love i{{color:var(--pink)}}
.tag.none{{color:var(--dim);background:none;padding-left:0}}
footer{{margin-top:48px;color:var(--dim);font-size:12px;text-align:center;line-height:1.8}}
</style></head><body>
<header>
<h1>桃大将军粉丝群 <span>· 群友 XP 观察报告</span></h1>
<div class="meta">
全量 {total_msgs:,} 条发言 · {len(per_speaker)} 位群友 · {len(mentions)} 名被提及的干员<br>
干员名表来自 PRTS 同步实体索引 + 社区黑话昵称表；@群友已剥离，机器人已剔除；单字名需语境才计数。<br>
娱乐向统计，误差客观存在，较真你就输了。
</div></header>
{''.join(sec)}
<footer>纯本地生成 · 仅含群昵称不含 QQ 号 · 本文件请勿外传<br>generated by xp_rank.py + xp_page.py</footer>
</body></html>"""

open("qq_info/xp_report.html", "w", encoding="utf-8").write(page)
print(f"[done] qq_info/xp_report.html ({len(page) // 1024} KB)")
