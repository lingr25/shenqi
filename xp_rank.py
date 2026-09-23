# -*- coding: utf-8 -*-
"""群友 XP 榜单挖掘（本地娱乐向，纯离线，不调用 API）。

输入:  qq_info/messages_clean.jsonl, kb/entity_index.json, qq_info/identities.json
输出:  qq_info/xp_report.md, qq_info/xp_data.json
隐私:  报告只使用昵称，不含 QQ 号；输出目录 qq_info/ 已被 .gitignore 保护。
"""
import json
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

# ---------- 干员名表 ----------
ent = json.load(open("kb/entity_index.json", encoding="utf-8"))
ops = set()
for name, lst in ent["mentions"].items():
    for m in lst:
        if m.get("type") == "operator":
            ops.add(m.get("canonical") or name)
            break
# 去掉带括号注释的卫戍协议npc、纯英文名（群里基本不用英文聊）
ops = {o for o in ops if "(" not in o and any("\u4e00" <= c <= "\u9fff" for c in o)}

# 社区黑话/昵称 -> 官方名（本群语境下基本无歧义的才收）
NICK = {
    "史尔特尔": ["42", "四二"],
    "玛恩纳": ["叔叔"],
    "棘刺": ["鸡翅"],
    "假日威龙陈": ["水陈"],
    "浊心斯卡蒂": ["红蒂", "浊蒂"],
    "斯卡蒂": ["蒂蒂", "蓝蒂"],
    "凯尔希": ["老猞猁", "太后"],
    "阿米娅": ["兔兔", "小兔子"],
    "艾雅法拉": ["小羊"],
    "纯烬艾雅法拉": ["奶羊"],
    "伊芙利特": ["小火龙"],
    "塞雷娅": ["塞爹", "塞妈"],
    "莫斯提马": ["小莫"],
    "能天使": ["阿能"],
    "拉普兰德": ["拉狗"],
    "德克萨斯": ["德狗"],
    "缄默德克萨斯": ["异德"],
    "银灰": ["银老板"],
    "推进之王": ["推王", "王小姐"],
    "桃金娘": ["桃子"],
    "极境": ["鸡精"],
    "幽灵鲨": ["鲨鲨"],
    "重岳": ["大哥"],
    "澄闪": ["粉毛"],
    "艾丽妮": ["小鸟"],
    "菲亚梅塔": ["肥鸭", "火鸟"],
    "琴柳": ["76"],
    "逻各斯": ["小罗", "logos", "Logos"],
    "W": ["达不溜"],
    "维什戴尔": ["维神"],
    "焰影苇草": ["焰苇"],
    "陈": ["陈sir", "老陈"],
    "星熊": ["熊姐"],
    "诗怀雅": ["富婆"],
    "令": ["令姐"],
    "黍": ["黍姐"],
    "山": ["山哥"],
    "傀影": ["影子哥"],
    "缪尔赛思": ["缪缪"],
    "霍尔海雅": ["蛇蛇"],
    "Mon3tr": ["m3", "M3"],
    "特蕾西娅": ["殿下"],
    "霜星": ["白兔子"],
    "塔露拉": ["塔姐"],
    "闪灵": ["闪妈"],
    "泥岩": ["泥岩巨像"],  # 误命中防护用，不常见可忽略
    "风笛": ["笛子"],
    "夜莺": ["鸟笼"],
}
# 这些昵称太泛，容易误伤，剔除
DROP_NICK = {"鸟笼", "泥岩巨像"}
alias2canon = {}
for canon, nicks in NICK.items():
    if canon not in ops:
        continue
    for n in nicks:
        if n not in DROP_NICK:
            alias2canon[n] = canon

