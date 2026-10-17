# -*- coding: utf-8 -*-
"""旧库 vs 增量新库：同 BM25、同 k、同上下文预算、同模型。40 次答题。不写生产文件。"""
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import grok_client

K = 6
PER_HIT_CHARS = 500
MAX_CTX_CHARS = 3000
WORKERS = 2
RETRIES = 2

DROP_CLUSTERS = {
    "帧时序与计时器-24-0", "索敌-0-1", "索敌-1-0", "帧时序与计时器-46-2",
    "位移-1-5", "帧时序与计时器-43-1", "索敌-22-7", "帧时序与计时器-3-10",
    "寻路-7-8", "其他-6-1", "寻路-36-6", "技能特例-16-7",
}

QQ_EXTRA_IDS = [
    "window:w001518", "canonical:c0021", "window:w000600",
    "window:w000063", "window:w000458", "canonical:c0014",
    "window:w001940", "window:w001181",
]


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
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in qtf:
                if t not in tf:
                    continue
                f = tf[t]
                idf = self.idf.get(t, 0)
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
            scores.append(s)
        return scores


def scrub(s):
    s = s or ""
    s = re.sub(r"QQ[:：]?\s*\d{5,}", "QQ:[id]", s)
    s = re.sub(r"(?<!\d)[1-9]\d{6,11}(?!\d)", "[id]", s)
    return s


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def load_prod_docs():
    docs = []
    with open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("status") == "noise":
                continue
            docs.append(d)
    return docs


def extra_docs():
    extras = []
    mechs = load_jsonl(os.path.join(ROOT, "kb_pilot_synth/evidence_round1/mechanisms.jsonl"))
    exps = load_jsonl(os.path.join(ROOT, "kb_pilot_synth/evidence_round1/experiments.jsonl"))
    for m in mechs:
        label = m.get("record_type")
        elig = m.get("eligibility")
        gate = "RAG_OK" if m.get("rag_gate") else "NOT_RAG_FACT"
        extras.append({
            "id": "er1:" + m["id"],
            "doc_type": "pilot_" + label,
            "track": "vod_official",
            "status": "draft",
            "retrieval_boost": 1.6 if m.get("rag_gate") else 0.9,
            "retrieval_weight": 1.0,
            "text": f"[{gate}|{label}|{elig}] {m.get('subject')}: {m.get('text')}\n条件:{m.get('when')}\n证据t:{[e.get('t') for e in m.get('evidence') or []]} file:{(m.get('evidence') or [{}])[0].get('file')}",
            "source": {"pilot": True, "eligibility": elig},
        })
    for e in exps:
        extras.append({
            "id": "er1:" + e["id"],
            "doc_type": "pilot_experiment",
            "track": "vod_official",
            "status": "draft",
            "retrieval_boost": 1.1,
            "retrieval_weight": 0.85,
            "text": f"[EXPERIMENT|{e.get('eligibility')}] {e.get('subject')}: {e.get('text')}\n条件:{e.get('when')}",
            "source": {"pilot": True, "eligibility": e.get("eligibility")},
        })
    by_id = {}
    with open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            by_id[d["id"]] = d
    for qid in QQ_EXTRA_IDS:
        d = by_id.get(qid)
        if not d:
            continue
        extras.append({
            "id": "qqx:" + qid,
            "doc_type": d.get("doc_type"),
            "track": "qq",
            "status": "draft",
            "retrieval_boost": 1.3,
            "retrieval_weight": 1.0,
            "conflict_resolution": "n/a",
            "text": "[QQ并列,非自动vod_wins] " + scrub(d.get("text") or "")[:1200],
            "source": d.get("source"),
        })
    return extras


def build_new_docs(old):
    out = []
    dropped = 0
    for d in old:
        if d.get("doc_type") == "vod_entry":
            cid = (d.get("links") or {}).get("cluster_id") or ""
            if cid in DROP_CLUSTERS:
                dropped += 1
                continue
        out.append(d)
    extras = extra_docs()
    return out + extras, dropped, len(extras)


class Index:
    def __init__(self, docs):
        self.docs = docs
        self.bm25 = BM25([bigrams(d.get("text") or "") for d in docs])

    def search(self, query, k=K):
        scores = self.bm25.score(bigrams(query))

        def final(i):
            d = self.docs[i]
            return scores[i] * (d.get("retrieval_boost") or 1.0) * (d.get("retrieval_weight") or 1.0)

        order = sorted(range(len(self.docs)), key=final, reverse=True)
        hits = []
        for i in order:
            if scores[i] <= 0:
                continue
            d = self.docs[i]
            hits.append({
                "id": d["id"],
                "doc_type": d.get("doc_type"),
                "track": d.get("track"),
                "score": round(final(i), 4),
                "text": (d.get("text") or "")[:PER_HIT_CHARS],
            })
            if len(hits) >= k:
                break
        return hits


def pack_ctx(hits):
    parts = []
    n = 0
    used = []
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


PROMPT = """你是明日方舟机制资料问答员。只能根据【检索片段】回答，禁止用片段外的游戏常识补全。
证据不足、单位不明、数字未闭合时必须 abstain=true，并写清缺什么。
引用必须使用片段标题里的 id。不要自动「以录播为准」删掉群聊并列内容。
实验观测不要升格成永恒通则。
输出严格JSON：
{{"answer": "中文简答", "cite_ids": ["id"], "abstain": false}}

【问题】{q}

【检索片段】
{ctx}
"""


