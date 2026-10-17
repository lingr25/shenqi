# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
errs = []


def jl(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    frozen = json.load(open(os.path.join(HERE, "heldout_frozen.json"), encoding="utf-8"))
    h = hashlib.sha256(open(os.path.join(HERE, "heldout_q.jsonl"), "rb").read()).hexdigest()
    if h != frozen.get("sha256"):
        errs.append("heldout hash mismatch")
    synth = jl("synthesized_v4.jsonl")
    kinds = {}
    for r in synth:
        kinds[r.get("kind") or "?"] = kinds.get(r.get("kind") or "?", 0) + 1
        blob = json.dumps(r.get("text") or "", ensure_ascii=False)
        if re.search(r"QQ[:：]?\s*\d{6,}", blob):
            errs.append("privacy QQ " + r.get("cluster_id"))
        if r.get("kind") == "mechanism":
            for rule in r.get("rules") or []:
                if isinstance(rule, dict) and not rule.get("evidence_atom_ids"):
                    errs.append("mech no evidence " + r.get("cluster_id"))
                    break
    n_cache = 0
    cdir = os.path.join(HERE, "cache_items")
    if os.path.isdir(cdir):
        n_cache = len([x for x in os.listdir(cdir) if x.endswith(".json")])
    print(json.dumps({
        "ok": not errs, "n_err": len(errs), "errors": errs[:20],
        "n_synth": len(synth), "kinds": kinds, "n_cache_items": n_cache,
        "heldout_sha": h[:16],
    }, ensure_ascii=False))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
