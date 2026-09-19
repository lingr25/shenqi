# -*- coding: utf-8 -*-
"""kb_search.py - 统一知识库检索入口 (纯本地 BM25)

用法:
  python kb_search.py "索敌是三帧一索吗"
  python kb_search.py "夜半眠兽撤退" --k 8 --track qq
  python kb_search.py --json "平整化"

冲突红线: novelty=conflict 且 conflict_resolution=vod_wins 时, 录播命题优先,
群聊被否结论不作为现行规则。hypothesis/question 不得当定论。
"""
import argparse
import json
import math
import re
import sys
from collections import Counter

DOCS_PATH = "kb/docs.jsonl"


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


_INDEX = None


def load_index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    docs = [json.loads(l) for l in open(DOCS_PATH, encoding="utf-8")]
    grams = [bigrams(d["text"]) for d in docs]
    _INDEX = (docs, BM25(grams))
    return _INDEX


def search(query, k=5, track=None, doc_type=None):
    docs, bm25 = load_index()
    scores = bm25.score(bigrams(query))

    def final(i):
        d = docs[i]
        return scores[i] * (d.get("retrieval_boost") or 1.0) * (d.get("retrieval_weight") or 1.0)

    order = sorted(range(len(docs)), key=final, reverse=True)
    hits = []
    for i in order:
        d = docs[i]
        if d.get("status") == "noise":
            continue
        if track and d.get("track") != track:
            continue
        if doc_type and d.get("doc_type") != doc_type:
            continue
        if scores[i] <= 0:
            continue
        hits.append({"score": round(final(i), 3), "id": d["id"],
                     "doc_type": d["doc_type"], "track": d["track"],
                     "novelty": d.get("novelty"), "issue_status": d.get("issue_status"),
                     "conflict_resolution": d.get("conflict_resolution"),
                     "claim_type": d.get("claim_type"),
                     "text": d["text"][:600],
                     "source": d.get("source"),
                     "links": d.get("links")})
        if len(hits) >= k:
            break
    return hits


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--track", choices=["vod_official", "vod_cloud", "qq"])
    p.add_argument("--doc-type")
    p.add_argument("--json", dest="as_json", action="store_true")
    args = p.parse_args(argv)
    if not args.query:
        p.error("需要 query")
    hits = search(args.query, k=args.k, track=args.track, doc_type=args.doc_type)
    if args.as_json:
        json.dump(hits, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    print(f"# {args.query}  ({len(hits)} hits)")
    print("红线: conflict 且 vod_wins 听录播; hypothesis/question 不当定论。\n")
    for i, h in enumerate(hits, 1):
        flag = ""
        if h.get("conflict_resolution") == "vod_wins":
            flag = " [VOD_WINS]"
        if h.get("claim_type") in ("hypothesis", "question"):
            flag += " [未证实]"
        first = h["text"].split("\n")[0][:80]
        print(f"{i}. {h['score']} [{h['doc_type']}|{h['track']}|{h.get('novelty') or h.get('issue_status')}]{flag}")
        print(f"   {first}")
        print(f"   id={h['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
