# -*- coding: utf-8 -*-
"""人工抽审整理：只写 kb_pilot_synth/accepted|rejected.jsonl，不调 API、不写生产 kb。"""
import glob
import json
import os
import re

OUT = os.path.dirname(os.path.abspath(__file__))


def load_atoms():
    atoms = {}
    for fp in glob.glob("knowledge_pilot/*.atoms.enriched.jsonl"):
        for line in open(fp, encoding="utf-8"):
            a = json.loads(line)
            atoms[a["atom_id"]] = a
    return atoms


def media_path(stem):
    for p in (f"transcripts_txt/{stem}.txt",
              f"asr_drafts/{stem}_asr.txt",
              f"asr_drafts/{stem}_asr_draft.txt"):
        if os.path.exists(p):
            return p
    return None


def ev_from_atom(atoms, aid):
    a = atoms.get(aid) or {}
    stem = a.get("source_id") or aid.split(":")[0]
    path = media_path(stem)
    out = []
    for ev in a.get("evidence") or []:
        out.append({
            "kind": "atom_quote",
            "atom_id": aid,
            "file": path,
            "t": ev.get("start"),
            "quote": ev.get("quote"),
        })
    if not out:
        out.append({"kind": "atom_quote", "atom_id": aid, "file": path, "t": None, "quote": None})
    return out


def sub_ev(stem, t, quote):
    return {"kind": "subtitle", "file": media_path(stem), "t": t, "quote": quote, "ctx_id": f"sub:{stem}:{t}"}


def rule(text, subject, when, scope, evidence, variables=None):
    rec = {
        "text": text,
        "subject": subject,
        "when": when,
        "scope": scope,
        "variables": variables or {},
        "evidence": evidence,
    }
    return rec


