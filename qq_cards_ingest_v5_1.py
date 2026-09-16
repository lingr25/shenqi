#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_ingest_v5_1.py
-----------------------
合并子代理补跑批次（reclass 002/003、novelty 分段），全量覆盖入库。
批次文件与主文件 window_id 冲突时批次优先；w000271–w000374 强制用 41-60。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qq_cards_ingest_v5 import (
    MANUAL_CONFLICTS,
    NEW_CATS,
    NOV_ENUM,
    apply_novelty,
    apply_reclass,
    patch_readme,
)
from qq_cards_ingest_rag import rebuild_rag
from qq_cards_rag_prep import (
    ALIAS_PATH,
    CANON_PATH,
    CARDS_PATH,
    RAG_PATH,
    privacy_scan,
)
from qq_cards_rag_ready import (
    GLOSSARY_PATH,
    alias_lookup,
    apply_boost_and_glossary_meta,
    link_glossary,
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
RECLASS_DIR = os.path.join(ROOT_DIR, "qq_info", "subagent_reclass")
NOVELTY_DIR = os.path.join(ROOT_DIR, "qq_info", "subagent_novelty")
MERGED_RECLASS = os.path.join(RECLASS_DIR, "out_reclass_merged.jsonl")
MERGED_NOVELTY = os.path.join(NOVELTY_DIR, "out_novelty_merged.jsonl")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "ingest_v5_1_report.md")
FORCE_NOVELTY = os.path.join(NOVELTY_DIR, "out_novelty_41-60.jsonl")
FORCE_LO, FORCE_HI = "w000271", "w000374"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def dump_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_garbled(s: Any) -> bool:
    if s is None:
        return False
    t = s if isinstance(s, str) else str(s)
    if "\ufffd" in t or "�" in t:
        return True
    if re.search(r"Ã.|Â.|æ.|å.|ä.|ç.", t) and not re.search(r"[\u4e00-\u9fff]", t) and len(t) > 8:
        return True
    return False


def merge_reclass() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    main = os.path.join(RECLASS_DIR, "out_reclass.jsonl")
    extras = sorted(
        p
        for p in glob.glob(os.path.join(RECLASS_DIR, "out_reclass_*.jsonl"))
        if not os.path.basename(p).startswith("out_reclass_merged")
    )
    merged: dict[str, dict[str, Any]] = {}
    overrides = 0
    for r in load_jsonl(main):
        merged[r["window_id"]] = r
    for p in extras:
        for r in load_jsonl(p):
            if r["window_id"] in merged:
                overrides += 1
            merged[r["window_id"]] = r
    rows = [merged[k] for k in sorted(merged)]
    garbled = [
        r["window_id"]
        for r in rows
        if is_garbled(r.get("reason") or "") or is_garbled(r.get("new_category") or "")
    ]
    bad_cat = [r["window_id"] for r in rows if r.get("new_category") not in NEW_CATS]
    stats = {
        "n": len(rows),
        "overrides": overrides,
        "garbled": garbled,
        "bad_cat": bad_cat,
        "dist": dict(Counter(r.get("new_category") for r in rows)),
        "dups": 0,
    }
    return rows, stats


def merge_novelty() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    main = os.path.join(NOVELTY_DIR, "out_novelty.jsonl")
    batches = sorted(
        p
        for p in glob.glob(os.path.join(NOVELTY_DIR, "out_novelty_*.jsonl"))
        if "merged" not in os.path.basename(p)
    )
    merged: dict[str, dict[str, Any]] = {}
    overrides = 0
    for r in load_jsonl(main):
        merged[r["window_id"]] = r
    for p in batches:
        for r in load_jsonl(p):
            if r["window_id"] in merged:
                overrides += 1
            merged[r["window_id"]] = r
    if os.path.exists(FORCE_NOVELTY):
        for r in load_jsonl(FORCE_NOVELTY):
            merged[r["window_id"]] = r
    rows = [merged[k] for k in sorted(merged)]
    garbled = []
    for r in rows:
        if is_garbled(r.get("reason") or "") or is_garbled(r.get("evidence") or ""):
            garbled.append(r["window_id"])
    bad = [r["window_id"] for r in rows if r.get("novelty") not in NOV_ENUM]
    conflict_empty = [
        r["window_id"]
        for r in rows
        if r.get("novelty") == "conflict" and not (r.get("evidence") or "").strip()
    ]
    stats = {
        "n": len(rows),
        "overrides": overrides,
        "garbled": garbled,
        "bad": bad,
        "conflict_empty": conflict_empty,
        "dist": dict(Counter(r.get("novelty") for r in rows)),
        "conflicts": [r["window_id"] for r in rows if r.get("novelty") == "conflict"],
        "force_range": [w for w in merged if FORCE_LO <= w <= FORCE_HI],
    }
    return rows, stats


