# -*- coding: utf-8 -*-
"""按显式 cluster_id 列表打印逐条证据视图。用法: python show_ids.py file.json"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import kb_synthesize as S  # noqa: E402


def safe(c):
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", c)[:180]


def main():
    ids = json.load(open(sys.argv[1], encoding="utf-8"))
    atoms = S.load_source_atoms(correct_quotes=False)
    by_id = {}
    for l in open("kb/docs.jsonl", encoding="utf-8"):
        d = json.loads(l)
        by_id[d["id"]] = d
    for cid in ids:
        p = os.path.join(HERE, "cache_items", safe(cid) + ".json")
        if not os.path.isfile(p):
            print(f"=== [{cid}] MISSING CACHE")
            continue
        r = json.load(open(p, encoding="utf-8"))
        if r.get("error"):
            print(f"=== [{cid}] CALL ERROR: {r['error'][:120]}")
            continue
        res = r["result"]
        cl = by_id.get("vod_cluster:" + cid) or {}
        print(f"=== [{cid}] cat={r.get('category')} issue={r.get('issue_status')} mem={r.get('n_members')}")
        print(f"  kind={res.get('kind')} scope={res.get('scope')} conf={res.get('confidence')} "
              f"inc={res.get('context_incomplete')}")
        print(f"  title: {res.get('title')} | applies_to: {res.get('applies_to')}")
        for x in res.get("rules") or []:
            if isinstance(x, dict):
                print(f"   R: {x.get('text')}")
                print(f"      subj={x.get('subject')} when={x.get('when')} ev={x.get('evidence_atom_ids')}")
            else:
                print(f"   R: {x}")
        if res.get("exceptions"):
            print(f"   EXC: {res['exceptions']}")
        if res.get("open_questions"):
            print(f"   OQ: {res['open_questions']}")
        mids = (cl.get("links") or {}).get("member_atom_ids") or []
        for m in mids[:6]:
            a = atoms.get(m)
            if not a:
                continue
            print(f"   - [{a.get('claim_type')}|obj={a.get('applies_to')}] {a.get('proposition')}")
            for q in (a.get("evidence") or [])[:1]:
                print(f"       q: {str(q.get('quote'))[:160]}")
        print()


if __name__ == "__main__":
    main()
