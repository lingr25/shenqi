# -*- coding: utf-8 -*-
"""校验 evidence_round1：引用真实、时刻对应原文、无孤链、分类分离。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TS = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")
errs = []


def loadj(name):
    return [json.loads(l) for l in open(os.path.join(HERE, name), encoding="utf-8") if l.strip()]


def file_index(rel):
    path = os.path.join(ROOT, rel)
    idx = {}
    if not os.path.exists(path):
        errs.append(f"missing file {rel}")
        return idx
    for line in open(path, encoding="utf-8"):
        m = TS.match(line.rstrip())
        if not m:
            continue
        h = int(m.group(1) or 0)
        sec = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        idx[sec] = m.group(4)
    return idx


def main():
    packets = loadj("evidence_packets.jsonl")
    mechs = loadj("mechanisms.jsonl")
    exps = loadj("experiments.jsonl")
    rejs = loadj("rejected.jsonl")
    cache = {}

    def idx(rel):
        if rel not in cache:
            cache[rel] = file_index(rel)
        return cache[rel]

    pkt_by = {p["topic_id"]: p for p in packets}
    pkt_ts = {p["topic_id"]: {ln["t"]: ln["text"] for ln in p["lines"]} for p in packets}

    for p in packets:
        rel = p["source"]["file"]
        ix = idx(rel)
        if p["line_count"] != len(p["lines"]):
            errs.append(f"{p['topic_id']} line_count mismatch")
        if p["line_count"] < 1:
            errs.append(f"{p['topic_id']} empty packet")
        for ln in p["lines"]:
            if ln["t"] not in ix:
                errs.append(f"{p['topic_id']} t={ln['t']} not in {rel}")
            elif ix[ln["t"]] != ln["text"]:
                errs.append(f"{p['topic_id']} t={ln['t']} text != file")
            if not (p["source"]["t_start"] <= ln["t"] <= p["source"]["t_end"]):
                errs.append(f"{p['topic_id']} t={ln['t']} outside span")

    mech_ids = {m["id"] for m in mechs}
    exp_ids = {e["id"] for e in exps}
    der_ids = {m["id"] for m in mechs if m.get("record_type") == "derivation"}

    def check_ev(rec, kind):
        for e in rec.get("evidence") or []:
            tid = e["topic_id"]
            if tid not in pkt_ts:
                errs.append(f"{kind} {rec.get('id')} unknown topic {tid}")
                continue
            if e["t"] not in pkt_ts[tid]:
                errs.append(f"{kind} {rec.get('id')} t={e['t']} not in packet {tid}")
            elif pkt_ts[tid][e["t"]] != e["text"]:
                errs.append(f"{kind} {rec.get('id')} t={e['t']} quote != packet")
            if e.get("file") != pkt_by[tid]["source"]["file"]:
                errs.append(f"{kind} {rec.get('id')} file mismatch")

    ok_el = {"accepted", "context_only", "needs_av"}
    for m in mechs:
        if m.get("eligibility") not in ok_el:
            errs.append(f"{m.get('id')} bad eligibility")
        want_gate = m.get("record_type") == "mechanism" and m.get("eligibility") == "accepted"
        if bool(m.get("rag_gate")) != want_gate:
            errs.append(f"{m.get('id')} rag_gate mismatch")
        if m.get("record_type") == "mechanism" and m.get("eligibility") == "accepted":
            bad = ("1/10=3/30", "1/10是3/30", "2.1→3", "已经完成索敌", "例外：精粹", "例外:精粹")
            t = m.get("text") or ""
            for b in bad:
                if b in t:
                    errs.append(f"{m['id']} accepted mechanism contains forbidden {b!r}")
        check_ev(m, "mech")
        if m["topic_id"] in ("T10", "T11", "T12"):
            errs.append(f"mechanism on reject topic {m['id']}")
        for x in m.get("linked_experiments") or []:
            if x not in exp_ids:
                errs.append(f"orphan exp link {m['id']} -> {x}")
        for x in m.get("linked_derivations") or []:
            if x not in der_ids and x not in mech_ids:
                errs.append(f"orphan der link {m['id']} -> {x}")

    for e in exps:
        if e.get("eligibility") not in ok_el:
            errs.append(f"{e.get('id')} bad eligibility")
        check_ev(e, "exp")
        for x in e.get("linked_mechanisms") or []:
            if x not in mech_ids:
                errs.append(f"orphan mech link {e['id']} -> {x}")

    # reverse: every linked_experiments should be pointed from that exp
    for m in mechs:
        for eid in m.get("linked_experiments") or []:
            exp = next(x for x in exps if x["id"] == eid)
            if m["id"] not in (exp.get("linked_mechanisms") or []) and m.get("record_type") != "derivation":
                # derivations may only sit on linked_derivations of exp
                if m["id"] not in (exp.get("linked_derivations") or []):
                    errs.append(f"one-way link {m['id']} -> {eid}")

    buckets = {p["topic_id"]: p["bucket"] for p in packets}
    if sum(1 for b in buckets.values() if b == "recoverable") != 6:
        errs.append("need 6 recoverable")
    if sum(1 for b in buckets.values() if b == "experiment_risk") != 3:
        errs.append("need 3 experiment_risk")
    if sum(1 for b in buckets.values() if b == "reject_negative") != 3:
        errs.append("need 3 reject_negative")

    asr_ok = all(p["source"]["layer"] == "asr_draft" for p in packets if p["source"]["file"].startswith("asr_drafts/"))
    off_ok = all(p["source"]["layer"] == "official_txt" for p in packets if p["source"]["file"].startswith("transcripts_txt/"))
    if not asr_ok or not off_ok:
        errs.append("layer vs path mismatch")

    out = {"ok": not errs, "errors": errs, "n_err": len(errs),
           "packets": len(packets), "mechs": len(mechs), "exps": len(exps), "rejs": len(rejs)}
    print(json.dumps(out, ensure_ascii=False, indent=2 if errs else None))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
