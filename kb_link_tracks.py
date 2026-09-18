# -*- coding: utf-8 -*-
"""kb_link_tracks.py - 阶段C: 跨轨弱对齐 (确定性打分, 无 LLM)

vod_cluster × qq_window/qq_canonical 候选对, 按实体 Jaccard + 分桶映射 + glossary 命中 + 文本bigram 打分。
产出:
  kb/cross_links.jsonl       {vod_cluster_id, qq_doc_id, score, shared_entities, ...}
  kb/docs.jsonl              links.counterpart_ids 双向写回; qq 侧 novelty 对齐后升级 also_in_vod
  kb/link_report.md          规模统计
  kb/cross_links_sample.md   top50 + 随机50 人工抽检样本
"""
import json
import random
import re
from collections import Counter, defaultdict

BUCKET_MAP = {  # vod bucket -> qq category
    "帧时序与计时器": "帧时序", "索敌": "索敌", "伤害结算": "伤害结算",
    "位移": "位移", "寻路": "寻路", "技能特例": "干员机制", "状态效果": "干员机制",
    "其他": "其他",
}
SCORE_THRESHOLD = 1.0        # cross_links.jsonl 记录阈值
WRITEBACK_THRESHOLD = 2.0    # counterpart_ids 写回阈值 (弱相关不回写)
MAX_COUNTERPARTS = 8


def bigrams(s):
    s = re.sub(r"\s+", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def main():
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    by_id = {d["id"]: d for d in docs}
    vod = [d for d in docs if d["doc_type"] == "vod_cluster"]
    qq = [d for d in docs if d["doc_type"] in ("qq_window", "qq_canonical")]

    def canon_set(d):
        return {e.get("canonical") for e in (d.get("entities") or []) if e.get("canonical")}

    gloss_terms = {d.get("term") for d in docs if d["doc_type"] == "glossary" and d.get("term")}

    # entity -> qq docs 倒排
    ent2qq = defaultdict(list)
    for q in qq:
        for c in canon_set(q):
            ent2qq[c].append(q["id"])

    links = []
    for v in vod:
        ve = canon_set(v)
        cand_ids = set()
        for e in ve:
            cand_ids.update(ent2qq.get(e, ()))
        v_bi = None
        v_gloss = {t for t in gloss_terms if t in (v["text"] or "")}
        for qid in cand_ids:
            q = by_id[qid]
            qe = canon_set(q)
            inter = ve & qe
            if not inter:
                continue
            jac = len(inter) / len(ve | qe)
            bmatch = 1.0 if BUCKET_MAP.get(v.get("category")) == q.get("category") else 0.0
            q_gloss = {t for t in gloss_terms if t in (q["text"] or "")}
            g_hit = len(v_gloss & q_gloss)
            if v_bi is None:
                v_bi = bigrams(v["text"])
            q_bi = bigrams(q["text"])
            bi = len(v_bi & q_bi) / max(1, len(v_bi | q_bi))
            score = 2.0 * jac + 0.5 * bmatch + 0.3 * min(g_hit, 3) + 1.0 * bi
            if score >= SCORE_THRESHOLD:
                links.append({"vod_cluster_id": v["links"]["cluster_id"],
                              "vod_doc_id": v["id"], "qq_doc_id": qid,
                              "score": round(score, 3),
                              "shared_entities": sorted(inter),
                              "bucket_match": bool(bmatch),
                              "glossary_hits": sorted(v_gloss & q_gloss)})

    # 写回 counterpart_ids (双向, 截断); 仅强链接(>=WRITEBACK_THRESHOLD)回写
    strong = [l for l in links if l["score"] >= WRITEBACK_THRESHOLD]
    cp_v = defaultdict(list)
    cp_q = defaultdict(list)
    for l in strong:
        cp_v[l["vod_doc_id"]].append((l["score"], l["qq_doc_id"]))
        cp_q[l["qq_doc_id"]].append((l["score"], l["vod_doc_id"]))
    n_novelty_up = 0
    for did, cps in cp_v.items():
        by_id[did]["links"]["counterpart_ids"] = [x[1] for x in sorted(cps, reverse=True)[:MAX_COUNTERPARTS]]
    for did, cps in cp_q.items():
        d = by_id[did]
        d["links"]["counterpart_ids"] = [x[1] for x in sorted(cps, reverse=True)[:MAX_COUNTERPARTS]]
        if d.get("novelty") in ("group_only", "unknown"):
            d["novelty"] = "also_in_vod"
            n_novelty_up += 1

    with open("kb/cross_links.jsonl", "w", encoding="utf-8") as f:
        for l in sorted(links, key=lambda x: -x["score"]):
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    random.seed(42)
    sample = links[:50] + random.sample(links, min(50, len(links)))
    out = ["# 跨轨对齐抽检样本", ""]
    for l in sample:
        v = by_id[l["vod_doc_id"]]
        q = by_id[l["qq_doc_id"]]
        out += [f"## {l['vod_cluster_id']} × {l['qq_doc_id']}  score={l['score']}",
                f"- 共享实体: {' '.join(l['shared_entities'])}  桶匹配: {l['bucket_match']}",
                f"- [VOD] {v['text'][:200]}", f"- [QQ] {q['text'][:200]}", ""]
    open("kb/cross_links_sample.md", "w", encoding="utf-8").write("\n".join(out))

    rep = ["# 阶段C 跨轨弱对齐报告", "",
           f"- 候选链接对: **{len(links)}** (记录阈值 score>={SCORE_THRESHOLD})",
           f"- 强链接(回写阈值 score>={WRITEBACK_THRESHOLD}): **{len(strong)}**",
           f"- 有 counterpart 的 vod_cluster: **{len(cp_v)}** / {len(vod)}",
           f"- 有 counterpart 的 qq 文档: **{len(cp_q)}** / {len(qq)}",
           f"- novelty 升级 group_only/unknown→also_in_vod: **{n_novelty_up}**", "",
           "## 分数分布", ""]
    buckets = Counter(">=3" if l["score"] >= 3 else "2-3" if l["score"] >= 2 else "1-2"
                      for l in links)
    for k, v in sorted(buckets.items()):
        rep.append(f"- {k}: {v}")
    open("kb/link_report.md", "w", encoding="utf-8").write("\n".join(rep) + "\n")
    print(json.dumps({"links": len(links), "vod_linked": len(cp_v), "qq_linked": len(cp_q),
                      "novelty_upgraded": n_novelty_up, "score_dist": dict(buckets)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