def ask(q, ctx):
    raw, usage = grok_client.call_llm(PROMPT.format(q=q, ctx=ctx), retries=RETRIES)
    if not isinstance(raw, dict):
        raise ValueError("not object")
    ans = str(raw.get("answer") or "")
    cites = raw.get("cite_ids") or []
    if isinstance(cites, str):
        cites = [cites]
    abstain = bool(raw.get("abstain"))
    return {"answer": ans, "cite_ids": cites, "abstain": abstain, "usage": usage or {}}


def run_side(name, index, questions):
    rows = []
    t_ret = t_llm = 0.0
    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0, "errors": 0}

    def one(qi):
        q = questions[qi]
        t0 = time.time()
        hits = index.search(q["q"], k=K)
        ctx, used, nchars = pack_ctx(hits)
        tr = time.time() - t0
        t1 = time.time()
        try:
            out = ask(q["q"], ctx)
            err = None
        except Exception as e:
            out = {"answer": "", "cite_ids": [], "abstain": True, "usage": {}}
            err = str(e)[:200]
        tl = time.time() - t1
        return qi, hits, used, nchars, tr, tl, out, err

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(one, i) for i in range(len(questions))]
        got = [f.result() for f in futs]
    got.sort(key=lambda x: x[0])
    for qi, hits, used, nchars, tr, tl, out, err in got:
        t_ret += tr
        t_llm += tl
        u = out.get("usage") or {}
        usage_tot["calls"] += 1
        if err:
            usage_tot["errors"] += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                usage_tot[k] += int(u.get(k) or 0)
            except Exception:
                pass
        rows.append({
            "id": questions[qi]["id"],
            "side": name,
            "q": questions[qi]["q"],
            "type": questions[qi]["type"],
            "hit_ids": [h["id"] for h in hits],
            "ctx_ids": used,
            "ctx_chars": nchars,
            "hits": hits,
            "answer": out.get("answer"),
            "cite_ids": out.get("cite_ids"),
            "abstain": out.get("abstain"),
            "error": err,
            "t_retrieve_sec": round(tr, 3),
            "t_llm_sec": round(tl, 3),
            "usage": u,
        })
    return rows, {"retrieve_sec": round(t_ret, 2), "llm_sec": round(t_llm, 2), "usage": usage_tot}


def kb_eval_baseline(docs):
    from kb_eval import QUERIES
    docs = [d for d in docs if d.get("status") != "noise"]
    bm25 = BM25([bigrams(d.get("text") or "") for d in docs])

    def final(i, s):
        d = docs[i]
        return s * (d.get("retrieval_boost") or 1.0) * (d.get("retrieval_weight") or 1.0)

    n_hit = 0
    for query, expect, note in QUERIES:
        scores = bm25.score(bigrams(query))
        top = sorted(range(len(scores)), key=lambda i: -final(i, scores[i]))[:5]
        hit = False
        for i in top:
            flat = re.sub(r"[、，。,\s]", "", docs[i].get("text") or "")
            if any(k in flat for k in expect):
                hit = True
        n_hit += int(hit)
    return {"manual_hit": n_hit, "manual_total": len(QUERIES)}


def main():
    os.chdir(ROOT)
    frozen = json.load(open(os.path.join(HERE, "questions_frozen.json"), encoding="utf-8"))
    qpath = os.path.join(HERE, "questions.jsonl")
    raw = open(qpath, "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    if h != frozen["sha256"]:
        raise SystemExit("questions.jsonl hash mismatch; refuse to answer")
    questions = load_jsonl(qpath)
    print("hash_ok", h[:16], "n", len(questions), "model", grok_client.MODEL, "base", grok_client.LLM_BASE, "key", bool(grok_client.LLM_KEY))

    t0 = time.time()
    old_docs = load_prod_docs()
    t_load = time.time() - t0
    t1 = time.time()
    new_docs, dropped, n_extra = build_new_docs(old_docs)
    idx_old = Index(old_docs)
    idx_new = Index(new_docs)
    t_index = time.time() - t1
    print("docs old", len(old_docs), "new", len(new_docs), "dropped_vod_entry", dropped, "extras", n_extra)

    base = kb_eval_baseline(old_docs)
    print("kb_eval_baseline", base)

    t2 = time.time()
    old_rows, old_tm = run_side("old", idx_old, questions)
    new_rows, new_tm = run_side("new", idx_new, questions)
    t_all = time.time() - t2

    def dump(name, rows):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dump("answers_old.jsonl", old_rows)
    dump("answers_new.jsonl", new_rows)
    usage = {
        "model": grok_client.MODEL,
        "base": grok_client.LLM_BASE,
        "k": K,
        "per_hit_chars": PER_HIT_CHARS,
        "max_ctx_chars": MAX_CTX_CHARS,
        "workers": WORKERS,
        "questions_sha256": h,
        "load_docs_sec": round(t_load, 2),
        "index_sec": round(t_index, 2),
        "old": old_tm,
        "new": new_tm,
        "qa_wall_sec": round(t_all, 2),
        "kb_eval_baseline": base,
        "corpus": {"old": len(old_docs), "new": len(new_docs), "dropped_vod_entry": dropped, "extras": n_extra},
    }
    json.dump(usage, open(os.path.join(HERE, "usage.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"old_calls": old_tm["usage"]["calls"], "new_calls": new_tm["usage"]["calls"],
                      "old_tok": old_tm["usage"]["total_tokens"], "new_tok": new_tm["usage"]["total_tokens"],
                      "qa_wall_sec": usage["qa_wall_sec"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
