# -*- coding: utf-8 -*-
"""从官方逐字稿/ASR 草稿切完整讲段，写出 evidence_round1 产物。无 LLM。"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.dirname(os.path.abspath(__file__))
TS = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")


def load_rows(rel):
    path = os.path.join(ROOT, rel)
    rows = []
    for line in open(path, encoding="utf-8"):
        raw = line.rstrip("\n")
        m = TS.match(raw)
        if not m:
            continue
        h = int(m.group(1) or 0)
        sec = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        rows.append({"t": sec, "text": m.group(4), "raw": raw})
    return path, rows


def slice_packet(rel, t0, t1):
    path, rows = load_rows(rel)
    lines = [r for r in rows if t0 <= r["t"] <= t1]
    layer = "official_txt" if rel.startswith("transcripts_txt/") else "asr_draft"
    return path, layer, lines


TOPICS = [
    {"topic_id": "T01", "cluster_id": "帧时序与计时器-24-0", "bucket": "recoverable",
     "focus": "动画/冷却", "file": "asr_drafts/BV199KH6TEra_p1_40136673556_asr.txt",
     "t0": 6639, "t1": 6775,
     "span_note": "从「动画何时播放从索敌开始」讲到计算器，约 2 分 16 秒，非 40 秒窗。"},
    {"topic_id": "T02", "cluster_id": "索敌-0-1", "bucket": "recoverable",
     "focus": "弹道检测", "file": "asr_drafts/BV14gby6LEni_p1_40940472044_asr.txt",
     "t0": 4392, "t1": 4433,
     "span_note": "「三针索敌并不是绝对」到「不要什么都三针索敌」；其后光环碰撞挂 buff 另标。"},
    {"topic_id": "T03", "cluster_id": "索敌-1-0", "bucket": "recoverable",
     "focus": "阻挡帧起点 vs 索敌/避障", "file": "asr_drafts/BV14gby6LEni_p1_40940472044_asr.txt",
     "t0": 6489, "t1": 6930,
     "span_note": "从 92 针眩晕/94 针可动讲到阻挡 3n+1 与要用非三倍控避障。含当场演示。"},
    {"topic_id": "T04", "cluster_id": "帧时序与计时器-46-2", "bucket": "recoverable",
     "focus": "动画 0.1 倍下限", "file": "transcripts_txt/BV1jd3m68E6f_p1_40508197659.txt",
     "t0": 1330, "t1": 1465,
     "span_note": "先讲冷却制/动画制索敌顺序，再讲杰西卡与 0.1 倍下限。"},
    {"topic_id": "T05", "cluster_id": "位移-1-5", "bucket": "recoverable",
     "focus": "四种移动", "file": "transcripts_txt/BV14gby6LEni_p3_40944668620.txt",
     "t0": 1314, "t1": 1385,
     "span_note": "12/13 帧部署撤退演示之后切入四种逻辑，到「鼠的传送是在什么阶段」提问为止。"},
    {"topic_id": "T06", "cluster_id": "帧时序与计时器-43-1", "bucket": "recoverable",
     "focus": "动画下限取整", "file": "asr_drafts/BV1j4KC6KEse_p1_40109737103_asr.txt",
     "t0": 7577, "t1": 7612,
     "span_note": "答疑第一问动画下限；下一问改祥子事件帧，在此切断。ASR 嘈杂。"},
    {"topic_id": "T07", "cluster_id": "索敌-22-7", "bucket": "experiment_risk",
     "focus": "城防炮两套索敌冷却+零帧演示", "file": "transcripts_txt/BV1jd3m68E6f_p1_40508197659.txt",
     "t0": 2113, "t1": 2406,
     "span_note": "从「普攻和技能索敌冷却差异」到占用攻击间隔的技能条件，含演示与出生错开。"},
    {"topic_id": "T08", "cluster_id": "帧时序与计时器-3-10", "bucket": "experiment_risk",
     "focus": "桃金娘空费帧出伤（不猜主语）", "file": "asr_drafts/BV14gby6LEni_p1_40940472044_asr.txt",
     "t0": 4609, "t1": 4737,
     "span_note": "空费帧下桃金娘到 39 挂 buff 说明；异德/重构体另起，切断。"},
    {"topic_id": "T09", "cluster_id": "寻路-7-8", "bucket": "experiment_risk",
     "focus": "一帧可达与酒神猫特例", "file": "transcripts_txt/BV14y8269EbS_p1_41164079923.txt",
     "t0": 6435, "t1": 6652,
     "span_note": "诱导不可完成路径点 → 一帧可达定义 → 酒神猫每帧瞬移。"},
    {"topic_id": "T10", "cluster_id": "其他-6-1", "bucket": "reject_negative",
     "focus": "费用条/车辆", "file": "asr_drafts/BV1JX8WzFEUU_p1_31284463292_asr.txt",
     "t0": 2869, "t1": 3071,
     "span_note": "负例：零到五十九无单位。"},
    {"topic_id": "T11", "cluster_id": "寻路-36-6", "bucket": "reject_negative",
     "focus": "路径点帧数例题", "file": "transcripts_txt/BV1TomVBBEK1_p1_34675165371.txt",
     "t0": 3185, "t1": 3431,
     "span_note": "负例：1.95/0.4 例题变量不闭合。"},
    {"topic_id": "T12", "cluster_id": "技能特例-16-7", "bucket": "reject_negative",
     "focus": "3N+2 测试口径", "file": "transcripts_txt/BV1j4KC6KEse_p2_40109932632.txt",
     "t0": 514, "t1": 559,
     "span_note": "负例：声明还有更完整索敌帧流程。"},
]


def line_at(lines, t):
    for r in lines:
        if r["t"] == t:
            return r
    return None


def main():
    packets = []
    by_id = {}
    for spec in TOPICS:
        path, layer, lines = slice_packet(spec["file"], spec["t0"], spec["t1"])
        pkt = {
            "topic_id": spec["topic_id"],
            "cluster_id": spec["cluster_id"],
            "bucket": spec["bucket"],
            "focus": spec["focus"],
            "source": {
                "file": spec["file"].replace("\\", "/"),
                "abspath_note": path,
                "layer": layer,
                "t_start": spec["t0"],
                "t_end": spec["t1"],
            },
            "span_note": spec["span_note"],
            "line_count": len(lines),
            "lines": [{"t": r["t"], "text": r["text"]} for r in lines],
            "needs_av": [],
        }
        packets.append(pkt)
        by_id[spec["topic_id"]] = pkt

    # 文本无法闭合处
    by_id["T01"]["needs_av"] = [
        "01:50:48「走的就是冷却值呃补整之后加一」听写不清，冷却制补整公式停补，需原音。"
    ]
    by_id["T06"]["needs_av"] = [
        "答疑 ASR 把 2.1→3 讲成「截向2.1也是3.32.1也是3」，取整例子需原音确认数字。"
    ]
    by_id["T08"]["needs_av"] = [
        "「某肺的9针」等 ASR 噪声；99/29 为当场反推，未独立实测，画面/原音才能核桃金娘轴。"
    ]

    def ev(topic_id, *ts):
        pkt = by_id[topic_id]
        out = []
        for t in ts:
            row = line_at(pkt["lines"], t)
            if not row:
                raise SystemExit(f"missing t={t} in {topic_id}")
            out.append({
                "topic_id": topic_id,
                "file": pkt["source"]["file"],
                "layer": pkt["source"]["layer"],
                "t": t,
                "text": row["text"],
            })
        return out

    mechanisms = []
    experiments = []

    def _gate(kind, eligibility):
        return kind == "mechanism" and eligibility == "accepted"

    def mech(eligibility, **kw):
        kw["record_type"] = "mechanism"
        kw["eligibility"] = eligibility
        kw["rag_gate"] = _gate("mechanism", eligibility)
        mechanisms.append(kw)

    def der(eligibility, **kw):
        kw["record_type"] = "derivation"
        kw["eligibility"] = eligibility
        kw["rag_gate"] = False
        mechanisms.append(kw)

    def exp(eligibility, **kw):
        kw["eligibility"] = eligibility
        kw["rag_gate"] = False
        experiments.append(kw)

    # ----- T01 24-0 -----
    mech("accepted", id="M01-seek-then-anim", topic_id="T01",
         text="动画从索敌开始播放：索敌之后才会进行动画播放。",
         subject="攻击动画播放起点", when=["索敌之后"],
         variables={},
         evidence=ev("T01", 6639, 6648),
         linked_experiments=[], linked_derivations=["D01-round-anim-length"])
    mech("accepted", id="M01-anim-vs-cooldown-branch", topic_id="T01",
         text="动画播放有多长，由动画长度上限和当前攻速决定。若攻速和攻击间隔算出来的数比动画长度上限更长，走冷却值；若更小，走动画值。",
         subject="攻击间隔走冷却值还是动画值",
         when=["比较「攻速与攻击间隔算出的数」与「动画长度上限」"],
         variables={},
         evidence=ev("T01", 6648),
         linked_experiments=[], linked_derivations=["D01-round-anim-length"])
    der("needs_av", id="D01-cd-plus-one-garbled", topic_id="T01",
        text="原话在「走冷却值」后出现「补整之后加一」，ASR 无法闭合为公式，不入库为机制。",
        subject="冷却值补整", when=[],
        variables={},
        evidence=ev("T01", 6648),
        linked_experiments=[], linked_derivations=[],
        supports=["M01-anim-vs-cooldown-branch"])
    der("accepted", id="D01-round-anim-length", topic_id="T01",
        text="动画播放长度本身四舍五入确定；最终使得攻击间隔被四舍五入。动画值与冷却值算出来不一致时按动画值，不能按冷却值。冷却归零时若仍在动画播放流程中，不能立刻抬手。",
        subject="动画制攻击间隔",
        when=["走动画播放"],
        variables={},
        evidence=ev("T01", 6686, 6717, 6724, 6739, 6745),
        linked_experiments=[], linked_derivations=[],
        supports=["M01-seek-then-anim", "M01-anim-vs-cooldown-branch"])
    der("needs_av", id="D01-remain-cd-0.5", topic_id="T01",
        text="动画播放结束时检测剩余冷却是不是小于 0.5，并把冷却四舍五入以服从动画。0.5 未标明单位，不作为机制阈值。",
        subject="剩余冷却检测", when=["动画播放结束"],
        variables={},
        evidence=ev("T01", 6686),
        linked_experiments=[], linked_derivations=[],
        supports=["D01-round-anim-length"])

    # ----- T02 弹道 -----
    mech("accepted", id="M02-projectile-no-3frame", topic_id="T02",
         text="三针索敌并不是非常绝对。弹道没有角色类或敌人类单位所应该有的三针索敌，单纯靠周期性检测实现索敌流程。",
         subject="弹道", when=[],
         variables={},
         evidence=ev("T02", 4392),
         linked_experiments=[], linked_derivations=["D02-period-unknown"])
    der("needs_av", id="D02-period-unknown", topic_id="T02",
        text="检测周期被说成「奇奇怪怪」，未给出周期数值，不得写成已知参数。",
        subject="弹道检测周期", when=[],
        variables={},
        evidence=ev("T02", 4392),
        linked_experiments=[], linked_derivations=[],
        supports=["M02-projectile-no-3frame"])
    mech("context_only", id="M02-halo-collision-buff", topic_id="T02",
         text="对光环：若碰撞针直接就可以挂上 buff，会直接挂，不走时针循环。口播称还要用潮汐的伞去证明。",
         subject="光环挂 buff", when=["碰撞针直接可以挂上 buff"],
         variables={},
         evidence=ev("T02", 4413),
         linked_experiments=[], linked_derivations=[])

    # ----- T03 阻挡 -----
    mech("accepted", id="M03-block-3cycle", topic_id="T03",
         text="阻挡针与索敌帧不同：索敌帧在某些进程（如眩晕）结束时会立刻触发；阻挡针反复在进行三循环。",
         subject="阻挡帧", when=[],
         variables={},
         evidence=ev("T03", 6546),
         linked_experiments=["E03-94-can-move"], linked_derivations=["D03-stun-split"])
    mech("accepted", id="M03-block-from-deploy", topic_id="T03",
         text="阻挡帧由部署决定，部署之后 3N 加一帧。无论开技能或解除不可阻挡发生在哪一帧，都按部署相位，不能理解成索敌那种立刻归零。",
         subject="阻挡帧", when=["以部署为计时零点"],
         variables={"相位": "3N+1（N 未展开成表）"},
         evidence=ev("T03", 6879),
         linked_experiments=["E03-94-can-move"], linked_derivations=[])
    mech("accepted", id="M03-avoid-path-only", topic_id="T03",
         text="避障帧只在寻路状态机下、并且不被跳过避障结算步骤的时候会用。",
         subject="避障帧", when=["处于寻路状态机", "未跳过避障结算"],
         variables={},
         evidence=ev("T03", 6568),
         linked_experiments=["E03-early-stun-still-4"], linked_derivations=["D03-stun-split"])
    der("accepted", id="D03-stun-split", topic_id="T03",
        text="避障会表现出寻路上的拼接感：眩晕前的两针和眩晕后的一针可以被拼接为 3N 的避障。",
        subject="避障帧", when=["眩晕跨越避障结算"],
        variables={},
        evidence=ev("T03", 6597),
        supports=["M03-avoid-path-only"],
        linked_experiments=["E03-early-stun-still-4"], linked_derivations=[])
    der("context_only", id="D03-avoid-cd-after-stun", topic_id="T03",
        text="该次演示里主播假设：眩晕前避障冷却是 3 则晕后再过三针，是 1 则再过一针；总共 92 针晕时，改变晕的时刻不改变晕完之后的避障针。绑定当场 92 针晕，不是独立通则。",
        subject="该次避障演示", when=["该次 92 针眩晕"],
        variables={"该次总晕": "92 针"},
        evidence=ev("T03", 6489, 6844),
        supports=["M03-avoid-path-only"],
        linked_experiments=["E03-early-stun-still-4", "E03-94-can-move"], linked_derivations=[])
    exp("accepted", id="E03-94-can-move", topic_id="T03",
        text="该次演示：晕 92 针；主播称 94 针才会开始动，且 94 帧只是可以动，不一定该帧就会动。测试对象未点名。",
        subject="未点名测试单位", when=["该次 92 针眩晕演示"],
        variables={"该次可动帧": "94 针"},
        evidence=ev("T03", 6489, 6526, 6531),
        linked_mechanisms=["M03-block-3cycle", "M03-block-from-deploy"],
        linked_derivations=["D03-avoid-cd-after-stun"])
    exp("accepted", id="E03-early-stun-still-4", topic_id="T03",
        text="按索敌帧逻辑早晕应早动；该次观察到三针仍不动、四针才动，用来对比避障≠索敌。",
        subject="未点名测试单位", when=["该次提前眩晕对比"],
        variables={},
        evidence=ev("T03", 6824),
        linked_mechanisms=["M03-avoid-path-only"],
        linked_derivations=["D03-stun-split", "D03-avoid-cd-after-stun"])

    # ----- T04 0.1 -----
    mech("accepted", id="M04-seek-order", topic_id="T04",
         text="结算顺序：冷却至索敌在先，索敌冷却减一在后；而动画制索敌是索敌冷却减一这个事件在先，动画制索敌在后。",
         subject="冷却至索敌 / 动画制索敌", when=[],
         variables={},
         evidence=ev("T04", 1330),
         linked_experiments=["E04-jessica-2frame"], linked_derivations=[])
    mech("accepted", id="M04-anim-floor-0.1", topic_id="T04",
         text="攻击持续或者攻击动画不能短于自己原初设定的动画长度的 0.1 倍。",
         subject="攻击持续或攻击动画", when=["动画被缩短时"],
         variables={"下限": "原初设定动画长度的 0.1 倍"},
         evidence=ev("T04", 1392),
         linked_experiments=["E04-jessica-2frame"], linked_derivations=[])
    exp("accepted", id="E04-jessica-2frame", topic_id="T04",
        text="底火杰西卡被用作能压到两帧间隔的例子：主播称其是目前唯一满足该 0.1 倍条件、可按理论两帧间隔攻击的干员。1.2 间隔属性、二技能减 0.9、0.3 秒九帧、满攻速 1.5 帧四舍五入两帧，均属该例。",
        subject="底火杰西卡（例）", when=["该例演算"],
        variables={"例_间隔属性": "1.2", "例_二技能加算": "-0.9", "例_0.3秒": "九帧"},
        evidence=ev("T04", 1348, 1361, 1392, 1414),
        linked_mechanisms=["M04-anim-floor-0.1", "M04-seek-order"],
        linked_derivations=[])

    # ----- T05 四种移动 -----
    mech("accepted", id="M05-four-moves", topic_id="T05",
         text="方舟移动分为寻路、阻挡偏移、失衡和传送。失衡在失衡状态机下基于物理速度移动；寻路在寻路状态机下基于移速移动；阻挡偏移在其规定之下瞄准落点移动；传送直接传送到指定位置。随后说瞬移直接改写坐标，大概是这四种。",
         subject="方舟移动", when=[],
         variables={},
         evidence=ev("T05", 1341, 1360, 1379),
         linked_experiments=["E05-12-13-deploy"], linked_derivations=[])
    exp("accepted", id="E05-12-13-deploy", topic_id="T05",
        text="切入四种逻辑前的当场操作：12 帧部署、13 针撤退，过来后又在原地不动。被测对象未点名。",
        subject="未点名", when=["该次 12/13 帧部署撤退"],
        variables={"部署": "12 帧", "撤退": "13 针"},
        evidence=ev("T05", 1317, 1321, 1327, 1331),
        linked_mechanisms=["M05-four-moves"], linked_derivations=[])

    # ----- T06 下限取整 -----
    mech("accepted", id="M06-floor-ceil", topic_id="T06",
         text="动画下限：大于下限，所以是向上取整。",
         subject="动画下限", when=["相对下限取整"],
         variables={},
         evidence=ev("T06", 7577),
         linked_experiments=[], linked_derivations=["D06-21-example-garbled"])
    der("needs_av", id="D06-21-example-garbled", topic_id="T06",
        text="答疑里出现 29×0.1 / 27×0.1 / 2.1 / 3 等数字，ASR 打成「截向2.1也是3.32.1也是3」，不得把 2.1→3 写成已核例子。",
        subject="动画下限取整例子", when=[],
        variables={},
        evidence=ev("T06", 7577),
        linked_experiments=[], linked_derivations=[],
        supports=["M06-floor-ceil"])

    # ----- T07 城防炮 -----
    mech("accepted", id="M07-two-seek-cd", topic_id="T07",
         text="以 11-20 城防炮引入的「这种技能」：技能的索敌冷却和普攻的索敌冷却是两个属性在转，不是一个东西。所以会出现技能已经转好却先打出一发普攻。",
         subject="这种技能（讲段以 11-20 城防炮为例）", when=["普攻索敌冷却与技能索敌冷却分开转"],
         variables={},
         evidence=ev("T07", 2113, 2133, 2148),
         linked_experiments=["E07-zero-one-cannon"], linked_derivations=["D07-spawn-stagger"])
    mech("accepted", id="M07-skill-needs-both-cd", topic_id="T07",
         text="释放技能需要攻击和技能冷却都清零；条件二技能同样也需要攻击冷却清零。这就是很多所谓占用攻击间隔的技能。",
         subject="占用攻击间隔的技能", when=["要释放技能"],
         variables={},
         evidence=ev("T07", 2406),
         linked_experiments=[], linked_derivations=[])
    mech("context_only", id="M07-laser-shared-seek", topic_id="T07",
         text="口播举例「精粹的激光头」：普攻和技能共用索敌帧，不会有阻挡立刻抬手那种事。这是另一套索敌是否共用的逻辑，不是「双冷却清零」的例外。指代未在本段定义清楚，不作通用机制。",
         subject="精粹的激光头（指代未闭合）", when=[],
         variables={},
         evidence=ev("T07", 2370, 2386),
         linked_experiments=[], linked_derivations=[])
    exp("accepted", id="E07-zero-one-cannon", topic_id="T07",
        text="零帧部署、一帧撤退：最左城防炮开一炮为普攻（索敌在一针）；中间两门抬手打技能（技能索敌帧在一帧而非普攻索敌帧）；再下一门被说成两种索敌帧都不在一帧。翼德只是测试干员，不是规则主语。",
        subject="城防炮（该次演示）", when=["零帧部署", "一帧撤退"],
        variables={"部署": "零帧", "撤退": "一帧"},
        evidence=ev("T07", 2178, 2182, 2185, 2196, 2213),
        linked_mechanisms=["M07-two-seek-cd"], linked_derivations=["D07-spawn-stagger"])
    der("accepted", id="D07-spawn-stagger", topic_id="T07",
        text="该次进图一帧一出怪，按出生把普攻/技能索敌帧错开，所以会碰到三种情况。",
        subject="该次进图出怪", when=["一帧一出怪"],
        variables={},
        evidence=ev("T07", 2213, 2232),
        supports=["E07-zero-one-cannon"],
        linked_experiments=["E07-zero-one-cannon"], linked_derivations=[])

    # ----- T08 桃金娘 -----
    exp("accepted", id="E08-myrtle-69", topic_id="T08",
        text="空费帧部署桃金娘：主播说 61 到 70 帧之间会出伤，该次读到 69。随性未卡帧再下一个仍同一帧；同帧再下红，出伤在下一秒 19。",
        subject="桃金娘（该次空费帧部署）", when=["空费帧部署"],
        variables={"该次出伤": "69 帧", "红出伤": "下一秒 19 帧"},
        evidence=ev("T08", 4616, 4635, 4675, 4699),
        linked_mechanisms=[], linked_derivations=["D08-39-plus-30"])
    der("context_only", id="D08-39-plus-30", topic_id="T08",
        text="同一次桃金娘演示里，主播说「这种技能」：碰撞箱碰撞针尝试挂 buff；挂不上加入时针循环检测列表；挂上后再过 30 帧走第一次冷却才出伤。因此 69 出伤他说实际是 39 挂 buff。99 和 29 是由 69 反推的检测周期。主语是当场「这种技能」+桃金娘演示，不能当成可直接 RAG 的无名光环通则。",
        subject="该次空费帧下的桃金娘演示（口播称这种技能）", when=["该次演示", "碰撞针未直接挂上 buff"],
        variables={"该次反推挂 buff": "39 帧", "口播冷却": "30 帧", "反推周期": "99 和 29"},
        evidence=ev("T08", 4635, 4699),
        supports=["E08-myrtle-69"],
        linked_experiments=["E08-myrtle-69"], linked_derivations=[])

    # ----- T09 一帧可达 -----
    mech("accepted", id="M09-one-frame-reach", topic_id="T09",
         text="若路径点在自己实坐标的一帧可达半径之内，则直接瞬移到路径点。一帧可达半径用「一帧乘帧时间乘移速」得到一针可移动距离再画圆。正常情况下需要移速属性大于三；这不是加速度。正常情况下踩到路径点完成半径之内即完成该点，完成后不再做一帧可达判定。",
         subject="寻路单位", when=["正常可完成的路径点"],
         variables={"移速属性阈值": "大于三"},
         evidence=ev("T09", 6477, 6490, 6512, 6580),
         linked_experiments=["E09-wine-cat"], linked_derivations=["D09-radius-number-corrected"])
    der("needs_av", id="D09-radius-number-corrected", topic_id="T09",
        text="主播先说移速为三时「1/10 是 3/30，1/10 是 0.05」，随即更正「三的属性速度要乘 0.5 是理论速度……忘了，这里说的是 0.05 的一针可达半径」。不得把未更正的 1/10=3/30=0.05 写成机制。0.05 未标明单位，数值不入库为机制。",
        subject="移速属性为三时的一帧可达半径", when=["移速属性为三"],
        variables={},
        evidence=ev("T09", 6542, 6580),
        supports=["M09-one-frame-reach"],
        linked_experiments=["E09-wine-cat"], linked_derivations=[])

    exp("accepted", id="E09-wine-cat", topic_id="T09",
        text="诱导是不可完成路径点。酒神的猫不会被完成，足够近时被一帧可达：每帧瞬移到路径点，跳过后续避障等步骤。",
        subject="酒神的猫 / 诱导路径点", when=["路径点不可完成"],
        variables={},
        evidence=ev("T09", 6452),
        linked_mechanisms=["M09-one-frame-reach"],
        linked_derivations=["D09-radius-number-corrected"])

    rejected = [
        {"topic_id": "T10", "cluster_id": "其他-6-1",
         "reason": "「它现在变成了零到五十九」无主语无单位；2n+1 未定义；整段拒收为机制。",
         "keep_nothing": True},
        {"topic_id": "T11", "cluster_id": "寻路-36-6",
         "reason": "1.95/0.4/2.75/149 为例题演算，0.4 对象与单位未闭合；取整绑在该例。整段拒。",
         "keep_nothing": True},
        {"topic_id": "T12", "cluster_id": "技能特例-16-7",
         "reason": "3N+2 未定义 N；主播声明还有更完整索敌帧流程；主语未点名。",
         "keep_nothing": True},
        {"topic_id": "T08", "cluster_id": "帧时序与计时器-3-10",
         "reason": "不把 99/29 写成普遍光环时钟；不把异德 33 并进桃金娘。机制槽位空，只保留实验+推导。",
         "keep_nothing": False, "rejected_as": "universal_mechanism"},
        {"topic_id": "T06", "cluster_id": "帧时序与计时器-43-1",
         "reason": "祥子事件帧问答与下限取整不是同一问，未收入。2.1→3 依赖嘈杂 ASR。",
         "keep_nothing": False},
    ]

    # Fix M09 evidence timestamps using actual packet lines
    t09 = [r["t"] for r in by_id["T09"]["lines"]]
    # pick known texts
    def ts_containing(topic_id, needle):
        hits = [r["t"] for r in by_id[topic_id]["lines"] if needle in r["text"]]
        if not hits:
            raise SystemExit(f"needle {needle!r} missing in {topic_id}")
        return hits[0]

    e09 = next(x for x in experiments if x["id"] == "E09-wine-cat")
    e09["evidence"] = ev("T09",
                         ts_containing("T09", "不可完成的路径点"),
                         ts_containing("T09", "酒神的猫"),
                         ts_containing("T09", "每一帧都在瞬移"))

    # T04 杰西卡行已按官方 [MM:SS] 秒数写入 ev()

    # bidirectional: fill linked_mechanisms on experiments already set
    # fill reverse on mechanisms already set

    # write
    def dump(name, rows):
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p

    dump("evidence_packets.jsonl", packets)
    dump("mechanisms.jsonl", mechanisms)
    dump("experiments.jsonl", experiments)
    dump("rejected.jsonl", rejected)

    n_mech = sum(1 for m in mechanisms if m.get("record_type") == "mechanism")
    n_der = sum(1 for m in mechanisms if m.get("record_type") == "derivation")
    manifest = {
        "round": "evidence_round1",
        "api_calls": 0,
        "not_game_truth": True,
        "topics": 12,
        "buckets": {"recoverable": 6, "experiment_risk": 3, "reject_negative": 3},
        "packets": len(packets),
        "packet_lines": sum(p["line_count"] for p in packets),
        "mechanisms": n_mech,
        "derivations": n_der,
        "experiments": len(experiments),
        "rejected": len(rejected),
        "eligibility": {
            "accepted_mechanisms": sum(1 for m in mechanisms if m.get("record_type")=="mechanism" and m.get("eligibility")=="accepted"),
            "accepted_derivations": sum(1 for m in mechanisms if m.get("record_type")=="derivation" and m.get("eligibility")=="accepted"),
            "context_only": sum(1 for m in mechanisms if m.get("eligibility")=="context_only") + sum(1 for e in experiments if e.get("eligibility")=="context_only"),
            "needs_av": sum(1 for m in mechanisms if m.get("eligibility")=="needs_av") + sum(1 for e in experiments if e.get("eligibility")=="needs_av"),
            "rag_gate_true": sum(1 for m in mechanisms if m.get("rag_gate")),
        },
        "files": [
            "evidence_packets.jsonl", "mechanisms.jsonl", "experiments.jsonl",
            "rejected.jsonl", "review.md", "validate_evidence_round1.py",
            "build_evidence_round1.py",
        ],
        "step3_qq": "pending",
        "step4_eval20": "pending",
        "new_vs_prior_accepted": [
            "索敌之后才播攻击动画",
            "冷却制 vs 动画制：算出的间隔与动画上限比较后走冷却或动画",
            "冷却制/动画制索敌事件顺序",
            "阻挡三循环 vs 索敌进程结束立刻触发",
            "避障仅寻路状态机",
            "两套索敌冷却（技能类）及技能需双冷却清零（激光头另条 context_only）",
            "桃金娘讲段内主播自己说的 39 挂 buff + 30 帧（推导，非普遍光环时钟）",
            "诱导不可完成路径点 / 酒神猫每帧瞬移",
            "光环碰撞帧可直接挂 buff 则不走时针循环",
        ],
    }
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: manifest[k] for k in
                      ["packets", "packet_lines", "mechanisms", "derivations",
                       "experiments", "rejected"]}, ensure_ascii=False))


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
