# -*- coding: utf-8 -*-
"""生成 review_verdicts_v5.json: 以 v4 判定为底, 只覆盖新面 ctx 改变的 20 题。

v5 = 关配额(QUOTA_MODE=off)的消融对照; 旧面 ctx 与 v4 完全一致(全部复用), 故旧面判定沿用 v4。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NEW = {
    "F01": (1.0, "none", "新面追加「手操不在逻辑帧结算、绑定逻辑帧触发的效果要再等一帧」, 与 expect 一致。"),
    "F02": (1.0, "none", "新面同样答「不是一回事 / 只看终点 / 红门只是标识」, 少了蓝门补述, 核心事实齐。"),
    "F03": (1.0, "none", "新面干脆利落: 巡逻状态机才做三帧索敌; 阻挡不索敌, 解阻挡立刻抬手。"),
    "F04": (1.0, "none", "gold 独立证据卡 B074 在 ctx rank3, 答案同样给出「两套独立速度不相加」; 未复述「退出失衡清零再走寻路」, 该句属 expect 第二要点, 记细节减少。"),
    "F06": (1.0, "none", "gold 独立证据卡 B036 在 ctx rank2, 答案完整否证。"),
    "F07": (1.0, "none", "两面一致(两部分: 路径点指令 + 只管时间的停住指令)。"),
    "X03": (1.0, "none", "两面本次都只给结论、未复述取整算法, 均满足 expect。"),
    "R03": (1.0, "none", "新面答「需要都清零, 即等攻击冷却归零才释放」, 满足 expect。"),
    "N01": (1.0, "none", "新面完整: 拒绝升格为通则 + 给出生命流失/克里斯滕相反特例。"),
    "N03": (1.0, "none", "新面直接答「适用对象为『未点名』」, 未编造主语, 引用为 fc1:伤害结算-0-4 (规范)。"),
    "N04": (1.0, "none", "新面答「不需要命中, 只需射出去/发射」, 引用规范。"),
    "N07": (1.0, "none", "【关配额新面答对】直接落「不是底层机制」, 并说明片段把它标为建议性规则/非底层代码机制 —— 这是 build2/v3/v4 都没能给出的正解; 反证层内去重对本题有代价。"),
    "N08": (0.0, "wrong_polarity", "【关配额新面答反】「这条属于机制结论, 但仅限其自身表述范围」→ 与 expect(不是机制结论, 是评价性元话语)极性相反。同一题在 layer_only(v4) 下作答方向正确, 说明该题对 ctx 中是否有 fc1 层条目敏感。另 cite_ids 含未加前缀的裸簇名 '技能特例-21-11', 属引用不可定位。"),
    "N09": (0.75, "failed_abstain", "新面仍两难 abstain, 与 v4 同分; 未断言错误事实。"),
    "N10": (1.0, "none", "新面本版最好: 明确区分「通则(fc1 scope:universal)」与「实例观测(scope:instance + [非通则:rule_scope_instance])」, 正是 expect 要求的「待核/不得当已知结论」方向。"),
    "N11": (1.0, "none", "新面答「保护时间是 3 帧 / 命中后三帧内不退出失衡」, 满足 expect。"),
    "N12": (1.0, "none", "两面均答三条件, 未简化。"),
    "N13": (1.0, "none", "新面同样给出推拉与位移速度都会变 + 换算式并自限「指代与数值未明确」。"),
    "N14": (1.0, "none", "新面内容正确(未闭合/门控), 但本次以 abstain 收尾; 期望允许 abstain, 记 1.0。"),
    "N15": (0.5, "missed_fact", "新面同样只能定位到 BV1j4KC6KEse p75 的证据串, 未给时间; 仍为半对。"),
}


def main():
    v4 = json.load(open(os.path.join(HERE, "review_verdicts_v4.json"), encoding="utf-8"))
    out = {
        "reviewer_type": "agent",
        "note": "v5 = 在 v4(build3 语料 + layer_only 配额)基础上**关掉同源配额**(QUOTA_MODE=off)的消融对照。"
                "旧面 ctx 与 v4 完全一致(答案行全部复用, 未重复调用), 故旧面判定沿用 v4; 只对本轮新面 ctx 改变的 20 题重新作答并复核。"
                "本判定是**代理证据审核标签, 不是人工审核真值, 仍可能出错**。",
        "ablation": {"baseline": "v4(layer_only 配额)", "variant": "off(无配额)", "n_new_rows_rejudged": 20},
        "score_rubric": v4["score_rubric"],
        "err_side": {},
        "verdicts": {},
    }
    for qid, row in v4["verdicts"].items():
        new = dict(row)
        if qid in NEW:
            v, err, note = NEW[qid]
            new["new"] = v
            new["err"] = err
            new["note"] = "【v5 关配额对照】" + note
            new["tag"] = ("fix" if v > row["old"] else
                          "regression" if v < row["old"] and abs(v - row["old"]) >= 0.25 and err != "none" and v <= 0.5
                          else "fix_partial" if v > row["old"] and v < 1.0 else
                          "neutral")
        out["verdicts"][qid] = new
    # err_side: 只保留 v5 实际存在的错误码
    for qid, row in out["verdicts"].items():
        e = row["err"]
        if e == "none":
            continue
        sides = []
        if row["old"] < 1.0:
            sides.append("old")
        if row["new"] < 1.0:
            sides.append("new")
        if not sides:
            sides = [v4["err_side"].get(qid, [e, "both"])[1]]
        out["err_side"][qid] = [e, "both" if len(sides) == 2 else sides[0]]
    json.dump(out, open(os.path.join(HERE, "review_verdicts_v5.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({q: out["verdicts"][q]["tag"] for q in NEW}, ensure_ascii=False))


if __name__ == "__main__":
    main()
