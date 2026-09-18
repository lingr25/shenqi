# -*- coding: utf-8 -*-
"""kb_eval.py - 阶段D: 统一知识库检索评测 (纯本地 bigram+BM25)

在 kb/docs.jsonl 全量文档上检索, 评分 = BM25 × retrieval_boost × retrieval_weight。
验证: 直播题 / QQ独有题 / 跨轨题 / conflict 题(vod_wins 排序)。
输出 kb/kb_eval_report.md
"""
import json
import math
import re
from collections import Counter

# (query, 期望关键词任一, 备注)
QUERIES = [
    # ---- 直播侧原 10 题 ----
    ("寻路第一步按什么顺序推地块", ["上右下左"], "vod 算法课定论"),
    ("开120帧会让费用条更精确吗", ["逻辑帧", "画面帧"], "vod 辟谣"),
    ("M3同帧部署奶谁", ["M3", "奶"], "vod conflict 两面召回"),
    ("索敌是三帧一索吗", ["三帧", "三针"], "vod 辟谣"),
    ("落地隐切换帧是第几帧", ["落地隐"], "vod conflict"),
    ("穿刺花生命比例相同时看仇恨吗", ["穿刺花"], "vod conflict"),
    ("冷却计时器剩余多少判定归零", ["冷却", "归零"], "vod 推导链"),
    ("城防炮索敌精度是多少", ["城防炮"], "vod 精度条件"),
    ("嘲讽和锁敌表现是不是反了", ["嘲讽", "颠倒"], "vod 版本相关"),
    ("同仇恨时打先创建还是后创建的", ["创建"], "vod conflict"),
    # ---- QQ 侧独有问题 ----
    ("夜半眠兽撤退后睡眠什么时候解除", ["眠兽", "睡眠"], "qq window w000006"),
    ("祥子的攻击类型按阻挡还是按地面飞行判定", ["阻挡"], "qq window w000136"),
    ("传送带的位移本质是修改速度还是传送", ["传送带"], "qq window w001356"),
    ("空A为什么看起来连A两下", ["前摇"], "qq window w000141"),
    ("H17-3右上角的花能挤偏移入坑吗", ["H17-3", "偏移"], "qq window w000081"),
    # ---- glossary 黑话题 ----
    ("索敌帧是什么", ["索敌帧"], "glossary"),
    ("平整化算法是什么", ["平整化"], "glossary/shenqi slang"),
    ("隐匿和迷彩有什么区别", ["隐匿", "迷彩"], "glossary 消歧"),
    ("visitNodeCenter是什么", ["visitNodeCenter"], "glossary 拆包"),
    # ---- conflict vod_wins 排序题 ----
    ("重构体撤退返还费用吗", ["重构体", "撤退"], "conflict vod_wins w000416"),
    ("位移和伤害的结算顺序是什么", ["位移", "结算"], "conflict vod_wins w000554"),
    ("冷却在部署前就开始转吗", ["冷却"], "conflict vod_wins w001186"),
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


def main():
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    grams = [bigrams(d["text"]) for d in docs]
    bm25 = BM25(grams)

    def final_score(i, s):
        d = docs[i]
        return s * (d.get("retrieval_boost") or 1.0) * (d.get("retrieval_weight") or 1.0)

    lines = ["# 统一知识库检索评测报告", "",
             f"- 语料: kb/docs.jsonl **{len(docs)}** 条 (vod_atom/vod_cluster/qq_window/qq_canonical/glossary)",
             f"- 评分: bigram BM25 × retrieval_boost × retrieval_weight", ""]
    n_hit = 0
    track_stat = Counter()
    for query, expect, note in QUERIES:
        scores = bm25.score(bigrams(query))
        top = sorted(range(len(scores)), key=lambda i: -final_score(i, scores[i]))[:5]
        lines.append(f"## {query}")
        lines.append(f"({note}; 期望: {'/'.join(expect)})")
        hit = False
        tracks = []
        for rank, i in enumerate(top, 1):
            d = docs[i]
            flat = re.sub(r"[、，。,\s]", "", d["text"])
            if any(k in flat for k in expect):
                hit = True
            tracks.append(d["track"])
            first = d["text"].split("\n")[0][:70]
            lines.append(f"{rank}. [{d['doc_type']}|{d.get('novelty') or d.get('issue_status') or '-'}] {first}")
        lines.append(f"判定: {'HIT' if hit else 'MISS'}; top5 轨道: {Counter(tracks)}")
        lines.append("")
        n_hit += hit
        track_stat.update(tracks[:3])
    lines.insert(4, f"- 命中率: **{n_hit}/{len(QUERIES)}**")
    lines.insert(5, f"- top3 轨道分布: {dict(track_stat)}")
    open("kb/kb_eval_report.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({"hit": n_hit, "total": len(QUERIES), "top3_tracks": dict(track_stat)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
