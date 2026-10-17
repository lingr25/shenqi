# -*- coding: utf-8 -*-
"""检索变体矩阵(纯本地, 零 LLM)。

三个变体, 全部同一 BM25 / k=6 / 500 字 / 3000 上限 / 同一 prompt:
  V0 = build2 语料 (registry 未对齐 + 近似即删的覆盖) —— 报告里的"新面"基线
  V1 = build3 语料 (恢复 registry downweight/keep + 保守覆盖)
  V2 = build3 语料 + 同簇/同源多样性配额 (每源至多 1 篇进 top-k)

产出各题的 top-k id 列表与上下文指纹, 用来判定"哪些题的 ctx 变了(需要真调 LLM)"。
"""
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
os.chdir(ROOT)
import trial_rag as T  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def scr(ds):
    return [dict(d, text=T.scrub(d.get("text") or "")) for d in ds]


def corpus(which):
    extras = scr(T.pilot_extras())
    if which == "old":
        return scr(load(os.path.join(FC1, "gated_old_kept.jsonl"))
                   + load(os.path.join(FC1, "gated_default.jsonl"))) + extras
    if which == "build2":
        return scr(load(os.path.join(HERE, "build2/gated_old_kept_v2.jsonl"))
                   + load(os.path.join(HERE, "build2/gated_default_v2.jsonl"))) + extras
    return scr(load(os.path.join(HERE, "gated_old_kept_v2.jsonl"))
               + load(os.path.join(HERE, "gated_default_v2.jsonl"))) + extras


def group_key(d):
    """同源分组键: 这里把『同一 cluster 的不同层表示』(fc1 / vod_entry / vod_cluster /
    该簇的 vod_atom) 视为同一源, 避免一个议题用多张等价文档占满 top-k。"""
    cid = d.get("cluster_id") or (d.get("links") or {}).get("cluster_id")
    if cid:
        return "c:" + str(cid)
    cids = (d.get("links") or {}).get("cluster_ids") or []
    if cids:
        return "c:" + str(sorted(cids)[0])
    return "d:" + str(d.get("id"))


def ranked(idx, q, quota=None):
    sc = idx.bm25.score(T.bigrams(q))
    order = sorted(range(len(idx.docs)),
                   key=lambda i: sc[i] * (idx.docs[i].get("retrieval_boost") or 1.0)
                   * (idx.docs[i].get("retrieval_weight") or 1.0), reverse=True)
    hits, seen = [], Counter()
    for i in order:
        if sc[i] <= 0:
            continue
        d = idx.docs[i]
        if quota:
            g = group_key(d)
            if seen[g] >= quota:
                continue
            seen[g] += 1
        hits.append({
            "id": d["id"], "doc_type": d.get("doc_type"), "cluster_id": group_key(d),
            "score": round(sc[i] * (d.get("retrieval_boost") or 1.0)
                           * (d.get("retrieval_weight") or 1.0), 4),
            "text": (d.get("text") or "")[:T.PER_HIT_CHARS]})
        if len(hits) >= T.K:
            break
    return hits


def ctx_of(hits):
    ctx, used, n = T.pack_ctx(hits)
    return ctx, used, n


def sig(ctx):
    return hashlib.sha256(ctx.encode()).hexdigest()[:16]


def main():
    qs = load(os.path.join(HERE, "heldout_q_v2.jsonl"))
    idx = {"old": T.Index(corpus("old")), "build2": T.Index(corpus("build2")),
           "build3": T.Index(corpus("build3"))}
    out = {"reviewer_type": "agent",
           "corpora": {k: len(v.docs) for k, v in idx.items()} | {"old": len(idx["old"].docs)},
           "k": T.K, "per_hit_chars": T.PER_HIT_CHARS, "max_ctx_chars": T.MAX_CTX_CHARS,
           "questions": {}}
    print("corpora:", json.dumps({k: len(v.docs) for k, v in idx.items()}, ensure_ascii=False))
    for q in qs:
        rec = {"q": q["q"], "type": q["type"]}
        for label, (side, quota) in {
                "old": ("old", None), "b2": ("build2", None),
                "b3": ("build3", None), "b3q": ("build3", 1)}.items():
            hits = ranked(idx[side], q["q"], quota)
            ctx, used, n = ctx_of(hits)
            rec[label] = {"ids": used, "ctx_chars": n, "sig": sig(ctx),
                          "top6_groups": [h["cluster_id"] for h in hits],
                          "dup_groups": [g for g, c in Counter(h["cluster_id"] for h in hits).items()
                                         if c > 1]}
        rec["changed_vs_b2"] = {k: (rec[k]["sig"] != rec["b2"]["sig"]) for k in ("b3", "b3q")}
        out["questions"][q["id"]] = rec

    agg = {k: sum(1 for r in out["questions"].values() if r["changed_vs_b2"][k])
           for k in ("b3", "b3q")}
    dup = {k: sum(1 for r in out["questions"].values() if r[k]["dup_groups"])
           for k in ("old", "b2", "b3", "b3q")}
    out["agg"] = {"n_ctx_changed_vs_b2": agg, "n_questions_with_dup_groups": dup}
    json.dump(out, open(os.path.join(HERE, "retrieval_matrix.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("ctx changed vs build2:", agg)
    print("questions with duplicate same-source groups in top6:", dup)
    print("total ctx_chars median per variant:",
          {k: sorted(r[k]["ctx_chars"] for r in out["questions"].values())[15]
           for k in ("old", "b2", "b3", "b3q")})
    for qid in ("X07", "X03", "X11", "X13", "X14", "X16", "N05", "N09", "F06", "N01"):
        r = out["questions"].get(qid)
        if not r:
            continue
        print("== %s (%s) dup=%s" % (qid, r["type"],
                                     {k: r[k]["dup_groups"] for k in ("old", "b2", "b3", "b3q")}))
        for k in ("old", "b2", "b3", "b3q"):
            print("   %-4s %s" % (k, r[k]["ids"]))


if __name__ == "__main__":
    main()
