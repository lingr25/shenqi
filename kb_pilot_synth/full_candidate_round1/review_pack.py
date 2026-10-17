# -*- coding: utf-8 -*-
"""逐条证据核查包: 把抽样条目的 簇文 + 成员原子命题 + 原话证据 + 合成结果 打成一包。

供代理 (reviewer_type=agent) 逐条对照原话, 不调 API。
用法: python review_pack.py [sample_random100.jsonl ...]
输出: review_pack.jsonl
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import kb_synthesize as S  # noqa: E402


def main():
    files = sys.argv[1:] or ["sample_random100.jsonl", "sample_risk_extra.jsonl",
                             "sample_errors.jsonl"]
    atoms = S.load_source_atoms(correct_quotes=False)
    by_id = {}
    with open("kb/docs.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            by_id[d["id"]] = d
    out = []
    for fn in files:
        p = os.path.join(HERE, fn)
        if not os.path.isfile(p):
            continue
        for l in open(p, encoding="utf-8"):
            row = json.loads(l)
            cid = row["cluster_id"]
            cl = by_id.get("vod_cluster:" + cid) or {}
            mids = (cl.get("links") or {}).get("member_atom_ids") or []
            ev = []
            for m in mids:
                a = atoms.get(m)
                if not a:
                    continue
                ev.append({
                    "atom_id": m,
                    "claim_type": a.get("claim_type"),
                    "applies_to": a.get("applies_to"),
                    "proposition": a.get("proposition"),
                    "quotes": [{"t": q.get("t"), "file": q.get("file"),
                                "layer": q.get("layer"), "quote": q.get("quote")}
                               for q in (a.get("evidence") or [])],
                })
            out.append({
                "cluster_id": cid,
                "audit_bucket": row.get("audit_bucket"),
                "issue_status": row.get("issue_status"),
                "category": row.get("category"),
                "cache_status": row.get("cache_status"),
                "call_error": row.get("call_error"),
                "risk_flags": row.get("risk_flags"),
                "synth": {
                    "kind": row.get("kind"), "scope": row.get("scope"),
                    "confidence": row.get("confidence"), "title": row.get("title"),
                    "applies_to": row.get("applies_to"),
                    "context_incomplete": row.get("context_incomplete"),
                    "rules": row.get("rules"), "conditions": row.get("conditions"),
                    "exceptions": row.get("exceptions"),
                    "open_questions": row.get("open_questions"),
                },
                "cluster_text": row.get("cluster_text"),
                "member_atoms": ev,
                "reviewer_type": "agent",
            })
    op = os.path.join(HERE, "review_pack.jsonl")
    with open(op, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"n": len(out), "out": op,
                      "note": "逐条核查须对照 quotes 原文, 不猜主语/单位。"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
