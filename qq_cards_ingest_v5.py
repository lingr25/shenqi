#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_ingest_v5.py
---------------------
校验并入库子代理 glossary / reclass / novelty 结果。
"""

from __future__ import annotations

import argparse
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

from qq_cards_ingest_rag import rebuild_rag
from qq_cards_rag_prep import (
    ALIAS_PATH,
    CANON_PATH,
    CARDS_PATH,
    RAG_PATH,
    README_PATH,
    privacy_scan,
)
from qq_cards_rag_ready import (
    GLOSSARY_PATH,
    alias_lookup,
    apply_boost_and_glossary_meta,
    link_glossary,
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
RECLASS_PATH = os.path.join(ROOT_DIR, "qq_info", "subagent_reclass", "out_reclass.jsonl")
NOVELTY_PATH = os.path.join(ROOT_DIR, "qq_info", "subagent_novelty", "out_novelty.jsonl")
GLOSS_OUT_DIR = os.path.join(ROOT_DIR, "qq_info", "subagent_glossary")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "ingest_v5_report.md")

NEW_CATS = {
    "索敌",
    "帧时序",
    "位移",
    "寻路",
    "伤害结算",
    "拆包数据",
    "干员机制",
    "关卡与出怪",
    "数值与读图",
    "其他",
}
NOV_ENUM = {"group_only", "also_in_vod", "conflict", "unknown"}
MANUAL_CONFLICTS = {
    "w000416": {
        "evidence": "录播明确可撤重构体换位跳",
        "reason": "群聊「不能手动撤退重构体」与录播相反",
        "takeaway": (
            "以录播为准：重构体可以手动撤退做换位跳；"
            "群聊曾持「不能手动撤退重构体」之说，已被录播否决。"
        ),
        "conflict_note": "原群聊结论：不能手动撤退重构体；弧光跳跃看重构体撤退/死亡动画。",
    },
    "w000554": {
        "evidence": "首先一针要先结算摩擦力……然后的话是推拉力",
        "reason": "录播顺序为摩擦→加力→位移，与卡内加力、磨损、位移相反",
        "takeaway": (
            "以录播为准：位移结算顺序为先摩擦力→推拉力→失衡移动；"
            "群聊「加力、磨损、位移」顺序与录播相反，以录播为准。"
        ),
        "conflict_note": "原群聊结论：位移结算按加力、磨损、位移循环。",
    },
}


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


def load_glossary_outs() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not os.path.isdir(GLOSS_OUT_DIR):
        return out
    for name in os.listdir(GLOSS_OUT_DIR):
        if not name.startswith("out_") or not name.endswith(".json"):
            continue
        path = os.path.join(GLOSS_OUT_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        term = obj.get("term")
        if term:
            out[term] = obj
    return out


def validate(
    cards: list[dict[str, Any]],
    reclass: list[dict[str, Any]],
    novelty: list[dict[str, Any]],
) -> dict[str, Any]:
    other = {
        c["window_id"]
        for c in cards
        if c.get("category") == "其他" and c.get("status", "draft") == "draft"
    }
    auth_go = {
        c["window_id"]
        for c in cards
        if c.get("novelty") == "group_only"
        and any(
            cc.get("credibility") == "authoritative"
            for cc in (c.get("core_conclusions") or [])
        )
    }
    re_ids = [r.get("window_id") for r in reclass]
    nv_ids = [r.get("window_id") for r in novelty]
    re_set, nv_set = set(re_ids), set(nv_ids)
    bad_cat = [r for r in reclass if r.get("new_category") not in NEW_CATS]
    bad_nov = [r for r in novelty if r.get("novelty") not in NOV_ENUM]
    conflict_empty = [
        r
        for r in novelty
        if r.get("novelty") == "conflict" and not (r.get("evidence") or "").strip()
    ]
    return {
        "other_n": len(other),
        "auth_go_n": len(auth_go),
        "re_n": len(reclass),
        "re_uniq": len(re_set),
        "re_dup": len(re_ids) - len(re_set),
        "re_missing": sorted(other - re_set),
        "re_extra": sorted(re_set - other),
        "re_bad_cat": [r.get("window_id") for r in bad_cat],
        "re_dist": dict(Counter(r.get("new_category") for r in reclass)),
        "nv_n": len(novelty),
        "nv_uniq": len(nv_set),
        "nv_dup": len(nv_ids) - len(nv_set),
        "nv_missing": sorted(auth_go - nv_set),
        "nv_extra": sorted(nv_set - auth_go),
        "nv_bad": [r.get("window_id") for r in bad_nov],
        "nv_dist": dict(Counter(r.get("novelty") for r in novelty)),
        "conflict_empty": [r.get("window_id") for r in conflict_empty],
        "conflict_ids": [r.get("window_id") for r in novelty if r.get("novelty") == "conflict"],
    }


def apply_glossary(
    glossary: list[dict[str, Any]], outs: dict[str, dict[str, Any]]
) -> list[str]:
    notes: list[str] = []
    by = {g.get("term"): g for g in glossary}
    if "阻挡" in outs and "阻挡" in by:
        src = outs["阻挡"]
        g = by["阻挡"]
        g["short_def"] = src.get("short_def") or g.get("short_def")
        g["mechanic_def"] = src.get("mechanic_def") or g.get("mechanic_def")
        g["needs_more_evidence"] = False
        g["confidence"] = src.get("confidence") or "medium"
        g["evidence"] = src.get("evidence") or []
        g["evidence_ref"] = "subagent_v5"
        notes.append("阻挡：mechanic_def 补完，needs_more_evidence=false，confidence=medium")
    for term in ("过伤", "入控", "免控"):
        if term not in outs or term not in by:
            notes.append(f"{term}：无子代理产物，跳过")
            continue
        src = outs[term]
        g = by[term]
        g["short_def"] = src.get("short_def") or g.get("short_def")
        g["mechanic_def"] = src.get("mechanic_def") or "unknown"
        g["needs_more_evidence"] = True
        g["confidence"] = src.get("confidence") or "low"
        g["evidence"] = src.get("evidence") or []
        g["evidence_ref"] = "subagent_v5"
        notes.append(f"{term}：保持 unknown，补 short_def/evidence，confidence=low")
    for term in ("力道", "visitNodeCenter", "TypeTree"):
        notes.append(f"{term}：无子代理产物，维持原样")
    return notes


def apply_reclass(cards: list[dict[str, Any]], reclass: list[dict[str, Any]]) -> int:
    by = {r["window_id"]: r for r in reclass}
    n = 0
    for c in cards:
        row = by.get(c.get("window_id"))
        if not row:
            continue
        newc = row.get("new_category")
        if newc not in NEW_CATS:
            continue
        if c.get("prev_category") is None:
            c["prev_category"] = c.get("category")
        c["category"] = newc
        n += 1
    return n


def apply_novelty(cards: list[dict[str, Any]], novelty: list[dict[str, Any]]) -> dict[str, int]:
    by_card = {c["window_id"]: c for c in cards}
    by_nv = {r["window_id"]: r for r in novelty}
    n_vod = n_conflict = n_keep = 0
    for wid, row in by_nv.items():
        c = by_card.get(wid)
        if not c:
            continue
        nov = row.get("novelty")
        if nov not in NOV_ENUM:
            continue
        old = c.get("novelty")
        c["novelty"] = nov
        if nov == "also_in_vod":
            ev = row.get("evidence") or ""
            if ev:
                c["vod_evidence"] = [ev] if isinstance(ev, str) else ev
            c["novelty_confidence"] = "subagent"
            n_vod += 1
        elif nov == "conflict":
            n_conflict += 1
            spec = MANUAL_CONFLICTS.get(wid, {})
            c["conflict_resolution"] = "vod_wins"
            if spec.get("takeaway"):
                if not c.get("conflict_note"):
                    c["conflict_note"] = spec.get("conflict_note") or (
                        "原群聊 takeaway：" + (c.get("summary_takeaway") or "")
                    )
                c["summary_takeaway"] = spec["takeaway"]
            ev = row.get("evidence") or spec.get("evidence")
            if ev:
                c["vod_evidence"] = [ev] if isinstance(ev, str) else ev
            c["novelty_confidence"] = "subagent"
        elif nov == "group_only":
            n_keep += 1
        _ = old
    # manual conflicts not in jsonl
    for wid, spec in MANUAL_CONFLICTS.items():
        c = by_card.get(wid)
        if not c:
            continue
        if c.get("novelty") == "conflict":
            continue
        c["novelty"] = "conflict"
        c["conflict_resolution"] = "vod_wins"
        c["conflict_note"] = spec["conflict_note"]
        c["summary_takeaway"] = spec["takeaway"]
        c["vod_evidence"] = [spec["evidence"]]
        c["novelty_confidence"] = "subagent"
        n_conflict += 1
    return {"also_in_vod": n_vod, "conflict": n_conflict, "group_only": n_keep}


def patch_readme(
    re_n: int,
    re_dist: dict[str, int],
    nv: dict[str, int],
    n_docs: int,
    other_left: int,
) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    dist_s = "，".join(f"{k} {v}" for k, v in sorted(re_dist.items(), key=lambda x: -x[1]))
    section = f"""
