# -*- coding: utf-8 -*-
"""收尾：审完 28 未审、抽查实验/拒收、重写 pending/rejected。无 API。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def jl(name):
    return [json.loads(l) for l in open(os.path.join(HERE, name), encoding="utf-8") if l.strip()]


def dump(name, rows):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    pas = {p["topic_id"]: p for p in jl("passages.jsonl")}

    def ev(tid, t, text):
        p = pas[tid]
        return {"file": p["file"], "layer": p["layer"], "t": t, "text": text}

    def mech(**kw):
        kw.setdefault("record_type", "mechanism")
        kw.setdefault("eligibility", "accepted")
        kw.setdefault("rag_gate", kw["eligibility"] == "accepted" and kw["record_type"] == "mechanism" and (kw.get("evidence") or [{}])[0].get("layer") == "official_txt")
        if (kw.get("evidence") or [{}])[0].get("layer") == "asr_draft":
            kw["rag_gate"] = False
        kw["cluster_id"] = pas[kw["topic_id"]]["cluster_id"]
        return kw

    extra_m = [
        mech(id="B003-grid-before-teleport", topic_id="B003",
             text="格判类型能力以格子为单位判定。同帧做位移/传送和格判更新，传送时要判定格判。刚进入格子那一帧无法传送，刚离开那一帧可以传送（格判尚未更新仍属原格），口播称这导致居民据点可以入坑。",
             subject="格判类型能力 / 传送带", when=["传送判定发生在格判更新之前"],
             evidence=[ev("B003", 2912, "进入这个格子之后，下一帧就会传送。"), ev("B003", 2956, "更新格判之前就是传送的判定时间点。")]),
        mech(id="B007-pitkill-once-on-enter", topic_id="B007",
             text="坑杀在进入坑格子时判定一次。进入瞬间若是飞行单位则免杀，后续落在坑上不重复判定。有刷新判定（口播近地悬浮落下）则可再判。主播称现已改，本段未给出改后完整表。",
             subject="坑杀", when=["进入坑格子时判定一次"],
             evidence=[ev("B007", 2206, "坑杀 是在进格子的时候判定一次的 坑杀是在进格子的时候判定一次的"), ev("B007", 2223, "所以的话在这一瞬间他是飞行单位 他就免了这个坑杀 然后的话即使后续落在这个坑上 他也不会重复判定")]),
        mech(id="B011-anim-cap-fallback-cd", topic_id="B011",
             text="动画长度有上下限；理论长度超过上限也只能走上限。播完若不能抬手则走冷却制。冷却制：冷却彻底归零之后下一针才能抬手。本段出现的 0.5/197.36 不入库为阈值。",
             subject="动画制 / 冷却制攻击间隔", when=["动画播完不能抬手则走冷却制"],
             evidence=[ev("B011", 9858, "但是动画它有一个限制 就是动画程度的上下限以及被打断等情况"), ev("B011", 9899, "冷却制就会认为冷彻底归零之后 下一针才能抬手")]),
        mech(id="B022-target-speed-in-path", topic_id="B022",
             text="寻路状态机里的目标速度：从自身寻路坐标指向拐角格中心，模长为理论移速。怪倾向于按该速度走，但不会直接变成该速度。停住、寻路断绝也在寻路状态机中，不走是因为目标速度为零。速度由目标速度、实际速度、加速度逐帧生成。",
             subject="寻路状态机中的目标速度", when=["寻路状态机"],
             evidence=[ev("B022", 3937, "从自身的寻路坐标 指向这个拐角格中心的这样一个 然后模长为自身的理论移速的"), ev("B022", 3979, "停住寻路断绝之类的状态 也在寻路状态机之中 但是他们不走了 是因为目标速度是零")]),
        mech(id="B028-tile-bfs-order", topic_id="B028",
             text="寻路地图按上右下左顺序推地块；每格记录来源方向；排完可通行地块后形成寻路地图。",
             subject="寻路地图遍历", when=[],
             evidence=[ev("B028", 264, "首先是这一步上右下左的顺序进行寻路"), ev("B028", 385, "每一个地块 像这个地块都会记录他是从哪个格子来的")]),
        mech(id="B029-obtuse-no-025", topic_id="B029",
             text="拐角大于 135 度的钝角寻路时，不会判定 0.25 拐角配置，从而贴墙。条件是从左上格往下走会路过该格。本段为 ASR。",
             subject="钝角寻路 / 0.25 拐角配置", when=["拐角大于135度"], eligibility="needs_av",
             evidence=[ev("B029", 1121, "路过这个格子就是代表着它这里的拐角是大于135度的。")]),
        mech(id="B032-stand-two-parts", topic_id="B032",
             text="罚站分成两部分：走到某个路径点的指令（与平常拐角格路径点相同），以及停住指令。停住只管时间，路径点只管去哪里。",
             subject="罚站", when=[],
             evidence=[ev("B032", 1485, "罚站严格算分为呃严严格来讲分为两个部分 一个是走到某个路径点的指令 它和平常的拐角格那种路径点没有任何不同 另一个是停住指令"), ev("B032", 1510, "停住的指令只管时间路径点的指令 只管去哪里 这两个是分开的")]),
        mech(id="B034-slow-move-two-forces", topic_id="B034",
             text="不可通行地块或罚站时的缓慢移动：避障力提供加速度；寻路断绝时目标速度为零，产生反向于实际移速的八倍加速度。二力平衡则匀速缓慢。走出不可通行地块是改写寻路光标获得目标速度，不是重新获得行动指令权限。避障力在不可通行地块指向周围八格最近可通行地块。",
             subject="不可通行地块 / 罚站时的缓慢移动", when=["寻路断绝或不可通行地块或罚站"],
             evidence=[ev("B034", 2731, "缓慢移动的本质是因为避障力提供的加速度 让他拥有了速度 但是在寻路断绝的情况下 他的目标速度是零"), ev("B034", 2748, "二力平衡的时候 达成一个缓慢运动的匀速移动状态 这是在不可通行地块或者是在罚站时"), ev("B034", 2773, "一旦走出不可通行地块 不是重新获得行动指令的权限 而是在可通行地块 他改写了当前的寻路光标")]),
        mech(id="B036-path-not-wallhack", topic_id="B036",
             text="卡墙只决定何时不发生传送，敌人怎么走由寻路机制决定；任何点位都按寻路向自己的路径点走。传送是改写坐标。抗性吃哪一种本段声明待研究，不入库。路径点完成半径数值不入库。",
             subject="寻路单位 / 传送", when=[],
             evidence=[ev("B036", 6010, "卡墙只是决定什么时候不发生这个传送现象 但是敌人会怎么走的话 一开始就是由敌人的寻路机制决定的"), ev("B036", 6024, "敌人在任何点位都是按照寻路规则向着自己的那个路径点在走"), ev("B036", 6139, "就是实际上传送这些机制的话 从一开始就没有什么特殊的 是一个单纯的改写坐标而已")]),
        mech(id="B043-logic-predelay-plus-one", topic_id="B043",
             text="若前摇由逻辑帧控制，则动画制索敌比冷却制索敌晚一帧。",
             subject="动画制索敌 / 冷却制索敌", when=["逻辑帧控制的前摇"],
             evidence=[ev("B043", 3492, "如果是 呃逻辑帧控制的前摇的话 那么动画质索敌就应该比冷却制索敌晚一帧")]),
        mech(id="B045-unoc-heal-lock", topic_id="B045",
             text="元末奶盾在技能释放期间若因奶满丢失索敌目标，会持续处于技能索敌、找谁能奶一口，无法平A，直到把这一口奶出去。",
             subject="元末奶盾", when=["技能释放期间丢失索敌目标（奶满不符合奶的条件）"],
             evidence=[ev("B045", 1916, "元末奶盾卡平A 就是他在技能释放期间突然丢失了索敌目标 丢失的理由是奶满了 不符合他奶的条件"), ev("B045", 1961, "他持续处在技能索敌的这个状态 他一直在找谁可以用我的技能奶一口")]),
        mech(id="B047-ranged-seek-patrol-only", topic_id="B047",
             text="只有在巡逻状态机下才可以进行远程索敌中的三帧索敌判定。兼具近战和远程的敌人在阻挡状态下不进行远程索敌；解阻挡之后会立刻抬手。",
             subject="兼具近战和远程的敌人", when=["远程三帧索敌仅巡逻状态机；阻挡状态下不远程索敌"],
             evidence=[ev("B047", 1497, "就是只有在巡逻状态机下才可以进行远程锁敌"), ev("B047", 1510, "比如说拥有近战和远程攻击能力的那些怪 他在阻挡状态下 其实是不进行远程锁敌的")]),
        mech(id="B053-highland-unbinds-block", topic_id="B053",
             text="高地设置会绑掉位于上面的干员的阻挡能力。口播阻挡半径 0.7071。围墙内部也不可阻挡。起飞能阻挡是无视高台的特殊设置。",
             subject="高台干员阻挡", when=["高地设置"],
             evidence=[ev("B053", 1921, "高地设置会办掉位于上面的干员的阻挡能力"), ev("B053", 1976, "实际上还有地面的类似高台的这种东西叫围墙 围墙里面也是不可阻挡")]),
        mech(id="B062-interval-multiple-floors", topic_id="B062",
             text="最短攻击时间可被多种下限卡住：连击间隔保底（口播至少一帧，例寒芒/能天使）、三帧索敌（例重装杰西卡理论两针但索敌不允许）、动画长度、攻速上限。各自限制不同，不是单一通则数字。",
             subject="干员最短攻击时间", when=[],
             evidence=[ev("B062", 10331, "有的人可能触发的是连击间隔的保底 从而拉长自己的攻击间隔"), ev("B062", 10364, "他理论上动画程度允许他到那个两针 但是他的三针索敌不允许他刀两针 就导致他只能三针一攻击")]),
        mech(id="B063-block-vs-teleport", topic_id="B063",
             text="阻挡偏移期间被传送会直接回来。鼠的传送一针只能一次。珊比直接不拉阻挡；鱼直接打断敌人与干员之间的阻挡状态。",
             subject="阻挡偏移 / 鼠·珊比·鱼", when=["阻挡偏移期间被传送"],
             evidence=[ev("B063", 1653, "阻挡偏移期间被传送就会直接回来"), ev("B063", 1675, "珊比是直接不拉阻挡 然后鱼的话就是直接打断阻挡")]),
        mech(id="B066-ammo-aspd-example", topic_id="B066",
             text="该次弹药类技能/藏品：开启技能后 15 秒内加 100 攻速，口播每 2A 减 1.2。主语锁该藏品，不升格所有弹药。",
             subject="弹药类技能（该藏品）", when=["开启技能后15秒"], rag_gate=False,
             evidence=[ev("B066", 6206, "这是弹药类技能 开启技能后 15S内加100攻速")]),
        mech(id="B074-imbalance-speed-separate", topic_id="B074",
             text="失衡状态下的速度与寻路状态下的速度从根本上不是一个东西。失衡时不计算寻路速度；推拉修正失衡速度。退出失衡后把该速度清零，再按寻路状态计算。",
             subject="失衡速度 / 寻路速度", when=["切入或退出失衡状态"],
             evidence=[ev("B074", 14699, "就是失衡状态下的速度和寻路状态下的速度 从根本上不是一个东西"), ev("B074", 14731, "退出失衡之后 把这个速度清零 然后去改成寻路状态")]),
        mech(id="B075-immune-imbalance-not-squeeze", topic_id="B075",
             text="免疫失衡只抵抗推拉的力度；挤位移不是同一套体系。ASR。",
             subject="免疫失衡 / 挤位移", when=[], eligibility="accepted",
             evidence=[ev("B075", 831, "免疫失衡只是抵抗推拉的力度，及位移根本不是一套体系的，就是挤这个东西。")]),
        mech(id="B078-attr-affects-actual-speed-per-frame", topic_id="B078",
             text="实际移速由实际速度、目标速度、加速度等推出。目标速度来自寻路光标方向和理论速度。属性骤减会在这两处应用，逐帧影响实际速度，但实际速度不是瞬间被改掉。",
             subject="实际移速", when=["属性骤减"],
             evidence=[ev("B078", 5652, "实际移速是由是怎么定的 是由实际速度 目标速度 加速度 倍率加速度等等东西推出来的对吧"), ev("B078", 5684, "也就是会应用到属性 所以属性的骤减会在这两个地方应用 从而逐帧的影响实际速度 但是实际速度并不是瞬间去被改变的")]),
        mech(id="B081-275-as-series-sum", topic_id="B081",
             text="口播把刹车 2.75 解释为 11/15 等比无穷求和：11/15 ÷ (1-11/15)=2.75。这是计算约定，主播同时说太小就不再考虑。不作独立游戏阈值。",
             subject="刹车距离近似 2.75", when=[], record_type="derivation", rag_gate=False,
             evidence=[ev("B081", 2410, "11杠15比1-1.75 就是11-15就是2.75"), ev("B081", 2424, "这个你说的是这个11比15额11比15 然后的话比上这个1-11比15")]),
        mech(id="B089-wall-contact-rewrite", topic_id="B089",
             text="向墙推时最终停在相距 0.005 的位置；该区间能判定碰撞但不会再向外挤；越过更近才会强行挤出到 0.005。挤出是改写坐标，没有速度概念，不是弹簧。",
             subject="贴墙碰撞 / 挤出", when=["把敌人向墙的方向推"],
             evidence=[ev("B089", 500, "停在这里 相距0.005的位置"), ev("B089", 548, "挤出来是改写坐标 没有什么速度的概念哦")]),
        mech(id="B100-exit-imbalance-three", topic_id="B100",
             text="同时满足则立刻退出失衡：新速度小于等于 0.1、已经超过失衡保护时间、无有效拉力来源。有效拉力来源指拉力钩子还在勾着。口播保护时间调为 0.1 后该次表现为三针，不把三针写成与参数无关的永恒值。",
             subject="退出失衡", when=["三条件同时满足"],
             evidence=[ev("B100", 4783, "如果新速度小于等于0.1 且已经超过失衡保护时间"), ev("B100", 4801, "且无有效拉力来源 这三句话是什么意思 这是三个条件 如果全部满足 那么则会立刻退出失衡")]),
    ]

    extra_e = [
        {"id": "B050-cannon-land-32", "topic_id": "B050", "cluster_id": pas["B050"]["cluster_id"],
         "text": "该次：炮台落地隐在 32 针可被索敌，与干员同样；无论哪一针放下的炮台，第 32 针都可被索。零针装置 vs 两针能天使当场未锁到。ASR。",
         "subject": "炮台（该次落地隐）", "when": ["该次放置炮台"], "eligibility": "accepted", "rag_gate": False,
         "record_type": "experiment",
         "evidence": [ev("B050", 7339, "那炮台的落地引是在32针可以被索敌和干源是同样的。")]},
        {"id": "B086-anso-half-duration", "topic_id": "B086", "cluster_id": pas["B086"]["cluster_id"],
         "text": "该次暗索：二距离加力度后本可拉 0.5 入坑，但弹道持续时间少了一半所以不能。绑该路点。",
         "subject": "暗索拉（该次）", "when": ["该次弹道持续时间少一半"], "eligibility": "accepted", "rag_gate": False,
         "record_type": "experiment",
         "evidence": [ev("B086", 297, "然后的话这是三负一级 是可以拉0.5入坑的 但是他这里不能 他这里为什么不能 他这里不能的理由 就是因为他的弹道的持续时间少了一半")]},
    ]

    mechs = jl("mechanisms.jsonl")
    have = {m["id"] for m in mechs}
    for m in extra_m:
        if m["id"] not in have:
            mechs.append(m)
    dump("mechanisms.jsonl", mechs)

    exps = jl("experiments.jsonl")
    havee = {e["id"] for e in exps}
    for e in extra_e:
        if e["id"] not in havee:
            exps.append(e)
    dump("experiments.jsonl", exps)

    used = {m["topic_id"] for m in mechs} | {e["topic_id"] for e in exps}

    rej_reason = {
        "B001": "11/15 已收 B025；本窗是刹车演示+美珍例，不另立机制。",
        "B004": "合约容错方法论，不是机制命题。",
        "B005": "费用条前 10 秒当场数字；不与全库费用条条目互证对错。",
        "B006": "取整方向取决于计算目的，是计算约定不是引擎单一规则。",
        "B009": "明确说 2.75 不是严格量。无穷求和另见 B081 推导。",
        "B014": "竖式工作流，不是机制。",
        "B015": "艾拉/大盾合约轴当场秒数。",
        "B017": "暴调窗口精算，当场酒神周期。",
        "B018": "M3/重构体合约轴，不是独立机制。",
        "B019": "上右下左演示被截断，规则已收 B028。",
        "B023": "海默 0.2875 例题演算，变量绑该次。",
        "B024": "示例路径点问答，命题未闭合。",
        "B031": "与 B025 同公式讲段，酒神路径例不另立。",
        "B035": "抽段切到邻题（元末奶盾卡平A）；同内容已收 B045。不是路径指令定义窗。",
        "B040": "主播声明单靠测试很难理清，猜想未收。",
        "B044": "隐德莱希/鱼叙事，不是机制卡。",
        "B048": "大棋骗仇恨部署顺序，攻略层。",
        "B049": "车阻挡时间轴调整，当场轴。",
        "B059": "与 evidence_round1 E09 酒神猫同讲段，不重复入库。",
        "B061": "酒神/鼠血线攻略。",
        "B064": "ASR 严重嘈杂，无法引用。",
        "B065": "传送门后哪帧可索敌是提问，本窗未答。",
        "B067": "合约拆弹资源分配。",
        "B073": "酒神牢笼随机数不可测，方法论。",
        "B076": "5.5 格→431 帧当场竖式。",
        "B084": "当场测速/注释代码。",
        "B087": "与 B072 同偏移讲段，不重复。",
        "B088": "例题坐标混乱。",
        "B090": "假设六格的移动时间竖式。",
        "B091": "干员定位评价。",
        "B095": "「理论覆盖率」纸面定义，不是底层规则。",
        "B096": "久诚囚笼攻略。",
        "B098": "睡眠永控干员选择。",
        "B099": "合约抗性是否普遍，攻略。",
    }
    pend_reason = {
        "B012": "M3 攻速变化演算截断，数字未核。",
        "B046": "选择组剩余冷却改小于 0 的 31.96/加一帧演算未闭合；不把单位写成游戏事实。",
        "B051": "EW 睡眠测试未完成。",
        "B058": "塑心停顿 7.8 为实测逆推，解剖结果被否认。",
        "B060": "酒神 857.14 与极小值，ASR+精度，needs_av。",
        "B079": "问答未闭合到规则。",
        "B083": "摩擦力数字讨论中途。",
    }

    rejected, pending = [], []
    for p in jl("passages.jsonl"):
        tid = p["topic_id"]
        if tid in used:
            continue
        if tid in pend_reason:
            pending.append({"topic_id": tid, "cluster_id": p["cluster_id"], "reason": pend_reason[tid], "risk": p["risk"], "reviewer_type": "agent"})
        else:
            rejected.append({
                "topic_id": tid, "cluster_id": p["cluster_id"],
                "reason": rej_reason.get(tid, "代理逐条证据审核：当场演算/攻略/无法闭合。"),
                "risk": p["risk"], "keep_nothing": True, "reviewer_type": "agent",
            })
    dump("rejected.jsonl", rejected)
    dump("pending.jsonl", pending)

    man = json.load(open(os.path.join(HERE, "manifest.json"), encoding="utf-8"))
    man["note"] = "只抽语段，不自动写成机制。无 LLM。代理逐条证据审核覆盖本批 94 条；以后批次不要求全审。"
    man["review"] = {
        "reviewer_type": "agent",
        "n_passages": 94,
        "why_not_100": "人为过滤：只 agreed、成员 4–25、单文件、每类最多 18，再 failed_span 丢 6，再截到 100。cand_by_cat 合计 368，不是全库只有 94。伤害结算/其他因排序截断未进最终 94。记录选择偏倚，未把未抽到的 QQ/全库条目判错。",
        "mechanisms": len(mechs),
        "experiments": len(exps),
        "rejected": len(rejected),
        "pending": len(pending),
        "unreviewed": 0,
        "api_calls": 0,
        "no_prod_pack": True,
    }
    json.dump(man, open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({
        "mechanisms": len(mechs), "experiments": len(exps),
        "rejected": len(rejected), "pending": len(pending),
        "sum": len(mechs) + len(exps) + len(rejected) + len(pending),
        "passages": len(pas),
        "used_topics": len(used),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
