# -*- coding: utf-8 -*-
"""rag_eval.py - RAG 检索实测 (纯本地, 无 LLM 无外部依赖)

用字符 bigram + BM25 在增强原子卡上检索, 验证:
1. 机制提问能否召回相关原子卡
2. 议题(cluster)标注能否把同议题卡成组带回
3. conflict 议题在敏感问题上是否两面都被召回(不能一面倒)

输出: knowledge_pilot/rag_eval_report.md
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "knowledge_pilot"

# 每个问题: (query, 期望命中关键词任一, 备注)
QUERIES = [
    ("寻路第一步按什么顺序推地块", ["上右下左"], "算法课定论"),
    ("开120帧会让费用条更精确吗", ["逻辑帧", "画面帧"], "辟谣型问题"),
    ("M3同帧部署奶谁", ["M3", "奶"], "conflict 议题, 两面都应召回"),
    ("索敌是三帧一索吗", ["三帧", "三针"], "辟谣专场核心"),
    ("落地隐切换帧是第几帧", ["落地隐"], "conflict 议题"),
    ("穿刺花生命比例相同时看仇恨吗", ["穿刺花"], "conflict 议题"),
    ("冷却计时器剩余多少判定归零", ["冷却", "归零"], "推导链, 应成组召回"),
    ("城防炮索敌精度是多少", ["城防炮"], "精度条件敏感"),
    ("嘲讽和锁敌表现是不是反了", ["嘲讽", "颠倒"], "版本相关"),
    ("同仇恨时打先创建还是后创建的", ["创建"], "conflict 议题"),
]


def bigrams(s: str):
    s = re.sub(r"\s+", "", s)
    toks = []
    for i in range(len(s) - 1):
        toks.append(s[i:i + 2])
    # 单字符也保留(中文单字有意义, 如"帧")
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


def main():
    atoms = []
    for f in sorted(OUT_DIR.glob("*.atoms.enriched.jsonl")):
        atoms.extend(json.loads(l) for l in f.read_text(encoding="utf-8").splitlines())

    clusters = {}
    cm_path = OUT_DIR / "clusters_merged.jsonl"
    c_path = cm_path if cm_path.exists() else OUT_DIR / "clusters.jsonl"
    cluster_of = {}
    cluster_status = {}
    for l in c_path.read_text(encoding="utf-8").splitlines():
        c = json.loads(l)
        for mid in c["member_ids"]:
            cluster_of[mid] = c["cluster_id"]
            cluster_status[mid] = c["status"]

    docs = []
    for a in atoms:
        conds = a.get("conditions") or []
        cond_txt = " ".join(
            c if isinstance(c, str) else json.dumps(c, ensure_ascii=False) for c in conds
        )
        text = (a.get("proposition") or "") + " " + cond_txt + " " + \
               " ".join(l["mention"] for l in a.get("entity_links", []))
        docs.append(bigrams(text))
    bm25 = BM25(docs)

    lines = [
        "# RAG 检索实测报告",
        "",
        f"- 语料: {len(atoms)} 张增强原子卡 (bigram+BM25, 纯本地)",
        f"- 聚类来源: {c_path.name}",
        "",
    ]
    n_hit = 0
    for query, expect, note in QUERIES:
        scores = bm25.score(bigrams(query))
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:5]
        lines.append(f"## {query}")
        lines.append(f"({note}; 期望关键词: {'/'.join(expect)})")
        hit = False
        seen_status = set()
        for rank, i in enumerate(top, 1):
            a = atoms[i]
            cid = cluster_of.get(a["atom_id"], "-")
            st = cluster_status.get(a["atom_id"], "-")
            seen_status.add(st)
            if any(k in re.sub(r"[、，。,\s]", "", a["proposition"]) for k in expect):
                hit = True
            lines.append(f"{rank}. [{a['claim_type']}|{st}|{cid}] {a['proposition'][:80]}")
        lines.append(f"判定: {'HIT' if hit else 'MISS'}" +
                     (f"; 召回状态分布: {sorted(seen_status)}" if len(seen_status) > 1 else ""))
        lines.append("")
        n_hit += hit

    lines.insert(4, f"- 命中率: {n_hit}/{len(QUERIES)}")
    (OUT_DIR / "rag_eval_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"命中 {n_hit}/{len(QUERIES)}, 报告已写出")


if __name__ == "__main__":
    main()
