# -*- coding: utf-8 -*-
"""X07 回归的检索层审计(纯本地, 零 LLM)。

审:
  1. k=6 / PER_HIT_CHARS / MAX_CTX_CHARS 是否紧约束(ctx_chars 是否够到上限);
  2. 新旧语料 top-N 的 doc_type / cluster_id 分布, 找出「同簇/同源重复占位」;
  3. intruder 相对 gold 的来源关系。
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
os.chdir(ROOT)
import trial_rag as T  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def corpus(side):
    """与 trial_rag_v2.py 完全一致: 三层语料 + pilot_extras, 且都过 scrub。"""
    if side == "old":
        docs = (load(os.path.join(FC1, "gated_old_kept.jsonl"))
                + load(os.path.join(FC1, "gated_default.jsonl")))
    else:
        docs = (load(os.path.join(HERE, "gated_old_kept_v2.jsonl"))
                + load(os.path.join(HERE, "gated_default_v2.jsonl")))
    return [dict(d, text=T.scrub(d.get("text") or "")) for d in docs] + \
           [dict(d, text=T.scrub(d.get("text") or "")) for d in T.pilot_extras()]


def topn(idx, q, n=12):
    sc = idx.bm25.score(T.bigrams(q))
    order = sorted(range(len(idx.docs)),
                   key=lambda i: sc[i] * (idx.docs[i].get("retrieval_boost") or 1.0)
                   * (idx.docs[i].get("retrieval_weight") or 1.0), reverse=True)
    out = []
    for i in order:
        if sc[i] <= 0:
            continue
        d = idx.docs[i]
        out.append({
            "rank": len(out) + 1,
            "id": d["id"],
            "doc_type": d.get("doc_type"),
            "cluster_id": d.get("cluster_id") or (d.get("links") or {}).get("cluster_id"),
            "boost": d.get("retrieval_boost"), "weight": d.get("retrieval_weight"),
            "score": round(sc[i] * (d.get("retrieval_boost") or 1.0)
                           * (d.get("retrieval_weight") or 1.0), 3),
            "chars": len(d.get("text") or ""),
        })
        if len(out) >= n:
            break
    return out


def main():
    qs = {q["id"]: q for q in load(os.path.join(HERE, "heldout_q_v2.jsonl"))}
    out = {"reviewer_type": "agent", "budget_audit": {}, "questions": {}}

    # --- 1. 预算审计: 全部 30 题的 ctx_chars 分布 (用 build2 answers) ---
    for side in ("old", "new"):
        rows = load(os.path.join(HERE, "answers_v2_%s.jsonl" % side))
        ch = sorted(r["ctx_chars"] for r in rows)
        out["budget_audit"][side] = {
            "k": T.K, "per_hit_chars": T.PER_HIT_CHARS, "max_ctx_chars": T.MAX_CTX_CHARS,
            "n_hits_mode": Counter(len(r["ctx_ids"]) for r in rows).most_common(),
            "ctx_chars_min": ch[0], "ctx_chars_median": ch[len(ch) // 2], "ctx_chars_max": ch[-1],
            "n_at_budget": sum(1 for c in ch if c >= T.MAX_CTX_CHARS - 20),
            "n_hits_cut_by_budget": sum(1 for r in rows if len(r["ctx_ids"]) < len(r["hit_ids"])),
        }

    idx = {s: T.Index(corpus(s)) for s in ("old", "new")}
    out["budget_audit"]["corpus"] = {s: {"n_docs": len(idx[s].docs)} for s in idx}

    # --- 2. 逐题 top-12 诊断 (默认 X07 + 相邻风险题) ---
    focus = ["X07", "X03", "X11", "X13", "X14", "X16", "N05", "N09", "N01", "F06"]
    for qid in focus:
        if qid not in qs:
            continue
        q = qs[qid]
        rec = {"q": q["q"], "type": q["type"], "expect": q.get("expect"),
               "gold_ids": q.get("gold_ids"), "gold_clusters": q.get("gold_clusters"),
               "sides": {}}
        for side in ("old", "new"):
            rows = topn(idx[side], q["q"], 12)
            cc = Counter(r["cluster_id"] for r in rows[:6])
            rec["sides"][side] = {
                "top12": rows,
                "top6_cluster_counts": cc.most_common(),
                "top6_dup_clusters": [c for c, n in cc.items() if n > 1],
                "top6_dup_after_norm": None,
            }
        # 组内命中差距
        o6 = {r["id"] for r in rec["sides"]["old"]["top12"][:6]}
        n6 = {r["id"] for r in rec["sides"]["new"]["top12"][:6]}
        rec["diff_top6"] = {"only_old": sorted(o6 - n6), "only_new": sorted(n6 - o6)}
        out["questions"][qid] = rec

    json.dump(out, open(os.path.join(HERE, "x07_diagnosis.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # --- 打印摘要 ---
    print("== budget ==", json.dumps(out["budget_audit"], ensure_ascii=False))
    for qid, rec in out["questions"].items():
        print("== %s (%s) ==" % (qid, rec["type"]))
        print("   q:", rec["q"][:70])
        for side in ("old", "new"):
            s = rec["sides"][side]
            c = Counter(r["cluster_id"] for r in s["top12"][:6])
            print("   %s top6 clusters:" % side, [(k, v) for k, v in c.most_common()])
            for r in s["top12"][:8]:
                print("      %2d %-46s %-22s %-24s s=%s" % (
                    r["rank"], r["id"], r["doc_type"], r["cluster_id"], r["score"]))
        print("   only_old:", rec["diff_top6"]["only_old"])
        print("   only_new:", rec["diff_top6"]["only_new"])


if __name__ == "__main__":
    main()
