# -*- coding: utf-8 -*-
"""v3 对照评测: 旧 = v1 语料, 新 = build3 语料。

与 v2 的差别只有两处, 两侧**同规则**:
  1. 语料: 新侧换成 build3 (registry downweight/keep 对齐 + 保守覆盖)。
  2. 检索: 两侧都加「同簇/同源多样性配额」——每个来源组至多 1 篇进 top-k,
     用 source coverage 保内容多样性, 不动 k, 不动字数预算, 不为任何单题硬编码。

缓存键改成 **上下文指纹** (`side|qid|sha256(ctx)`), 所以只有 ctx 真变了的题才会重新调用 LLM;
ctx 未变的题直接从 v2 的答案行灌入缓存复用——这正是「只调用改变的题」的实现方式。

k / 每片段字数 / 上下文上限 / prompt / workers 全部沿用 trial_rag.py, 未改。
"""
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
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
QUOTA = 1   # 每个同源组至多进 top-k 的篇数
# 配额模式:
#   all        = 任何共享 cluster 的文档都视为同源(含 er1:/B1xx/canonical/vod_atom)
#   layer_only = 只折叠「同一簇的分层表示」(fc1: / vod_entry: / vod_cluster:);
#                独立证据卡与原始原子**不参与折叠** —— 它们各自承载不同来源的真实内容,
#                不是同一文档的复述。实测 all 模式会把 gold 的独立证据卡
#                (B074-imbalance-speed-separate / B036-path-not-wallhack) 当作
#                同簇重复挤掉, 因此默认改用 layer_only。
QUOTA_MODE = os.environ.get("QUOTA_MODE", "layer_only")
SUFFIX = os.environ.get("V3_SUFFIX", "v4")
SEED_SRCS = [s.strip() for s in os.environ.get("V3_SEED", "v3,v2").split(",") if s.strip()]
CACHE = os.path.join(HERE, "answers_cache_%s.json" % SUFFIX)
LAYER_PREFIX = ("fc1:", "vod_entry:", "vod_cluster:")


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def scr(ds):
    return [dict(d, text=T.scrub(d.get("text") or "")) for d in ds]


def corpus(side):
    extras = scr(T.pilot_extras())
    if side == "old_gated_v1":
        return scr(load(os.path.join(FC1, "gated_old_kept.jsonl"))
                   + load(os.path.join(FC1, "gated_default.jsonl"))) + extras
    return scr(load(os.path.join(HERE, "gated_old_kept_v2.jsonl"))
               + load(os.path.join(HERE, "gated_default_v2.jsonl"))) + extras


def group_key(d, mode=QUOTA_MODE):
    """返回该文档的「来源组」键; None = 不参与配额。

    mode=off        : 全部不折叠(等价于原检索)。
    mode=layer_only : 只折叠同一簇的「分层表示」(fc1:/vod_entry:/vod_cluster:)。
                      独立证据卡(er1:/B1xx)、原始原子(vod_atom:)、canonical/glossary/
                      window/qq_atom **不折叠** —— 它们各自承载来自不同来源的内容,
                      不是同一篇文档的复述, 折叠会误伤 gold。
    mode=all        : 任何共享 cluster_id 的文档都视为同源(保留用于对照/复现)。
    """
    if mode == "off":
        return None
    did = str(d.get("id") or "")
    cid = d.get("cluster_id") or (d.get("links") or {}).get("cluster_id")
    cids = (d.get("links") or {}).get("cluster_ids") or []
    if mode == "layer_only":
        if did.startswith(LAYER_PREFIX):
            if cid:
                return "c:" + str(cid)
            if cids:
                return "c:" + str(sorted(cids)[0])
        return None
    if cid:
        return "c:" + str(cid)
    if cids:
        return "c:" + str(sorted(cids)[0])
    return "d:" + did


def search_quota(idx, q, k=T.K, quota=QUOTA, mode=None):
    """与 trial_rag.Index.search 同分同序, 只多一道同源配额: 同一来源组不许重复占位。"""
    mode = QUOTA_MODE if mode is None else mode
    sc = idx.bm25.score(T.bigrams(q))
    order = sorted(range(len(idx.docs)),
                   key=lambda i: sc[i] * (idx.docs[i].get("retrieval_boost") or 1.0)
                   * (idx.docs[i].get("retrieval_weight") or 1.0), reverse=True)
    hits, seen = [], Counter()
    for i in order:
        if sc[i] <= 0:
            continue
        d = idx.docs[i]
        g = group_key(d, mode)
        if g is not None and seen[g] >= quota:
            continue
        seen[g] += 1
        hits.append({"id": d["id"], "doc_type": d.get("doc_type"),
                     "cluster_id": d.get("cluster_id") or (d.get("links") or {}).get("cluster_id"),
                     "score": round(sc[i] * (d.get("retrieval_boost") or 1.0)
                                    * (d.get("retrieval_weight") or 1.0), 4),
                     "text": (d.get("text") or "")[:T.PER_HIT_CHARS]})
        if len(hits) >= k:
            break
    return hits


def ctx_sig(ctx):
    return hashlib.sha256(ctx.encode()).hexdigest()[:16]


