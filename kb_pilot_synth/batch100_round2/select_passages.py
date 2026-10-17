# -*- coding: utf-8 -*-
"""纯本地：从未做过的 vod_cluster 抽完整讲段。不写生产、不调用 LLM。"""
import json
import os
import random
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
TS = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")

DONE = {
    "帧时序与计时器-24-0", "索敌-0-1", "索敌-1-0", "帧时序与计时器-46-2",
    "位移-1-5", "帧时序与计时器-43-1", "索敌-22-7", "帧时序与计时器-3-10",
    "寻路-7-8", "其他-6-1", "寻路-36-6", "技能特例-16-7",
}
PER_CAT = 18
TARGET = 100
PAD = 8
MAX_SPAN = 180
RNG = random.Random(20260920)


def load_docs():
    clusters, atoms = {}, {}
    with open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            dt = d.get("doc_type")
            if dt == "vod_cluster":
                cid = (d.get("links") or {}).get("cluster_id") or d["id"].replace("vod_cluster:", "")
                clusters[cid] = d
            elif dt == "vod_atom":
                atoms[d.get("atom_id") or d["id"].replace("vod_atom:", "")] = d
                atoms[d["id"]] = d
    return clusters, atoms


def resolve_file(stem):
    off = os.path.join(ROOT, "transcripts_txt", stem + ".txt")
    asr = os.path.join(ROOT, "asr_drafts", stem + "_asr.txt")
    if os.path.isfile(off):
        return "transcripts_txt/" + stem + ".txt", "official_txt"
    if os.path.isfile(asr):
        return "asr_drafts/" + stem + "_asr.txt", "asr_draft"
    return None, None


def load_rows(rel):
    path = os.path.join(ROOT, rel)
    rows = []
    for line in open(path, encoding="utf-8"):
        raw = line.rstrip("\n")
        m = TS.match(raw)
        if not m:
            continue
        h = int(m.group(1) or 0)
        sec = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        rows.append({"t": sec, "text": m.group(4), "raw": raw})
    return rows


def atom_times(a):
    ev = a.get("evidence") or {}
    clips = ev.get("clips") or []
    out = []
    for c in clips:
        if "t_start" in c:
            out.append(int(c["t_start"]))
        if "t_end" in c:
            out.append(int(c["t_end"]))
    return out


def risk_flags(text):
    flags = []
    if re.search(r"\d", text):
        flags.append("has_number")
    if re.search(r"[0-9.]+(帧|秒|格|倍|针)", text):
        flags.append("unit_number")
    if "补整" in text or "加一" in text:
        flags.append("plus_one")
    if re.search(r"0\.05|1/10|3/30", text):
        flags.append("radius_formula")
    if "该次" in text or "演示" in text or "部署" in text and re.search(r"\d+\s*帧", text):
        flags.append("experimentish")
    subj_weak = ("适用对象: 通用" in text) or ("未点名" in text)
    if subj_weak:
        flags.append("weak_subject")
    return flags


def slice_rows(rows, t0, t1):
    return [r for r in rows if t0 <= r["t"] <= t1]


