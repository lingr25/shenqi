#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_ingest_v5_3.py
-----------------------
校验并入库 6 条 subagent canonical 词条（float/cost/deploy_hate/gepan/redeploy/spawn）。
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
TOPIC_GLOB = os.path.join(ROOT_DIR, "qq_info", "subagent_canonical", "out_topic_*.json")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "ingest_v5_3_report.md")
REQUIRED = (
    "title",
    "entities",
    "canonical_conclusions",
    "parameters",
    "open_questions",
    "source_window_ids",
    "as_of",
)
CRED = {"authoritative", "expert", "lead"}
WS = re.compile(r"\s+")
TOPIC_ORDER = [
    "float",
    "cost",
    "deploy_hate",
    "gepan",
    "redeploy",
    "spawn",
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def compact(s: str) -> str:
    return WS.sub("", s or "")


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


def load_topics() -> list[tuple[str, dict[str, Any]]]:
    found: dict[str, dict[str, Any]] = {}
    for path in glob.glob(TOPIC_GLOB):
        name = os.path.basename(path)
        m = re.match(r"out_topic_(.+)\.json$", name)
        key = m.group(1) if m else name
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, list):
            obj = obj[0]
        found[key] = obj
    out = []
    for k in TOPIC_ORDER:
        if k in found:
            out.append((k, found[k]))
    for k, obj in found.items():
        if k not in TOPIC_ORDER:
            out.append((k, obj))
    return out


def card_search_blobs(card: dict[str, Any]) -> list[str]:
    blobs = [str(x) for x in (card.get("source_spans") or []) if x]
    for cc in card.get("core_conclusions") or []:
        if cc.get("conclusion"):
            blobs.append(str(cc["conclusion"]))
    for p in card.get("underlying_parameters") or []:
        if p.get("source_span"):
            blobs.append(str(p["source_span"]))
        if p.get("value") is not None:
            blobs.append(str(p["value"]))
    if card.get("summary_takeaway"):
        blobs.append(str(card["summary_takeaway"]))
    if card.get("topic"):
        blobs.append(str(card["topic"]))
    return blobs


def value_in_blobs(val: str, blobs: list[str]) -> bool:
    needle = compact(str(val))
    if not needle:
        return False
    return any(needle in compact(b) for b in blobs)


