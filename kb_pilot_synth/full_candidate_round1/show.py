# -*- coding: utf-8 -*-
"""review_pack.jsonl 紧凑视图。用法: python show.py <bucket> <start> <end> [max_quote_chars]"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def view(r, qc=220):
    s = r["synth"]
    L = []
    L.append(f"### [{r['cluster_id']}] cat={r['category']} issue={r['issue_status']} "
             f"mem={len(r['member_atoms'])} flags={r['risk_flags']}")
    L.append(f"SYNTH kind={s['kind']} scope={s['scope']} conf={s['confidence']} "
             f"incomplete={s['context_incomplete']}")
    L.append(f"  title: {s['title']}")
    L.append(f"  applies_to: {s['applies_to']}")
    for i, x in enumerate(s["rules"] or []):
        if isinstance(x, dict):
            L.append(f"  rule{i}: {x.get('text')}")
            L.append(f"     subj={x.get('subject')} when={x.get('when')} "
                     f"scope={x.get('scope')} ev={x.get('evidence_atom_ids')}")
        else:
            L.append(f"  rule{i}: {x}")
    if s.get("conditions"):
        L.append(f"  conditions: {s['conditions']}")
    if s.get("exceptions"):
        L.append(f"  exceptions: {s['exceptions']}")
    if s.get("open_questions"):
        L.append(f"  OQ: {s['open_questions']}")
    L.append("  ATOMS:")
    for a in r["member_atoms"][:8]:
        L.append(f"   - [{a['claim_type']}|obj={a['applies_to']}] {a['proposition']}")
        for q in (a["quotes"] or [])[:2]:
            L.append(f"       q t={q.get('t')} {q.get('file')}: {str(q.get('quote'))[:qc]}")
    return "\n".join(L)


def main():
    bucket = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    end = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 9
    qc = int(sys.argv[4]) if len(sys.argv) > 4 else 220
    rows = [json.loads(l) for l in open(os.path.join(HERE, "review_pack.jsonl"), encoding="utf-8")]
    sel = [r for r in rows if r["audit_bucket"] == bucket
           and r["cache_status"] == "ok"]
    for i, r in enumerate(sel[start:end], start):
        print(f"----- #{i} -----")
        print(view(r, qc))
    print(f"[bucket={bucket} ok={len(sel)} shown={start}:{min(end,len(sel))}]")


if __name__ == "__main__":
    main()
