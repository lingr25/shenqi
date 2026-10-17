# -*- coding: utf-8 -*-
"""纯本地: 打印 v3 vs v4 的逐题对照(仅 ctx 改变的题), 供代理复核。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WANT = sys.argv[1:] or None


def load(p):
    return {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, p), encoding="utf-8") if l.strip()}


def main():
    qs = {q["id"]: q for q in load("heldout_q_v2.jsonl").values()}
    a3o, a3n = load("answers_v3_old.jsonl"), load("answers_v3_new.jsonl")
    a4o, a4n = load("answers_v4_old.jsonl"), load("answers_v4_new.jsonl")
    ids = WANT or [q["id"] for q in load("heldout_q_v2.jsonl").values()]
    for qid in ids:
        q = qs[qid]
        ch = []
        if a3o[qid]["ctx_sig"] != a4o[qid]["ctx_sig"]:
            ch.append("old")
        if a3n[qid]["ctx_sig"] != a4n[qid]["ctx_sig"]:
            ch.append("new")
        print("=" * 100)
        print(f"### {qid} ({q['type']})  changed_sides={ch}  gold={q.get('gold_ids')}")
        print("Q:", q["q"])
        print("EXPECT:", q.get("expect"))
        for side, a3, a4 in (("OLD", a3o, a4o), ("NEW", a3n, a4n)):
            if side.lower() not in ch and not WANT:
                continue
            print(f"-- {side} v3 ctx={a3[qid]['ctx_ids']}")
            print(f"   v3 A({a3[qid]['abstain']}): {(a3[qid]['answer'] or '')[:600]}")
            print(f"-- {side} v4 ctx={a4[qid]['ctx_ids']}  reused={a4[qid].get('reused_from')}")
            print(f"   v4 A({a4[qid]['abstain']}): {(a4[qid]['answer'] or '')[:600]}")
            print(f"   v4 cites: {a4[qid]['cite_ids']}")


if __name__ == "__main__":
    main()
