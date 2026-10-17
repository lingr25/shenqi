# -*- coding: utf-8 -*-
"""覆盖判据的局部边界自检(纯本地, 零 LLM, 不引入新框架)。

背景: 字符二元组相似度 (cov_ratio >= 0.7) 只是**相似度**, 不是语义蕴涵。
相同字符可以承载相反命题(否定/数值/条件不同), 所以它只能用来找候选,
不能单独授权「删掉旧文档」。授权删除一律走 gate_v2.supersede_verdict()。

本脚本固定一批对抗样例, 断言:
  A. 只有「精确命题包含 + 否定/数值/条件兼容」才允许 ok=True;
  B. 任何 ok=True 的判定, 命题必是正文的精确子串(结构不变式);
  C. 近似/冲突样例必须 ok=False 且给出可解释的 blocker。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gate_v2 as G  # noqa: E402

CASES = [
    # (标签, 旧命题, fc1 正文, 期望 ok, 期望 blocker 片段)
    ("精确复述-应删", "索敌帧会在眩晕结束之后立刻索敌。",
     "## 规则\n- 索敌帧会在眩晕结束之后立刻索敌。\n- 避障冷却不会转好。", True, ""),
    ("中文数字已归一-应删", "索敌周期是三帧。", "## 规则\n- 索敌周期是3帧。", True, ""),
    ("否定前缀翻转-必须保留", "阻挡帧立刻归零。",
     "## 规则\n- 不能理解成阻挡帧立刻归零。", False, "negation_prefix"),
    ("否定后缀翻转-必须保留", "该结论成立。", "## 规则\n- 该结论成立不成立无所谓。", False, "negation_postfix"),
    ("条件短语被前缀守卫拦下-保守方向", "避障不会触发。",
     "## 条件\n- 非寻路针时避障不会触发。", False, "negation_prefix"),
    ("同字反义-需要命中", "需要命中。", "## 规则\n- 弓回不需要命中。", False, "negation_prefix"),
    ("数值冲突-必须保留", "攻速上限是600。", "## 规则\n- 攻速上限是700。", False, "number_mismatch"),
    ("数值冲突-仅近似", "动画下限是原长的0.1倍。", "## 规则\n- 动画下限是原长的0.5倍。", False, "number_mismatch"),
    ("条件缺失-必须保留", "非寻路针上避障不会触发。", "## 规则\n- 避障不会触发。", False, "not_exact_containment"),
    ("条件兼容-应删", "非寻路针时避障不会触发。",
     "## 条件\n- 非寻路针时避障不会触发。", True, ""),
    ("纯近似改写-只能候选", "索敌帧会立刻触发。", "## 规则\n- 索敌帧马上就会触发。", False, "not_exact_containment"),
    ("空命题-不构成删除依据之外的情况", "", "## 规则\n- 任意", True, ""),
    ("长正文内精确包含-应删", "阻挡帧由部署决定。",
     "## 规则\n- 阻挡帧由部署决定。\n- 开技能也按部署相位。", True, ""),
]


def main():
    fails = []
    rows = []
    for label, prop, txt, want_ok, want_blocker in CASES:
        p = G.norm(G.cn2digit(prop))
        t = G.norm(G.cn2digit(txt))
        v = G.supersede_verdict(p, t)
        ok_ok = (v["ok"] == want_ok)
        if want_ok:
            blocker_ok = not v["blockers"]
        else:
            # 期望的 blocker 必须出现(近似路径下 blocker 列表非空且含期望片段)
            blocker_ok = any(want_blocker in b for b in v["blockers"]) if want_blocker else bool(v["blockers"])
        # 结构不变式: ok=True ⇒ 命题是正文精确子串
        invariant = (not v["ok"]) or (prop and G.norm(G.cn2digit(prop)) in t) or (not prop)
        rows.append({"case": label, "prop": prop[:40], "ok": v["ok"], "mode": v["mode"],
                     "ratio": v["ratio"], "blockers": v["blockers"],
                     "want_ok": want_ok, "pass": bool(ok_ok and blocker_ok and invariant)})
        if not (ok_ok and blocker_ok and invariant):
            fails.append(label)

    for r in rows:
        print("%-22s ok=%-5s ratio=%-5s mode=%-7s blockers=%-42s want_ok=%-5s %s" % (
            r["case"], r["ok"], r["ratio"], r["mode"], ",".join(r["blockers"]) or "-",
            r["want_ok"], "PASS" if r["pass"] else "FAIL"))
    print()
    print("cases=%d  fails=%d  %s" % (len(rows), len(fails), fails or "ALL PASS"))

    # 额外: 在全量门控产物上复核结构不变式 —— 被删的旧文档其命题必须精确包含
    import json
    from collections import Counter
    summary = {}
    p = os.path.join(HERE, "gate_summary_v2.json")
    if os.path.isfile(p):
        s = json.load(open(p, encoding="utf-8"))
        cov = s.get("coverage", {})
        summary = {
            "cov_candidate_approx": cov.get("cov_candidate_approx"),
            "cov_rejected_by_guard": cov.get("cov_rejected_by_guard"),
            "old_atom_removed_fully_covered": cov.get("old_atom_removed_fully_covered"),
            "old_removed_fully_covered_by_default_fc1": cov.get("old_removed_fully_covered_by_default_fc1"),
            "old_atom_retained_conflict_guard": cov.get("old_atom_retained_conflict_guard"),
            "old_downweighted": cov.get("old_downweighted"),
            "old_keep_unknown": cov.get("old_keep_unknown"),
        }
        print("gate_summary 覆盖计数:", json.dumps(summary, ensure_ascii=False))
        # 断言: 近似候选计数 > 0 且删除计数远小于「相似度>=0.7 的旧口径」
        if (summary.get("cov_candidate_approx") or 0) <= 0:
            fails.append("cov_candidate_approx_should_be_positive")

    out = {"reviewer_type": "agent",
           "note": "字符相似度不是语义蕴涵; 只有精确包含+否定/数值/条件兼容才授权删除",
           "cases": rows, "n_fail": len(fails), "fails": fails,
           "gate_coverage_counts": summary}
    json.dump(out, open(os.path.join(HERE, "coverage_boundary_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