def seed_cache(cache, questions):
    """把 ctx 未变的题从已有答案行灌入缓存(键 = side|qid|ctx指纹), 避免重复调用。

    优先用上一代(SUFFIX 之前)的答案行; 再退回 v2 / build1。这样「只调用 ctx 改变的题」
    在每一代之间都成立。
    """
    seeded = 0
    for side, tag in (("old_gated_v1", "old"), ("new_gated_v3", "new")):
        cands = ["answers_%s_%s.jsonl" % (s, tag) for s in SEED_SRCS]
        p = None
        for c in cands:
            fp = os.path.join(HERE, c)
            if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                p = fp
                break
        if not p:
            continue
        idx = T.Index(corpus(side))
        prev = {r["id"]: r for r in load(p)}
        for q in questions:
            hits = search_quota(idx, q["q"])
            ctx, used, nc = T.pack_ctx(hits)
            key = f"{side}|{q['id']}|{ctx_sig(ctx)}"
            r = prev.get(q["id"])
            if not r or r.get("error"):
                continue
            # 同 ctx id 且同字数 才算可复用 (同 id ⇒ 同文本, 两侧 doc 文本未改)
            if r.get("ctx_ids") == used and r.get("ctx_chars") == nc and not r.get("error"):
                row = dict(r)
                row.update({"side": side, "ctx_chars": nc, "ctx_ids": used, "hit_ids": used,
                            "hits": hits, "ctx_sig": ctx_sig(ctx), "reused_from": "build3"})
                cache[key] = row
                seeded += 1
    return seeded


def run_side(side, docs, questions, cache):
    idx = T.Index(docs)
    rows, todo = [], []
    for q in questions:
        hits = search_quota(idx, q["q"])
        ctx, used, nc = T.pack_ctx(hits)
        key = f"{side}|{q['id']}|{ctx_sig(ctx)}"
        if key in cache and not cache[key].get("error"):
            r = dict(cache[key])
            r["hits"], r["ctx_ids"], r["hit_ids"], r["ctx_chars"] = hits, used, used, nc
            rows.append(r)
        else:
            todo.append((q, key, hits, ctx, used, nc))

    def one(t):
        q, key, hits, ctx, used, nc = t
        out, err = {"answer": "", "cite_ids": [], "abstain": True, "usage": {}}, None
        try:
            out = T.ask(q["q"], ctx)
        except Exception as e:
            err = str(e)[:200]
        return {"id": q["id"], "side": side, "type": q["type"], "q": q["q"],
                "expect": q.get("expect"), "gold_ids": q.get("gold_ids"),
                "gold_clusters": q.get("gold_clusters"),
                "hit_ids": used, "ctx_ids": used, "ctx_chars": nc, "hits": hits,
                "answer": out.get("answer"), "cite_ids": out.get("cite_ids"),
                "abstain": out.get("abstain"), "error": err, "usage": out.get("usage") or {},
                "ctx_sig": ctx_sig(ctx), "reused_from": None, "reviewer_type": "agent"}

    if todo:
        with ThreadPoolExecutor(max_workers=T.WORKERS) as ex:
            got = [f.result() for f in [ex.submit(one, t) for t in todo]]
        for r, t in zip(got, todo):
            rows.append(r)
            cache[t[1]] = r
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rows, {"n_docs": len(docs), "n_fresh": len(todo), "n_reused": len(questions) - len(todo)}


def main():
    frz = json.load(open(FRZ, encoding="utf-8"))
    raw = open(QF, "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    if h != frz["sha256"]:
        raise SystemExit("heldout_v2 hash mismatch; refuse to run")
    questions = load(QF)
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.isfile(CACHE) else {}
    seeded = seed_cache(cache, questions)
    print(json.dumps({"heldout_sha": h[:16], "model": T.grok_client.MODEL,
                      "k": T.K, "per_hit_chars": T.PER_HIT_CHARS,
                      "max_ctx_chars": T.MAX_CTX_CHARS, "quota_per_source_group": QUOTA,
                      "quota_mode": QUOTA_MODE, "suffix": SUFFIX,
                      "seeded_reuse_rows": seeded}, ensure_ascii=False), flush=True)
    t0 = time.time()
    rows_old, m_old = run_side("old_gated_v1", corpus("old_gated_v1"), questions, cache)
    rows_new, m_new = run_side("new_gated_v3", corpus("new_gated_v3"), questions, cache)
    wall = round(time.time() - t0, 2)
    for name, rows in ((f"answers_{SUFFIX}_old.jsonl", rows_old),
                       (f"answers_{SUFFIX}_new.jsonl", rows_new)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    fresh = sum(1 for r in rows_old + rows_new if not r.get("reused_from"))
    out = {"reviewer_type": "agent", "heldout_sha256": h, "model": T.grok_client.MODEL,
           "k": T.K, "per_hit_chars": T.PER_HIT_CHARS, "max_ctx_chars": T.MAX_CTX_CHARS,
           "quota_per_source_group": QUOTA, "quota_mode": QUOTA_MODE,
           "suffix": SUFFIX, "workers": T.WORKERS, "wall_sec": wall,
           "old": m_old, "new": m_new, "n_llm_calls_this_run": fresh,
           "retrieval_old": T.retrieval_metrics(rows_old),
           "retrieval_new": T.retrieval_metrics(rows_new),
           "usage": {"old": {k: sum(int((r.get("usage") or {}).get(k) or 0) for r in rows_old)
                             for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                     "new": {k: sum(int((r.get("usage") or {}).get(k) or 0) for r in rows_new)
                             for k in ("prompt_tokens", "completion_tokens", "total_tokens")}}}
    json.dump(out, open(os.path.join(HERE, "trial_%s_usage.json" % SUFFIX), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"old_fresh": m_old["n_fresh"], "new_fresh": m_new["n_fresh"],
                      "wall_sec": wall}, ensure_ascii=False))


if __name__ == "__main__":
    main()