# 高风险词：单字干员 + 与日常词冲突的两字名 → 需要语境才计数
RISKY2 = {
    "医生", "乌有", "但书", "双月", "可颂", "白雪", "流星", "香草", "红豆",
    "布丁", "酸糖", "清流", "暴雨", "惊蛰", "霜叶", "泡泡", "豆苗", "松果",
    "卡夫卡", "罗宾", "远山", "芙蓉", "炎熔", "杜林", "梅尔", "地灵",
    "空爆", "斑点", "黑角", "夜刀", "巡林者", "清道夫", "翎羽", "米格鲁",
    "月见夜", "梓兰", "泡普卡", "空弦", "凛视", "冰酿", "云迹", "冬时",
    "红隼", "温米", "衡沙", "行箸", "深靛", "蚀清", "风暴", "断崖",
}
CTX_KW = ["干员", "抽", "潜", "专", "精二", "精1", "精一", "练", "皮肤", "老婆", "老公",
          "厨", "推", "技能", "天赋", "模组", "池", "歪", "满级", "2903", "2803", "2603",
          "2906", "2703", "开模", "专三", "专九", "强度", "基建", "信赖", "异格"]

AFF_KW = ["老婆", "老公", "我推", "单推", "激推", "好喜欢", "喜欢", "可爱", "涩",
          "嘶哈", "满潜", "专九", "拉满", "抽爆", "必抽", "梦中情", "好耶",
          "爱他", "爱她", "太爱", "本命"]

def build_matcher():
    safe, risky = [], []
    risky_canons = set()
    for o in ops:
        if len(o) == 1 or o in RISKY2:
            risky.append(o)
            risky_canons.add(o)
        else:
            safe.append(o)
    for n in alias2canon:
        safe.append(n)  # 昵称在本群语境按无歧义处理
    # 长的优先，避免短名抢先
    safe.sort(key=len, reverse=True)
    risky.sort(key=len, reverse=True)
    name2canon = {o: o for o in ops}
    name2canon.update(alias2canon)
    return (re.compile("|".join(map(re.escape, safe))) if safe else None,
            re.compile("|".join(map(re.escape, risky))) if risky else None,
            name2canon, risky_canons)

SAFE_RE, RISKY_RE, NAME2CANON, RISKY_CANONS = build_matcher()
AFF_RE = re.compile("|".join(map(re.escape, AFF_KW)))
CTX_RE = re.compile("|".join(map(re.escape, CTX_KW)))

ident = json.load(open("qq_info/identities.json", encoding="utf-8"))
BOTS = set(ident["bot_qqs"])

# 机器人同名干员（本群有个叫「贝娜」的功能 bot，讨论基本都在说 bot）
EXCLUDE_OPS = {"贝娜"}

# 全部历史昵称，用于剥离 @提及（@的是群友，不是干员本人）
smap = json.load(open("qq_info/speaker_map.json", encoding="utf-8"))
all_nicks = set()
for qq, info in smap["speakers"].items():
    for n in info["nicks"]:
        all_nicks.add(n["nick"])
AT_RE = re.compile("@(?:" + "|".join(map(re.escape, sorted(all_nicks, key=len, reverse=True))) + r")")
AT_GENERIC_RE = re.compile(r"@[^\s@]{1,25}")  # 兜底：未收录的历史昵称变体

def strip_mentions(text):
    return AT_GENERIC_RE.sub("", AT_RE.sub("", text))

# 昵称官宣单推: 「xx@OO单推人」「OO单推人」
DECL_RE = re.compile(r"(?:^|[@／/])([^@／/]{1,15}?)(?:单推人?|激推人?|单推<人>)$")
declared = defaultdict(Counter)   # speaker_id -> Counter(target)
for qq, info in smap["speakers"].items():
    for n in info["nicks"]:
        for seg in (n["nick"], n["nick"].split("@")[-1]):
            m = DECL_RE.search(seg)
            if m:
                t = m.group(1)
                t = re.sub(r"(妈妈|宝宝|宝|酱)$", "", t) or t  # 忍冬妈妈→忍冬
                declared[info["speaker_id"]][t] += n["count"]
                break

sid2nick = {}
for qq, info in smap["speakers"].items():
    nicks = sorted(info["nicks"], key=lambda x: -x["count"])
    sid2nick[info["speaker_id"]] = nicks[0]["nick"] if nicks else "匿名"

def nick(sid):
    return sid2nick.get(sid, "匿名")

mention = defaultdict(Counter)     # speaker_id -> Counter(op)
affection = defaultdict(Counter)   # speaker_id -> Counter(op)
op_mention = Counter()             # 全群
op_affection = Counter()
op_fans = defaultdict(set)         # op -> {speaker_id}
speaker_msgs = Counter()
month_op = defaultdict(Counter)    # YYYY-MM -> Counter(op)
n_lines = 0