def max_cluster_n(canon: list[dict[str, Any]]) -> int:
    mx = 0
    for e in canon:
        m = re.match(r"c(\d+)$", str(e.get("cluster_id") or ""))
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def validate_entry(
    key: str, obj: dict[str, Any], cards_by: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    errs: list[str] = []
    missing = [k for k in REQUIRED if k not in obj]
    if missing:
        errs.append(f"missing:{missing}")
    src = list(obj.get("source_window_ids") or [])
    unknown = [w for w in src if w not in cards_by]
    if unknown:
        errs.append(f"unknown_windows:{unknown}")
    for i, cc in enumerate(obj.get("canonical_conclusions") or []):
        if not isinstance(cc, dict):
            errs.append(f"conc_not_obj:{i}")
            continue
        if cc.get("credibility") not in CRED:
            errs.append(f"bad_cred:{i}:{cc.get('credibility')}")
        if cc.get("speaker") == "主播" and cc.get("credibility") != "authoritative":
            errs.append(f"host_not_auth:{i}")
    param_fail: list[str] = []
    for i, p in enumerate(obj.get("parameters") or []):
        if not isinstance(p, dict):
            errs.append(f"param_not_obj:{i}")
            continue
        wid = p.get("source_window_id")
        if wid and wid not in src:
            errs.append(f"param_wid_outside:{i}:{wid}")
        val = p.get("value")
        if val is None or val == "":
            continue
        card = cards_by.get(wid) if wid else None
        blobs: list[str] = []
        if card:
            blobs = card_search_blobs(card)
        else:
            for w in src:
                blobs.extend(card_search_blobs(cards_by.get(w) or {}))
        if not value_in_blobs(str(val), blobs):
            param_fail.append(f"{key}[{i}] {wid} value={val!r}")
    reject = len(param_fail) > 3
    if reject:
        errs.append(f"param_untraced>{3}:{len(param_fail)}")
    return {
        "key": key,
        "title": obj.get("title"),
        "n_src": len(src),
        "n_param": len(obj.get("parameters") or []),
        "n_conc": len(obj.get("canonical_conclusions") or []),
        "n_oq": len(obj.get("open_questions") or []),
        "param_fail": param_fail,
        "errs": errs,
        "reject": reject,
        "ok": not errs and not reject,
    }


def patch_readme(mapping: list[tuple[str, str, str, int]], n_canon: int, n_docs: int, linked: str) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    lines = [
        "",
        "## v5.3 六条主题 canonical",
        "",
        f"子代理合成 6 条词条并入 `canonical.jsonl`，总数 **{n_canon}**。rag_docs **{n_docs}**（window 773 + canonical {n_canon} + glossary 50）。glossary 挂载 {linked}。",
        "",
    ]
    for key, cid, title, n_oq in mapping:
        lines.append(f"- `{cid}` {key}：{title}（open_questions {n_oq}）")
    lines.append("")
    section = "\n".join(lines) + "\n"
    if "## v5.3 六条主题" in text:
        text = re.sub(
            r"\n## v5.3 六条主题 canonical[\s\S]*?(?=\n## |\n\*\*数据边界\*\*)",
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
    text = re.sub(
        r"canonical_draft 词条 \*\*\d+\*\*",
        f"canonical_draft 词条 **{n_canon}**",
        text,
        count=1,
    )
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="ingest 6 canonical topics v5.3").parse_args(argv)
    cards = load_jsonl(CARDS_PATH)
    cards_by = {c["window_id"]: c for c in cards}
    canon = load_jsonl(CANON_PATH)
    glossary = load_jsonl(GLOSSARY_PATH)
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))
    topics = load_topics()

    reports = [validate_entry(k, obj, cards_by) for k, obj in topics]
    accepted: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for (key, obj), rep in zip(topics, reports):
        if rep["reject"] or any(e.startswith("missing:") or e.startswith("unknown_windows") for e in rep["errs"]):
            rejected.append(rep)
        else:
            accepted.append((key, obj, rep))

    nid = max_cluster_n(canon) + 1
    mapping: list[tuple[str, str, str, int]] = []
    n_back = 0
    for key, obj, rep in accepted:
        cid = f"c{nid:04d}"
        nid += 1
        rec = dict(obj)
        rec["cluster_id"] = cid
        rec["status"] = "canonical_draft"
        rec["origin"] = "subagent_v5_3"
        rec.setdefault("version_note", obj.get("version_note"))
        rec.setdefault("notes", obj.get("notes"))
        canon.append(rec)
        mapping.append((key, cid, rec.get("title") or "", len(rec.get("open_questions") or [])))
        for w in rec.get("source_window_ids") or []:
            card = cards_by.get(w)
            if not card:
                continue
            ids = list(card.get("canonical_ids") or [])
            if card.get("canonical_id") and card["canonical_id"] not in ids:
                ids.append(card["canonical_id"])
            if cid not in ids:
                ids.append(cid)
                n_back += 1
            card["canonical_ids"] = ids

    dump_jsonl(CARDS_PATH, cards)
    dump_jsonl(CANON_PATH, canon)

    lookup = alias_lookup(aliases)
    docs = rebuild_rag(cards, canon, glossary, aliases)
    glossary, gstats = link_glossary(glossary, docs, lookup)
    docs = apply_boost_and_glossary_meta(docs, glossary, cards)
    dump_jsonl(GLOSSARY_PATH, glossary)
    dump_jsonl(RAG_PATH, docs)
    dist = Counter(d.get("doc_type") for d in docs)

    patch_readme(
        mapping,
        len(canon),
        len(docs),
        f"{gstats['with_links']}/{gstats['n']}",
    )
    hits = privacy_scan()

    today = date.today().isoformat()
    lines = [
        "# v5.3 canonical 六主题入库报告",
        "",
        f"日期：{today}",
        "",
        "## 校验总览",
        "",
        f"- 输入词条：{len(topics)}；入库：{len(accepted)}；打回：{len(rejected)}",
        f"- 隐私 hits：{len(hits)}",
        "",
        "## cluster_id 映射",
        "",
    ]
    for key, cid, title, n_oq in mapping:
        lines.append(f"- `{cid}` ← {key}：{title}（open_questions {n_oq}）")
    lines += ["", "## 参数溯源失败明细", ""]
    any_fail = False
    for rep in reports:
        if rep["param_fail"]:
            any_fail = True
            lines.append(
                f"### {rep['key']}（{len(rep['param_fail'])} 条未溯源，reject={rep['reject']}）"
            )
            lines.append("")
            for x in rep["param_fail"]:
                lines.append(f"- {x}")
            lines.append("")
    if not any_fail:
        lines.append("（无）")
        lines.append("")
    lines += ["", "## 其它错误", ""]
    for rep in reports:
        other = [e for e in rep["errs"] if not e.startswith("param_untraced")]
        if other:
            lines.append(f"- {rep['key']}: {other}")
    if not any(
        [e for e in rep["errs"] if not e.startswith("param_untraced")] for rep in reports
    ):
        lines.append("（无）")
    lines += [
        "",
        "## rag_docs / glossary",
        "",
        f"- rag_docs：{len(docs)} {dict(dist)}",
        f"- glossary 挂载：{gstats['with_links']}/{gstats['n']}（空 {gstats['empty']}）",
        f"- 窗卡回指新增：{n_back}",
        f"- canonical 总数：{len(canon)}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(
        f"accepted={len(accepted)} rejected={len(rejected)} "
        f"canonical={len(canon)} rag={len(docs)} {dict(dist)} "
        f"glossary={gstats['with_links']}/{gstats['n']} privacy={len(hits)}"
    )
    for key, cid, title, n_oq in mapping:
        print(f"  {cid} {key} oq={n_oq}")
    if hits or len(rejected):
        return 1
    if len(docs) != 773 + len(canon) + 50:
        log(f"rag_docs {len(docs)} != expected {773 + len(canon) + 50}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
