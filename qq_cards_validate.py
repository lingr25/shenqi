#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_validate.py
--------------------
验收 LLM 回写的知识卡片 JSONL。
对照 windows.jsonl / messages_clean.jsonl / speaker_map.json。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import tempfile
from collections import Counter
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WINDOWS = os.path.join(ROOT_DIR, "qq_info", "windows.jsonl")
DEFAULT_MESSAGES = os.path.join(ROOT_DIR, "qq_info", "messages_clean.jsonl")
DEFAULT_SPEAKERS = os.path.join(ROOT_DIR, "qq_info", "speaker_map.json")
DEFAULT_CARDS_DIR = os.path.join(ROOT_DIR, "qq_info", "llm_results")
DEFAULT_TRANSCRIPTS = os.path.join(ROOT_DIR, "transcripts_txt")
DEFAULT_QQ_CARDS = os.path.join(ROOT_DIR, "qq_cards", "cards.jsonl")
NOVELTY_ENUM = {"group_only", "also_in_vod", "conflict", "unknown"}
CONF_ENUM = {"high", "medium", "low"}

HOST_QQ = "2580863623"
EXPERT_QQ = "724873295"

CATEGORIES = {"索敌", "帧时序", "位移", "寻路", "伤害结算", "拆包数据", "其他"}
SPEAKERS = {"主播", "专家", "群友"}
CRED = {"authoritative", "expert", "lead"}
REQUIRED = (
    "topic",
    "category",
    "entities",
    "context_question",
    "core_conclusions",
    "underlying_parameters",
    "summary_takeaway",
    "window_id",
    "as_of",
    "status",
    "novelty",
    "source_msg_ids",
    "source_spans",
)

