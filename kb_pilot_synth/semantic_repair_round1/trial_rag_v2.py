# -*- coding: utf-8 -*-
"""v2 对照评测: 旧 = 当前 gated(v1 语料) vs 新 = gate v2 语料。

严格同口径: 同一 BM25(bigram) / 同 k=6 / 同每片段 500 字 / 同上下文上限 3000 字 /
同一 prompt(复用 trial_rag.PROMPT) / 同 workers。两侧语料都做 QQ 号脱敏(T.scrub)。

语料:
  old = gated_old_kept.jsonl      + gated_default.jsonl      + pilot_extras
  new = gated_old_kept_v2.jsonl   + gated_default_v2.jsonl   + pilot_extras
逐 (side, qid, corpus_sha) 缓存到 answers_cache_v2.json, 命中不重复调用。
冻结题先校验 sha256 再答题。
"""
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
os.chdir(ROOT)
import trial_rag as T  # noqa: E402

QF = os.path.join(HERE, "heldout_q_v2.jsonl")
FRZ = os.path.join(HERE, "heldout_v2_frozen.json")
CACHE = os.path.join(HERE, "answers_cache_v2.json")


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def corpus_sha(docs):
    h = hashlib.sha256()
    for d in docs:
        h.update((d.get("id") or "").encode())
        h.update((d.get("text") or "")[:200].encode())
    return h.hexdigest()[:16]


def scrub_docs(docs):
    out = []
    for d in docs:
        d = dict(d)
        d["text"] = T.scrub(d.get("text") or "")
        out.append(d)
    return out


def run_side(side, docs, questions, cache):
    key_sha = corpus_sha(docs)
    idx = T.Index(docs)
    rows, todo = [], []
    for q in questions:
        k = f"{side}|{q['id']}|{key_sha}"
        if k in cache and not cache[k].get("error"):
            rows.append(cache[k])
        else:
            todo.append((q, k))

    def one(qk):
        q, k = qk
        hits = idx.search(q["q"], k=T.K)
        ctx, used, nc = T.pack_ctx(hits)
        out, err = {"answer": "", "cite_ids": [], "abstain": True, "usage": {}}, None
        try:
            out = T.ask(q["q"], ctx)
        except Exception as e:
            err = str(e)[:200]
        return {"id": q["id"], "side": side, "type": q["type"], "q": q["q"],
                "expect": q.get("expect"), "gold_ids": q.get("gold_ids"),
                "gold_clusters": q.get("gold_clusters"),
                "hit_ids": [h["id"] for h in hits], "ctx_ids": used, "ctx_chars": nc,
                "hits": hits, "answer": out.get("answer"), "cite_ids": out.get("cite_ids"),
                "abstain": out.get("abstain"), "error": err, "usage": out.get("usage") or {},
                "corpus_sha": key_sha, "reviewer_type": "agent"}

    if todo:
        with ThreadPoolExecutor(max_workers=T.WORKERS) as ex:
            got = [f.result() for f in [ex.submit(one, t) for t in todo]]
        for r in got:
            rows.append(r)
            cache[f"{side}|{r['id']}|{key_sha}"] = r
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return rows, {"corpus_sha": key_sha, "n_docs": len(docs),
                  "n_fresh": len(todo), "n_reused": len(questions) - len(todo)}


def main():
    frz = json.load(open(FRZ, encoding="utf-8"))
    raw = open(QF, "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    if h != frz["sha256"]:
        raise SystemExit("heldout_v2 hash mismatch; refuse to run")
    questions = load(QF)
    extras = scrub_docs(T.pilot_extras())
    old = scrub_docs(load(os.path.join(FC1, "gated_old_kept.jsonl"))
                     + load(os.path.join(FC1, "gated_default.jsonl"))) + extras
    new = scrub_docs(load(os.path.join(HERE, "gated_old_kept_v2.jsonl"))
                     + load(os.path.join(HERE, "gated_default_v2.jsonl"))) + extras
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.isfile(CACHE) else {}
    print(json.dumps({"heldout_sha": h[:16], "n_q": len(questions),
                      "model": T.grok_client.MODEL, "old_docs": len(old),
                      "new_docs": len(new), "workers": T.WORKERS, "k": T.K,
                      "per_hit_chars": T.PER_HIT_CHARS, "max_ctx_chars": T.MAX_CTX_CHARS},
                     ensure_ascii=False), flush=True)
    t0 = time.time()
    rows_old, m_old = run_side("old_gated_v1", old, questions, cache)
    rows_new, m_new = run_side("new_gated_v2", new, questions, cache)
    wall = round(time.time() - t0, 2)
    for name, rows in (("answers_v2_old.jsonl", rows_old), ("answers_v2_new.jsonl", rows_new)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {"reviewer_type": "agent", "heldout_sha256": h, "model": T.grok_client.MODEL,
           "k": T.K, "per_hit_chars": T.PER_HIT_CHARS, "max_ctx_chars": T.MAX_CTX_CHARS,
           "workers": T.WORKERS, "wall_sec": wall,
           "old": m_old, "new": m_new,
           "retrieval_old": T.retrieval_metrics(rows_old),
           "retrieval_new": T.retrieval_metrics(rows_new),
           "usage": {
               "old": {k: sum(int((r.get("usage") or {}).get(k) or 0) for r in rows_old)
                       for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
               "new": {k: sum(int((r.get("usage") or {}).get(k) or 0) for r in rows_new)
                       for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
               "note": "tokens 为 cache 内全部行的 usage 之和(含本轮之前同 corpus_sha 的复用行)"}}
    json.dump(out, open(os.path.join(HERE, "trial_v2_usage.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"old_fresh": m_old["n_fresh"], "new_fresh": m_new["n_fresh"],
                      "wall_sec": wall, "old_tok": out["usage"]["old"]["total_tokens"],
                      "new_tok": out["usage"]["new"]["total_tokens"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