with open("qq_info/messages_clean.jsonl", encoding="utf-8") as f:
    for line in f:
        n_lines += 1
        m = json.loads(line)
        if m.get("qq") in BOTS:
            continue
        text = m.get("text_stripped") or m.get("text") or ""
        if not text:
            continue
        text = strip_mentions(text)  # 剥掉 @群友，防止昵称里的干员名/示爱词串味
        if not text:
            continue
        sid = m["speaker_id"]
        speaker_msgs[sid] += 1
        hits = set()
        if SAFE_RE:
            for t in SAFE_RE.findall(text):
                hits.add(NAME2CANON[t])
        if RISKY_RE and CTX_RE.search(text):
            for t in RISKY_RE.findall(text):
                hits.add(NAME2CANON[t])
        if not hits:
            continue
        is_aff = bool(AFF_RE.search(text))
        month = m.get("time_str", "")[:7]
        for op in hits:
            if op in EXCLUDE_OPS:
                continue
            mention[sid][op] += 1
            op_mention[op] += 1
            op_fans[op].add(sid)
            if month:
                month_op[month][op] += 1
            if is_aff:
                affection[sid][op] += 1
                op_affection[op] += 1

# ---------- 榜单 ----------
MIN_MSG = 30          # 发言门槛，防一日游选手
MIN_MENTION = 5       # 提及门槛

hot_top = op_mention.most_common(30)
love_top = op_affection.most_common(30)

# 真爱率 = 示爱数/提及数（提及>=8）
love_rate = [(op, op_affection[op] / op_mention[op], op_mention[op], op_affection[op])
             for op in op_mention if op_mention[op] >= 8]
love_rate.sort(key=lambda x: -x[1])

# 单推浓度: 某干员示爱占其全部示爱比例（示爱总数>=5）
stan = []
for sid, c in affection.items():
    total = sum(c.values())
    if total >= 5 and speaker_msgs[sid] >= MIN_MSG:
        op, cnt = c.most_common(1)[0]
        stan.append((sid, op, cnt, total, cnt / total))
stan.sort(key=lambda x: (-x[4], -x[2]))

# 花心榜: 示爱过的不同干员数
playboy = sorted(((sid, len(c), sum(c.values())) for sid, c in affection.items()
                  if speaker_msgs[sid] >= MIN_MSG),
                 key=lambda x: -x[1])[:15]

# 话痨榜
chatty = speaker_msgs.most_common(15)

# 月度热点: 每个月讨论最多的干员
monthly_top = []
for mo in sorted(month_op):
    if sum(month_op[mo].values()) >= 50:
        monthly_top.append((mo, month_op[mo].most_common(3)))

# ---------- 输出 ----------
out = []
out.append("# 桃大将军粉丝群 · 群友 XP 观察报告\n")
out.append("> 数据范围: qq_info/messages_clean.jsonl 全量 %d 条消息（机器人已剔除）\n" % n_lines)
out.append("> 方法: 干员名表来自 kb/entity_index.json（PRTS 同步，%d 名）+ 手工社区黑话昵称表；" % len(ops))
out.append("单字名/易冲突词需语境关键词才计数。娱乐向统计，存在误差，勿当真。\n")
out.append("> 隐私: 仅使用群昵称，不含 QQ 号；本文件位于 gitignore 保护的 qq_info/ 内。\n")

out.append("\n## 〇、官宣单推墙（群昵称自带「XX单推人」声明）\n")
out.append("| 群友 | 官宣本命 | 类型 | 昵称使用消息数 |")
out.append("|---|---|---|---|")
decl_rows = []
for sid, c in declared.items():
    target, cnt = c.most_common(1)[0]
    canon = NAME2CANON.get(target, target if target in ops else None)
    kind = "干员" if canon else ("群友/其他")
    decl_rows.append((nick(sid), target + (f"（{canon}）" if canon and canon != target else ""), kind, cnt))
for r in sorted(decl_rows, key=lambda x: -x[3]):
    out.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")

