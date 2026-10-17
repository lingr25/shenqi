# -*- coding: utf-8 -*-
"""运行间方差核查: 用完全相同的 corpus/检索/上下文/prompt, 对指定题重复调用 N 次。

目的: 区分「门控语义导致的回答变化」与「模型采样方差」。
不写 answers_cache_v2.json (那是评测主缓存); 结果另存 variance_check.json。

用法:
  python variance_check.py --side new --reps 3 X07 N12 R03
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
os.chdir(ROOT)
import trial_rag as T  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def scrub_docs(docs):
    out = []
    for d in docs:
        d = dict(d)
        d["text"] = T.scrub(d.get("text") or "")
        out.append(d)
    return out


def build(side):
    if side == "old":
        return scrub_docs(load(os.path.join(FC1, "gated_old_kept.jsonl"))
                          + load(os.path.join(FC1, "gated_default.jsonl"))) + scrub_docs(T.pilot_extras())
    return scrub_docs(load(os.path.join(HERE, "gated_old_kept_v2.jsonl"))
                      + load(os.path.join(HERE, "gated_default_v2.jsonl"))) + scrub_docs(T.pilot_extras())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", default="new", choices=["old", "new"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("ids", nargs="+")
    args = ap.parse_args()

    qs = {q["id"]: q for q in load(os.path.join(HERE, "heldout_q_v2.jsonl"))}
    docs = build(args.side)
    idx = T.Index(docs)
    out = {"reviewer_type": "agent", "side": args.side, "reps": args.reps,
           "model": T.grok_client.MODEL, "k": T.K, "n_docs": len(docs), "rows": {}}
    for qid in args.ids:
        q = qs[qid]
        hits = idx.search(q["q"], k=T.K)
        ctx, used, nc = T.pack_ctx(hits)
        recs = []
        for i in range(args.reps):
            t0 = time.time()
            try:
                r = T.ask(q["q"], ctx)
                recs.append({"run": i, "answer": r.get("answer"), "abstain": r.get("abstain"),
                             "cite_ids": r.get("cite_ids"), "usage": r.get("usage"),
                             "sec": round(time.time() - t0, 2)})
            except Exception as e:
                recs.append({"run": i, "error": str(e)[:200]})
        out["rows"][qid] = {"q": q["q"], "type": q["type"], "expect": q.get("expect"),
                            "ctx_ids": used, "ctx_chars": nc, "runs": recs}
        ab = [r.get("abstain") for r in recs]
        print(json.dumps({"id": qid, "abstain": ab,
                          "empty": [not (r.get("answer") or "").strip() for r in recs]},
                         ensure_ascii=False), flush=True)
    json.dump(out, open(os.path.join(HERE, "variance_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    tok = sum(int((r.get("usage") or {}).get("total_tokens") or 0)
              for v in out["rows"].values() for r in v["runs"])
    print(json.dumps({"out": "variance_check.json", "tokens": tok}, ensure_ascii=False))


if __name__ == "__main__":
    main()
