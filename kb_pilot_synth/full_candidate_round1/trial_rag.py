# -*- coding: utf-8 -*-
"""试验 RAG: 精确 supersedes 旧 entry/atom/cluster + 冻结 heldout 对照评测。

规则:
  - 生产 kb/docs.jsonl 只读, 不改。
  - 每条 v4 合成条目 fc1:<cid> 精确取代:
      vod_entry:<cid>        (旧词条)
      vod_cluster:<cid>      (旧议题档案)
      vod_atom:*             (其 links.cluster_ids 含该 cid 的成员原子)
  - 旧侧 = 生产非 noise 文档原样; 新侧 = 旧侧去掉被取代者 + fc1 条目。
  - 两侧同一 BM25 / 同一 k / 同一 hit 字数 / 同一上下文上限 / 同一 prompt
    (一致性检索与上下文对照)。
  - heldout 先校验 sha256 再答题。

用法:
  python trial_rag.py --retrieve-only     # 纯本地, 不调 LLM
  python trial_rag.py                     # 两侧各答 heldout, 落盘 answers
"""
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import grok_client  # noqa: E402

K = 6
PER_HIT_CHARS = 500
MAX_CTX_CHARS = 3000
WORKERS = 4
RETRIES = 3

def bigrams(s):
    s = re.sub(r"\s+", "", s or "")
    toks = [s[i:i + 2] for i in range(len(s) - 1)]
    toks += [c for c in s if "一" <= c <= "鿿"]
    return toks


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.dl = [len(d) for d in docs]
        self.avgdl = sum(self.dl) / max(len(self.dl), 1)
        df = Counter()
        for d in docs:
            for t in set(d):
                df[t] += 1
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query):
        qtf = Counter(query)
        out = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in qtf:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf.get(t, 0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
            out.append(s)
        return out


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_prod():
    docs = []
    with open("kb/docs.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("status") == "noise":
                continue
            docs.append(d)
    return docs


def load_v4():
    """v4 缓存 -> {cid: entry_doc}。只取有正文的结果; reject 也保留(可检索到"无法成卡")。"""
    cache_dir = os.path.join(HERE, "cache_items")
    out = {}
    for fn in os.listdir(cache_dir):
        if not fn.endswith(".json"):
            continue
        try:
            rec = json.load(open(os.path.join(cache_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        r = rec.get("result") or {}
        if rec.get("error") or not r.get("_text"):
            continue
        cid = rec.get("cluster_id")
        out[cid] = rec
    return out


def apply_repairs(v4):
    """把 repair_categories.py 的定向补丁叠加到 v4 结果上 (不改 cache_items 原始文件)。"""
    p = os.path.join(HERE, "repaired.jsonl")
    if not os.path.isfile(p):
        return v4, 0
    n = 0
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        cid = r.get("cluster_id")
        if cid in v4:
            v4[cid] = r
            n += 1
    return v4, n


def pilot_extras():
    """两侧都带的既有 pilot 卡 (batch100 + evidence_round1), 保证 gold 可达。"""
    extras = []
    b100 = os.path.join(ROOT, "kb_pilot_synth/batch100_round2")
    for sub in ("mechanisms.jsonl", "experiments.jsonl"):
        p = os.path.join(b100, sub)
        if not os.path.isfile(p):
            continue
        for m in load_jsonl(p):
            rag = bool(m.get("rag_gate"))
            boost = 1.6 if rag else 0.9
            extras.append({
                "id": m["id"], "doc_type": "pilot_b100_" + (m.get("record_type") or "mech"),
                "track": "vod_official", "status": "draft",
                "retrieval_boost": boost, "retrieval_weight": 1.0,
                "cluster_id": m.get("cluster_id"),
                "text": (f"[{'RAG_OK' if rag else 'NOT_RAG_FACT'}|{m.get('eligibility')}] "
                         f"{m.get('subject')}: {m.get('text')}"),
                "supersedes": [],
            })
    er = os.path.join(ROOT, "kb_pilot_synth/evidence_round1")
    for sub in ("mechanisms.jsonl", "experiments.jsonl"):
        p = os.path.join(er, sub)
        if not os.path.isfile(p):
            continue
        for m in load_jsonl(p):
            elig = m.get("eligibility")
            rag = bool(m.get("rag_gate"))
            boost = 0.4 if elig == "needs_av" else (1.6 if rag else 0.9)
            extras.append({
                "id": "er1:" + m["id"], "doc_type": "pilot_er1",
                "track": "vod_official", "status": "draft",
                "retrieval_boost": boost, "retrieval_weight": 1.0,
                "text": f"[{elig}] {m.get('subject')}: {m.get('text')}",
                "supersedes": [],
            })
    return extras


def scrub(s):
    s = s or ""
    s = re.sub(r"QQ[:：]?\s*\d{5,}", "QQ:[id]", s)
    s = re.sub(r"(?<!\d)[1-9]\d{6,11}(?!\d)", "[id]", s)
    return s


def build_new(old, v4):
    """精确 supersedes: 移除旧 entry/cluster/成员 atom, 加入 fc1 条目。"""
    entry_ids = {f"vod_entry:{cid}" for cid in v4}
    cluster_ids = {f"vod_cluster:{cid}" for cid in v4}
    atom_cids = set(v4)
    new = []
    removed = Counter()
    atom_by_cluster = set()
    for d in old:
        did = d.get("id") or ""
        if did in entry_ids:
            removed["entry"] += 1
            continue
        if did in cluster_ids:
            removed["cluster"] += 1
            continue
        if d.get("doc_type") == "vod_atom":
            cids = (d.get("links") or {}).get("cluster_ids") or []
            if any(c in atom_cids for c in cids):
                removed["atom"] += 1
                atom_by_cluster.update(cids)
                continue
        new.append(d)
    added = 0
    for cid, rec in v4.items():
        r = rec["result"]
        added += 1
        new.append({
            "id": "fc1:" + cid,
            "doc_type": "pilot_v4_entry",
            "track": "vod_official",
            "status": "draft",
            "cluster_id": cid,
            "retrieval_boost": (1.5 if (r.get("kind") == "mechanism" and r.get("scope") == "universal")
                                else 0.85 if (r.get("kind") == "experiment" or r.get("scope") in ("instance", "example"))
                                else 0.4 if (r.get("kind") == "pending" or r.get("context_incomplete"))
                                else 1.1),
            "retrieval_weight": 1.0,
            "text": scrub(r.get("_text")),
            "supersedes": [f"vod_entry:{cid}", f"vod_cluster:{cid}"],
        })
    stats = {
        "removed_entry": removed["entry"], "removed_cluster": removed["cluster"],
        "removed_atom": removed["atom"], "added_fc1": added,
        "atom_clusters_touched": len(atom_by_cluster),
    }
    return new, stats


class Index:
    def __init__(self, docs):
        self.docs = docs
        self.bm25 = BM25([bigrams(d.get("text") or "") for d in docs])

    def search(self, q, k=K):
        sc = self.bm25.score(bigrams(q))
        order = sorted(range(len(self.docs)), key=lambda i: sc[i] * (self.docs[i].get("retrieval_boost") or 1.0)
                       * (self.docs[i].get("retrieval_weight") or 1.0), reverse=True)
        hits = []
        for i in order:
            if sc[i] <= 0:
                continue
            d = self.docs[i]
            hits.append({"id": d["id"], "doc_type": d.get("doc_type"),
                         "cluster_id": d.get("cluster_id") or ((d.get("links") or {}).get("cluster_id")),
                         "score": round(sc[i] * (d.get("retrieval_boost") or 1.0)
                                        * (d.get("retrieval_weight") or 1.0), 4),
                         "text": (d.get("text") or "")[:PER_HIT_CHARS]})
            if len(hits) >= k:
                break
        return hits


def pack_ctx(hits):
    parts, used, n = [], [], 0
    for h in hits:
        block = f"### {h['id']}\n{h['text']}\n"
        if n + len(block) > MAX_CTX_CHARS:
            block = block[: max(0, MAX_CTX_CHARS - n)]
        if not block:
            break
        parts.append(block)
        used.append(h["id"])
        n += len(block)
        if n >= MAX_CTX_CHARS:
            break
    return "\n".join(parts), used, n


PROMPT = """你是明日方舟机制资料问答员。只能根据【检索片段】回答, 禁止用片段外的游戏常识补全。
证据不足、单位不明、数字未闭合时必须 abstain=true, 并写清缺什么。
单位未写明时不得猜「秒」或「帧」; 口播里「补整之后加一」不得写成公式。
标记 NEEDS_AV / 不得当已知 的片段只能用来说明未闭合, 不能当已核参数。
实验观测、当场演示不要升格成永恒通则。
引用必须使用片段标题里的 id。
输出严格JSON:
{{"answer": "中文简答", "cite_ids": ["id"], "abstain": false}}

【问题】{q}

【检索片段】
{ctx}
"""


def ask(q, ctx):
    raw, usage = grok_client.call_llm(PROMPT.format(q=q, ctx=ctx), retries=RETRIES)
    if not isinstance(raw, dict):
        raise ValueError("not object")
    cites = raw.get("cite_ids") or []
    if isinstance(cites, str):
        cites = [cites]
    return {"answer": str(raw.get("answer") or ""), "cite_ids": cites,
            "abstain": bool(raw.get("abstain")), "usage": usage or {}}


def run_side(name, idx, questions, retrieve_only=False):
    rows = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0, "errors": 0}
    t_llm = 0.0

    def one(q):
        hits = idx.search(q["q"], k=K)
        ctx, used, nc = pack_ctx(hits)
        tr = 0.0
        out, err = {"answer": "", "cite_ids": [], "abstain": True, "usage": {}}, None
        if not retrieve_only:
            t1 = time.time()
            try:
                out = ask(q["q"], ctx)
            except Exception as e:
                err = str(e)[:200]
            tr = time.time() - t1
        return hits, used, nc, out, err, tr

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        got = [f.result() for f in [ex.submit(one, q) for q in questions]]
    for q, (hits, used, nc, out, err, tr) in zip(questions, got):
        t_llm += tr
        if not retrieve_only:
            usage["calls"] += 1
        if err:
            usage["errors"] += 1
        u = out.get("usage") or {}
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                usage[k] += int(u.get(k) or 0)
            except Exception:
                pass
        rows.append({
            "id": q["id"], "side": name, "type": q["type"], "q": q["q"],
            "expect": q.get("expect"), "gold_ids": q.get("gold_ids"),
            "hit_ids": [h["id"] for h in hits], "ctx_ids": used, "ctx_chars": nc,
            "hits": hits, "answer": out.get("answer"), "cite_ids": out.get("cite_ids"),
            "abstain": out.get("abstain"), "error": err,
            "t_llm_sec": round(tr, 3),
        })
    return rows, {"usage": usage, "llm_sec": round(t_llm, 2)}


def retrieval_metrics(rows):
    """gold 命中率 + 是否有 fc1/旧 entry 命中 (纯检索, 不判对错)。"""
    m = {}
    for r in rows:
        ids = [x.replace("er1:", "") for x in r["hit_ids"]]
        cids = {(h.get("cluster_id") or "") for h in r["hits"] if h.get("cluster_id")}
        gold = set(r.get("gold_ids") or [])
        m[r["id"]] = {
            "hit_gold_doc": any(g in ids for g in gold),
            "hit_gold_cluster": bool(gold & cids),
            "hit_any_entry": any(x.startswith(("fc1:", "vod_entry:")) for x in r["hit_ids"]),
            "hit_v4": any(x.startswith("fc1:") for x in r["hit_ids"]),
            "top1": r["hit_ids"][0] if r["hit_ids"] else None,
            "n_hits": len(ids),
        }
    return m


def main():
    retrieve_only = "--retrieve-only" in sys.argv
    frz = json.load(open(os.path.join(HERE, "heldout_frozen.json"), encoding="utf-8"))
    raw = open(os.path.join(HERE, "heldout_q.jsonl"), "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    if h != frz["sha256"]:
        raise SystemExit("heldout hash mismatch; refuse to run")
    questions = load_jsonl(os.path.join(HERE, "heldout_q.jsonl"))
    print("heldout_sha", h[:16], "n", len(questions), "model", grok_client.MODEL,
          "base", grok_client.LLM_BASE, "key", bool(grok_client.LLM_KEY),
          "retrieve_only", retrieve_only, "workers", WORKERS, flush=True)

    t0 = time.time()
    old = load_prod()
    v4 = load_v4()
    v4, n_rep = apply_repairs(v4)
    t1 = time.time()
    new, sup_stats = build_new(old, v4)
    extras = pilot_extras()
    old_all = old + extras
    new_all = new + extras
    idx_old, idx_new = Index(old_all), Index(new_all)
    idx_stats = {
        "prod_docs": len(old), "prod_plus_pilot_old": len(old_all),
        "new_plus_pilot": len(new_all), "n_v4": len(v4), "n_repaired_applied": n_rep,
        "supersede": sup_stats, "load_sec": round(t1 - t0, 2),
        "index_sec": round(time.time() - t1, 2),
    }
    print(json.dumps(idx_stats, ensure_ascii=False), flush=True)
    # 旧侧被取代前的 entry/cluster 是否真被移除
    new_ids = {d["id"] for d in new_all}
    leaked = [f"vod_entry:{c}" for c in list(v4)[:500] if f"vod_entry:{c}" in new_ids]
    idx_stats["supersede_leak"] = len(leaked)

    t2 = time.time()
    old_rows, old_tm = run_side("old", idx_old, questions, retrieve_only)
    new_rows, new_tm = run_side("new", idx_new, questions, retrieve_only)
    wall = round(time.time() - t2, 2)

    for name, rows in (("answers_old.jsonl", old_rows), ("answers_new.jsonl", new_rows)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for r in rows:
                r["reviewer_type"] = "agent"
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {
        "model": grok_client.MODEL, "base": grok_client.LLM_BASE,
        "k": K, "per_hit_chars": PER_HIT_CHARS, "max_ctx_chars": MAX_CTX_CHARS,
        "workers": WORKERS, "retrieve_only": retrieve_only,
        "heldout_sha256": h,
        "index": idx_stats,
        "old": old_tm, "new": new_tm, "qa_wall_sec": wall,
        "retrieval_old": retrieval_metrics(old_rows),
        "retrieval_new": retrieval_metrics(new_rows),
        "reviewer_type": "agent",
    }
    json.dump(out, open(os.path.join(HERE, "trial_usage.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({
        "old_tok": old_tm["usage"]["total_tokens"], "new_tok": new_tm["usage"]["total_tokens"],
        "old_errors": old_tm["usage"]["errors"], "new_errors": new_tm["usage"]["errors"],
        "wall_sec": wall,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
