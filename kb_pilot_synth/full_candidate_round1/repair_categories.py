# -*- coding: utf-8 -*-
"""问题按类别定向修复 (不清全量缓存, 不重跑有效条目)。

设计原则:
  - cache_items/ 的 LLM 原始输出保持不动 —— 有效缓存不重复调用。
  - 只对**确定性可判定的问题类别**打补丁, 落盘 repaired.jsonl + repair_log.jsonl。
  - 语义类缺陷 (E 元话语当机制 / I 公式仅 ctx 支撑) 无法确定性判定,
    改为按代理逐条核查结论 (audit_verdicts.jsonl) 定向处理, 不猜测不扩散。
  - 修复以 overlay 形式给出, 由 trial_rag.py 读取, 便于随时回退。

类别:
  A mech_but_narrow_scope   kind=mechanism 但 scope=instance/example
      -> kind 改 experiment (标签归类对齐; 正文一字不动)。
  B unclosed_as_mechanism   mechanism+universal 正文含未闭合数字/单位
      -> kind 改 pending。
  C high_on_universal_nonmech  非 mechanism 却 universal 且 confidence=high
      -> confidence 改 mid。(instance/experiment 的高置信观测不算问题, 不动。)
  D incomplete              context_incomplete
      -> retrieval_weight 0.6 (仅降权, 不改正文)。
  R review_flagged          代理逐条核查判 severe 的条目
      -> kind 改 pending 并记 needs_review, 等待人工/下一轮重跑。
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diagnose as D  # noqa: E402


def patch(rec, cats):
    r = dict(rec)
    res = dict(r.get("result") or {})
    ch = []
    if "A_mech_but_narrow_scope" in cats:
        ch.append({"field": "kind", "from": res.get("kind"), "to": "experiment",
                   "why": "scope=instance/example 的观测不应当作已闭合机制"})
        res["kind"] = "experiment"
    if ({"B_unclosed_as_mechanism", "unclosed_as_mech"} & set(cats)
            and res.get("kind") == "mechanism"):
        ch.append({"field": "kind", "from": "mechanism", "to": "pending",
                   "why": "universal 机制含未闭合数字/单位"})
        res["kind"] = "pending"
    if "C_high_on_universal_nonmech" in cats:
        ch.append({"field": "confidence", "from": "high", "to": "mid",
                   "why": "非机制条目不得以 universal+high 呈现"})
        res["confidence"] = "mid"
    if "D_incomplete" in cats:
        ch.append({"field": "retrieval_weight", "from": 1.0, "to": 0.6,
                   "why": "上下文不完整, 检索降权"})
        r["retrieval_weight"] = 0.6
    if "R_review_severe" in cats:
        if res.get("kind") != "pending":
            ch.append({"field": "kind", "from": res.get("kind"), "to": "pending",
                       "why": "代理逐条核查判 severe, 撤回机制/实验定性"})
            res["kind"] = "pending"
        res["needs_review"] = True
    r["result"] = res
    r["repair_categories"] = cats
    r["repair_changes"] = ch
    r["reviewer_type"] = "agent"
    return r, ch


def load_review_severe():
    p = os.path.join(HERE, "audit_verdicts.jsonl")
    out = set()
    if os.path.isfile(p):
        for l in open(p, encoding="utf-8"):
            v = json.loads(l)
            if v.get("severe") or v.get("verdict", "").startswith("over_claim"):
                out.add(v["cluster_id"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写出 repaired.jsonl")
    args = ap.parse_args()
    cache_dir = os.path.join(HERE, "cache_items")
    severe = load_review_severe()
    cats_count = collections.Counter()
    n = 0
    repaired, log = [], []
    for fn in sorted(os.listdir(cache_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            rec = json.load(open(os.path.join(cache_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        if rec.get("error") or not (rec.get("result") or {}).get("_text"):
            continue
        n += 1
        cats = list(D.flags(rec))
        if rec.get("cluster_id") in severe:
            cats.append("R_review_severe")
        for c in cats:
            cats_count[c] += 1
        if not cats:
            continue
        pr, ch = patch(rec, cats)
        repaired.append(pr)
        log.append({"cluster_id": rec.get("cluster_id"), "categories": cats,
                    "changes": ch, "reviewer_type": "agent"})
    summary = {
        "n_ok_scanned": n, "n_repaired": len(repaired),
        "category_counts": dict(cats_count.most_common()),
        "review_severe_used": sorted(severe),
        "cache_items_untouched": True, "apply": args.apply,
        "reviewer_type": "agent",
    }
    if args.apply:
        op = os.path.join(HERE, "repaired.jsonl")
        with open(op, "w", encoding="utf-8") as f:
            for r in repaired:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        lp = os.path.join(HERE, "repair_log.jsonl")
        with open(lp, "w", encoding="utf-8") as f:
            for r in log:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary["out"] = op
        summary["log"] = lp
    json.dump(summary, open(os.path.join(HERE, "repair_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
