# -*- coding: utf-8 -*-
"""kb_pack_synth.py - 合成词条并入 kb/docs.jsonl (doc_type=vod_entry)"""
import json

BOOST = {"agreed": 1.6, "conflict": 1.5, "open": 1.2}
CONF_W = {"high": 1.0, "mid": 0.85, "low": 0.6}


def main():
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    docs = [d for d in docs if d["doc_type"] != "vod_entry"]
    by_id = {d["id"]: d for d in docs}
    n = 0
    for l in open("kb/synthesized.jsonl", encoding="utf-8"):
        s = json.loads(l)
        cl = by_id.get(s["doc_id"])
        if not cl:
            continue
        boost = BOOST.get(s["issue_status"], 1.0) * CONF_W.get(s.get("confidence"), 0.8)
        docs.append({
            "id": f"vod_entry:{s['cluster_id']}",
            "doc_type": "vod_entry",
            "track": "vod_official",
            "status": "draft",
            "issue_status": s["issue_status"],
            "novelty": "vod_only",
            "conflict_resolution": "n/a",
            "text": s["text"],
            "category": cl.get("category"),
            "applies_to": s.get("applies_to"),
            "conditions": [],
            "scope": "instance" if s.get("applies_to") not in (None, "", "通用", "general") else "general",
            "claim_type": None,
            "audit_kind": s.get("audit_kind"),
            "confidence": s.get("confidence"),
            "entities": cl.get("entities") or [],
            "evidence": cl.get("evidence") or {"kind": "video_quote", "clips": []},
            "source": cl.get("source") or {},
            "retrieval_weight": 1.0,
            "retrieval_boost": round(boost, 3),
            "links": {"cluster_id": s["cluster_id"],
                      "member_atom_ids": cl["links"].get("member_atom_ids") or [],
                      "counterpart_ids": s.get("counterpart_ids") or []},
            "game_version": None,
        })
        n += 1
    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(json.dumps({"vod_entry_added": n, "total": len(docs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
