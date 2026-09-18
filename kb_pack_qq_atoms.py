# -*- coding: utf-8 -*-
"""kb_pack_qq_atoms.py - 把 kb/qq_atoms.jsonl 并入 kb/docs.jsonl (doc_type=qq_atom)"""
import json

CLAIM_W = {"conclusion": 1.0, "correction": 1.0, "derivation": 0.6,
           "observation": 0.6, "hypothesis": 0.2, "question": 0.1}
CRED_W = {"authoritative": 1.0, "expert": 0.8, "lead": 0.6, "member": 0.4}


def main():
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    docs = [d for d in docs if d["doc_type"] != "qq_atom"]
    n = 0
    for l in open("kb/qq_atoms.jsonl", encoding="utf-8"):
        a = json.loads(l)
        lines = [a["proposition"]]
        if a.get("applies_to") and a["applies_to"] != "general":
            lines.append(f"适用对象: {a['applies_to']}")
        if a.get("conditions"):
            lines.append("条件: " + "; ".join(str(c) for c in a["conditions"]))
        if a.get("parameters"):
            lines.append("参数: " + "; ".join(
                f"{p.get('name','')}={p.get('value','')}{p.get('unit','')}"
                for p in a["parameters"] if isinstance(p, dict)))
        if a.get("entities"):
            lines.append("实体: " + " ".join(a["entities"]))
        w = CLAIM_W.get(a.get("claim_type"), 0.6)
        cred = a.get("speaker_credibility") or "member"
        doc = {
            "id": f"qq_atom:{a['atom_id']}",
            "doc_type": "qq_atom",
            "track": "qq",
            "status": "draft",
            "issue_status": "n/a",
            "novelty": a.get("novelty"),
            "conflict_resolution": "n/a",
            "text": "\n".join(lines),
            "category": a.get("category"),
            "applies_to": a.get("applies_to"),
            "conditions": a.get("conditions") or [],
            "scope": "instance" if a.get("applies_to") not in (None, "", "general") else "general",
            "claim_type": a.get("claim_type"),
            "entities": [{"mention": e, "canonical": e, "type": None}
                         for e in (a.get("entities") or [])],
            "evidence": {"kind": "qq_span", "window_id": a.get("window_id")},
            "source": {"window_id": a.get("window_id"), "as_of": a.get("as_of"),
                       "credibility": cred},
            "retrieval_weight": round(w * CRED_W.get(cred, 0.4) + 0.1, 3),
            "retrieval_boost": 1.0,
            "links": {"counterpart_ids": []},
            "game_version": None,
        }
        docs.append(doc)
        n += 1
    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(json.dumps({"qq_atom_added": n, "total": len(docs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