def main():
    os.makedirs(HERE, exist_ok=True)
    clusters, atoms = load_docs()
    cands_by_cat = defaultdict(list)
    skip = Counterish = defaultdict(int)
    reasons = defaultdict(int)

    for cid, c in clusters.items():
        if cid in DONE:
            reasons["already_round1"] += 1
            continue
        if c.get("status") == "noise":
            reasons["noise"] += 1
            continue
        if c.get("issue_status") != "agreed":
            reasons["not_agreed"] += 1
            continue
        n = c.get("member_count") or len((c.get("links") or {}).get("member_atom_ids") or [])
        if n < 4 or n > 25:
            reasons["member_count"] += 1
            continue
        cat = c.get("category") or "其他"
        mids = (c.get("links") or {}).get("member_atom_ids") or []
        stems = set()
        times = []
        for mid in mids:
            a = atoms.get(mid) or atoms.get("vod_atom:" + mid)
            if not a:
                continue
            stem = (a.get("source") or {}).get("bvid_stem")
            if stem:
                stems.add(stem)
            times.extend(atom_times(a))
        if not stems or not times:
            reasons["no_time"] += 1
            continue
        # 单文件优先，完整语段
        if len(stems) != 1:
            reasons["multi_stem"] += 1
            continue
        stem = next(iter(stems))
        rel, layer = resolve_file(stem)
        if not rel:
            reasons["no_file"] += 1
            continue
        cands_by_cat[cat].append({
            "cluster_id": cid,
            "category": cat,
            "member_count": n,
            "stem": stem,
            "file": rel,
            "layer": layer,
            "t_min": min(times),
            "t_max": max(times),
            "issue_status": c.get("issue_status"),
            "text_head": (c.get("text") or "").split("\n", 1)[0][:80],
        })

    selected = []
    leftover = []
    for cat, rows in sorted(cands_by_cat.items(), key=lambda x: -len(x[1])):
        RNG.shuffle(rows)
        take = rows[:PER_CAT]
        rest = rows[PER_CAT:]
        selected.extend(take)
        leftover.extend(rest)
    RNG.shuffle(leftover)
    if len(selected) < TARGET:
        selected.extend(leftover[: TARGET - len(selected)])
    selected = selected[:TARGET]

    packets = []
    failed_span = 0
    for i, s in enumerate(selected, 1):
        rows = load_rows(s["file"])
        t0 = max(0, s["t_min"] - PAD)
        t1 = s["t_max"] + PAD
        if t1 - t0 > MAX_SPAN:
            # 收束到原子时间并仍 pad，超长则截 max span 居中
            mid = (s["t_min"] + s["t_max"]) // 2
            t0 = max(0, mid - MAX_SPAN // 2)
            t1 = t0 + MAX_SPAN
            s["truncated"] = True
        else:
            s["truncated"] = False
        lines = slice_rows(rows, t0, t1)
        if len(lines) < 3:
            failed_span += 1
            continue
        blob = "\n".join(r["raw"] for r in lines)
        flags = risk_flags(blob + "\n" + (s["text_head"] or ""))
        high = bool(set(flags) & {"unit_number", "plus_one", "radius_formula", "weak_subject"})
        topic_id = f"B{i:03d}"
        packets.append({
            "topic_id": topic_id,
            "cluster_id": s["cluster_id"],
            "category": s["category"],
            "file": s["file"],
            "layer": s["layer"],
            "t0": t0,
            "t1": t1,
            "n_lines": len(lines),
            "truncated": s["truncated"],
            "member_count": s["member_count"],
            "text_head": s["text_head"],
            "risk_flags": flags,
            "risk": "high" if high else "low",
            "lines": [{"t": r["t"], "text": r["text"]} for r in lines],
        })

    with open(os.path.join(HERE, "passages.jsonl"), "w", encoding="utf-8") as f:
        for p in packets:
            slim = {k: p[k] for k in p if k != "lines"}
            slim["passage"] = "\n".join(f"[{x['t']}] {x['text']}" for x in p["lines"])
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

    high = [p for p in packets if p["risk"] == "high"]
    low = [p for p in packets if p["risk"] == "low"]
    sample20 = RNG.sample(low, min(20, len(low))) if low else []
    manifest = {
        "target": TARGET,
        "n_packets": len(packets),
        "failed_span": failed_span,
        "n_high": len(high),
        "n_low": len(low),
        "per_cat_cap": PER_CAT,
        "already_done_12": sorted(DONE),
        "candidate_reasons_skip": dict(reasons),
        "cand_by_cat": {k: len(v) for k, v in cands_by_cat.items()},
        "selected_by_cat": dict(Counterish_cat(packets)),
        "high_ids": [p["topic_id"] for p in high],
        "low_sample20": [p["topic_id"] for p in sample20],
        "api_calls": 0,
        "not_game_truth": True,
        "note": "只抽语段，不自动写成机制。LLM 未调用。代理逐条证据审核见 finish_audit 后的 manifest.review。",
    }
    json.dump(manifest, open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({
        "n_packets": len(packets),
        "n_high": len(high),
        "n_low": len(low),
        "skip": dict(reasons),
        "cats": manifest["selected_by_cat"],
    }, ensure_ascii=False))


def Counterish_cat(packets):
    from collections import Counter
    return Counter(p["category"] for p in packets)


if __name__ == "__main__":
    main()