WS_RE = re.compile(r"\s+")
LEADING_AT_RE = re.compile(r"(?m)^(?:@\S+\s*)+")
PRIVACY_FIELDS = (
    "topic",
    "context_question",
    "core_conclusions",
    "underlying_parameters",
    "summary_takeaway",
    "source_spans",
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def compact(s: str) -> str:
    return WS_RE.sub("", s or "")


def normalize_text(s: str) -> str:
    """Strip leading @mentions, unify spaces, then drop all whitespace."""
    t = (s or "").replace("\u3000", " ").replace("\xa0", " ")
    t = LEADING_AT_RE.sub("", t)
    return WS_RE.sub("", t)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            raw = line.strip()
            if not raw:
                continue
            rows.append({"_line": i, "_file": os.path.basename(path), "_raw": raw})
    return rows


def parse_card(row: dict[str, Any]) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    try:
        obj = json.loads(row["_raw"])
    except json.JSONDecodeError as e:
        return None, f"json_invalid: {e}"
    if not isinstance(obj, (dict, list)):
        return None, "json_invalid: not an object or list"
    return obj, None


def collect_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(collect_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(collect_strings(v))
    return out


def load_windows(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                w = json.loads(line)
                out[w["window_id"]] = w
    return out


def load_messages(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                m = json.loads(line)
                out[m["msg_id"]] = m
    return out


def window_texts(w: dict[str, Any], msg_idx: dict[str, dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for mid in w.get("source_msg_ids") or []:
        m = msg_idx.get(mid)
        if not m:
            continue
        t = m.get("text") or ""
        ts = m.get("text_stripped") or ""
        if t:
            texts.append(t)
        if ts and ts != t:
            texts.append(ts)
    return texts


def value_in_texts(value: str, texts: list[str]) -> bool:
    needle = normalize_text(str(value))
    if not needle:
        return False
    return any(needle in normalize_text(t) for t in texts)


def span_in_texts(span: str, texts: list[str]) -> bool:
    s = normalize_text(span or "")
    if not s:
        return False
    return any(s in normalize_text(t) for t in texts)


def privacy_lists(speaker_map: dict[str, Any]) -> tuple[list[str], list[str]]:
    speakers = (speaker_map or {}).get("speakers") or {}
    host = speakers.get(HOST_QQ) or {}
    expert = speakers.get(EXPERT_QQ) or {}
    allow = {
        "主播",
        "专家",
        "群友",
        "神祇读神奇",
        "神奇",
        "调零",
    }
    for rec in (host, expert):
        allow.add(rec.get("speaker_id") or "")
        for n in rec.get("nicks") or []:
            nick = (n.get("nick") if isinstance(n, dict) else str(n)) or ""
            if nick:
                allow.add(nick)
                if "@" in nick:
                    allow.add(nick.split("@", 1)[0])
    qqs: list[str] = []
    banned_nicks: list[str] = []
    for key, rec in speakers.items():
        if str(key).isdigit() and len(str(key)) >= 5:
            qqs.append(str(key))
        for n in (rec or {}).get("nicks") or []:
            nick = (n.get("nick") if isinstance(n, dict) else str(n)) or ""
            if len(nick) < 2:
                continue
            if nick in allow:
                continue
            banned_nicks.append(nick)
    qqs = sorted(set(qqs), key=len, reverse=True)
    banned_nicks = sorted(set(banned_nicks), key=len, reverse=True)
    return qqs, banned_nicks


def privacy_hits(card: dict[str, Any], qqs: list[str], nicks: list[str]) -> list[str]:
    parts: list[str] = []
    for k in PRIVACY_FIELDS:
        if k in card:
            parts.extend(collect_strings(card[k]))
    blob = "\n".join(parts)
    hits: list[str] = []
    for qq in qqs:
        if qq and re.search(rf"(?<![0-9]){re.escape(qq)}(?![0-9])", blob):
            hits.append(f"qq:{qq}")
    for nick in nicks:
        if not nick:
            continue
        if f"@{nick}" in blob:
            hits.append(f"nick:@{nick}")
        elif len(nick) >= 4 and nick in blob:
            hits.append(f"nick:{nick}")
        if len(hits) > 20:
            break
    return hits


def validate_card(
    card: dict[str, Any],
    windows: dict[str, dict[str, Any]],
    msg_idx: dict[str, dict[str, Any]],
    qqs: list[str],
    nicks: list[str],
) -> list[str]:
    errs: list[str] = []
    if card.get("skip") is True:
        wid = card.get("window_id")
        if not wid:
            errs.append("skip_missing_window_id")
        elif wid not in windows:
            errs.append("window_id_unknown")
        if not card.get("reason"):
            errs.append("skip_missing_reason")
        return errs

    for k in REQUIRED:
        if k not in card:
            errs.append(f"missing_field:{k}")
    if errs:
        return errs

    wid = card.get("window_id")
    if wid not in windows:
        errs.append("window_id_unknown")
        return errs
    w = windows[wid]
    allowed_ids = set(w.get("source_msg_ids") or [])
    texts = window_texts(w, msg_idx)

    if card.get("category") not in CATEGORIES:
        errs.append(f"bad_category:{card.get('category')}")
    if card.get("status") != "draft":
        errs.append(f"bad_status:{card.get('status')}")
    if card.get("novelty") != "unknown":
        errs.append(f"bad_novelty:{card.get('novelty')}")
    if not isinstance(card.get("entities"), list):
        errs.append("bad_entities")
    if not isinstance(card.get("core_conclusions"), list):
        errs.append("bad_core_conclusions")
    else:
        for i, c in enumerate(card["core_conclusions"]):
            if not isinstance(c, dict):
                errs.append(f"conclusion_not_object:{i}")
                continue
            if c.get("speaker") not in SPEAKERS:
                errs.append(f"bad_speaker:{c.get('speaker')}")
            if c.get("credibility") not in CRED:
                errs.append(f"bad_credibility:{c.get('credibility')}")
            if not c.get("conclusion"):
                errs.append(f"empty_conclusion:{i}")

    src_ids = card.get("source_msg_ids")
    if not isinstance(src_ids, list):
        errs.append("bad_source_msg_ids")
    else:
        extra = [x for x in src_ids if x not in allowed_ids]
        if extra:
            errs.append(f"source_msg_ids_outside_window:{len(extra)}")

    spans = card.get("source_spans")
    if not isinstance(spans, list):
        errs.append("bad_source_spans")
    else:
        for i, sp in enumerate(spans):
            if not isinstance(sp, str) or not span_in_texts(sp, texts):
                errs.append(f"span_not_in_window:{i}")

    params = card.get("underlying_parameters")
    if params is None:
        errs.append("missing_field:underlying_parameters")
    elif params == []:
        pass
    elif not isinstance(params, list):
        errs.append("bad_underlying_parameters")
    else:
        for i, p in enumerate(params):
            if not isinstance(p, dict):
                errs.append(f"param_not_object:{i}")
                continue
            val = p.get("value")
            if val is None or val == "":
                errs.append(f"param_empty_value:{i}")
                continue
            if not value_in_texts(str(val), texts):
                errs.append(f"hallucination:{wid}:{val}")
            sp = p.get("source_span")
            if sp and not span_in_texts(str(sp), texts):
                errs.append(f"param_span_not_in_window:{i}")
            elif sp and normalize_text(str(val)) not in normalize_text(str(sp)):
                errs.append(f"param_value_not_in_source_span:{i}")

    for h in privacy_hits(card, qqs, nicks):
        errs.append(f"privacy:{h}")
    return errs


def load_transcript_blobs(dir_path: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not dir_path or not os.path.isdir(dir_path):
        return out
    for name in os.listdir(dir_path):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(dir_path, name)
        with open(path, "r", encoding="utf-8") as f:
            out.append((name, f.read()))
    return out


def evidence_in_vod(ev: Any, blobs: list[tuple[str, str]]) -> bool:
    if isinstance(ev, dict):
        s = str(ev.get("text") or ev.get("span") or ev.get("quote") or "").strip()
        src = ev.get("source")
    else:
        s = str(ev or "").strip()
        src = None
    if not s:
        return False
    for name, text in blobs:
        if src and name != src and not str(src).endswith(name):
            continue
        if s in text:
            return True
    if src:
        return any(s in text for _, text in blobs)
    return False


def validate_novelty_card(
    card: dict[str, Any],
    windows: dict[str, dict[str, Any]],
    blobs: list[tuple[str, str]],
) -> list[str]:
    errs: list[str] = []
    if card.get("skip") is True:
        if not card.get("window_id"):
            errs.append("skip_missing_window_id")
        elif card["window_id"] not in windows:
            errs.append("window_id_unknown")
        return errs
    wid = card.get("window_id")
    if not wid or wid not in windows:
        errs.append("window_id_unknown")
    nov = card.get("novelty")
    if nov not in NOVELTY_ENUM:
        errs.append(f"bad_novelty:{nov}")
    conf = card.get("confidence")
    if conf is not None and conf not in CONF_ENUM:
        errs.append(f"bad_confidence:{conf}")
    ev = card.get("vod_evidence")
    if ev is None:
        ev = []
    if not isinstance(ev, list):
        errs.append("bad_vod_evidence")
        return errs
    if not ev and nov == "also_in_vod":
        errs.append("also_in_vod_without_evidence")
    for i, item in enumerate(ev):
        if not evidence_in_vod(item, blobs):
            errs.append(f"vod_evidence_not_in_transcripts:{i}")
    return errs


def load_cluster_index(cards_dir: str) -> dict[str, set[str]]:
    path = os.path.join(cards_dir, "clusters.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out: dict[str, set[str]] = {}
    for row in data:
        cid = row.get("cluster_id")
        if cid:
            out[cid] = set(row.get("source_window_ids") or [])
    return out


def source_card_spans(wids: list[str], cards_by_id: dict[str, dict[str, Any]]) -> list[str]:
    spans: list[str] = []
    for wid in wids:
        c = cards_by_id.get(wid)
        if not c:
            continue
        spans.extend(str(x) for x in (c.get("source_spans") or []) if x)
        for p in c.get("underlying_parameters") or []:
            if p.get("source_span"):
                spans.append(str(p["source_span"]))
    return spans


def validate_merge_card(
    card: dict[str, Any],
    windows: dict[str, dict[str, Any]],
    clusters: dict[str, set[str]],
    cards_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    errs: list[str] = []
    if card.get("skip") is True:
        return errs
    cid = card.get("cluster_id")
    src = card.get("source_window_ids")
    if not isinstance(src, list) or not src:
        errs.append("missing_source_window_ids")
        src = []
    unknown = [w for w in src if w not in windows]
    if unknown:
        errs.append(f"source_window_ids_unknown:{len(unknown)}")
    if cid and clusters.get(cid):
        extra = [w for w in src if w not in clusters[cid]]
        if extra:
            errs.append(f"source_window_ids_outside_cluster:{len(extra)}")
    spans = source_card_spans([str(w) for w in src], cards_by_id)
    params = card.get("parameters")
    if params is None:
        params = []
    if not isinstance(params, list):
        errs.append("bad_parameters")
        return errs
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            errs.append(f"param_not_object:{i}")
            continue
        val = str(p.get("value") or "")
        sp = str(p.get("source_span") or "")
        if val and not any(normalize_text(val) in normalize_text(s) for s in spans):
            errs.append(f"merge_param_not_in_source_cards:{i}")
        if sp and not any(normalize_text(sp) in normalize_text(s) for s in spans + [val]):
            if not any(normalize_text(sp) in normalize_text(s) for s in spans):
                errs.append(f"merge_span_not_in_source_cards:{i}")
    return errs


def load_qq_cards_by_id(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path or not os.path.exists(path):
        return out
    for row in load_jsonl(path):
        obj = json.loads(row["_raw"]) if "_raw" in row else row
        if isinstance(obj, dict) and obj.get("window_id"):
            out[obj["window_id"]] = obj
    return out


def validate_glossary_card(
    card: dict[str, Any], cards_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    errs: list[str] = []
    if not (card.get("term") or "").strip():
        errs.append("empty_term")
    if card.get("status") not in (None, "glossary_draft"):
        if card.get("status") != "glossary_draft":
            errs.append(f"bad_status:{card.get('status')}")
    src = card.get("source_window_ids") or []
    if src and not isinstance(src, list):
        errs.append("bad_source_window_ids")
        src = []
    for w in src:
        if w not in cards_by_id:
            errs.append(f"source_window_id_unknown:{w}")
    return errs


FAKE_CD = re.compile(r"不随后续攻速|已有的冷却不会因为后续")


def iter_split_entries(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        if isinstance(obj.get("entries"), list):
            return [x for x in obj["entries"] if isinstance(x, dict)]
        return [obj]
    return []


def validate_split_payload(
    obj: Any, clusters: dict[str, set[str]]
) -> list[str]:
    errs: list[str] = []
    entries = iter_split_entries(obj)
    if not entries:
        errs.append("split_empty")
        return errs
    parent = None
    for e in entries:
        pid = e.get("parent_cluster_id")
        if pid:
            parent = pid
            break
    allowed = clusters.get(parent or "", set())
    for i, e in enumerate(entries):
        pid = e.get("parent_cluster_id") or parent
        if pid and pid not in clusters:
            errs.append(f"unknown_parent_cluster:{pid}")
        src = e.get("source_window_ids") or []
        if not isinstance(src, list):
            errs.append(f"bad_source_window_ids:{i}")
            continue
        allow = clusters.get(pid, allowed)
        extra = [w for w in src if allow and w not in allow]
        if extra:
            errs.append(f"source_window_ids_outside_parent:{i}:{len(extra)}")
        if pid == "c0011" and len(entries) < 2:
            errs.append("c0011_must_split")
        for cc in e.get("canonical_conclusions") or []:
            conc = str(cc.get("conclusion") or "")
            if FAKE_CD.search(conc) and "rejected" not in conc.lower() and not cc.get("rejected"):
                if "否" not in conc and "录播" not in conc:
                    errs.append(f"conflict_cooldown_as_fact:{i}")
    if parent == "c0011" and len(entries) < 2:
        if "c0011_must_split" not in errs:
            errs.append("c0011_must_split")
    return errs


def validate_alias_card(card: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for k in ("zh", "canonical_zh", "canonical_en", "merge_into", "note"):
        if k not in card:
            errs.append(f"missing_field:{k}")
    if "canonical_en" in card and card.get("canonical_en") is None:
        errs.append("canonical_en_null")
    return errs


def write_report(path: str, stats: dict[str, Any], details: list[str]) -> None:
    lines = [
        "# 知识卡片验收报告",
        "",
        f"- 总对象：{stats['total']}",
        f"- skip：{stats['skip']}",
        f"- 非 skip 卡：{stats['cards']}",
        f"- 通过：{stats['pass']}",
        f"- 失败：{stats['fail']}",
        f"- JSON 非法：{stats['json_invalid']}",
        "",
        "## 错误计数",
        "",
    ]
    counts: Counter[str] = Counter(stats.get("err_kinds") or [])
    if not counts:
        lines.append("（无）")
    else:
        for k, n in counts.most_common():
            lines.append(f"- `{k}`：{n}")
    lines.append("")
    lines.append("## 幻觉参数")
    lines.append("")
    halls = stats.get("hallucinations") or []
    if not halls:
        lines.append("（无）")
    else:
        for h in halls:
            lines.append(f"- `{h['window_id']}` value=`{h['value']}`")
    lines.append("")
    if details:
        lines.append("## 明细")
        lines.append("")
        lines.extend(details[:200])
        if len(details) > 200:
            lines.append(f"- …另有 {len(details) - 200} 条")
        lines.append("")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def result_glob(cards_dir: str, mode: str) -> list[str]:
    if mode == "novelty":
        patt = os.path.join(cards_dir, "cards_novelty_batch_*.jsonl")
    elif mode == "merge":
        patt = os.path.join(cards_dir, "cards_merge_batch_*.jsonl")
    elif mode == "glossary":
        patt = os.path.join(cards_dir, "cards_glossary_batch_*.jsonl")
    elif mode == "split":
        patt = os.path.join(cards_dir, "cards_split_batch_*.jsonl")
    elif mode == "alias":
        patt = os.path.join(cards_dir, "cards_alias_batch_*.jsonl")
    else:
        patt = os.path.join(cards_dir, "cards_batch_*.jsonl")
    files = sorted(glob.glob(patt))
    if not files:
        files = sorted(
            p
            for p in glob.glob(os.path.join(cards_dir, "*.jsonl"))
            if not os.path.basename(p).startswith("batch_")
            and os.path.basename(p) != "clusters.json"
        )
    return files


def run_validate(
    cards_dir: str,
    windows_path: str,
    messages_path: str,
    speakers_path: str,
    report_path: str,
    mode: str = "cards",
    transcripts_dir: str = "",
    qq_cards_path: str = "",
) -> dict[str, Any]:
    windows = load_windows(windows_path)
    msg_idx = load_messages(messages_path) if mode in {"cards", "ignore"} else {}
    qqs: list[str] = []
    nicks: list[str] = []
    if mode in {"cards", "ignore"}:
        with open(speakers_path, "r", encoding="utf-8") as f:
            speaker_map = json.load(f)
        qqs, nicks = privacy_lists(speaker_map)
    blobs = load_transcript_blobs(transcripts_dir) if mode == "novelty" else []
    clusters = load_cluster_index(cards_dir) if mode in {"merge", "split"} else {}
    cards_by_id: dict[str, dict[str, Any]] = {}
    if mode in {"merge", "glossary", "split"} and qq_cards_path:
        cards_by_id = load_qq_cards_by_id(qq_cards_path)

    files = result_glob(cards_dir, mode)
    rows: list[dict[str, Any]] = []
    for fp in files:
        rows.extend(load_jsonl(fp))

    stats: dict[str, Any] = {
        "total": 0,
        "skip": 0,
        "cards": 0,
        "pass": 0,
        "fail": 0,
        "json_invalid": 0,
        "err_kinds": [],
        "hallucinations": [],
    }
    details: list[str] = []
    for row in rows:
        stats["total"] += 1
        card, err = parse_card(row)
        loc = f"{row['_file']}:{row['_line']}"
        if err:
            stats["json_invalid"] += 1
            stats["fail"] += 1
            stats["err_kinds"].append("json_invalid")
            details.append(f"- {loc} {err}")
            continue
        assert card is not None
        if isinstance(card, dict) and card.get("skip") is True:
            stats["skip"] += 1
        else:
            stats["cards"] += 1
        if mode == "novelty":
            errs = validate_novelty_card(card, windows, blobs)
        elif mode == "merge":
            errs = validate_merge_card(card, windows, clusters, cards_by_id)
        elif mode == "glossary":
            errs = validate_glossary_card(card, cards_by_id)
        elif mode == "split":
            errs = validate_split_payload(card, clusters)
        elif mode == "alias":
            errs = validate_alias_card(card)
        else:
            errs = validate_card(card, windows, msg_idx, qqs, nicks)
        if errs:
            stats["fail"] += 1
            for e in errs:
                kind = e.split(":")[0]
                stats["err_kinds"].append(kind)
                if e.startswith("hallucination:"):
                    parts = e.split(":", 2)
                    stats["hallucinations"].append(
                        {"window_id": parts[1], "value": parts[2] if len(parts) > 2 else ""}
                    )
            wid = card.get("window_id") if isinstance(card, dict) else (card[0].get("parent_cluster_id") if isinstance(card, list) and card and isinstance(card[0], dict) else "")
            details.append(
                f"- {loc} window={wid} " + "; ".join(errs)
            )
        else:
            stats["pass"] += 1

    write_report(report_path, stats, details)
    return stats


def build_selftest(windows: dict[str, dict[str, Any]], msg_idx: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    wid = "w000001"
    w = windows.get(wid)
    if not w:
        wid = next(iter(windows))
        w = windows[wid]
    texts = window_texts(w, msg_idx)
    real_span = ""
    real_val = ""
    for t in texts:
        t1 = t.strip()
        if len(t1) >= 4:
            real_span = t1[: min(40, len(t1))]
            real_val = t1[:2]
            break
    mid = (w.get("source_msg_ids") or [""])[0]
    good = {
        "topic": "自测合法卡",
        "category": "其他",
        "entities": ["测试实体（Test Entity）"],
        "context_question": "自测",
        "core_conclusions": [
            {
                "speaker": "主播",
                "credibility": "authoritative",
                "conclusion": "自测结论，不引用外部知识。",
            }
        ],
        "underlying_parameters": [
            {
                "name": "excerpt",
                "value": real_val,
                "unit": "",
                "source_span": real_span,
            }
        ],
        "summary_takeaway": "自测通过样例",
        "window_id": wid,
        "as_of": w.get("end_time") or "",
        "status": "draft",
        "novelty": "unknown",
        "source_msg_ids": [mid] if mid else [],
        "source_spans": [real_span] if real_span else [],
    }
    bad = json.loads(json.dumps(good, ensure_ascii=False))
    bad["topic"] = "自测幻觉卡"
    bad["underlying_parameters"] = [
        {
            "name": "fake_frames",
            "value": "99999帧",
            "unit": "帧",
            "source_span": real_span,
        }
    ]
    return [good, bad]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="验收 LLM 知识卡片 JSONL")
    p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR)
    p.add_argument("--windows", default=DEFAULT_WINDOWS)
    p.add_argument("--messages", default=DEFAULT_MESSAGES)
    p.add_argument("--speakers", default=DEFAULT_SPEAKERS)
    p.add_argument("--report", default="", help="默认写到 cards-dir/validation_report.md")
    p.add_argument("--selftest", action="store_true", help="用 1 合法 + 1 幻觉卡自测")
    p.add_argument(
        "--mode",
        default="cards",
        choices=["cards", "ignore", "novelty", "merge", "glossary", "split", "alias"],
        help="cards/ignore=主 schema；novelty；merge；glossary；split；alias",
    )
    p.add_argument("--transcripts", default=DEFAULT_TRANSCRIPTS)
    p.add_argument("--qq-cards", default=DEFAULT_QQ_CARDS)
    args = p.parse_args(argv)

    if args.selftest:
        windows = load_windows(args.windows)
        msg_idx = load_messages(args.messages)
        cards = build_selftest(windows, msg_idx)
        tmp = tempfile.mkdtemp(prefix="qq_cards_selftest_")
        sample = os.path.join(tmp, "cards_batch_000.jsonl")
        with open(sample, "w", encoding="utf-8") as f:
            for c in cards:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        report = os.path.join(tmp, "validation_report.md")
        stats = run_validate(
            tmp, args.windows, args.messages, args.speakers, report, mode="cards"
        )
        print(
            f"selftest dir={tmp} total={stats['total']} pass={stats['pass']} "
            f"fail={stats['fail']} hallucinations={len(stats['hallucinations'])}"
        )
        print(f"report={report}")
        ok = stats["pass"] == 1 and stats["fail"] == 1 and len(stats["hallucinations"]) == 1
        if not ok:
            log("selftest 期望：1 通过 + 1 幻觉失败")
            return 1
        print("selftest OK")
        return 0

    cards_dir = args.cards_dir
    report = args.report or os.path.join(cards_dir, "validation_report.md")
    if not os.path.isdir(cards_dir):
        log(f"cards-dir 不存在: {cards_dir}")
        return 1
    stats = run_validate(
        cards_dir,
        args.windows,
        args.messages,
        args.speakers,
        report,
        mode=args.mode,
        transcripts_dir=args.transcripts,
        qq_cards_path=args.qq_cards,
    )
    print(
        f"total={stats['total']} skip={stats['skip']} cards={stats['cards']} "
        f"pass={stats['pass']} fail={stats['fail']} json_invalid={stats['json_invalid']} "
        f"hallucinations={len(stats['hallucinations'])}"
    )
    print(f"report={report}")
    return 0 if stats["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
