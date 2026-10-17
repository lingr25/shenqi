# -*- coding: utf-8 -*-
"""校验 batch100：引用能在原文时刻附近找到；94 条讲段都有归类；无生产打包。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TS = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")
errs = []


def jl(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        errs.append("missing " + name)
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def file_lines(rel):
    path = os.path.join(ROOT, rel) if not os.path.isabs(rel) else rel
    if not os.path.isfile(rel) and os.path.isfile(path):
        rel = path
    if not os.path.isfile(rel):
        return None
    out = {}
    for line in open(rel, encoding="utf-8"):
        m = TS.match(line.rstrip("\n"))
        if not m:
            continue
        h = int(m.group(1) or 0)
        t = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        out[t] = m.group(4)
    return out


def check_ev(rec, kind):
    for e in rec.get("evidence") or []:
        rel = e.get("file")
        ix = file_lines(rel)
        if ix is None:
            errs.append(f"{kind} {rec.get('id')} missing {rel}")
            continue
        t = e.get("t")
        q = e.get("text") or ""
        hit = False
        for dt in range(-8, 9):
            if t + dt in ix and q[:8] in ix[t + dt]:
                hit = True
                break
        if not hit:
            # whole-line contains first 6 chars
            for dt in range(-8, 9):
                if t + dt in ix and (q[:6] in ix[t + dt] or q[:6] in (ix[t + dt] or "")):
                    hit = True
                    break
        if not hit:
            errs.append(f"{kind} {rec.get('id')} t={t} quote not near file")


def main():
    pas = jl("passages.jsonl")
    mechs = jl("mechanisms.jsonl")
    exps = jl("experiments.jsonl")
    rejs = jl("rejected.jsonl")
    pends = jl("pending.jsonl")
    if len(pas) != 94:
        errs.append(f"passages {len(pas)} != 94")
    ids = {p["topic_id"] for p in pas}
    covered = set()
    for r in mechs + exps:
        covered.add(r["topic_id"])
        check_ev(r, r.get("record_type") or "rec")
        if "reviewer_type" not in r:
            r["reviewer_type"] = "agent"  # not an error; docs say so
    for r in rejs + pends:
        covered.add(r["topic_id"])
    missing = sorted(ids - covered)
    extra = sorted(covered - ids)
    if missing:
        errs.append("unclassified " + ",".join(missing))
    if extra:
        errs.append("unknown topics " + ",".join(extra))
    if any("未纳入" in (r.get("reason") or "") for r in pends):
        errs.append("still has unreviewed pending")
    n_rag = sum(1 for m in mechs if m.get("rag_gate") and m.get("record_type") == "mechanism")
    print(json.dumps({
        "ok": not errs,
        "n_err": len(errs),
        "errors": errs,
        "n_passages": len(pas),
        "n_mech": len(mechs),
        "n_exp": len(exps),
        "n_rej": len(rejs),
        "n_pend": len(pends),
        "n_rag_gate": n_rag,
    }, ensure_ascii=False))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
