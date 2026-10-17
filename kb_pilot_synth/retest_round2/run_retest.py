# -*- coding: utf-8 -*-
"""隔离污染后复测：6 失败题 + 冻结 heldout。不写生产文件。"""
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
DOWNWEIGHT_BOOST = 0.15
DOWNWEIGHT_WEIGHT = 0.3
NEEDS_AV_BOOST = 0.4

DROP_CLUSTERS = {
    "帧时序与计时器-24-0", "索敌-0-1", "索敌-1-0", "帧时序与计时器-46-2",
    "位移-1-5", "帧时序与计时器-43-1", "索敌-22-7", "帧时序与计时器-3-10",
    "寻路-7-8", "其他-6-1", "寻路-36-6", "技能特例-16-7",
}

QQ_EXTRA_IDS = [
    "window:w001518", "canonical:c0021", "window:w000600",
    "window:w000063", "window:w000458",
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


def load_quarantine():
    rows = load_jsonl(os.path.join(HERE, "quarantine.jsonl"))
    drop, down, keep = set(), set(), set()
    for r in rows:
        a = r.get("action")
        i = r["id"]
        if a == "drop":
            drop.add(i)
        elif a == "downweight":
            down.add(i)
        else:
            keep.add(i)
    return drop, down, keep, rows


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
        needs_av = elig == "needs_av"
        rag = bool(m.get("rag_gate"))
        if needs_av:
            gate = "NEEDS_AV_不得当已知"
            boost = NEEDS_AV_BOOST
        elif rag:
            gate = "RAG_OK"
            boost = 1.6
        else:
            gate = "NOT_RAG_FACT_不得当已知通则"
            boost = 0.9
        extras.append({
            "id": "er1:" + m["id"],
            "doc_type": "pilot_" + (label or "mech"),
            "track": "vod_official",
            "status": "draft",
            "retrieval_boost": boost,
            "retrieval_weight": 1.0,
            "text": (
                f"[{gate}|{label}|{elig}] {m.get('subject')}: {m.get('text')}\n"
                f"条件:{m.get('when')}\n"
                f"证据t:{[e.get('t') for e in m.get('evidence') or []]} "
                f"file:{(m.get('evidence') or [{}])[0].get('file')}"
            ),
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
            "text": f"[EXPERIMENT_当场演示不得升通则|{e.get('eligibility')}] {e.get('subject')}: {e.get('text')}\n条件:{e.get('when')}",
            "source": {"pilot": True, "eligibility": e.get("eligibility")},
        })
    extras.append({
        "id": "er1:M05-blink-not-teleport",
        "doc_type": "pilot_context_only",
        "track": "vod_official",
        "status": "draft",
        "retrieval_boost": 1.0,
        "retrieval_weight": 1.0,
        "text": (
            "[context_only|不得当第五种|不得等同传送] 口播在四种移动（寻路、阻挡偏移、失衡、传送）之后补一句"
            "「瞬移直接改写坐标，大概是这四种」。这不是独立定义的第五种，也没有把瞬移等同于传送。"
            "不宜斩钉截铁说瞬移=传送，也不宜斩钉截铁否定第五种。"
        ),
        "source": {"pilot": True, "eligibility": "context_only"},
    })
    by_id = {}
    with open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            by_id[d["id"]] = d
    for qid in QQ_EXTRA_IDS:
        if qid == "canonical:c0014" or qid.startswith("qqx:canonical:c0014"):
            continue
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


def build_new_docs(old, drop_ids, down_ids):
    out = []
    dropped = 0
    downed = 0
    for d in old:
        did = d.get("id") or ""
        if did in drop_ids:
            dropped += 1
            continue
        if d.get("doc_type") == "vod_entry":
            cid = (d.get("links") or {}).get("cluster_id") or ""
            if cid in DROP_CLUSTERS:
                dropped += 1
                continue
        if did in down_ids:
            d = dict(d)
            d["retrieval_boost"] = DOWNWEIGHT_BOOST
            d["retrieval_weight"] = DOWNWEIGHT_WEIGHT
            downed += 1
        out.append(d)
    extras = extra_docs()
    extras = [e for e in extras if e.get("id") not in drop_ids]
    return out + extras, dropped, downed, len(extras)


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
单位未写明时不得猜「秒」或「帧」；「可能对但未证实」必须 abstain，不要写成游戏事实对或错。
口播里「补整之后加一」不得写成公式。
「瞬移直接改写坐标」不是把瞬移定义成传送，也不是确认或否定第五种。
标记 NEEDS_AV / 不得当已知 的片段只能用来说明未闭合，不能当已核参数。
实验观测、当场演示不要升格成永恒通则。
片段已给出明确对比结论时，不要因措辞不完全相同而过度 abstain。
引用必须使用片段标题里的 id。不要自动「以录播为准」删掉群聊并列内容。
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


def run_side(name, index, questions, retrieve_only=False):
    rows = []
    t_ret = t_llm = 0.0
    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0, "errors": 0}

    def one(qi):
        q = questions[qi]
        t0 = time.time()
        hits = index.search(q["q"], k=K)
        ctx, used, nchars = pack_ctx(hits)
        tr = time.time() - t0
        if retrieve_only:
            out = {"answer": "", "cite_ids": [], "abstain": True, "usage": {}}
            return qi, hits, used, nchars, tr, 0.0, out, None
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
        if not retrieve_only:
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


