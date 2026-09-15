#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_rag_ready.py
---------------------
规则层：glossary 挂载、retrieval_boost、刷新 rag_docs。
载荷：subagent_glossary / reclass / novelty（不跑 LLM）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qq_cards_ingest_rag import (
    glossary_text,
    rebuild_rag,
)
from qq_cards_pack import excerpt_segments, load_transcripts, search_terms_for_card
from qq_cards_rag_prep import (
    ALIAS_PATH,
    CANON_PATH,
    CARDS_PATH,
    CRED_RANK,
    RAG_PATH,
    README_PATH,
    SPEAKERS_PATH,
    parse_entity,
    privacy_scan,
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GLOSSARY_PATH = os.path.join(ROOT_DIR, "qq_cards", "glossary.jsonl")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "rag_ready_report.md")
WINDOWS_PATH = os.path.join(ROOT_DIR, "qq_info", "windows.jsonl")
MESSAGES_PATH = os.path.join(ROOT_DIR, "qq_info", "messages_clean.jsonl")
TRANSCRIPTS_DIR = os.path.join(ROOT_DIR, "transcripts_txt")
HOST_QQ = "2580863623"
EXPERT_QQ = "724873295"

GLOSSARY_TERMS = [
    "力道",
    "过伤",
    "入控",
    "免控",
    "visitNodeCenter",
    "TypeTree",
    "阻挡",
]
MECH_HINTS = (
    "帧",
    "格",
    "半径",
    "判定",
    "索敌",
    "技力",
    "拆包",
    "prefab",
    "碰撞",
    "寻路",
    "位移",
    "冷却",
    "间隔",
    "状态机",
)


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


