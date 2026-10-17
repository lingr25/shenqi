# -*- coding: utf-8 -*-
"""纯本地: 打印 v4 vs v5 的新面对照(仅 ctx 改变的题), 供代理复核配额的真实效果。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    return {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, p), encoding="utf-8") if l.strip()}


def main():
    qs = load("heldout_q_v2.jsonl")
    a4, a5 = load("answers_v4_new.jsonl"), load("answers_v5_new.jsonl")
    for qid in a5:
        if a5[qid]["ctx_sig"] == a4[qid]["ctx_sig"]:
            continue
        q = qs[qid]
        print("=" * 100)
        print(f"### {qid} ({q['type']}) gold={q.get('gold_ids')}")
        print("Q:", q["q"])
        print("EXPECT:", q.get("expect"))
        print(f"-- LAYER_ONLY(v4) ctx={a4[qid]['ctx_ids']}")
        print(f"   A({a4[qid]['abstain']}): {(a4[qid]['answer'] or '')[:700]}")
        print(f"-- OFF(v5)       ctx={a5[qid]['ctx_ids']}")
        print(f"   A({a5[qid]['abstain']}): {(a5[qid]['answer'] or '')[:700]}")
        print(f"   cites={a5[qid]['cite_ids']}")


if __name__ == "__main__":
    main()
