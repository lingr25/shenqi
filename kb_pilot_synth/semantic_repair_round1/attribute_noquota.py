# -*- coding: utf-8 -*-
"""归因用: 在 build3 语料上**关掉配额**, 重跑少数题, 分离两个改动各自的贡献。

  build3 无配额 vs build3 有配额 vs build2 无配额 三者对比, 回答「X07 是被 registry
  对齐修好的, 还是被同源配额修好的」。只用少量调用, 不做全量重跑。
"""
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
sys.path.insert(0, HERE)
os.chdir(ROOT)
import trial_rag as T          # noqa: E402
import trial_rag_v3 as V3      # noqa: E402

TARGETS = {"X07": 3, "F04": 1, "F06": 1, "N09": 1}   # 题 -> 重采次数
OUT = os.path.join(HERE, "attribution_noquota.json")


def main():
    qs = {q["id"]: q for q in V3.load(V3.QF)}
    docs = V3.corpus("new_gated_v3")
    idx = T.Index(docs)
    jobs = []
    for qid, reps in TARGETS.items():
        hits = V3.search_quota(idx, qs[qid]["q"], quota=999)   # 999 = 实质关闭配额
        ctx, used, nc = T.pack_ctx(hits)
        for r in range(reps):
            jobs.append((qid, r, qs[qid]["q"], hits, ctx, used, nc))

    def one(j):
        qid, rep, q, hits, ctx, used, nc = j
        out, err = None, None
        try:
            out = T.ask(q, ctx)
        except Exception as e:
            err = str(e)[:200]
        return {"qid": qid, "rep": rep, "ctx_ids": used, "ctx_chars": nc,
                "answer": (out or {}).get("answer"), "abstain": (out or {}).get("abstain"),
                "cite_ids": (out or {}).get("cite_ids"), "error": err,
                "usage": (out or {}).get("usage") or {}, "reviewer_type": "agent"}

    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = [f.result() for f in [ex.submit(one, j) for j in jobs]]
    tot = sum(int((r["usage"] or {}).get("total_tokens") or 0) for r in rows)
    meta = {"reviewer_type": "agent",
            "quota": "off (999)",
            "n_docs": len(docs), "n_calls": len(rows), "tokens": tot,
            "why": "分离 registry 对齐 vs 同源配额 对 X07 的贡献",
            "rows": rows}
    json.dump(meta, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for r in rows:
        print("== %s rep%d abstain=%s" % (r["qid"], r["rep"], r["abstain"]))
        print("   ctx:", r["ctx_ids"])
        print("   ans:", (r["answer"] or "")[:260].replace("\n", " "))
    print(json.dumps({"n_calls": len(rows), "tokens": tot}, ensure_ascii=False))


if __name__ == "__main__":
    main()