def main():
    os.chdir(ROOT)
    retrieve_only = "--retrieve-only" in sys.argv
    frozen = json.load(open(os.path.join(HERE, "questions_frozen.json"), encoding="utf-8"))
    qpath = os.path.join(HERE, "questions.jsonl")
    raw = open(qpath, "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    if h != frozen["sha256"]:
        raise SystemExit("questions.jsonl hash mismatch; refuse to answer")
    questions = load_jsonl(qpath)
    print("hash_ok", h[:16], "n", len(questions), "model", grok_client.MODEL,
          "base", grok_client.LLM_BASE, "key", bool(grok_client.LLM_KEY),
          "retrieve_only", retrieve_only)

    drop_ids, down_ids, keep_ids, qrows = load_quarantine()
    t0 = time.time()
    old_docs = load_prod_docs()
    t_load = time.time() - t0
    t1 = time.time()
    new_docs, dropped, downed, n_extra = build_new_docs(old_docs, drop_ids, down_ids)
    idx_old = Index(old_docs)
    idx_new = Index(new_docs)
    t_index = time.time() - t1
    print("docs old", len(old_docs), "new", len(new_docs),
          "dropped", dropped, "downweighted", downed, "extras", n_extra,
          "quarantine_drop", len(drop_ids), "quarantine_down", len(down_ids),
          "keep_unknown", len(keep_ids))

    t2 = time.time()
    old_rows, old_tm = run_side("old", idx_old, questions, retrieve_only=retrieve_only)
    new_rows, new_tm = run_side("new", idx_new, questions, retrieve_only=retrieve_only)
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
        "retrieve_only": retrieve_only,
        "load_docs_sec": round(t_load, 2),
        "index_sec": round(t_index, 2),
        "old": old_tm,
        "new": new_tm,
        "qa_wall_sec": round(t_all, 2),
        "corpus": {
            "old": len(old_docs), "new": len(new_docs),
            "dropped": dropped, "downweighted": downed, "extras": n_extra,
        },
        "quarantine": {
            "drop": sorted(drop_ids),
            "downweight": sorted(down_ids),
            "keep_unknown": sorted(keep_ids),
            "n": len(qrows),
        },
    }
    json.dump(usage, open(os.path.join(HERE, "usage.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({
        "old_calls": old_tm["usage"]["calls"], "new_calls": new_tm["usage"]["calls"],
        "old_tok": old_tm["usage"]["total_tokens"], "new_tok": new_tm["usage"]["total_tokens"],
        "qa_wall_sec": usage["qa_wall_sec"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
