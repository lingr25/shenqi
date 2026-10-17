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
    frozen = json.load(open(os.path.join(HERE, "questions_frozen.json"), encoding="utf-8"))
    h = hashlib.sha256(open(os.path.join(HERE, "questions.jsonl"), "rb").read()).hexdigest()
    if h != frozen.get("sha256"):
        errs.append("questions hash != frozen")
    if len(qs) != 20:
        errs.append(f"need 20 questions got {len(qs)}")
    types = {q["type"] for q in qs}
    for t in ("direct", "misleading", "insufficient", "boundary", "citation"):
        if t not in types:
            errs.append("missing type " + t)

    merges = jl("cross_merge.jsonl")
    if len(merges) != 5:
        errs.append(f"need 5 merge topics got {len(merges)}")
    for m in merges:
        if m.get("vod_wins_applied"):
            errs.append(m["topic_id"] + " vod_wins_applied")
        if m.get("priority") not in (None, "none"):
            errs.append(m["topic_id"] + " unexpected priority")
        blob = json.dumps(m, ensure_ascii=False)
        if re.search(r"QQ[:：]?\s*\d{6,}", blob):
            errs.append("privacy QQ number in " + m["topic_id"])

    old = jl("answers_old.jsonl")
    new = jl("answers_new.jsonl")
    if old and new:
        if len(old) != 20 or len(new) != 20:
            errs.append(f"answers count old={len(old)} new={len(new)}")
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