out.append("\n## 一、全群干员热度榜 TOP30（被提及次数）\n")
out.append("| 排名 | 干员 | 提及 | 讨论过TA的人数 |")
out.append("|---|---|---|---|")
for i, (op, c) in enumerate(hot_top, 1):
    out.append(f"| {i} | {op} | {c} | {len(op_fans[op])} |")

out.append("\n## 二、真爱榜 TOP20（明示爱语境命中：老婆/喜欢/满潜/我推…）\n")
out.append("> 带 \\* 的是语境受限词（单字名/易冲突词，只在有干员语境时计数），真爱率口径偏高，看个乐。\n")
out.append("| 排名 | 干员 | 示爱次数 | 提及总数 | 真爱率 |")
out.append("|---|---|---|---|---|")
rate_map = {op: r for op, r, _, _ in love_rate}
for i, (op, c) in enumerate(love_top[:20], 1):
    mark = "\\*" if op in RISKY_CANONS else ""
    out.append(f"| {i} | {op}{mark} | {c} | {op_mention[op]} | {rate_map.get(op, 0):.0%} |")

out.append("\n## 三、单推浓度榜（个人示爱最集中于某干员，示爱总数≥5）\n")
out.append("| 排名 | 群友 | 本命 | 本命示爱/总示爱 | 浓度 |")
out.append("|---|---|---|---|---|")
for i, (sid, op, cnt, total, r) in enumerate(stan[:20], 1):
    out.append(f"| {i} | {nick(sid)} | {op} | {cnt}/{total} | {r:.0%} |")

out.append("\n## 四、花心榜（示爱过的不同干员最多）\n")
out.append("| 排名 | 群友 | 爱过的干员数 | 总示爱次数 |")
out.append("|---|---|---|---|")
for i, (sid, n, tot) in enumerate(playboy, 1):
    tops = "、".join(f"{op}" for op, _ in affection[sid].most_common(5))
    out.append(f"| {i} | {nick(sid)} | {n} | {tot}（最爱：{tops}） |")

out.append("\n## 五、话痨榜 TOP10\n")
out.append("| 排名 | 群友 | 发言数 | 提及干员数 |")
out.append("|---|---|---|---|")
for i, (sid, c) in enumerate(chatty[:10], 1):
    out.append(f"| {i} | {nick(sid)} | {c} | {len(mention[sid])} |")

out.append("\n## 六、逐月热点（每月讨论量 TOP3 干员，月提及≥50）\n")
out.append("| 月份 | TOP1 | TOP2 | TOP3 |")
out.append("|---|---|---|---|")
for mo, tops in monthly_top:
    cells = [f"{op}({c})" for op, c in tops] + [""] * (3 - len(tops))
    out.append(f"| {mo} | {cells[0]} | {cells[1]} | {cells[2]} |")

# 每人 XP 名片（发言>=100 的活跃群友）
out.append("\n## 七、活跃群友 XP 名片（发言≥100）\n")
out.append("| 群友 | 发言 | 最常聊 TOP3 | 最爱 TOP3 |")
out.append("|---|---|---|---|")
active = [(sid, c) for sid, c in speaker_msgs.most_common() if c >= 100]
for sid, c in active:
    m3 = "、".join(f"{op}({n})" for op, n in mention[sid].most_common(3)) or "-"
    a3 = "、".join(f"{op}({n})" for op, n in affection[sid].most_common(3)) or "-"
    out.append(f"| {nick(sid)} | {c} | {m3} | {a3} |")

report = "\n".join(out) + "\n"
open("qq_info/xp_report.md", "w", encoding="utf-8").write(report)

json.dump({
    "op_mention": op_mention.most_common(),
    "op_affection": op_affection.most_common(),
    "per_speaker": {
        nick(sid): {
            "msgs": speaker_msgs[sid],
            "mention": mention[sid].most_common(),
            "affection": affection[sid].most_common(),
        } for sid in speaker_msgs
    },
}, open("qq_info/xp_data.json", "w", encoding="utf-8"), ensure_ascii=False)

print(report[:6000])
print("...")
print(f"\n[done] speakers={len(speaker_msgs)} ops_covered={len(ops)} -> qq_info/xp_report.md")
