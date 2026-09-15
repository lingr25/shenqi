#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_ingest_rag.py
----------------------
把 glossary / split / alias 三包 LLM 结果入库，刷新 rag_docs（v4）。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qq_cards_rag_prep import (
    ALIAS_PATH,
    CANON_PATH,
    CARDS_PATH,
    CRED_RANK,
    RAG_PATH,
    README_PATH,
    SPEAKERS_PATH,
    canon_text,
    credibility_max,
    privacy_scan,
    window_text,
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GLOSSARY_PATH = os.path.join(ROOT_DIR, "qq_cards", "glossary.jsonl")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "ingest_report.md")
GLOSSARY_GLOB = os.path.join(
    ROOT_DIR, "qq_info", "llm_batch_glossary", "cards_glossary_batch_*.jsonl"
)
SPLIT_GLOB = os.path.join(
    ROOT_DIR, "qq_info", "llm_batch_split", "cards_split_batch_*.jsonl"
)
ALIAS_GLOB = os.path.join(
    ROOT_DIR, "qq_info", "llm_batch_alias", "cards_alias_batch_*.jsonl"
)

KEEP_SEPARATE = {"隐匿", "迷彩", "仇恨", "嘲讽等级"}
FAKE_CD = re.compile(r"不随后续攻速|已有的冷却不会因为后续")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_glob(pattern: str) -> list[Any]:
    rows: list[Any] = []
    for path in sorted(glob.glob(pattern)):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def dump_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def next_cluster_id(existing: list[dict[str, Any]]) -> int:
    mx = 0
    for e in existing:
        cid = str(e.get("cluster_id") or "")
        m = re.match(r"c(\d+)$", cid)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def mechanic_unknown(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    return t == "unknown" or t.startswith("unknown")


def ingest_glossary(
    rows: list[dict[str, Any]], card_ids: set[str]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    out: list[dict[str, Any]] = []
    dropped = 0
    n_need = 0
    for raw in rows:
        src = [w for w in (raw.get("source_window_ids") or []) if w in card_ids]
        dropped += len(raw.get("source_window_ids") or []) - len(src)
        mech = raw.get("mechanic_def")
        need = mechanic_unknown(str(mech or ""))
        rec = {
            "term": raw.get("term"),
            "aliases": list(raw.get("aliases") or []),
            "short_def": raw.get("short_def") or "",
            "mechanic_def": mech if mech is not None else "unknown",
            "related_terms": list(raw.get("related_terms") or []),
            "source_window_ids": src,
            "status": raw.get("status") or "glossary_draft",
            "needs_more_evidence": need,
        }
        if need:
            n_need += 1
        out.append(rec)
    stats = {"n": len(out), "needs_more_evidence": n_need, "dropped_ids": dropped}
    return out, stats


def ingest_split(
    lines: list[Any],
    old_canon: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    old_src: set[str] = set()
    for e in old_canon:
        old_src |= set(e.get("source_window_ids") or [])
    by_id = {c.get("window_id"): c for c in cards}
    nid = next_cluster_id(old_canon)
    new_entries: list[dict[str, Any]] = []
    overlap_report: list[str] = []
    n_overlap_windows = 0
    fake_cd_ok = True
    for line in lines:
        arr = line if isinstance(line, list) else [line]
        for raw in arr:
            if not isinstance(raw, dict):
                continue
            src = list(raw.get("source_window_ids") or [])
            inter = [w for w in src if w in old_src]
            if inter:
                n_overlap_windows += len(inter)
                overlap_report.append(
                    f"{raw.get('parent_cluster_id')} {raw.get('title')}: {inter}"
                )
                src = [w for w in src if w not in old_src]
            cid = f"c{nid:04d}"
            nid += 1
            rec = {
                "cluster_id": cid,
                "title": raw.get("title"),
                "entities": list(raw.get("entities") or []),
                "canonical_conclusions": list(raw.get("canonical_conclusions") or []),
                "parameters": list(raw.get("parameters") or []),
                "open_questions": list(raw.get("open_questions") or []),
                "source_window_ids": src,
                "parent_cluster_id": raw.get("parent_cluster_id"),
                "split_reason": raw.get("split_reason"),
                "status": "canonical_draft",
                "origin": "split",
            }
            for cc in rec["canonical_conclusions"]:
                conc = str(cc.get("conclusion") or "")
                if FAKE_CD.search(conc) and not cc.get("rejected") and "否" not in conc and "录播" not in conc:
                    fake_cd_ok = False
            new_entries.append(rec)
            for w in src:
                card = by_id.get(w)
                if not card:
                    continue
                ids = list(card.get("canonical_ids") or [])
                if card.get("canonical_id") and card["canonical_id"] not in ids:
                    ids.append(card["canonical_id"])
                if cid not in ids:
                    ids.append(cid)
                card["canonical_ids"] = ids
    # migrate leftover single canonical_id
    n_migrated = 0
    for c in cards:
        ids = list(c.get("canonical_ids") or [])
        old = c.get("canonical_id")
        if old and old not in ids:
            ids.append(old)
            n_migrated += 1
        if ids:
            c["canonical_ids"] = ids
    stats = {
        "n_new": len(new_entries),
        "first_id": new_entries[0]["cluster_id"] if new_entries else None,
        "last_id": new_entries[-1]["cluster_id"] if new_entries else None,
        "overlap_windows": n_overlap_windows,
        "overlap_report": overlap_report,
        "migrated_canonical_id": n_migrated,
        "fake_cd_ok": fake_cd_ok,
    }
    return old_canon + new_entries, cards, stats


def ingest_alias(
    rows: list[dict[str, Any]], table: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    n_update = 0
    n_merge = 0
    merges: list[str] = []
    for row in rows:
        zh = (row.get("zh") or "").strip()
        canon_zh = (row.get("canonical_zh") or zh).strip()
        merge_into = row.get("merge_into")
        if merge_into in ("", None):
            merge_into = None
        else:
            merge_into = str(merge_into).strip()
        en = row.get("canonical_en")
        if en is None:
            en = ""
        en = str(en).strip()
        if merge_into:
            target = merge_into
            rec = table.setdefault(
                target, {"canonical": target, "aliases": [], "en": []}
            )
            aliases = set(rec.get("aliases") or [])
            if zh:
                aliases.add(zh)
            if canon_zh and canon_zh != target:
                aliases.add(canon_zh)
            rec["aliases"] = sorted(aliases)
            if en:
                ens = set(rec.get("en") or [])
                ens.add(en)
                rec["en"] = sorted(ens)
            if zh in table and zh != target:
                del table[zh]
            n_merge += 1
            merges.append(f"{zh} → {target}")
            continue
        rec = table.setdefault(
            canon_zh, {"canonical": canon_zh, "aliases": [], "en": []}
        )
        rec["canonical"] = canon_zh
        aliases = set(rec.get("aliases") or [])
        if zh and zh != canon_zh:
            aliases.add(zh)
        rec["aliases"] = sorted(aliases)
        if en:
            ens = set(rec.get("en") or [])
            ens.add(en)
            rec["en"] = sorted(ens)
            rec["canonical_en"] = en
        elif "canonical_en" not in rec:
            rec["canonical_en"] = ""
        n_update += 1
    # uniqueness of KEEP_SEPARATE
    for name in KEEP_SEPARATE:
        table.setdefault(name, {"canonical": name, "aliases": [], "en": []})
        table[name]["canonical"] = name
    # drop if someone merged them as alias of another keep-separate
    for name in list(KEEP_SEPARATE):
        for other in KEEP_SEPARATE:
            if other == name:
                continue
            rec = table.get(other) or {}
            als = rec.get("aliases") or []
            if name in als:
                rec["aliases"] = [a for a in als if a != name]
    alias_ok = (
        len({table[n]["canonical"] for n in KEEP_SEPARATE if n in table}) == 4
    )
    stats = {
        "n_rows": len(rows),
        "n_update": n_update,
        "n_merge": n_merge,
        "merges": merges,
        "n_canonical": len(table),
        "keep_separate_ok": alias_ok,
    }
    return table, stats


def glossary_text(rec: dict[str, Any]) -> str:
    parts = [rec.get("term") or ""]
    als = rec.get("aliases") or []
    if als:
        parts.append(" ".join(str(a) for a in als))
    if rec.get("short_def"):
        parts.append(rec["short_def"])
    mech = rec.get("mechanic_def") or ""
    if mech and not mechanic_unknown(str(mech)):
        parts.append(str(mech))
    rel = rec.get("related_terms") or []
    if rel:
        parts.append(" ".join(str(x) for x in rel))
    return "\n".join(p for p in parts if p)


def rebuild_rag(
    cards: list[dict[str, Any]],
    canon: list[dict[str, Any]],
    glossary: list[dict[str, Any]],
    aliases: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup = {}
    for rec in aliases.values():
        lookup[rec["canonical"]] = rec
        for a in rec.get("aliases") or []:
            lookup.setdefault(a, rec)
    docs: list[dict[str, Any]] = []
    for c in cards:
        if c.get("status") == "duplicate":
            continue
        cids = list(c.get("canonical_ids") or [])
        if c.get("canonical_id") and c["canonical_id"] not in cids:
            cids.append(c["canonical_id"])
        docs.append(
            {
                "id": f"window:{c.get('window_id')}",
                "doc_type": "window",
                "text": window_text(c, lookup),
                "metadata": {
                    "category": c.get("category"),
                    "credibility_max": credibility_max(c),
                    "novelty": c.get("novelty") or "unknown",
                    "as_of": c.get("as_of"),
                    "scope": c.get("scope") or "general",
                    "canonical_id": c.get("canonical_id"),
                    "canonical_ids": cids,
                    "status": c.get("status", "draft"),
                    "origin": c.get("origin") or "main",
                    "window_id": c.get("window_id"),
                },
            }
        )
    as_of_by = {c.get("window_id"): c.get("as_of") for c in cards}
    for e in canon:
        src = e.get("source_window_ids") or []
        as_ofs = [as_of_by.get(w) or "" for w in src]
        as_of = max(as_ofs) if as_ofs else None
        docs.append(
            {
                "id": f"canonical:{e.get('cluster_id')}",
                "doc_type": "canonical",
                "text": canon_text(e, lookup),
                "metadata": {
                    "category": e.get("category"),
                    "credibility_max": credibility_max(e),
                    "novelty": None,
                    "as_of": as_of,
                    "scope": "general",
                    "canonical_id": e.get("cluster_id"),
                    "status": e.get("status"),
                    "origin": e.get("origin") or "merge",
                    "cluster_id": e.get("cluster_id"),
                    "parent_cluster_id": e.get("parent_cluster_id"),
                },
            }
        )
    for g in glossary:
        docs.append(
            {
                "id": f"glossary:{g.get('term')}",
                "doc_type": "glossary",
                "text": glossary_text(g),
                "metadata": {
                    "doc_type": "glossary",
                    "needs_more_evidence": bool(g.get("needs_more_evidence")),
                    "aliases": list(g.get("aliases") or []),
                    "term": g.get("term"),
                    "status": g.get("status"),
                },
            }
        )
    return docs


def patch_readme(
    n_canon: int,
    n_docs: int,
    dist: Counter,
    n_gloss: int,
    n_need: int,
    n_alias: int,
) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    section = f"""
## v4 glossary / split / alias 入库

- glossary：`glossary.jsonl` **{n_gloss}** 条（`needs_more_evidence` {n_need}：mechanic_def 推不出精确机制，仅保留人话 short_def）。
- split：大簇拆词条并入 `canonical.jsonl`，词条 **23 → {n_canon}**；新词条带 `parent_cluster_id` / `split_reason`。
- alias：更新 `entity_aliases.json`，主词 **{n_alias}**；隐匿≠迷彩，仇恨≠嘲讽等级。
- 检索合同：`rag_docs.jsonl` **{n_docs}** 条（window {dist.get('window', 0)} + canonical {dist.get('canonical', 0)} + glossary {dist.get('glossary', 0)}）。
- glossary 的 `mechanic_def=unknown` 不是低质量人话，只表示卡片证据不够写精确定义。
- 窗卡 `canonical_ids` 为数组（可挂多条词条）；旧字段 `canonical_id` 仍保留。

"""
    if "## v4 glossary" in text:
        text = re.sub(
            r"\n## v4 glossary[\s\S]*?(?=\n## |\n\*\*数据边界\*\*)",
            "\n" + section,
            text,
            count=1,
        )
    else:
        needle = "**数据边界**"
        if needle in text:
            text = text.replace(needle, section + needle, 1)
        else:
            text += "\n" + section
    # refresh canonical count line if present
    text = re.sub(
        r"canonical_draft 词条 \*\*\d+\*\*",
        f"canonical_draft 词条 **{n_canon}**",
        text,
        count=1,
    )
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="ingest glossary/split/alias").parse_args(argv)
    cards = load_jsonl(CARDS_PATH)
    old_canon = load_jsonl(CANON_PATH)
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))
    card_ids = {c.get("window_id") for c in cards}

    gloss_raw = load_glob(GLOSSARY_GLOB)
    split_raw = load_glob(SPLIT_GLOB)
    alias_raw = load_glob(ALIAS_GLOB)

    glossary, gstats = ingest_glossary(gloss_raw, card_ids)
    dump_jsonl(GLOSSARY_PATH, glossary)

    canon, cards, sstats = ingest_split(split_raw, old_canon, cards)
    dump_jsonl(CANON_PATH, canon)
    dump_jsonl(CARDS_PATH, cards)

    aliases, astats = ingest_alias(alias_raw, aliases)
    with open(ALIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(aliases, f, ensure_ascii=False, indent=2)

    docs = rebuild_rag(cards, canon, glossary, aliases)
    dump_jsonl(RAG_PATH, docs)
    dist = Counter(d.get("doc_type") for d in docs)

    today = date.today().isoformat()
    patch_readme(
        len(canon),
        len(docs),
        dist,
        gstats["n"],
        gstats["needs_more_evidence"],
        astats["n_canonical"],
    )

    hits = privacy_scan()
    json_ok = True
    for path in (CARDS_PATH, CANON_PATH, GLOSSARY_PATH, RAG_PATH):
        for i, row in enumerate(load_jsonl(path), 1):
            if not isinstance(row, dict):
                json_ok = False
                log(f"non-object {path}:{i}")

    report = [
        "# v4 ingest 报告",
        "",
        f"日期：{today}",
        "",
        "## glossary",
        "",
        f"- 落盘：{gstats['n']}",
        f"- needs_more_evidence：{gstats['needs_more_evidence']}",
        f"- 丢弃无效 source_window_ids：{gstats['dropped_ids']}",
        "",
        "## split",
        "",
        f"- 新增词条：{sstats['n_new']}（{sstats['first_id']}–{sstats['last_id']}）",
        f"- canonical 总数：{len(canon)}",
        f"- 与旧词条源窗交集：{sstats['overlap_windows']}",
        f"- canonical_id → canonical_ids 迁移：{sstats['migrated_canonical_id']}",
        f"- w001186 冷却假结论未当定论：{sstats['fake_cd_ok']}",
        "",
        "## alias",
        "",
        f"- 输入行：{astats['n_rows']}",
        f"- 更新主词：{astats['n_update']}；merge_into：{astats['n_merge']}",
        f"- 合并：{', '.join(astats['merges']) or '无'}",
        f"- 主词总数：{astats['n_canonical']}",
        f"- 隐匿/迷彩/仇恨/嘲讽等级独立：{astats['keep_separate_ok']}",
        "",
        "## rag_docs",
        "",
        f"- 总条数：{len(docs)}",
        f"- 分布：{dict(dist)}",
        "",
        f"- 隐私 hits：{len(hits)}",
        f"- JSON 可解析：{json_ok}",
        "",
    ]
    if sstats["overlap_report"]:
        report.append("交集明细：")
        report.extend(f"- {x}" for x in sstats["overlap_report"])
        report.append("")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print(
        f"glossary={gstats['n']} need={gstats['needs_more_evidence']} "
        f"split_new={sstats['n_new']} {sstats['first_id']}-{sstats['last_id']} "
        f"canonical={len(canon)} aliases={astats['n_canonical']} "
        f"rag_docs={len(docs)} {dict(dist)} privacy={len(hits)} "
        f"fake_cd_ok={sstats['fake_cd_ok']}"
    )
    if hits or not json_ok or not astats["keep_separate_ok"] or not sstats["fake_cd_ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
