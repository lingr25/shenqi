#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_workbench.py — 由 kb_trial/curated_high_quality.json 生成单文件交互式机制工作台。

输出: dist/mechanics-workbench/index.html (单文件、离线、无外部依赖)
模板: workbench/template.html + workbench/app.js
纯本地构建，不调用任何外部 API；QQ 引文原样引用甄选层（已脱敏）。
"""
import json
import re
import collections
import datetime
import pathlib

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "kb_trial" / "curated_high_quality.json"
ENTITY_INDEX = ROOT / "kb_trial" / "entity_index.json"
TEMPLATE = ROOT / "workbench" / "template.html"
APP_JS = ROOT / "workbench" / "app.js"
OUT = ROOT / "dist" / "mechanics-workbench" / "index.html"

# ---------------------------------------------------------------- topics
# 专题版图：参照人类讲义《机制合订本》章节脉络，category 前缀归并
TOPICS = [
    {"id": "frames", "name": "帧时序与计时器", "en": "FRAME TIMING & TIMERS", "color": "#45e0b8",
     "prefixes": ["帧时序", "技力", "攻速", "冷却", "同帧结算", "动画", "UI表现"],
     "intro": "一切的地基：30 帧/秒的逻辑世界、费用技力计时器、攻击间隔双轨制。",
     "intro_long": "方舟的底层不是连续时间，而是 30 帧/秒的离散逻辑帧。本板块收束逻辑帧与动画帧的关系、费用/技力「每 30 帧回 1」的冷却槽模型与「多一帧」现象、攻击间隔的双轨制与攻速精算，以及各类周期性检测计时器。读懂本板块，才能理解其余一切机制讨论的度量衡。"},
    {"id": "pathfinding", "name": "寻路与推地块", "en": "PATHFINDING & TILE PUSHING", "color": "#6ea8fe",
     "prefixes": ["寻路"],
     "intro": "格判、SPFA 推地块、平整化拉直、避障力与足坐标判定区。",
     "intro_long": "敌人如何决定往哪走：格判与「上右下左」推地块、SPFA 推地块算法、路径平整化（拉直）、有箱图的反转例外，以及避障力的足坐标判定区与向量计算。本板块是甄选库中条目最多的专题。"},
    {"id": "displacement", "name": "位移与力学", "en": "DISPLACEMENT & FORCE", "color": "#ff9e64",
     "prefixes": ["位移", "碰撞检测"],
     "intro": "推拉传送、失衡击坠、三坐标体系与位移四系统的结算细节。",
     "intro_long": "三个坐标系与位移四系统：推力拉力的速度与路程结算、传送与临时路径点、失衡/击坠/浮空的状态机、碰撞与阻挡偏移。从「挤一下 0.5 格」到黍传送，位移是精算战术的核心杠杆。"},
    {"id": "targeting", "name": "索敌·仇恨与隐匿", "en": "TARGETING, AGGRO & STEALTH", "color": "#f5c542",
     "prefixes": ["索敌", "仇恨", "隐匿", "反隐", "选中判定", "光环"],
     "intro": "索敌帧四条件、仇恨排序精度、隐匿迷彩与反隐、光环检测。",
     "intro_long": "谁打谁、谁先被打：索敌帧的定义与四条件、冷却制/动画制索敌、仇恨排序与精度（辟谣「三帧索敌」）、嘲讽数值、隐匿/迷彩/反隐的判定、光环 vs 格判 vs 碰撞三种范围检测。"},
    {"id": "damage", "name": "伤害结算与数值", "en": "DAMAGE RESOLUTION & MATH", "color": "#ff6b81",
     "prefixes": ["伤害结算", "数值", "伤害类型"],
     "intro": "命中与伤判体系、乘区与倍率、取整规则、元素损伤与伤害来源。",
     "intro_long": "一次攻击如何变成数字：命中率与伤判体系、计算环节与判定环节的拆分、乘区叠加顺序、四舍六入五成双的取整、法抗与元素损伤、弹道出伤与伤害来源归属。"},
    {"id": "status", "name": "状态·控制与异常", "en": "STATUS & CONTROL", "color": "#7ee081",
     "prefixes": ["状态效果", "异常", "buff", "Buff", "重生"],
     "intro": "控制状态对比、buff 存续与叠加、异常状态结算时序。",
     "intro_long": "眩晕、沉睡、冰冻、束缚等控制状态的底层对比；buff 持续时间的「理论值 +1」规律、切状态机类 +2 的特例，以及异常状态的施加与解除时序。"},
    {"id": "operator", "name": "干员机制·技能特例", "en": "OPERATOR MECHANICS", "color": "#e08bd0",
     "prefixes": ["干员机制", "技能", "天赋", "模组", "阵营buff", "藏品"],
     "intro": "具体干员/技能的特例判定：再部署、锁血、召唤物、藏品交互。",
     "intro_long": "通用法则之外的实体特例：具体干员的技能判定、再部署与锁血、召唤物与盟约、模组与藏品的结算顺序。每一条都绑定到具体实体的实测或推导。"},
    {"id": "ballistic", "name": "弹道系统", "en": "PROJECTILE SYSTEM", "color": "#9d8cff",
     "prefixes": ["弹道"],
     "intro": "追踪弹、弹道碰撞与飞行参数、激光帧数。",
     "intro_long": "弹道的底层：追踪弹的追踪与命中、弹道碰撞半径与飞行参数、激光类弹道的帧数结算，以及悬而未决的考据案。"},
    {"id": "stage", "name": "关卡·地形与阻挡", "en": "STAGE, TERRAIN & BLOCKING", "color": "#8bd5e0",
     "prefixes": ["关卡", "出怪", "地形", "阻挡", "部署"],
     "intro": "出怪生成、地形判定、阻挡判定与部署时序。",
     "intro_long": "地图侧的机制：出怪生成时序、地块与地形判定、阻挡的判定与「三帧阻挡」循环、部署与撤退的帧级时序。"},
    {"id": "unpack", "name": "拆包数据·术语考据", "en": "UNPACKED DATA & TERMINOLOGY", "color": "#c8b28a",
     "prefixes": ["拆包数据", "文案", "术语"],
     "intro": "来自拆包的底层参数、内部命名沿革与文案/实现差异。",
     "intro_long": "群聊拆包沉淀的底层参数与内部命名：实例标识、状态机命名沿革、随机数，以及游戏文案与真实实现之间的差异考据。"},
    {"id": "misc", "name": "其他与拾遗", "en": "MISCELLANEOUS", "color": "#8fa0b3",
     "prefixes": [],
     "intro": "未归入上述板块的散点规则与方法论拾遗。",
     "intro_long": "未归入主要板块的散点规则：表现层协调、考据方法论、以及其他尚待归类的机制观察。"},
]

def classify(cat: str) -> str:
    head = cat.split("/")[0]
    for t in TOPICS:
        if any(head.startswith(p) for p in t["prefixes"]):
            return t["id"]
    return "misc"

# ---------------------------------------------------------------- constants (讲义附录 A)
CONSTANTS = [
    {"n": "帧长", "v": "69905×2⁻²¹ ≈ 0.033326 秒（略小于 1/30；旧版误记 2⁻²⁰≈0.0663，实为两帧长度）", "q": "帧长"},
    {"n": "移速系数", "v": "实际格/秒 = 属性移速 × 0.5", "q": "移速"},
    {"n": "加速度倍率", "v": "地面 8 / 飞行 20（特殊单位例外：孤星球 20、托生莲坐 8）", "q": "加速度"},
    {"n": "加速度上限", "v": "10 或 100（因单位而异）", "q": "加速度"},
    {"n": "刹车/起步亏损", "v": "地面 2.75 帧；飞行 0.5 帧", "q": "2.75"},
    {"n": "路径点判定半径", "v": "0.05 格；一帧可达 = 移速属性 > 3 时可触发", "q": "路径点"},
    {"n": "碰撞半径", "v": "干员受击 0.25；阻挡 0.7071；高台距离 0.1 磕墙；干员弹道碰撞半径 0.1~0.5", "q": "碰撞半径"},
    {"n": "避障判定区", "v": "足坐标（下偏 0.2）为中心 0.9×0.5：上 0.05、下左右 0.45", "q": "避障"},
    {"n": "缓慢移动速度", "v": "0.0625 格/秒（属性 <0.25 时 = 理论移速）", "q": "0.0625"},
    {"n": "仇恨精度", "v": "通用 0.1（干员 3 帧/敌人 0.1 格）；医疗 0.001；城防炮 0.001", "q": "仇恨"},
    {"n": "嘲讽", "v": "敌人类 1 级 = +1000；角色类 1 级 = +10000", "q": "嘲讽"},
    {"n": "箱子/坑权重", "v": "+1000 / +1000000", "q": "箱子"},
    {"n": "挤一下", "v": "0.5 格位移", "q": "挤一下"},
    {"n": "激光/弹道飞行", "v": "十字路口激光 6 帧；重构体道标形态 2 帧不可选中", "q": "激光"},
    {"n": "Buff 持续时间", "v": "一般理论值+1；切状态机类+2；夜半+1", "q": "持续时间"},
    {"n": "四舍六入五成双", "v": "局外乘算后进图取整（2s×75=3.5→4）", "q": "四舍六入"},
    {"n": "攻速上下限", "v": "20~600", "q": "攻速"},
    {"n": "费用第 10→11 秒", "v": "31 帧（10⁻⁵ 阈值+数据精度；费用/冷却/技力普遍「多一帧」；怪出生为 10 秒 12~16 帧之间）", "q": "31帧"},
    {"n": "光环检测帧", "v": "每费 9、19、29 帧（10 帧循环检测；挂上后再过 30 帧出伤）", "q": "光环"},
    {"n": "三帧阻挡", "v": "部署+1 帧再加 3n 帧（重复进行、不被打断）", "q": "三帧"},
    {"n": "阻挡偏移时长", "v": "0.2 秒＝7 帧到达、8 帧切格/传送", "q": "阻挡偏移"},
    {"n": "血量循环检测", "v": "早期怪每 6 帧（0.2 秒）一判，附带 99.9% 数值判定", "q": "血量"},
]

# ---------------------------------------------------------------- load
raw = json.load(open(SRC, encoding="utf-8"))
entries_raw = raw["entries"]

BV_RE = re.compile(r"(BV[0-9A-Za-z]+)(?:_p(\d+))?")

def slim_citation(c):
    layers = c.get("source_layers", [])
    is_qq = "window_id" in c or "qq" in layers
    quotes = []
    for q in c.get("quotes", []):
        t = q.get("t_start")
        quotes.append({
            "x": q.get("text", ""),
            "t": int(t) if isinstance(t, (int, float)) else None,
            "l": q.get("t_line_label"),
        })
    if is_qq:
        return {"kind": "qq", "wid": c.get("window_id"), "asof": c.get("as_of"),
                "nmsg": c.get("n_source_msgs"), "q": quotes}
    tf = c.get("transcript_file", "")
    m = BV_RE.search(tf)
    return {"kind": "vod", "file": tf,
            "bv": m.group(1) if m else None,
            "part": int(m.group(2)) if m and m.group(2) else 1,
            "cloud": any("asr" in s.lower() or "cloud" in s.lower() for s in layers),
            "q": quotes}

entries = []
for e in entries_raw:
    entries.append({
        "i": e["id"],
        "c": e["claim"],
        "s": e.get("subject", ""),
        "k": e.get("condition", ""),
        "sc": e.get("scope", ""),
        "cat": e.get("category", ""),
        "tp": classify(e.get("category", "")),
        "tr": e.get("track", ""),
        "sl": e.get("source_layer", ""),
        "ym": e.get("recorded_ym"),
        "rv": (e.get("review") or {}).get("status", ""),
        "rr": (e.get("review") or {}).get("reason", ""),
        "rp": 1 if e.get("derived_text_repairs") else 0,
        "ev": [slim_citation(c) for c in e.get("citations", [])],
        "ents": [],
    })

# ---------------------------------------------------------------- entities
ent_idx = json.load(open(ENTITY_INDEX, encoding="utf-8"))
mentions = ent_idx.get("mentions", {})
TYPE_PRIORITY = ["operator", "enemy", "mechanic", "device", "status", "shenqi_slang", "slang", "untyped"]

canon_type = {}
alias_map = {}
for name, lst in mentions.items():
    for it in lst:
        canon = it.get("canonical") or name
        ty = it.get("type") or "untyped"
        if canon not in canon_type or TYPE_PRIORITY.index(ty) < TYPE_PRIORITY.index(canon_type[canon]):
            canon_type[canon] = ty
        for alias in {name, canon}:
            if len(alias) < 2 or alias.isascii():
                continue
            prev = alias_map.get(alias)
            if prev is None or TYPE_PRIORITY.index(ty) < TYPE_PRIORITY.index(canon_type[prev]):
                alias_map[alias] = canon
# untyped 短词噪声大，只保留 ≥3 字
alias_map = {a: c for a, c in alias_map.items()
             if canon_type.get(c) != "untyped" or len(a) >= 3}

by_first = collections.defaultdict(list)
for a in alias_map:
    by_first[a[0]].append(a)

ent_count = collections.Counter()
for e in entries:
    text = e["c"] + " " + e["s"] + " " + e["k"]
    chars = set(text)
    found = set()
    for ch in chars:
        for a in by_first.get(ch, ()):
            if a in text:
                found.add(alias_map[a])
    e["__ents"] = found
    for c_ in found:
        ent_count[c_] += 1

for e in entries:
    e["ents"] = sorted(
        (n for n in e.pop("__ents") if canon_type.get(n) != "untyped"),
        key=lambda n: -ent_count[n],
    )[:8]

ENT_VIEW_CAP = {"operator": 60, "enemy": 40, "mechanic": 40, "shenqi_slang": 30,
                "slang": 20, "device": 20, "status": 20}
ent_view = []
for ty, cap in ENT_VIEW_CAP.items():
    pool = [(n, c) for n, c in ent_count.items() if canon_type.get(n) == ty and c >= 2]
    pool.sort(key=lambda x: -x[1])
    ent_view += [{"n": n, "c": c, "ty": ty} for n, c in pool[:cap]]

# ---------------------------------------------------------------- numbers
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:帧|格/秒|格|秒|级|倍|%)")
num_count = collections.Counter()
for e in entries:
    seen = set(m.group(0).replace(" ", "") for m in NUM_RE.finditer(e["c"]))
    for n in seen:
        num_count[n] += 1
nums = [{"t": n, "c": c} for n, c in num_count.most_common() if c >= 2][:80]

# ---------------------------------------------------------------- stats
tracks = collections.Counter()
for e in entries:
    if e["tr"] in ("qq", "qq_chat"):
        tracks["qq"] += 1
    elif e["tr"] in ("vod_official", "vod_cloud"):
        tracks["vod"] += 1
    else:
        tracks["mixed"] += 1
months = collections.Counter(str(e["ym"]) for e in entries)
bv_set = set()
for e in entries:
    for c in e["ev"]:
        if c.get("bv"):
            bv_set.add(c["bv"] + "#" + str(c.get("part", 1)))
stats = {
    "tracks": dict(tracks),
    "months": dict(months),
    "bv_count": len(bv_set),
    "user_verified": sum(1 for e in entries if e["rv"] == "user_verified"),
    "agent_verified": sum(1 for e in entries if e["rv"] == "agent_verified"),
}

db = {
    "schema_version": raw.get("schema_version", ""),
    "built": datetime.date.today().isoformat(),
    "stats": stats,
    "topics": [{k: t[k] for k in ("id", "name", "en", "color", "intro", "intro_long")} for t in TOPICS],
    "constants": CONSTANTS,
    "nums": nums,
    "entities": ent_view,
    "entries": entries,
}

db_json = json.dumps(db, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

tpl = open(TEMPLATE, encoding="utf-8").read()
app = open(APP_JS, encoding="utf-8").read()
html = tpl.replace("__DB_JSON__", db_json).replace("__APP_JS__", "<script>\n" + app + "\n</script>")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")

size_mb = OUT.stat().st_size / 1024 / 1024
print(f"entries={len(entries)} entities_view={len(ent_view)} nums={len(nums)}")
print(f"topic dist: {collections.Counter(e['tp'] for e in entries).most_common()}")
print(f"wrote {OUT} ({size_mb:.2f} MB)")
