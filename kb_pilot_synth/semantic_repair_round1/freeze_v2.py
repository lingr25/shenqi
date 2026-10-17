# -*- coding: utf-8 -*-
"""冻结 v2 评测题: 原冻结 7 题 + 20 题集/重测集里的失败样本 + 15 道新题(覆盖未参与调参的议题)。

新题选题原则(见 docs/plans/2026-09-20-kb-targeted-semantic-repair.md §4):
  - 只用**未参与前两轮调参**的议题: 伤害结算-0-10(真伤框架) / 伤害结算-12-18(弓回) /
    伤害结算-0-4(肉鸽侵蚀损伤) / 伤害结算-4-3(交通亭定位) / 状态效果-8-0(失衡退出条件) /
    技能特例-15-1(书刀与字) / 技能特例-21-11(PRTS 元话语) / 其他-3-17(龙控器建议) /
    其他-9-5(MOMULTIPLAYER) / 寻路-36-5(刹车计算)。
  - 题型覆盖: 范围误导(实例当通则/单条件当全部) / 缺主语 / 符号单位 / 原公式(未核) /
    有效例题 / 引用核验。
  - gold 用 `fc1:<cluster_id>`; 同时给 gold_clusters 供簇级召回统计。
冻结后写 heldout_v2_frozen.json(sha256 + id 清单), 评测脚本先校验哈希。
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
RET = os.path.join(os.path.dirname(HERE), "retest_round2")
CROSS = os.path.join(os.path.dirname(HERE), "cross_eval_round1")

NEW = [
    {"id": "N01", "type": "misleading", "must_cite": True, "abstain_ok": False,
     "q": "据录播，伊德的减三十伤害可以抗真伤，所以真伤都能被减三十类减伤减免，对吗？",
     "expect": "不对。伊德那条是单个干员的实例观测（已标为非通则）；真伤的通则只是跳过抗性结算、仍吃伤判。不得把实例升格为通则。",
     "gold_ids": ["fc1:伤害结算-0-10"], "gold_clusters": ["伤害结算-0-10"]},
    {"id": "N02", "type": "direct", "must_cite": True, "abstain_ok": False,
     "q": "真伤和生命流失在伤害结算步骤上分别跳过什么？",
     "expect": "真伤跳过抗性结算，但仍吃伤判，所以可以增伤/减伤；生命流失连伤判也跳过，不能吃增伤减伤。",
     "gold_ids": ["fc1:伤害结算-0-10"], "gold_clusters": ["伤害结算-0-10"]},
    {"id": "N03", "type": "direct", "must_cite": True, "abstain_ok": False,
     "q": "「在肉鸽中，侵蚀损伤削弱的是肉鸽加成前的基础防御」——这条的适用对象是谁？",
     "expect": "原片未点名具体对象，是一般性表述（不是某个干员/敌人）；不得编造主语。",
     "gold_ids": ["fc1:伤害结算-0-4"], "gold_clusters": ["伤害结算-0-4"]},
    {"id": "N04", "type": "direct", "must_cite": True, "abstain_ok": False,
     "q": "攻回/弓回充能需不需要命中？",
     "expect": "不需要命中，只需要发射。",
     "gold_ids": ["fc1:伤害结算-12-18"], "gold_clusters": ["伤害结算-12-18"]},
    {"id": "N05", "type": "insufficient", "must_cite": True, "abstain_ok": True,
     "q": "失衡退出判定里的 0.1 是位移还是速度？它的单位在原片写明了是格还是别的吗？",
     "expect": "是速度阈值（速度小于 0.1 会退出失衡）；单位在原片未写明，不得猜。退出失衡共三个条件。",
     "gold_ids": ["fc1:状态效果-8-0"], "gold_clusters": ["状态效果-8-0"]},
    {"id": "N06", "type": "direct", "must_cite": True, "abstain_ok": False,
     "q": "录播里怎么定位交通亭的爆炸源？",
     "expect": "用炸死/炸不死的临界值取三个点、三点画圆，圆心即爆炸中心与坐标；这是测量方法/该实例的操作，不能当全员通则。",
     "gold_ids": ["fc1:伤害结算-4-3"], "gold_clusters": ["伤害结算-4-3"]},
    {"id": "N07", "type": "misleading", "must_cite": True, "abstain_ok": False,
     "q": "「买过龙控器之后要至少留一个种子，不要把种子随便卖掉」——这是不是一条底层机制？",
     "expect": "不是机制，是对局操作建议（元话语），已从机制层隔离，不得当机制通则引用。",
     "gold_ids": ["fc1:其他-3-17"], "gold_clusters": ["其他-3-17"]},
    {"id": "N08", "type": "misleading", "must_cite": True, "abstain_ok": False,
     "q": "「PRTS 仍然是重要的参考指标，有设置不一定有结果」——这条是机制结论吗？",
     "expect": "不是机制结论，是讲解者对 PRTS 与基础设置的评价性元话语，已隔离。",
     "gold_ids": ["fc1:技能特例-21-11"], "gold_clusters": ["技能特例-21-11"]},
    {"id": "N09", "type": "boundary", "must_cite": True, "abstain_ok": False,
     "q": "书刀和字必须交替、不能连续进行同一种操作——这是机制限制还是操作建议？这条已经定论了吗？",
     "expect": "是书刀相关的机制/操作限制，不是对局策略建议；但交替粒度未闭合（另有片段说「不必须一个书刀一个字」），不得当已核通则。",
     "gold_ids": ["fc1:技能特例-15-1"], "gold_clusters": ["技能特例-15-1"]},
    {"id": "N10", "type": "insufficient", "must_cite": True, "abstain_ok": True,
     "q": "「刹车计算决定怪拐弯后是越过路径点还是停在前头；把速度改得特别高时怪会超过去」——这条有可追溯的证据吗？",
     "expect": "该条的部分原子引用在语料里找不到（引用不可追溯），已标待核；不能当已知结论。",
     "gold_ids": ["fc1:寻路-36-5"], "gold_clusters": ["寻路-36-5"]},
    {"id": "N11", "type": "direct", "must_cite": True, "abstain_ok": False,
     "q": "失衡保护时间是三帧还是三针？拉力或推力命中之后多久不退出失衡？",
     "expect": "录播讲的是三帧（帧/针为同音记法，原文怎么写就怎么保留）；拉力或推力命中三帧之内不退出失衡；钩索师弹道持续期间也不退出。",
     "gold_ids": ["fc1:状态效果-8-0"], "gold_clusters": ["状态效果-8-0"]},
    {"id": "N12", "type": "misleading", "must_cite": True, "abstain_ok": False,
     "q": "失衡退出只看「速度小于 0.1」这一个条件，对吗？",
     "expect": "不对。退出失衡有三个条件：0.1 速度阈值、失衡保护时间（三帧）、存在拉力/推力来源。",
     "gold_ids": ["fc1:状态效果-8-0"], "gold_clusters": ["状态效果-8-0"]},
    {"id": "N13", "type": "direct", "must_cite": True, "abstain_ok": False,
     "q": "在地图文件里改写 MOMULTIPLAYER 会产生什么影响？",
     "expect": "该地图的推拉与位移速度都会改变；它同时用在推力与寻路位移上，写在地图文件中。",
     "gold_ids": ["fc1:其他-9-5"], "gold_clusters": ["其他-9-5"]},
    {"id": "N14", "type": "insufficient", "must_cite": True, "abstain_ok": True,
     "q": "「力的大小 = 前面那个东西 × 0.02 × MOMULTIPLAYER」是已经核过的公式吗？",
     "expect": "不是。该式只在原字幕邻近出现（ctx），「前面那个东西」指代未闭合，应标未闭合，不得当已知公式。",
     "gold_ids": ["fc1:其他-9-5"], "gold_clusters": ["其他-9-5"]},
    {"id": "N15", "type": "citation", "must_cite": True, "abstain_ok": False,
     "q": "「弓回不需要命中，只需要发射」这句原话出自哪个视频、大概什么时间？",
     "expect": "出自 BV1j4KC6KEse_p1_40109737103，约 t=9407-9425 秒（字幕原文「不需要命中的，只需要发射」，同音把「弓回」打成勾回/公回）。须给出文件与时间。",
     "gold_ids": ["fc1:伤害结算-12-18"], "gold_clusters": ["伤害结算-12-18"]},
]

FAILING = {
    "cross": ["Q03", "Q07", "Q11", "Q13", "Q14", "Q16"],
    "retest": ["H03", "H05"],
}


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    base = load(os.path.join(FC1, "heldout_q.jsonl"))
    assert len(base) == 7
    cross = {q["id"]: q for q in load(os.path.join(CROSS, "questions.jsonl"))}
    ret = {q["id"]: q for q in load(os.path.join(RET, "heldout_q.jsonl"))}
    qs = []
    prov = {}
    for q in base:
        qs.append(q)
        prov[q["id"]] = "full_candidate_round1/heldout_q.jsonl(原冻结 7 题)"
    for i in FAILING["cross"]:
        q = cross[i]
        q = dict(q)
        q["id"] = "X" + q["id"][1:]
        qs.append(q)
        prov[q["id"]] = f"cross_eval_round1/questions.jsonl 失败样本({i})"
    for i in FAILING["retest"]:
        q = ret[i]
        q = dict(q)
        q["id"] = "R" + q["id"][1:]
        qs.append(q)
        prov[q["id"]] = f"retest_round2/heldout_q.jsonl 失败样本({i})"
    for q in NEW:
        qs.append(dict(q))
        prov[q["id"]] = "本轮新题(未参与调参议题)"
    assert len({q["id"] for q in qs}) == len(qs), "dup id"
    p = os.path.join(HERE, "heldout_q_v2.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    types = {}
    for q in qs:
        types[q["type"]] = types.get(q["type"], 0) + 1
    frz = {"sha256": h, "n": len(qs), "ids": [q["id"] for q in qs],
           "n_new": len(NEW), "n_reused_7": len(base),
           "n_failing_samples": sum(len(v) for v in FAILING.values()),
           "types": types, "provenance": prov,
           "frozen_at": "2026-09-20", "reviewer_type": "agent",
           "note": "冻结后不再修改; 评测脚本先校验 sha256"}
    json.dump(frz, open(os.path.join(HERE, "heldout_v2_frozen.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in frz.items() if k != "provenance"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