## v5 子代理入库

- 再分类：{re_n} 张原「其他」draft 卡写入新 10 类（{dist_s}）。未覆盖的仍留「其他」（{other_left}）。`prev_category` 保留旧值。
- 新类别：索敌 / 帧时序 / 位移 / 寻路 / 伤害结算 / 拆包数据 / 干员机制 / 关卡与出怪 / 数值与读图 / 其他。
- novelty 复核：also_in_vod 升级 {nv.get('also_in_vod', 0)}；新 conflict {nv.get('conflict', 0)}（`w000416` 重构体可撤、`w000554` 位移顺序摩擦→推力，均 vod_wins）。
- glossary：阻挡补完 mechanic_def（confidence=medium）；过伤/入控/免控仍 unknown 但补了用法 short_def。
- rag_docs 仍 **{n_docs}** 条，boost 规则不变。

"""
    if "## v5 子代理入库" in text:
        text = re.sub(
            r"\n## v5 子代理入库[\s\S]*?(?=\n## |\n\*\*数据边界\*\*)",
            "\n" + section,
            text,
            count=1,
        )
    elif "## v5 RAG" in text:
        text = text.replace("## v5 RAG 挂载与降权", section + "## v5 RAG 挂载与降权", 1)
    else:
        needle = "**数据边界**"
        if needle in text:
            text = text.replace(needle, section + needle, 1)
        else:
            text += "\n" + section
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="ingest subagent v5").parse_args(argv)
    cards = load_jsonl(CARDS_PATH)
    glossary = load_jsonl(GLOSSARY_PATH)
    canon = load_jsonl(CANON_PATH)
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))
    reclass = load_jsonl(RECLASS_PATH) if os.path.exists(RECLASS_PATH) else []
    novelty = load_jsonl(NOVELTY_PATH) if os.path.exists(NOVELTY_PATH) else []
    gloss_outs = load_glossary_outs()

    val = validate(cards, reclass, novelty)
    gnotes = apply_glossary(glossary, gloss_outs)
    n_re = apply_reclass(cards, reclass)
    nv_stats = apply_novelty(cards, novelty)

    dump_jsonl(CARDS_PATH, cards)
    dump_jsonl(GLOSSARY_PATH, glossary)

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
    patch_readme(n_re, val["re_dist"], nv_stats, len(docs), other_left)
    hits = privacy_scan()

    today = date.today().isoformat()
    report = [
        "# v5 子代理入库报告",
        "",
        f"日期：{today}",
        "",
        "## 校验",
        "",
        f"- 「其他」draft：{val['other_n']}；reclass 行 {val['re_n']} 唯一 {val['re_uniq']} 重复 {val['re_dup']}",
        f"- 未覆盖：{len(val['re_missing'])}；多余：{len(val['re_extra'])}；非法类别：{val['re_bad_cat'] or '无'}",
        f"- group_only∩authoritative：{val['auth_go_n']}；novelty 行 {val['nv_n']} 唯一 {val['nv_uniq']} 重复 {val['nv_dup']}",
        f"- novelty 未覆盖：{len(val['nv_missing'])}；多余：{len(val['nv_extra'])}；非法枚举：{val['nv_bad'] or '无'}",
        f"- jsonl 内 conflict：{val['conflict_ids']}；evidence 空：{val['conflict_empty'] or '无'}",
        f"- 产物缺口：reclass 缺 {len(val['re_missing'])}，novelty 缺 {len(val['nv_missing'])}（含任务点名的 w000416，已按评审结论手动入库）",
        "",
        "## reclass 分布（已入库）",
        "",
    ]
    for k, v in sorted(val["re_dist"].items(), key=lambda x: -x[1]):
        report.append(f"- {k}：{v}")
    report += [
        "",
        f"- 实际写入 cards.jsonl：{n_re}；仍为「其他」的 draft：{other_left}",
        "",
        "## novelty",
        "",
        f"- also_in_vod 升级：{nv_stats['also_in_vod']}",
        f"- conflict 写入：{nv_stats['conflict']}（jsonl 有 w000554；w000416 手动 vod_wins）",
        f"- 仍 group_only：{nv_stats['group_only']}",
        "",
        "## glossary",
        "",
    ]
    report.extend(f"- {n}" for n in gnotes)
    report += [
        "",
        "## rag_docs",
        "",
        f"- 条数：{len(docs)}；glossary 挂载 {gstats['with_links']}/{gstats['n']}",
        f"- 隐私 hits：{len(hits)}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print(
        f"reclass={n_re} other_left={other_left} "
        f"vod={nv_stats['also_in_vod']} conflict={nv_stats['conflict']} "
        f"rag={len(docs)} privacy={len(hits)}"
    )
    if hits or len(docs) != 869:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
