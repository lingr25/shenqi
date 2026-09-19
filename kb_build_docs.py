# -*- coding: utf-8 -*-
"""kb_build_docs.py - 阶段A: 统一文档层

直播轨(knowledge_pilot/*.atoms.enriched.jsonl + clusters_merged.jsonl)
与 QQ 轨(qq_cards/rag_docs.jsonl + cards.jsonl) pack 成统一 schema 文档,
输出 kb/docs.jsonl + kb/build_report.md。

统一 schema 见 kb/SCHEMA.md。纯本地确定性脚本, 不调 LLM。
"""
import glob
import json
import os
from collections import Counter, defaultdict

KP_DIR = "knowledge_pilot"
QQ_DIR = "qq_cards"
OUT_DIR = "kb"

ISSUE_BOOST = {"agreed": 1.3, "conflict": 1.4, "open": 1.0}


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fmt_t(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def norm_cond(c):
    if isinstance(c, dict):
        return f"{c.get('name', '')}={c.get('value', '')}".strip("=")
    return str(c)


def atom_text(a, conflict_clusters):
    lines = [a["proposition"]]
    if a.get("applies_to") and a["applies_to"] != "general":
        lines.append(f"适用对象: {a['applies_to']}")
    if a.get("conditions"):
        lines.append("条件: " + "; ".join(norm_cond(c) for c in a["conditions"]))
    if a.get("parameters"):
        ps = []
        for p in a["parameters"]:
            v = str(p.get("value_norm") or p.get("value_raw") or "")
            u = p.get("unit") or ""
            if u and v.endswith(u):
                u = ""  # 值已带单位, 避免 "零点七秒秒"
            ps.append(f"{p.get('name','')}={v}{u}".strip())
        ps = [p for p in ps if p.strip("=")]
        if ps:
            lines.append("参数: " + "; ".join(ps))
    if a.get("entities"):
        lines.append("实体: " + " ".join(a["entities"]))
    if a.get("parent_topic"):
        lines.append(f"主题: {a['parent_topic']}")
    for c in conflict_clusters:
        lines.append(f"⚠ 本命题属于争议议题「{c['title']}」({c['cluster_id']}), 结论以议题档案与录播为准")
    return "\n".join(lines)


def pack_atoms(clusters):
    atom2clusters = defaultdict(list)
    for c in clusters:
        for mid in c.get("member_ids", []):
            atom2clusters[mid].append(c)

    docs, stats = [], Counter()
    for path in sorted(glob.glob(os.path.join(KP_DIR, "*.atoms.enriched.jsonl"))):
        for a in load_jsonl(path):
            my_clusters = atom2clusters.get(a["atom_id"], [])
            conflict = [c for c in my_clusters if c["status"] == "conflict"]
            issue_status = "n/a"
            if my_clusters:
                st = {c["status"] for c in my_clusters}
                issue_status = "conflict" if "conflict" in st else ("agreed" if "agreed" in st else "open")
            doc = {
                "id": f"vod_atom:{a['atom_id']}",
                "doc_type": "vod_atom",
                "track": "vod_" + (a.get("track") or "official"),
                "status": a.get("claim_status") or a.get("status") or "draft",
                "issue_status": issue_status,
                "novelty": "vod_only",  # 阶段C 对齐后可能更新
                "conflict_resolution": "n/a",
                "text": atom_text(a, conflict),
                "category": a.get("category"),
                "applies_to": a.get("applies_to"),
                "conditions": a.get("conditions") or [],
                "scope": "instance" if (a.get("applies_to") not in (None, "", "general")) else "general",
                "claim_type": a.get("claim_type"),
                "lesson_kind": a.get("lesson_kind"),
                "entities": a.get("entity_links") or [
                    {"mention": e, "canonical": e, "type": None} for e in (a.get("entities") or [])],
                "evidence": {"kind": "video_quote",
                             "clips": [{"t_start": e.get("start"), "t_end": e.get("end"),
                                        "quote": e.get("quote")} for e in (a.get("evidence") or [])]},
                "source": {"bvid_stem": a.get("source_id"),
                           "recorded_at": a.get("recorded_at"),
                           "speaker": "神祇读神奇", "credibility": "authoritative",
                           "timeline": a.get("timeline"),
                           "chapter": (a.get("chapter") or {}).get("title")},
                "retrieval_weight": a.get("retrieval_weight", 0.6),
                "retrieval_boost": 1.0,
                "links": {"cluster_ids": [c["cluster_id"] for c in my_clusters],
                          "counterpart_ids": []},
                "game_version": a.get("game_version"),
                "atom_id": a["atom_id"],
                "claim_id": a.get("claim_id"),
            }
            docs.append(doc)
            stats["vod_atom"] += 1
    return docs, atom2clusters, stats


def pack_clusters(clusters, atom_by_id):
    docs = []
    stats = Counter()
    for c in clusters:
        members = [atom_by_id[m] for m in c.get("member_ids", []) if m in atom_by_id]
        lines = [c["title"], f"问题: {c.get('question','')}"]
        if c.get("note"):
            lines.append(f"档案备注: {c['note']}")
        if c.get("proposed_canonical"):
            lines.append(f"共识草案: {c['proposed_canonical']}")
        if c["status"] == "conflict":
            lines.append("⚠ 争议议题, 以下为各方命题, 均未裁对错:")
            for m in members[:12]:
                lines.append(f"- [{m.get('claim_type','?')}] {m['proposition']}")
        elif members:
            for m in members[:8]:
                lines.append(f"- {m['proposition']}")
        ent = sorted({e.get("canonical") for m in members for e in (m.get("entity_links") or []) if e.get("canonical")})
        doc = {
            "id": f"vod_cluster:{c['cluster_id']}",
            "doc_type": "vod_cluster",
            "track": "vod_official",  # 簇可跨源, 源信息在 sources
            "status": "draft",
            "issue_status": c["status"],
            "novelty": "vod_only",
            "conflict_resolution": "n/a",
            "text": "\n".join(lines),
            "category": c.get("bucket"),
            "applies_to": None,
            "conditions": [],
            "scope": "general",
            "claim_type": None,
            "entities": [{"mention": e, "canonical": e, "type": None} for e in ent],
            "evidence": {"kind": "video_quote",
                         "clips": [{"t_start": ev.get("start"), "t_end": ev.get("end"),
                                    "quote": ev.get("quote"), "atom_id": m["atom_id"]}
                                   for m in members[:6] for ev in (m.get("evidence") or [])[:1]]},
            "source": {"bvid_stem": None, "stems": c.get("sources") or [],
                       "speaker": "神祇读神奇", "credibility": "authoritative"},
            "retrieval_weight": 1.0,
            "retrieval_boost": ISSUE_BOOST.get(c["status"], 1.0),
            "links": {"cluster_id": c["cluster_id"], "member_atom_ids": c.get("member_ids", []),
                      "merged_from": c.get("merged_from") or [], "counterpart_ids": []},
            "game_version": None,
            "canonical_status": c.get("canonical_status"),
            "member_count": c.get("member_count"),
        }
        docs.append(doc)
        stats[f"vod_cluster_{c['status']}"] += 1
    return docs, stats


def pack_qq():
    cards = {c["window_id"]: c for c in load_jsonl(os.path.join(QQ_DIR, "cards.jsonl"))}
    docs = []
    stats = Counter()
    for d in load_jsonl(os.path.join(QQ_DIR, "rag_docs.jsonl")):
        md = d.get("metadata") or {}
        dt = {"window": "qq_window", "canonical": "qq_canonical", "glossary": "glossary"}[d["doc_type"]]
        doc = {
            "id": d["id"],
            "doc_type": dt,
            "track": "qq",
            "status": md.get("status") or "draft",
            "issue_status": "n/a",
            "novelty": md.get("novelty"),
            "conflict_resolution": "n/a",
            "text": d["text"],
            "category": md.get("category"),
            "applies_to": None,
            "conditions": [],
            "scope": md.get("scope"),
            "claim_type": None,
            "entities": [],
            "evidence": {"kind": "qq_span"},
            "source": {"as_of": md.get("as_of"), "credibility": md.get("credibility_max"),
                       "origin": md.get("origin")},
            "retrieval_weight": 1.0,
            "retrieval_boost": md.get("retrieval_boost", 1.0),
            "links": {"canonical_ids": md.get("canonical_ids") or [],
                      "canonical_id": md.get("canonical_id"),
                      "linked_doc_ids": md.get("linked_doc_ids") or [],
                      "counterpart_ids": []},
            "game_version": None,
        }
        if dt == "qq_window":
            card = cards.get(md.get("window_id"), {})
            doc["entities"] = [{"mention": e, "canonical": e, "type": None}
                               for e in (card.get("entities") or [])]
            doc["novelty"] = card.get("novelty") or doc["novelty"]
            if (card.get("novelty") == "conflict"):
                doc["conflict_resolution"] = card.get("conflict_resolution") or "vod_wins"
            doc["evidence"] = {"kind": "qq_span",
                               "window_id": md.get("window_id"),
                               "n_source_msgs": len(card.get("source_msg_ids") or []),
                               "vod_evidence": card.get("vod_evidence") or []}
            doc["source"]["window_id"] = md.get("window_id")
        if dt == "qq_canonical":
            doc["links"]["cluster_id"] = md.get("cluster_id")
        if dt == "glossary":
            doc["term"] = md.get("term")
            doc["needs_more_evidence"] = md.get("needs_more_evidence")
        docs.append(doc)
        stats[dt] += 1
    return docs, stats


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    clusters = load_jsonl(os.path.join(KP_DIR, "clusters_merged.jsonl"))

    atom_docs, atom2clusters, s1 = pack_atoms(clusters)
    atom_by_id = {}
    for path in sorted(glob.glob(os.path.join(KP_DIR, "*.atoms.enriched.jsonl"))):
        for a in load_jsonl(path):
            atom_by_id[a["atom_id"]] = a
    cluster_docs, s2 = pack_clusters(clusters, atom_by_id)
    qq_docs, s3 = pack_qq()

    docs = atom_docs + cluster_docs + qq_docs
    ids = [d["id"] for d in docs]
    dup = [k for k, v in Counter(ids).items() if v > 1]

    with open(os.path.join(OUT_DIR, "docs.jsonl"), "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    stats = {**s1, **s2, **s3}
    report = ["# kb/docs.jsonl 构建报告 (阶段A)", "",
              f"- 总文档数: **{len(docs)}**", f"- 重复 id: {len(dup)} {dup[:5]}", "",
              "## 分类统计", ""]
    for k, v in sorted(stats.items()):
        report.append(f"- {k}: {v}")
    report += ["", "## novelty 分布", ""]
    for k, v in Counter(str(d.get("novelty")) for d in docs).most_common():
        report.append(f"- {k}: {v}")
    with open(os.path.join(OUT_DIR, "build_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print(json.dumps({"total": len(docs), "dups": dup, "stats": stats}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