def alias_lookup(table: dict[str, dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rec in table.values():
        canon = rec.get("canonical") or ""
        if canon:
            out[canon] = canon
        for a in rec.get("aliases") or []:
            if a:
                out.setdefault(a, canon)
        for e in rec.get("en") or []:
            if e:
                out.setdefault(e, canon)
    return out


def normalize_term(term: str, lookup: dict[str, str]) -> str:
    t = (term or "").strip()
    if not t:
        return t
    if t in lookup:
        return lookup[t]
    zh, _ = parse_entity(t)
    if zh and zh in lookup:
        return lookup[zh]
    return zh or t


def retrieval_boost(doc: dict[str, Any]) -> float:
    dt = doc.get("doc_type")
    if dt == "canonical":
        return 1.5
    if dt == "glossary":
        return 1.3
    meta = doc.get("metadata") or {}
    nov = meta.get("novelty") or "unknown"
    origin = meta.get("origin") or "main"
    if nov == "group_only":
        return 1.2
    if nov in {"also_in_vod", "conflict"}:
        return 1.0
    if nov == "unknown" and origin in {"maybe", "ignore"}:
        return 0.6
    return 1.0


def doc_terms(doc: dict[str, Any], lookup: dict[str, str]) -> set[str]:
    terms: set[str] = set()
    text = doc.get("text") or ""
    meta = doc.get("metadata") or {}
    for raw in [
        meta.get("term"),
        meta.get("category"),
    ]:
        if raw:
            terms.add(normalize_term(str(raw), lookup))
    blob = text
    for key, canon in lookup.items():
        if key and len(key) >= 2 and key in blob:
            terms.add(canon)
    return {t for t in terms if t}


def link_glossary(
    glossary: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    lookup: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    for g in glossary:
        raw_term = (g.get("term") or "").strip()
        g["term"] = raw_term
        g["canonical_term"] = normalize_term(raw_term, lookup) or raw_term
        g["aliases"] = sorted(
            {str(a).strip() for a in (g.get("aliases") or []) if a}
            - {g.get("term")}
        )
        g["related_terms"] = sorted(
            {str(a).strip() for a in (g.get("related_terms") or []) if a}
            - {g.get("term")}
        )
    needles: dict[str, set[str]] = {}
    for g in glossary:
        term = g.get("term") or ""
        canon = g.get("canonical_term") or term
        keys = {term, canon}
        keys |= set(g.get("aliases") or [])
        for k, c in lookup.items():
            if c == canon and k:
                keys.add(k)
        needles[term] = {k for k in keys if k}
    scored: dict[str, list[tuple[tuple, str]]] = {g["term"]: [] for g in glossary}

    for doc in docs:
        if doc.get("doc_type") not in {"window", "canonical"}:
            continue
        meta = doc.get("metadata") or {}
        text = doc.get("text") or ""
        cred = meta.get("credibility_max") or ""
        is_canon = 0 if doc.get("doc_type") == "canonical" else 1
        cred_rank = CRED_RANK.get(cred, 9)
        for term, keys in needles.items():
            hit = False
            for k in keys:
                if len(k) >= 2 and k in text:
                    hit = True
                    break
            if not hit:
                continue
            scored[term].append(((is_canon, cred_rank), doc["id"]))
    n_linked = 0
    n_empty = 0
    for g in glossary:
        term = g.get("term") or ""
        items = scored.get(term) or []
        items.sort(key=lambda x: x[0])
        ids: list[str] = []
        seen: set[str] = set()
        for _k, did in items:
            if did in seen:
                continue
            seen.add(did)
            ids.append(did)
            if len(ids) >= 30:
                break
        g["linked_doc_ids"] = ids
        if ids:
            n_linked += 1
        else:
            n_empty += 1
    stats = {"n": len(glossary), "with_links": n_linked, "empty": n_empty}
    return glossary, stats


def apply_boost_and_glossary_meta(
    docs: list[dict[str, Any]], glossary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_term = {g.get("term"): g for g in glossary}
    out = []
    for doc in docs:
        meta = dict(doc.get("metadata") or {})
        meta["retrieval_boost"] = retrieval_boost(doc)
        if doc.get("doc_type") == "glossary":
            term = meta.get("term") or (doc.get("id") or "").split(":", 1)[-1]
            g = by_term.get(term)
            if g:
                meta["linked_doc_ids"] = list(g.get("linked_doc_ids") or [])
                meta["aliases"] = list(g.get("aliases") or [])
        out.append({**doc, "metadata": meta})
    return out


def clock_of(time_str: str) -> str:
    ts = (time_str or "").strip()
    if " " in ts:
        return ts.split(" ", 1)[1][:5]
    return ts[-5:] if len(ts) >= 5 else ts or "??:??"


def speaker_tag(msg: dict[str, Any]) -> str:
    qq = str(msg.get("qq") or "")
    if qq == HOST_QQ:
        return "[主播]"
    if qq == EXPERT_QQ:
        return "[专家]"
    return msg.get("speaker_id") or "unknown"


def mech_score(text: str) -> int:
    t = text or ""
    return sum(1 for h in MECH_HINTS if h.lower() in t.lower()) + (
        2 if re.search(r"\d", t) else 0
    )


def safe_filename(term: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", term)


def write_glossary_payloads() -> dict[str, Any]:
    out_dir = os.path.join(ROOT_DIR, "qq_info", "subagent_glossary")
    os.makedirs(out_dir, exist_ok=True)
    msgs = load_jsonl(MESSAGES_PATH)
    files = []
    details = []
    for term in GLOSSARY_TERMS:
        hits = []
        for i, m in enumerate(msgs):
            blob = (m.get("text_stripped") or m.get("text") or "")
            if term in blob:
                hits.append(i)
        segs: list[list[int]] = []
        if hits:
            cur = [hits[0]]
            for h in hits[1:]:
                prev = msgs[cur[-1]]
                now = msgs[h]
                gap = (now.get("ts") or 0) - (prev.get("ts") or 0)
                if gap > 10 * 60:
                    segs.append(cur)
                    cur = [h]
                else:
                    cur.append(h)
            segs.append(cur)
        ranked = []
        for seg in segs:
            lo = max(0, min(seg) - 15)
            hi = min(len(msgs), max(seg) + 16)
            idxs = list(range(lo, hi))
            if len(idxs) > 60:
                # center on densest hit
                mid = seg[len(seg) // 2]
                lo = max(0, mid - 30)
                hi = min(len(msgs), lo + 60)
                idxs = list(range(lo, hi))
            score = 0
            for i in idxs:
                blob = msgs[i].get("text_stripped") or msgs[i].get("text") or ""
                score += mech_score(blob)
                if term in blob:
                    score += 5
            t0 = msgs[idxs[0]].get("time_str")
            t1 = msgs[idxs[-1]].get("time_str")
            ranked.append((score, t0, t1, idxs))
        ranked.sort(key=lambda x: -x[0])
        picked = ranked[:3]
        path = os.path.join(out_dir, f"term_{safe_filename(term)}.md")
        lines = [
            f"# 术语补证据：{term}",
            "",
            "任务：只依据本文件内的群聊消息，为该术语写 `short_def`（≤80 字人话）和 `mechanic_def`（机制精确定义）。",
            "推不出精确机制则 `mechanic_def` 保持 `unknown`，并列出依据不足之处。",
            "禁止用 Wiki / 训练记忆补数字。输出一个 JSON：",
            '`{"term":"...","short_def":"...","mechanic_def":"...","source_time_ranges":["..."]}`',
            "",
            f"检索命中段数（切段后）：{len(segs)}；选用机制密度最高的 {len(picked)} 段。",
            "",
        ]
        for i, (_s, t0, t1, idxs) in enumerate(picked, 1):
            lines.append(f"## 段 {i}  {t0} ~ {t1}")
            lines.append("")
            for j in idxs:
                m = msgs[j]
                blob = re.sub(r"\s+", " ", m.get("text_stripped") or m.get("text") or "")
                lines.append(f"- `[{clock_of(m.get('time_str') or '')}]` {speaker_tag(m)} {blob}")
            lines.append("")
        if not picked:
            lines.append("（全库无命中消息）")
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        files.append(os.path.basename(path))
        details.append({"term": term, "segments": len(segs), "used": len(picked)})
    return {"dir": out_dir, "files": files, "details": details}


def write_reclass_payloads(cards: list[dict[str, Any]]) -> dict[str, Any]:
    out_dir = os.path.join(ROOT_DIR, "qq_info", "subagent_reclass")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for c in cards:
        if c.get("category") != "其他":
            continue
        if c.get("status", "draft") != "draft":
            continue
        rows.append(
            {
                "window_id": c.get("window_id"),
                "topic": c.get("topic"),
                "context_question": c.get("context_question"),
                "core_conclusions": c.get("core_conclusions") or [],
                "summary_takeaway": c.get("summary_takeaway"),
                "entities": c.get("entities") or [],
            }
        )
    batch = 25
    n_batches = (len(rows) + batch - 1) // batch if rows else 0
    files = []
    for b in range(n_batches):
        chunk = rows[b * batch : (b + 1) * batch]
        name = f"reclass_{b + 1:03d}.jsonl"
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            for obj in chunk:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        files.append(name)
    return {"dir": out_dir, "n": len(rows), "files": files, "batches": n_batches}


def write_novelty_payloads(cards: list[dict[str, Any]]) -> dict[str, Any]:
    out_dir = os.path.join(ROOT_DIR, "qq_info", "subagent_novelty")
    os.makedirs(out_dir, exist_ok=True)
    windows = {w["window_id"]: w for w in load_jsonl(WINDOWS_PATH)} if os.path.exists(WINDOWS_PATH) else {}
    transcripts = load_transcripts(TRANSCRIPTS_DIR)
    selected = []
    for c in cards:
        if c.get("novelty") != "group_only":
            continue
        if not any(
            cc.get("credibility") == "authoritative"
            for cc in (c.get("core_conclusions") or [])
        ):
            continue
        selected.append(c)
    files = []
    n_empty = 0
    for c in selected:
        terms = search_terms_for_card(c, windows.get(c.get("window_id")))
        segs = excerpt_segments(transcripts, terms)
        if not segs:
            n_empty += 1
        slim = {
            "window_id": c.get("window_id"),
            "topic": c.get("topic"),
            "category": c.get("category"),
            "entities": c.get("entities"),
            "summary_takeaway": c.get("summary_takeaway"),
            "core_conclusions": c.get("core_conclusions"),
            "novelty": c.get("novelty"),
        }
        path = os.path.join(out_dir, f"novelty_{c.get('window_id')}.md")
        lines = [
            f"# novelty 复核 `{c.get('window_id')}`",
            "",
            "任务：判断本卡结论是否已在录播逐字稿出现。只依据下方卡片与摘录。",
            "输出一个 JSON：`{\"window_id\":\"...\",\"novelty\":\"also_in_vod|group_only|conflict\",\"evidence\":\"摘录原文子串或空\",\"reason\":\"一句理由\"}`",
            "摘录为空时只能判 group_only（或无法判断时仍 group_only），禁止编造录播内容。",
            "",
            "## 卡片",
            "",
            "```json",
            json.dumps(slim, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 候选逐字稿",
            "",
        ]
        if not segs:
            lines.append("（无命中）")
            lines.append("")
        for s in segs:
            lines.append(
                f"### {s.get('source')} L{s.get('start_line')}-{s.get('end_line')} hit={s.get('terms_hit')}"
            )
            lines.append("")
            for ln in s.get("lines") or []:
                lines.append(ln)
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        files.append(os.path.basename(path))
    return {
        "dir": out_dir,
        "n": len(selected),
        "files": files,
        "empty_excerpts": n_empty,
    }


def patch_readme(n_docs: int, n_linked: int, n_gloss: int) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    section = f"""
## v5 RAG 挂载与降权

- glossary 词条带 `linked_doc_ids`（最多 30，优先 canonical / authoritative）：{n_linked}/{n_gloss} 条至少挂 1 个文档。
- `rag_docs.jsonl` 仍为 **{n_docs}** 条；window metadata 增加 `retrieval_boost`（group_only 1.2，maybe/ignore+unknown 0.6，canonical 1.5，glossary 1.3）。
- 提问链路：命中 glossary → 沿 `linked_doc_ids` 取出相关 canonical/window。

"""
    if "## v5 RAG" in text:
        text = re.sub(
            r"\n## v5 RAG[\s\S]*?(?=\n## |\n\*\*数据边界\*\*)",
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
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="RAG ready + subagent payloads").parse_args(argv)
    cards = load_jsonl(CARDS_PATH)
    canon = load_jsonl(CANON_PATH)
    glossary = load_jsonl(GLOSSARY_PATH)
    TERM_RESTORE = {"SPFA算法": "SPFA", "预制体": "Prefab"}
    for g in glossary:
        t = g.get("term") or ""
        if t in TERM_RESTORE:
            g["term"] = TERM_RESTORE[t]
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))
    lookup = alias_lookup(aliases)

    docs = rebuild_rag(cards, canon, glossary, aliases)
    if len(docs) != 869:
        log(f"warn: rag_docs rebuilt {len(docs)} expected 869")
    glossary, gstats = link_glossary(glossary, docs, lookup)
    docs = apply_boost_and_glossary_meta(docs, glossary)
    dump_jsonl(GLOSSARY_PATH, glossary)
    dump_jsonl(RAG_PATH, docs)

    gpay = write_glossary_payloads()
    rpay = write_reclass_payloads(cards)
    npay = write_novelty_payloads(cards)

    patch_readme(len(docs), gstats["with_links"], gstats["n"])
    hits = privacy_scan()
    today = date.today().isoformat()
    report = [
        "# RAG ready / subagent 载荷报告",
        "",
        f"日期：{today}",
        "",
        "## glossary 挂载",
        "",
        f"- 词条：{gstats['n']}；至少 1 链：{gstats['with_links']}；空链：{gstats['empty']}",
        "",
        "## rag_docs",
        "",
        f"- 条数：{len(docs)}",
        f"- 含 retrieval_boost 的文档：{sum(1 for d in docs if 'retrieval_boost' in (d.get('metadata') or {}))}",
        f"- 隐私 hits：{len(hits)}",
        "",
        "## subagent_glossary",
        "",
        f"- 目录：`qq_info/subagent_glossary/` 文件 {len(gpay['files'])}",
    ]
    for d in gpay["details"]:
        report.append(f"- {d['term']}：切段 {d['segments']}，选用 {d['used']}")
    report += [
        "",
        "## subagent_reclass",
        "",
        f"- 「其他」draft 卡：{rpay['n']}；文件 {rpay['batches']}：{', '.join(rpay['files'])}",
        "",
        "## subagent_novelty",
        "",
        f"- group_only ∩ authoritative：{npay['n']}；无逐字稿摘录：{npay['empty_excerpts']}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print(
        f"rag_docs={len(docs)} glossary_linked={gstats['with_links']}/{gstats['n']} "
        f"reclass={rpay['n']}/{rpay['batches']} novelty={npay['n']} "
        f"glossary_files={len(gpay['files'])} privacy={len(hits)}"
    )
    if hits or len(docs) != 869:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