def confirm_conflicts(cards: list[dict[str, Any]]) -> list[str]:
    notes = []
    by = {c["window_id"]: c for c in cards}
    for wid, spec in MANUAL_CONFLICTS.items():
        c = by.get(wid)
        if not c:
            notes.append(f"{wid} 缺失")
            continue
        ok = (
            c.get("novelty") == "conflict"
            and c.get("conflict_resolution") == "vod_wins"
            and spec["takeaway"][:12] in (c.get("summary_takeaway") or "")
        )
        notes.append(
            f"{wid} novelty={c.get('novelty')} resolution={c.get('conflict_resolution')} "
            f"takeaway_ok={ok} note={bool(c.get('conflict_note'))}"
        )
    return notes


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="v5.1 merge leftover batches").parse_args(argv)
    cards = load_jsonl(CARDS_PATH)
    glossary = load_jsonl(GLOSSARY_PATH)
    canon = load_jsonl(CANON_PATH)
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))

    reclass, re_st = merge_reclass()
    novelty, nv_st = merge_novelty()
    dump_jsonl(MERGED_RECLASS, reclass)
    dump_jsonl(MERGED_NOVELTY, novelty)

    n_re = apply_reclass(cards, reclass)
    nv_stats = apply_novelty(cards, novelty)
    dump_jsonl(CARDS_PATH, cards)

    lookup = alias_lookup(aliases)
    docs = rebuild_rag(cards, canon, glossary, aliases)
    glossary, gstats = link_glossary(glossary, docs, lookup)
    docs = apply_boost_and_glossary_meta(docs, glossary, cards)
    dump_jsonl(GLOSSARY_PATH, glossary)
    dump_jsonl(RAG_PATH, docs)

    other_left = sum(
        1
        for c in cards
        if c.get("category") == "其他" and c.get("status", "draft") == "draft"
    )
    patch_readme(n_re, re_st["dist"], nv_stats, len(docs), other_left)
    hits = privacy_scan()
    conflict_notes = confirm_conflicts(cards)

    nov_all = Counter(c.get("novelty") for c in cards)
    today = date.today().isoformat()
    report = [
        "# v5.1 批次合并入库报告",
        "",
        f"日期：{today}",
        "",
        "## 乱码 / 覆盖",
        "",
        f"- reclass 合并 {re_st['n']}（批次覆盖 {re_st['overrides']}）；乱码 {re_st['garbled'] or '无'}；非法类别 {re_st['bad_cat'] or '无'}",
        f"- novelty 合并 {nv_st['n']}（批次覆盖 {nv_st['overrides']}）；乱码 {nv_st['garbled'] or '无'}；非法枚举 {nv_st['bad'] or '无'}",
        f"- conflict evidence 空：{nv_st['conflict_empty'] or '无'}；jsonl conflict：{nv_st['conflicts']}",
        f"- 强制 41-60 覆盖窗：{len(nv_st['force_range'])}（{FORCE_LO}–{FORCE_HI}）",
        "",
        "## reclass 十类",
        "",
    ]
    for k, v in sorted(re_st["dist"].items(), key=lambda x: -x[1]):
        report.append(f"- {k}：{v}")
    report += [
        "",
        f"- 写入 cards：{n_re}；仍为「其他」draft：{other_left}",
        "",
        "## novelty 复核（257 行）",
        "",
        f"- 行内分布：{nv_st['dist']}",
        f"- 写入 also_in_vod：{nv_stats['also_in_vod']}；conflict：{nv_stats['conflict']}；仍 group_only：{nv_stats['group_only']}",
        f"- 全库 novelty：{dict(nov_all)}（复核前约 group_only 397 / also_in_vod 56 / conflict 1）",
        "",
        "## conflict 卡",
        "",
    ]
    report.extend(f"- {n}" for n in conflict_notes)
    report += [
        "",
        f"- rag_docs：{len(docs)}；glossary 挂载 {gstats['with_links']}/{gstats['n']}；隐私 {len(hits)}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print(
        f"reclass={re_st['n']} novelty={nv_st['n']} "
        f"vod={nv_stats['also_in_vod']} conflict={nv_stats['conflict']} "
        f"rag={len(docs)} garbled_re={len(re_st['garbled'])} garbled_nv={len(nv_st['garbled'])} "
        f"privacy={len(hits)}"
    )
    if hits or len(docs) != 869 or re_st["n"] != 146 or nv_st["n"] != 257:
        return 1
    if re_st["garbled"] or nv_st["garbled"] or re_st["bad_cat"] or nv_st["bad"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
