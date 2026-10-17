# -*- coding: utf-8 -*-
"""门控后 heldout 对照: 旧侧(生产原样) vs 新侧(default accepted 层)。

与 trial_rag.py 的区别:
  - 新侧语料 = gated_old_kept.jsonl(旧文档经 coverage/quarantine 处理) + gated_default.jsonl
    (只含 default 层 fc1, pending/reject/needs_review 与规则被隔离的都在 gated_archive.jsonl,
     用 --include-archive 才进语料, 默认不检索)。
  - 两侧都带同一批 pilot extras(batch100 + evidence_round1), 保证 gold 可达且对照同底。
  - 逐 (side, question, corpus_sha) 缓存到 answers_cache.json; 命中即复用, 不重复付费。
  - 冻结 heldout 先校验 sha256。
"""
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import trial_rag as T  # noqa: E402   (需要 GROK_API_KEY 才会 import 成功)

CACHE = os.path.join(HERE, "answers_cache.json")


def load(name):
    return [json.loads(l) for l in open(os.path.join(HERE, name), encoding="utf-8") if l.strip()]


def corpus_sha(docs):
    h = hashlib.sha256()
    for d in docs:
        h.update((d.get("id") or "").encode())
        h.update((d.get("text") or "")[:200].encode())
    return h.hexdigest()[:16]


def run_cached(side, docs, questions):
    key_sha = corpus_sha(docs)
    cache = {}
    if os.path.isfile(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    idx = T.Index(docs)
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
             "calls": 0, "errors": 0, "cache_reused": 0}
    rows = []
    todo = []
    for q in questions:
        k = f"{side}|{q['id']}|{key_sha}"
        if k in cache:
            rows.append(cache[k])
            usage["cache_reused"] += 1
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
                "hit_ids": [h["id"] for h in hits], "ctx_ids": used, "ctx_chars": nc,
                "hits": hits, "answer": out.get("answer"), "cite_ids": out.get("cite_ids"),
                "abstain": out.get("abstain"), "error": err, "usage": out.get("usage") or {},
                "corpus_sha": key_sha, "cached": False}

    if todo:
        with ThreadPoolExecutor(max_workers=T.WORKERS) as ex:
            got = [f.result() for f in [ex.submit(one, t) for t in todo]]
        for r in got:
            rows.append(r)
            cache[f"{side}|{r['id']}|{key_sha}"] = r
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    for r in rows:
        u = r.get("usage") or {}
        usage["calls"] += 0 if r.get("cached") or r.get("cache_key_hit") else 1
        if not r.get("cached"):
            usage["calls"] += 0
        for k2 in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                usage[k2] += int(u.get(k2) or 0)
            except Exception:
                pass
        if r.get("error"):
            usage["errors"] += 1
    # 本次真实付费 = 非缓存行
    fresh = [r for r in rows if r.get("usage", {}).get("total_tokens") or not r.get("cached")]
    usage["fresh_calls"] = len(todo)
    rows.sort(key=lambda r: r["id"])
    return rows, usage, {"corpus_sha": key_sha, "n_docs": len(docs),
                         "n_fresh": len(todo), "n_reused": usage["cache_reused"]}


def main():
    include_archive = "--include-archive" in sys.argv
    frz = json.load(open(os.path.join(HERE, "heldout_frozen.json"), encoding="utf-8"))
    raw = open(os.path.join(HERE, "heldout_q.jsonl"), "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    if h != frz["sha256"]:
        raise SystemExit("heldout hash mismatch; refuse to run")
    questions = load("heldout_q.jsonl")
    old = T.load_prod() + T.pilot_extras()
    kept = load("gated_old_kept.jsonl")
    default = load("gated_default.jsonl")
    arch = load("gated_archive.jsonl") if include_archive else []
    new = kept + default + arch + T.pilot_extras()
    print(json.dumps({"heldout_sha": h[:16], "n": len(questions), "model": T.grok_client.MODEL,
                      "old_docs": len(old), "new_docs": len(new),
                      "kept": len(kept), "default_fc1": len(default), "archive_in": len(arch),
                      "include_archive": include_archive, "workers": T.WORKERS},
                     ensure_ascii=False), flush=True)
    t0 = time.time()
    old_rows, old_u, old_m = run_cached("old", old, questions)
    new_name = "new_gated_archive" if include_archive else "new_gated"
    new_rows, new_u, new_m = run_cached(new_name, new, questions)
    wall = round(time.time() - t0, 2)
    for name, rows in ((f"answers_old_gatedrun.jsonl", old_rows),
                       (f"answers_{new_name}.jsonl", new_rows)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for r in rows:
                r["reviewer_type"] = "agent"
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {"heldout_sha256": h, "model": T.grok_client.MODEL,
           "k": T.K, "per_hit_chars": T.PER_HIT_CHARS, "max_ctx_chars": T.MAX_CTX_CHARS,
           "workers": T.WORKERS, "include_archive": include_archive,
           "old": {"metric": old_m, "usage": old_u}, "new": {"metric": new_m, "usage": new_u},
           "wall_sec": wall,
           "retrieval_old": T.retrieval_metrics(old_rows),
           "retrieval_new": T.retrieval_metrics(new_rows),
           "reviewer_type": "agent"}
    json.dump(out, open(os.path.join(HERE, f"trial_gated_usage{'_archive' if include_archive else ''}.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"old_fresh": old_m["n_fresh"], "old_reused": old_m["n_reused"],
                      "new_fresh": new_m["n_fresh"], "new_reused": new_m["n_reused"],
                      "old_tokens": old_u["total_tokens"], "new_tokens": new_u["total_tokens"],
                      "wall_sec": wall}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
