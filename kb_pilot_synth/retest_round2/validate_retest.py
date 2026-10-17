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
        errs.append("missing " + name)
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    qs = jl("questions.jsonl")
    held = jl("heldout_q.jsonl")
    frozen = json.load(open(os.path.join(HERE, "questions_frozen.json"), encoding="utf-8"))
    h = hashlib.sha256(open(os.path.join(HERE, "questions.jsonl"), "rb").read()).hexdigest()
    if h != frozen.get("sha256"):
        errs.append("questions hash != frozen")
    if len(qs) != 13:
        errs.append(f"need 13 questions got {len(qs)}")
    if len(held) < 6:
        errs.append(f"need >=6 heldout got {len(held)}")
    types = {q["type"] for q in held}
    for t in ("direct", "misleading", "insufficient", "boundary"):
        if t not in types:
            errs.append("heldout missing type " + t)
    fail_ids = {q["id"] for q in qs if q["id"].startswith("Q")}
    if fail_ids != {"Q03", "Q07", "Q11", "Q13", "Q14", "Q16"}:
        errs.append("fail set mismatch " + str(sorted(fail_ids)))
    if {q["id"] for q in held} & fail_ids:
        errs.append("heldout overlaps fail set")

    qtn = jl("quarantine.jsonl")
    if not qtn:
        errs.append("empty quarantine")
    must = {
        "vod_entry:帧时序与计时器-40-5",
        "vod_atom:BV14y8269EbS_p1_41164079923:p76:a0:da8985bd",
        "canonical:c0014",
        "vod_atom:BV199KH6TEra_p1_40136673556:p46:a13:1f522cdf",
        "vod_atom:BV14VZCB1EJR_p1_36119907781:p115:a2:4ef07b70",
        "vod_entry:帧时序与计时器-12-7",
        "vod_entry:帧时序与计时器-13-6",
    }
    have = {r["id"] for r in qtn}
    for i in must:
        if i not in have:
            errs.append("quarantine missing " + i)
    keep = [r for r in qtn if r.get("action") == "keep_unknown"]
    if not keep:
        errs.append("need at least one keep_unknown")

    old = jl("answers_old.jsonl")
    new = jl("answers_new.jsonl")
    if old and new:
        if len(old) != len(qs) or len(new) != len(qs):
            errs.append(f"answers count old={len(old)} new={len(new)}")
        drop = {r["id"] for r in qtn if r.get("action") == "drop"}
        for row in new:
            leaked = [i for i in (row.get("hit_ids") or []) if i in drop]
            if leaked:
                errs.append(row["id"] + " leaked drop ids " + ",".join(leaked))
        for row in old + new:
            if row.get("ctx_chars", 0) > 3000:
                errs.append(row["id"] + " ctx over budget")
            if not row.get("hit_ids"):
                errs.append(row["id"] + " empty retrieval")
            blob = json.dumps(row.get("answer") or "", ensure_ascii=False)
            if re.search(r"QQ[:：]?\s*\d{6,}", blob):
                errs.append("privacy QQ in answer " + row["id"])

    print(json.dumps({"ok": not errs, "n_err": len(errs), "errors": errs}, ensure_ascii=False))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
