# -*- coding: utf-8 -*-
"""把 v4 合成打成试验检索库，不覆盖 kb/docs.jsonl。"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

QPATH = os.path.join(ROOT, "kb_pilot_synth/retest_round2/quarantine.jsonl")
# v4 抽审确认把未闭合「0.5帧/冷却加一」写成 universal，不覆盖旧卡
NO_SUPERSEDE = {
    "帧时序与计时器-39-6",
}
DROP_CLUSTERS = {
    "帧时序与计时器-24-0", "索敌-0-1", "索敌-1-0", "帧时序与计时器-46-2",
    "位移-1-5", "帧时序与计时器-43-1", "索敌-22-7", "帧时序与计时器-3-10",
    "寻路-7-8", "其他-6-1", "寻路-36-6", "技能特例-16-7",
}


def scrub(s):
    s = s or ""
    s = re.sub(r"QQ[:：]?\s*\d{5,}", "QQ:[id]", s)
    s = re.sub(r"(?<!\d)[1-9]\d{6,11}(?!\d)", "[id]", s)
    return s


def load_q():
    drop, down = set(), set()
    p = QPATH
    if os.path.isfile(p):
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            if r.get("action") == "drop":
                drop.add(r["id"])
            elif r.get("action") == "downweight":
                down.add(r["id"])
    return drop, down


def main():
    drop, down = load_q()
    synth = {}
    cdir = os.path.join(HERE, "cache_items")
    if os.path.isdir(cdir):
        for fn in os.listdir(cdir):
            if not fn.endswith(".json"):
                continue
            rec = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
            r = rec.get("result") or {}
            if rec.get("error") or not r.get("_text"):
                continue
            cid = rec.get("cluster_id")
            synth[cid] = {
                "cluster_id": cid,
                "text": r.get("_text"),
                "kind": r.get("kind"),
                "scope": r.get("scope"),
                "confidence": r.get("confidence"),
                "context_incomplete": r.get("context_incomplete"),
            }
    sp = os.path.join(HERE, "synthesized_v4.jsonl")
    if os.path.isfile(sp):
        for l in open(sp, encoding="utf-8"):
            r = json.loads(l)
            synth[r["cluster_id"]] = r
    extras = [{
        "id": "er1:M05-blink-not-teleport",
        "doc_type": "pilot_context_only",
        "track": "vod_official",
        "status": "draft",
        "retrieval_boost": 1.0,
        "retrieval_weight": 1.0,
        "text": "[context_only|不得当第五种|不得等同传送] 口播在四种移动之后补一句「瞬移直接改写坐标，大概是这四种」。不是独立第五种，也没有把瞬移等同传送。",
        "supersedes": [],
    }]
    for er in ("kb_pilot_synth/evidence_round1/mechanisms.jsonl",
               "kb_pilot_synth/evidence_round1/experiments.jsonl"):
        if not os.path.isfile(er):
            continue
        for l in open(er, encoding="utf-8"):
            m = json.loads(l)
            elig = m.get("eligibility")
            rag = bool(m.get("rag_gate"))
            if elig == "needs_av":
                boost, gate = 0.4, "NEEDS_AV_不得当已知"
            elif rag:
                boost, gate = 1.6, "RAG_OK"
            else:
                boost, gate = 0.9, "NOT_RAG_FACT"
            extras.append({
                "id": "er1:" + m["id"],
                "doc_type": "pilot_" + (m.get("record_type") or "mech"),
                "track": "vod_official",
                "status": "draft",
                "retrieval_boost": boost,
                "retrieval_weight": 1.0,
                "text": f"[{gate}] {m.get('subject')}: {m.get('text')}",
                "supersedes": [],
            })
    n_drop = n_down = n_entry = 0
    out = []
    with open("kb/docs.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("status") == "noise":
                continue
            did = d.get("id") or ""
            if did in drop:
                n_drop += 1
                continue
            if d.get("doc_type") == "vod_entry":
                cid = (d.get("links") or {}).get("cluster_id") or ""
                if cid in NO_SUPERSEDE:
                    out.append(d)
                    continue
                if cid in DROP_CLUSTERS or cid in synth:
                    n_drop += 1
                    continue
            if did in down:
                d = dict(d)
                d["retrieval_boost"] = 0.15
                d["retrieval_weight"] = 0.3
                n_down += 1
            out.append(d)
    for cid, s in synth.items():
        kind = s.get("kind") or "mechanism"
        if kind == "reject":
            continue
        # instance 标成 mechanism 仍按实验降权，避免轴/开局卡伪装通则
        if s.get("scope") in ("instance", "example") or kind == "experiment":
            kind_eff = "experiment"
        else:
            kind_eff = kind
        boost = 1.5 if kind_eff == "mechanism" and s.get("scope") == "universal" else 1.1
        if kind_eff == "experiment" or s.get("scope") in ("instance", "example"):
            boost = 0.85
        if kind == "pending" or s.get("context_incomplete"):
            boost = 0.4
        if cid in NO_SUPERSEDE:
            boost = 0.35
        if s.get("confidence") == "low":
            boost *= 0.7
        extras.append({
            "id": "fc1:" + cid,
            "doc_type": "pilot_v4_entry",
            "track": "vod_official",
            "status": "draft",
            "retrieval_boost": round(boost, 3),
            "retrieval_weight": 1.0,
            "text": scrub(s.get("text") or ""),
            "supersedes": [] if cid in NO_SUPERSEDE else [f"vod_entry:{cid}"],
            "kind": kind,
            "scope": s.get("scope"),
        })
        n_entry += 1
    trial = out + extras
    op = os.path.join(HERE, "trial_docs.jsonl")
    with open(op, "w", encoding="utf-8") as f:
        for d in trial:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(json.dumps({
        "trial_docs": len(trial), "prod_kept": len(out), "extras": len(extras),
        "dropped": n_drop, "downweighted": n_down, "v4_entries": n_entry,
        "out": op,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