def main():
    atoms = load_atoms()
    A = lambda *ids: sum((ev_from_atom(atoms, i) for i in ids), [])

    accepted = []
    rejected = []

    def acc(**kw):
        accepted.append(kw)

    def rej(**kw):
        rejected.append(kw)

    # ----- rejects (user-mandated / unusable) -----
    rej(cluster_id="帧时序与计时器-3-10", delivery="rejected",
        reason="整体暂不作为机制交付。空费帧桃金娘出伤是单场观测；光环99/29由69反推，未闭合。禁止用邻近字幕自行补成「39挂buff+30帧冷却」等价式。未知光环周期不得当已知机制。",
        dropped=["六十一到七十出伤", "六十九实测", "光环检测周期九十九和二十九", "同帧下红十九出伤"])
    rej(cluster_id="其他-6-1", delivery="rejected",
        reason="「它现在变成了零到五十九」无主语、无单位，绝不可收。同位置2n+1未定义n与「同位置」指什么。再过两帧动 vs 每一帧一个人动未分清对象。五秒起点主播自己在问。整卡暂拒。",
        dropped=["第一辆车开局五秒", "零到五十九", "二n加一", "再过两帧动", "每一帧一个人动"])
    rej(cluster_id="寻路-36-6", delivery="rejected",
        reason="1.95/0.4/2.75/149是具体演算例题，0.4的对象与单位未在可独立引用的变量表里闭合。取整原则也绑在该例上。按授权：数值例题变量不完整则拒数值；无足够独立通则则整卡拒。",
        dropped=["1.95格", "0.4×30", "2.75亏损", "149→150", "整数向上/非整数向下"])
    rej(cluster_id="技能特例-16-7", delivery="rejected",
        reason="主语未点名；3N加二未定义N；主播明确还有更完整索敌帧流程。绑定无操作定义。不能当RAG独立规则。",
        dropped=["出生帧按3N加二", "索敌帧和攻击间隔绑定"])
    rej(cluster_id="帧时序与计时器-20-2", delivery="rejected",
        reason="「隔几帧」间隔未给出；主语未点名；邻近是传送取消/不可通行，atoms丢掉场景后无法写成自包含规则。",
        dropped=["隔几帧不能往下", "出格帧不触发传送"])

    # ----- 22-7 appendix only -----
    acc(
        cluster_id="索敌-22-7", delivery="experiment_appendix",
        title="零帧部署一帧撤退时城防炮普攻/技能索敌帧（实验记录）",
        applies_to="城防炮（该次演示）",
        scope="instance", confidence="high",
        synth_version="v3",
        limitations=["不得写成城防炮索敌帧恒为1。翼德是测试干员，不是本规则主语。"],
        rules=[
            rule("零帧部署、一帧撤退时：最左边城防炮直接开一炮，该炮为普攻，主播据此称其索敌帧在一帧（原话「一针」）。",
                 "最左边城防炮", ["零帧部署", "一帧撤退"], "instance",
                 A("BV1jd3m68E6f_p1_40508197659:p18:a0:cb272236",
                   "BV1jd3m68E6f_p1_40508197659:p18:a1:4b4f46a5",
                   "BV1jd3m68E6f_p1_40508197659:p18:a2:626ffd7e"),
                 {"部署": "零帧", "撤退": "一帧", "索敌帧": "一帧（原话一针）"}),
            rule("同一条件下，中间两门城防炮在抬手打技能；主播称其技能索敌帧在一帧，而不是普攻索敌帧在一帧。",
                 "中间两个城防炮", ["零帧部署", "一帧撤退", "抬手打技能"], "instance",
                 A("BV1jd3m68E6f_p1_40508197659:p18:a3:179ac4a5",
                   "BV1jd3m68E6f_p1_40508197659:p18:a4:411f97dd")),
            rule("同一条件下，再下一门被推导为普攻索敌帧与技能索敌帧都不在一帧。",
                 "再下一个城防炮", ["零帧部署", "一帧撤退"], "instance",
                 A("BV1jd3m68E6f_p1_40508197659:p18:a5:454a1a66")),
        ],
        human_note="只作可追溯实验附录，不并入通用索敌机制卡。同讲还有「普攻/技能两套索敌冷却」「一帧一出怪错开」，未写入本附录以免与实验观测混成通则。",
    )

    # ----- keepers -----
    acc(
        cluster_id="帧时序与计时器-24-0", delivery="mechanism",
        title="动画制下攻击间隔被四舍五入、冷却服从动画",
        applies_to="走动画播放的攻击间隔（材料未限具体干员）",
        scope="universal", confidence="mid",
        synth_version="v3",
        limitations=["1.67只是问答举例，两边算出的具体值材料没给。ASR「卡动化」「抬售」按同段理解为卡动画/抬手。"],
        rules=[
            rule("动画播放长度本身按四舍五入确定，并因此使攻击间隔最终被四舍五入。",
                 "攻击间隔（经由动画长度）", ["存在按动画长度播放的攻击"], "universal",
                 A("BV199KH6TEra_p1_40136673556:p47:a3:144910dc") + [
                     sub_ev("BV199KH6TEra_p1_40136673556", 6686,
                            "你放完这个动画之后，四舍也就是四舍五入。是为什么四舍五入是因为因为动画的播放长度本身是四舍五入确定的")]),
            rule("动画播放结束时检测剩余冷却是否小于0.5；用四舍五入后的动画长度把冷却也四舍五入，使冷却服从于动画。",
                 "剩余冷却", ["动画播放结束", "剩余冷却小于0.5"], "universal",
                 [sub_ev("BV199KH6TEra_p1_40136673556", 6686,
                         "动画播放结束的时候，又会检测剩余冷却是不是小于0.5。如果实力刻抬手，这个就是用最开始四舍五入的动画，然后把冷却也进行四舍五入，让冷却服从于动画的方法。")],
                 {"冷却阈值": "0.5（材料未标明单位，同段讲冷却与动画）"}),
            rule("动画值与冷却值算出来不一致时，以动画值为准，不能按冷却值。",
                 "攻击间隔取值", ["动画值与冷却值结果不一致"], "universal",
                 [sub_ev("BV199KH6TEra_p1_40136673556", 6724,
                         "原来如此，那如果说我这边是1.67的话，他们两个算出来的就不一样……应该按动画值来。"),
                  sub_ev("BV199KH6TEra_p1_40136673556", 6739,
                         "就不能按冷却值来。对，因为现在被卡动化了。")]),
            rule("冷却归零时若仍在动画播放流程中，不能立刻抬手。",
                 "抬手", ["冷却已归零", "动画播放尚未结束"], "universal",
                 [sub_ev("BV199KH6TEra_p1_40136673556", 6745,
                         "冷却归零的时候没有办法立刻抬售，因为还在动画播放流程之中")]),
        ],
        human_note="atoms只有末句；规则2–4来自同一段邻近字幕补证，不是另开课题。未写入任何攻速公式。",
    )

    acc(
        cluster_id="位移-1-5", delivery="mechanism",
        title="方舟移动的四种逻辑",
        applies_to="移动单位（材料按「方舟」总述）",
        scope="universal", confidence="high",
        synth_version="v3",
        limitations=["「鼠的传送在哪个阶段」是主播当场提问，不是结论。"],
        rules=[
            rule("方舟移动分为四种逻辑：寻路、阻挡偏移、失衡、传送。",
                 "方舟移动", [], "universal",
                 A("BV14gby6LEni_p3_40944668620:p13:a0:63283e81")),
            rule("失衡：在失衡状态机下基于物理速度移动。",
                 "失衡", ["处于失衡状态机"], "universal",
                 A("BV14gby6LEni_p3_40944668620:p13:a1:aec68264")),
            rule("寻路：在寻路状态机下基于移速移动。",
                 "寻路", ["处于寻路状态机"], "universal",
                 A("BV14gby6LEni_p3_40944668620:p13:a2:3f985910")),
            rule("阻挡偏移：在阻挡偏移的规定之下瞄准落点移动。",
                 "阻挡偏移", ["处于阻挡偏移规定之下"], "universal",
                 A("BV14gby6LEni_p3_40944668620:p13:a3:d352fde3")),
            rule("传送：直接传送到指定位置。",
                 "传送", [], "universal",
                 A("BV14gby6LEni_p3_40944668620:p13:a4:67f69e5d")),
            rule("瞬移：直接改写坐标。主播把它与上述四种并列说明（「大概是这四种」后补这一句）。",
                 "瞬移", [], "universal",
                 A("BV14gby6LEni_p3_40944668620:p13:a5:dea37a73")),
        ],
        human_note="官方字幕 t=1341–1379。四种+瞬移均有原话。",
    )

    acc(
        cluster_id="伤害结算-0-9", delivery="mechanism",
        title="抗性结算与伤判是两个环节",
        applies_to="伤害结算（物理/法术攻击）",
        scope="universal", confidence="high",
        synth_version="v3",
        limitations=[],
        rules=[
            rule("吃不吃抗与吃不吃增伤是两个环节。",
                 "伤害结算", [], "universal",
                 A("BV14gby6LEni_p2_40943751084:p40:a0:e1afe5f0")),
            rule("物理和法术攻击根据抗性计算伤害；属性和属性（如攻击与防御）确定伤害的这一步是抗性结算环节。",
                 "抗性结算环节", ["物理或法术攻击"], "universal",
                 A("BV14gby6LEni_p2_40943751084:p40:a1:234d333f",
                   "BV14gby6LEni_p2_40943751084:p40:a4:8de60d70")),
            rule("伤判用来计算增伤和减伤，让伤害变大或变小；伤害倍率就是伤判。抗性结算之后，伤判改写伤害。伤判与抗性不是同一环节。",
                 "伤判环节", ["抗性结算已完成"], "universal",
                 A("BV14gby6LEni_p2_40943751084:p40:a2:3ed9602f",
                   "BV14gby6LEni_p2_40943751084:p40:a5:4bb3fa44",
                   "BV14gby6LEni_p2_40943751084:p40:a6:c03f3391",
                   "BV14gby6LEni_p2_40943751084:p42:a1:dc228eda")),
            rule("面板加成通过四则运算确定属性。",
                 "面板加成", [], "universal",
                 A("BV14gby6LEni_p2_40943751084:p40:a3:14bcd667")),
        ],
        human_note="官方/atoms 原话 t=4841–5018。合并同义后四条，均可单独引用。",
    )

    acc(
        cluster_id="索敌-0-1", delivery="mechanism",
        title="弹道没有角色/敌人那种三帧索敌",
        applies_to="弹道",
        scope="universal", confidence="high",
        synth_version="v1",
        limitations=["周期性检测的周期数值未给。不要把「三帧索敌」写成一切单位的唯一索敌模型。"],
        rules=[
            rule("弹道没有角色类或敌人类单位所应有的三帧索敌。",
                 "弹道", [], "universal",
                 A("BV14gby6LEni_p1_40940472044:p37:a5:a9b994df")),
            rule("弹道靠周期性检测实现索敌流程。",
                 "弹道", [], "universal",
                 A("BV14gby6LEni_p1_40940472044:p37:a6:694141ae")),
        ],
        human_note="云端ASR t=4391。三帧是主播对比用语，不是待听原音。",
    )

    acc(
        cluster_id="帧时序与计时器-46-2", delivery="mechanism",
        title="攻击动画/攻击持续不能短于原初设定的0.1倍",
        applies_to="干员攻击动画或攻击持续",
        scope="universal", confidence="high",
        synth_version="v1",
        limitations=["邻近举例底火杰西卡能压到两帧，是「目前唯一满足该下限」的例子，不是本规则主语。"],
        rules=[
            rule("攻击持续或攻击动画不能短于自身原初设定动画长度的0.1倍。",
                 "攻击持续或攻击动画", ["动画被缩短/加速时"], "universal",
                 A("BV1jd3m68E6f_p1_40508197659:p11:a6:78184449"),
                 {"下限": "原初设定动画长度的0.1倍"}),
        ],
        human_note="官方字幕 t=1392。主播先说「方舟的干员还有一个别的限制」再给0.1倍。",
    )

    acc(
        cluster_id="索敌-20-10", delivery="mechanism",
        title="敌人索敌帧因敌人而异、从出生开始转",
        applies_to="敌人索敌帧",
        scope="universal", confidence="high",
        synth_version="v1",
        limitations=["邻近「258只特指这个术士」，不得把某一敌人的索敌帧数列写成通则。"],
        rules=[
            rule("索敌帧因敌人而异。",
                 "敌人索敌帧", [], "universal",
                 A("BV1jd3m68E6f_p1_40508197659:p4:a3:b8d1208d")),
            rule("索敌帧从敌人出生开始转。",
                 "敌人索敌帧", [], "universal",
                 A("BV1jd3m68E6f_p1_40508197659:p4:a4:178b3067")),
        ],
        human_note="官方字幕 t=689。两条均可单独引用。",
    )

    acc(
        cluster_id="帧时序与计时器-65-4", delivery="mechanism",
        title="酒神三技能：无动画、前后保底六帧、减攻速拉间隔不拉前摇",
        applies_to="酒神三技能",
        scope="universal", confidence="high",
        synth_version="v2",
        limitations=["开技能后「两针索敌、七针命中」是当场演示；主播称减攻速时时机一样。原话用针=帧。"],
        rules=[
            rule("酒神三技能是无动画机制，前后保底为六帧（原话「六针」）。",
                 "酒神三技能", [], "universal",
                 A("BV1qReG6XE6W_p3_41897689954:p41:a0:8a4dc442",
                   "BV1qReG6XE6W_p3_41897689954:p41:a1:5938ef6f"),
                 {"前后保底": "六帧"}),
            rule("减攻速会大幅延长酒神三技能的攻击间隔，但不会影响其前摇。",
                 "酒神三技能", ["受到减攻速"], "universal",
                 A("BV1qReG6XE6W_p3_41897689954:p41:a2:0cb15490",
                   "BV1qReG6XE6W_p3_41897689954:p41:a3:6a2519ac")),
            rule("开技能之后两帧索敌、七帧命中；减攻速与不减攻速时该索敌/命中时机一样。",
                 "酒神三技能", ["开技能之后"], "instance",
                 A("BV1qReG6XE6W_p3_41897689954:p41:a4:2db71169",
                   "BV1qReG6XE6W_p3_41897689954:p41:a5:78a2de08"),
                 {"索敌": "两帧", "命中": "七帧"}),
        ],
        human_note="官方字幕 t=6092–6153。第三条标 instance，因是开技能演示轴。",
    )

    acc(
        cluster_id="寻路-7-8", delivery="mechanism",
        title="一帧可达半径与0.05路径点完成半径",
        applies_to="寻路单位（材料按「自己」）",
        scope="universal", confidence="high",
        synth_version="v2",
        limitations=["酒神的猫作为不可完成路径点、会反复一帧可达，是邻近字幕特例，未写入通则。0.05对应移速属性为三时的一帧可达半径。"],
        rules=[
            rule("若路径点落在自身实坐标的一帧可达半径内，则直接瞬移到该路径点。一帧可达半径由「一帧×帧时间×移速」可移动距离画圆得到。",
                 "寻路单位", ["路径点在一帧可达半径内"], "universal",
                 A("BV14y8269EbS_p1_41164079923:p75:a0:62daaf9d",
                   "BV14y8269EbS_p1_41164079923:p75:a1:94c723a9",
                   "BV14y8269EbS_p1_41164079923:p75:a2:eec63ee2")),
            rule("正常情况下，触发上述一帧可达需要移速属性大于三；这不是加速度。",
                 "一帧可达判定", ["正常情况", "移速属性大于三"], "universal",
                 A("BV14y8269EbS_p1_41164079923:p75:a3:9f975f28",
                   "BV14y8269EbS_p1_41164079923:p75:a4:5767345f"),
                 {"移速属性阈值": "大于三"}),
            rule("移速属性为三时，一帧可达半径按1/10即3/30计为0.05；此处0.05已是一帧可达半径，不必再乘0.5（0.5是理论速度系数）。",
                 "一帧可达半径", ["移速属性为三"], "universal",
                 A("BV14y8269EbS_p1_41164079923:p76:a0:da8985bd",
                   "BV14y8269EbS_p1_41164079923:p76:a1:3d9dce8f"),
                 {"一帧可达半径(移速3)": "0.05"}),
            rule("正常情况下踩到0.05之内即完成路径点，完成后该点不再是路径点，因而不会再做一帧可达判定。",
                 "路径点完成", ["正常情况"], "universal",
                 A("BV14y8269EbS_p1_41164079923:p77:a0:7c61a686",
                   "BV14y8269EbS_p1_41164079923:p77:a1:ed00937b",
                   "BV14y8269EbS_p1_41164079923:p77:a2:f33186d6"),
                 {"路径点完成半径": "0.05"}),
        ],
        human_note="官方字幕 t=6477–6604。",
    )

    acc(
        cluster_id="帧时序与计时器-43-1", delivery="mechanism",
        title="动画下限取整为向上取整",
        applies_to="动画下限（材料未限具体干员）",
        scope="universal", confidence="high",
        synth_version="v2",
        limitations=["答疑ASR较乱；2.1→3是下限向上的例子。邻近提到祥子事件帧，未当主语。"],
        rules=[
            rule("动画下限的取整方式为向上取整。例如值为2.1时接上限，结果为3。",
                 "动画下限", [], "universal",
                 A("BV1j4KC6KEse_p1_40109737103:p61:a0:02591650",
                   "BV1j4KC6KEse_p1_40109737103:p61:a1:e90f0b2e"),
                 {"例": "2.1→3"}),
        ],
        human_note="ASR t=7601：「下限，所以是向上」「二点一也是三」。",
    )

    acc(
        cluster_id="技能特例-3-6", delivery="mechanism",
        title="酒神开技能：已爆条目标生成牢笼并等价围普攻溅射",
        applies_to="酒神",
        scope="universal", confidence="high",
        synth_version="v2",
        limitations=["1.3半径、0.23损攻击的单位材料写成「半径/损攻击」，未改写成格或百分比。"],
        rules=[
            rule("酒神开技能会给范围内所有已爆条的怪生成牢笼，该行为相当于一次围普攻。",
                 "酒神", ["开技能", "目标在范围内且已爆条"], "universal",
                 A("BV14VZCB1EJR_p1_36119907781:p15:a1:a98f6870")),
            rule("该次围普攻对该敌人周围1.3半径内的所有其他敌人生成一次0.23的损攻击。",
                 "酒神围普攻溅射", ["上述牢笼/围普攻已触发"], "universal",
                 A("BV14VZCB1EJR_p1_36119907781:p15:a2:b598cda5"),
                 {"溅射半径": "1.3（原话「1.3半径」）", "损攻击": "0.23"}),
        ],
        human_note="atoms t=1986–1997。",
    )

    acc(
        cluster_id="帧时序与计时器-14-5", delivery="mechanism",
        title="无目标时以整个攻击间隔为前摇并加一帧保底后摇",
        applies_to="无目标时的弹道播放（主播举小羊、塞雷娅的奶、白面脑啡肽为同一现象）",
        scope="universal", confidence="high",
        synth_version="v2",
        limitations=["小羊16帧、塞雷娅奶31帧是被拿来解释该现象的间隔数字，不是本机制算出来的公式。ASR「前腰/一身」按一帧保底后摇理解。"],
        rules=[
            rule("无目标时，以整个攻击间隔为前摇，并加上一帧保底后摇。这是与动画无关的一种弹道播放。",
                 "无目标攻击流程", ["无目标"], "universal",
                 A("BV14VZCB1EJR_p1_36119907781:p135:a0:5f9d089a",
                   "BV14VZCB1EJR_p1_36119907781:p135:a2:1c7d532b"),
                 {"保底后摇": "一帧"}),
            rule("主播将小羊、塞雷娅的奶、白面脑啡肽列为该无目标整间隔前摇现象的共通例子。",
                 "小羊 / 塞雷娅的奶 / 白面脑啡肽", ["无目标"], "example",
                 A("BV14VZCB1EJR_p1_36119907781:p135:a1:44a86ac2")),
        ],
        human_note="未收入旧合成里的空A连A假象、动画拉伸+1、Boss时间换算。",
    )

    acc(
        cluster_id="状态效果-3-7", delivery="mechanism",
        title="移速Buff只改移速属性，实际移速由速度/目标速度/加速度推出",
        applies_to="移速Buff与移速属性（材料按单位总述）",
        scope="universal", confidence="high",
        synth_version="v2",
        limitations=["0.5→0.1是停顿命中的例子，不是所有停顿的固定数值。"],
        rules=[
            rule("移速Buff对移速属性做直接加、直接乘、最终加、最终乘；其唯一能力是改写移速属性，不直接规定实际移速向量多长。",
                 "移速Buff", [], "universal",
                 A("BV14y8269EbS_p1_41164079923:p62:a0:efdbfb25",
                   "BV14y8269EbS_p1_41164079923:p62:a3:471d4c93")),
            rule("移速属性影响理论移速上限；实际移速由实际速度、目标速度、加速度、倍率加速度等推出；目标速度来自寻路光标方向和自己的理论速度；实际移速对目标速度与理论速度（属性速度）取模长上限，这两处用到移速属性。",
                 "实际移速", [], "universal",
                 A("BV14y8269EbS_p1_41164079923:p62:a1:8010f824",
                   "BV14y8269EbS_p1_41164079923:p62:a4:fce404b1",
                   "BV14y8269EbS_p1_41164079923:p62:a5:44e2d9ca",
                   "BV14y8269EbS_p1_41164079923:p62:a6:b4174556")),
            rule("停顿命中时把移速属性切换为新值并按新属性应用。例子：0.5经停顿变成0.1。",
                 "停顿命中", ["停顿命中"], "example",
                 A("BV14y8269EbS_p1_41164079923:p62:a2:362d3ba5"),
                 {"例_停顿前": "0.5", "例_停顿后": "0.1"}),
            rule("属性骤减在目标速度与模长上限两处应用，逐帧影响实际速度，不是瞬间改掉实际速度；属性被改写后下一次移动会因上限立刻被降下来。加速过程没有属性下限，不会突然降到零。",
                 "移速属性变化", ["属性骤减或移速属性被改写", "或处于加速过程"], "universal",
                 A("BV14y8269EbS_p1_41164079923:p62:a7:8401636d",
                   "BV14y8269EbS_p1_41164079923:p62:a8:0fa42a1c",
                   "BV14y8269EbS_p1_41164079923:p62:a9:31cbdca9")),
        ],
        human_note="官方字幕 t=5554–5684 一带。",
    )

    acc(
        cluster_id="寻路-14-14", delivery="mechanism",
        title="避障力：远离周围八格障碍/不可通行，判定中心在足坐标/骨架",
        applies_to="敌人（贴图/避障）",
        scope="universal", confidence="mid",
        synth_version="v2",
        limitations=["0.4/0.9/0.5/0.2 原话未写单位，讲座语境为格，不得当成已标定SI单位。上边缘0.05、左右下0.45是在下偏0.2且判定区0.9×0.5时的推导。"],
        rules=[
            rule("自身处于某地块且离周围八格的障碍物类或不可通行类地块太近时，避障力使其远离这些地块。最直观功能是让敌人贴图动画远离坑和高台。原则上偏美术效果，不是给计算复杂度用的。",
                 "避障力", ["处于某地块", "周围八格有障碍或不可通行且太近"], "universal",
                 A("BV1CZ8t6wEyr_p1_41192326752:p6:a0:99cab4ea",
                   "BV1CZ8t6wEyr_p1_41192326752:p6:a1:4a240747",
                   "BV1CZ8t6wEyr_p1_41192326752:p6:a2:a30ccb31")),
            rule("避障力判定中心由骨架动画决定。以敌人足坐标为中心；足坐标是绑在敌人span骨架上的点。很多敌人没有足坐标，则直接取骨架动画坐标。",
                 "避障判定中心", [], "universal",
                 A("BV1CZ8t6wEyr_p1_41192326752:p6:a3:b4a72e68",
                   "BV1CZ8t6wEyr_p1_41192326752:p6:a5:9e22ca40",
                   "BV1CZ8t6wEyr_p1_41192326752:p6:a6:17911bfa")),
            rule("以足坐标为中心画左右方向长0.4的线段。避障判定区是足坐标周围横宽0.9、纵宽0.5的长方形（原话未写单位）。一般足坐标下偏0.2。",
                 "避障判定区", [], "universal",
                 A("BV1CZ8t6wEyr_p1_41192326752:p6:a4:054a91eb",
                   "BV1CZ8t6wEyr_p1_41192326752:p14:a2:bce45280",
                   "BV1CZ8t6wEyr_p1_41192326752:p14:a1:d05136ff"),
                 {"线段长": "0.4（单位未写）", "横宽": "0.9（单位未写）", "纵宽": "0.5（单位未写）", "足坐标下偏": "0.2（原话格）"}),
        ],
        human_note="未把右偏0.0816（邻近另一图）写入。边缘0.05/0.45推导未单列，避免无单位数字当已知。",
    )

    acc(
        cluster_id="索敌-1-0", delivery="mechanism",
        title="阻挡帧由部署决定，在部署后3n+1帧",
        applies_to="阻挡帧（相对部署）",
        scope="universal", confidence="mid",
        synth_version="v3",
        limitations=["94帧「可以动但不一定动」是当场观测，不收入机制卡。避障拼接/冷却3或1来自邻近字幕，未全部核成独立变量表，故不写入。"],
        rules=[
            rule("阻挡帧由部署决定，与眩晕、开技能或解除不可阻挡发生在哪一帧无关。",
                 "阻挡帧", [], "universal",
                 A("BV14gby6LEni_p1_40940472044:p64:a2:fcece2a1")),
            rule("阻挡帧发生在部署之后的3n+1帧（原话「三n加一帧」）。",
                 "阻挡帧", ["以部署为计时零点"], "universal",
                 A("BV14gby6LEni_p1_40940472044:p64:a3:e6592184"),
                 {"相位": "3n+1（n未在该句展开为具体整数列）"}),
            rule("避障帧的表现比阻挡帧更特殊。",
                 "避障帧", [], "universal",
                 A("BV14gby6LEni_p1_40940472044:p64:a4:a438470e")),
        ],
        human_note="拒收合成里的94帧通则和example词条分类。3n+1保留但n的取值序列未在本卡展开。",
    )

    acc(
        cluster_id="位移-3-5", delivery="mechanism",
        title="合成速度超过移速上限时缩模",
        applies_to="受移速上限约束的移动（该讲以酒神为例）",
        scope="universal", confidence="mid",
        synth_version="v2",
        limitations=["0.2是该课题当时的理论匀速/上限例子，不是全图移速上限。0.8比11是集海默有停顿时的挤入角，不收入通则。无停顿三条是hypothesis，已拒。"],
        rules=[
            rule("合成速度超过理论移速上限时，不可能以该合成速度移动，需要除以模长再乘以上限（缩模）。",
                 "移动速度向量", ["合成速度超过理论移速上限max"], "universal",
                 A("BV14y8269EbS_p2_41167359561:p1:a2:9c155d60")),
        ],
        human_note="只收缩模通则。集海默0.8比11/四比上55与0.2数值例题整段不进入accepted规则。",
    )

    # leftover rejects
    rej(cluster_id="位移-3-5#numbers", delivery="rejected",
        reason="集海默有停顿挤入角0.8比11、理论匀速0.2、11/15分量演算未闭合为可独立变量表；无停顿为hypothesis。仅保留缩模通则于accepted。",
        dropped=["0.2V", "0.8比11", "四比上55", "无停顿四比11"])

    # write
    ap = os.path.join(OUT, "accepted.jsonl")
    rp = os.path.join(OUT, "rejected.jsonl")
    with open(ap, "w", encoding="utf-8") as f:
        for rec in accepted:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(rp, "w", encoding="utf-8") as f:
        for rec in rejected:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_rules = sum(len(x.get("rules") or []) for x in accepted)
    mech = sum(1 for x in accepted if x.get("delivery") == "mechanism")
    appn = sum(1 for x in accepted if x.get("delivery") == "experiment_appendix")
    print(json.dumps({
        "accepted_cards": len(accepted),
        "mechanism_cards": mech,
        "appendix_cards": appn,
        "accepted_rules": n_rules,
        "rejected_items": len(rejected),
        "accepted_path": ap,
        "rejected_path": rp,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
