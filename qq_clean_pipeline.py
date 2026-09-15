#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_clean_pipeline.py
--------------------
桃大将军粉丝群聊天清洗流水线（第 0–4 步 + 金标抽样）：
  0. 流式解析 CSV → speaker_map.json
  1. 硬过滤打标后物理删除：empty / bot / flood_dup / 纯占位媒体
     保留 mixed_media 正文（text_stripped）→ messages_clean.jsonl
  2. 弱切簇 + 权威窗（默认 20 分钟间隔，±K 条）
  3. 召回排序：保送 / score 分档 candidate|maybe|ignore
  4. 锚点瘦身：保送/词表命中为锚，连续 --slack 条无锚即截断；<5 条降 maybe
     并写出 gold_sample.md 分层抽样

群聊原文零纠错，禁止调用 entity_corrector。
仅使用标准库。产物写入 qq_info/（已被 .gitignore）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(
    ROOT_DIR, "qq_info", "1097395794_桃大将军粉丝群_聊天记录.csv"
)
DEFAULT_OUTDIR = os.path.join(ROOT_DIR, "qq_info")
DEFAULT_ENTITIES = os.path.join(ROOT_DIR, "prts_entities.json")

HOST_QQ = "2580863623"
EXPERT_QQ = "724873295"
DEFAULT_BOT_QQS = (
    "3369126805",  # 可露希尔 LLM bot（含每日群聊分析报告）
    "798522056",  # 小凌弥
    "2846210149",
)

TIME_FMT = "%Y-%m-%d %H:%M:%S"

MEDIA_TOKENS = (
    "[图片]",
    "[视频]",
    "[文件]",
    "[语音]",
    "[多媒体消息或表情]",
    "[表情]",
)
MEDIA_RE = re.compile(
    r"\[(?:图片|视频|文件|语音|多媒体消息或表情|表情)\]"
)

NUM_UNIT_RE = re.compile(r"\d+(?:\.\d+)?(?:帧|秒|格|半径|费|技力)")
UNPACK_RE = re.compile(
    r"拆包|解包|prefab|ab包|TypeTree|AssetStudio",
    re.IGNORECASE,
)
LIVE_HINTS = ("开播", "上课", "开课", "加课", "继续播")

HARDCORE_TERMS = (
    "帧",
    "索敌",
    "技力",
    "攻速",
    "攻击间隔",
    "判定",
    "位移",
    "力道",
    "阻挡",
    "碰撞",
    "寻路",
    "出怪",
    "永控",
    "入控",
    "免控",
    "锁血",
    "隐匿",
    "嘲讽",
    "再部署",
)

REPORT_MARKERS = ("每日群聊分析报告", "群分析日报告", "每日群聊分析")
DROP_FLAGS = frozenset({"media_placeholder", "is_bot", "flood_dup", "empty"})
SLIM_MAX = 60
SLIM_DEMOTE_LT = 5


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def sha1_8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def parse_time(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, TIME_FMT)
    except ValueError:
        return None


def speaker_key(qq: str, uid: str, nick: str, msg_id: str) -> tuple[str, str]:
    """Return (raw_id, id_type). Identity binds to QQ, else UID."""
    if qq:
        return qq, "qq"
    if uid:
        return uid, "uid"
    if nick:
        return "nick:" + nick, "nick"
    return "msg:" + msg_id, "anon"


def strip_media(text: str) -> str:
    return MEDIA_RE.sub("", text).strip()


def classify_media(text: str) -> tuple[bool, bool, str]:
    """Return (media_placeholder, mixed_media, text_stripped)."""
    stripped = strip_media(text)
    has_token = any(tok in text for tok in MEDIA_TOKENS)
    if has_token and not stripped:
        return True, False, ""
    if has_token and stripped:
        return False, True, stripped
    return False, False, ""


def is_live_session(text: str) -> bool:
    t = (text or "").strip()
    if "@全体成员" in t and any(h in t for h in LIVE_HINTS):
        return True
    if t.startswith("开播"):
        return True
    return False


def load_shenqi_slangs(path: str) -> list[str]:
    terms: list[str] = []
    if not os.path.exists(path):
        log(f"[warn] 未找到实体词表: {path}")
        return terms
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    slangs = data.get("shenqi_slangs") or {}
    if isinstance(slangs, dict):
        for _group, items in slangs.items():
            if isinstance(items, list):
                terms.extend(str(x) for x in items if x)
    elif isinstance(slangs, list):
        terms.extend(str(x) for x in slangs if x)
    return terms


def build_vocab(slang_terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in list(slang_terms) + list(HARDCORE_TERMS):
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    out.sort(key=len, reverse=True)
    return out


def hit_terms_in(text: str, vocab: list[str]) -> list[str]:
    if not text:
        return []
    low = text.lower()
    hits = []
    for term in vocab:
        needle = term.lower()
        if needle and needle in low:
            hits.append(term)
    return hits


def percentile(sorted_vals: list[int], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def parse_id_list(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def parse_csv(path: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "physical_lines": 0,
        "logical_messages": 0,
        "empty_time": 0,
        "empty_qq": 0,
        "empty_qq_uid": 0,
        "multiline": 0,
        "out_of_order": 0,
    }
    with open(path, "rb") as bf:
        stats["physical_lines"] = sum(1 for _ in bf)

    messages: list[dict[str, Any]] = []
    prev_dt: datetime | None = None
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            msg_id = (row.get("消息ID") or "").strip()
            time_str = (row.get("发送时间") or "").strip()
            qq = (row.get("发送人QQ") or "").strip()
            uid = (row.get("发送人UID") or "").strip()
            nick = row.get("发送人昵称") or ""
            text = row.get("消息内容") or ""
            dt = parse_time(time_str)
            flags: list[str] = []
            if dt is None:
                flags.append("empty_time")
                stats["empty_time"] += 1
            elif prev_dt is not None and dt < prev_dt:
                stats["out_of_order"] += 1
            if dt is not None:
                prev_dt = dt
            if not qq:
                stats["empty_qq"] += 1
            if not qq and not uid:
                stats["empty_qq_uid"] += 1
            if "\n" in text or "\r" in text:
                stats["multiline"] += 1

            sk, id_type = speaker_key(qq, uid, nick.strip(), msg_id)
            media_ph, mixed, stripped = classify_media(text)
            if media_ph:
                flags.append("media_placeholder")
            if mixed:
                flags.append("mixed_media")

            rec = {
                "msg_id": msg_id,
                "ts": None if dt is None else int(dt.timestamp()),
                "time_str": time_str,
                "qq": qq,
                "uid": uid,
                "nick": nick,
                "text": text,
                "flags": flags,
                "_idx": idx,
                "_dt": dt,
                "_sk": sk,
                "_id_type": id_type,
                "speaker_id": sha1_8(sk),
            }
            if mixed:
                rec["text_stripped"] = stripped
            messages.append(rec)

    stats["logical_messages"] = len(messages)
    return messages, stats


def fill_empty_times(messages: list[dict[str, Any]]) -> None:
    carry: int | None = None
    for m in messages:
        if m["ts"] is None:
            m["ts"] = carry
        else:
            carry = m["ts"]
    carry = None
    for m in reversed(messages):
        if m["ts"] is None:
            m["ts"] = carry
        else:
            carry = m["ts"]
    for m in messages:
        if m["ts"] is None:
            m["ts"] = 0
        if m["_dt"] is None and m["ts"]:
            try:
                m["_dt"] = datetime.fromtimestamp(m["ts"])
                if not m["time_str"]:
                    m["time_str"] = m["_dt"].strftime(TIME_FMT)
            except (OSError, OverflowError, ValueError):
                pass


def apply_bot_and_live(
    messages: list[dict[str, Any]],
    bot_qqs: set[str],
    host_qq: str,
) -> dict[str, int]:
    n_bot = 0
    n_live = 0
    for m in messages:
        if m["qq"] and m["qq"] in bot_qqs:
            if "is_bot" not in m["flags"]:
                m["flags"].append("is_bot")
            n_bot += 1
        if m["qq"] == host_qq and is_live_session(m["text"]):
            if "live_session" not in m["flags"]:
                m["flags"].append("live_session")
            n_live += 1
    return {"is_bot": n_bot, "live_session": n_live}


def discover_report_bots(
    messages: list[dict[str, Any]], bot_qqs: set[str]
) -> tuple[list[tuple[str, int]], Counter[str]]:
    counts: Counter[str] = Counter()
    for m in messages:
        text = m["text"] or ""
        if any(marker in text for marker in REPORT_MARKERS) or text.startswith("📊"):
            if m["qq"]:
                counts[m["qq"]] += 1
    extra: list[tuple[str, int]] = []
    for qq, n in counts.most_common():
        if qq not in bot_qqs and n >= 20:
            extra.append((qq, n))
    return extra, counts


def apply_noise_and_flood(
    messages: list[dict[str, Any]],
    authority_qqs: set[str],
) -> dict[str, int]:
    n_empty = 0
    n_flood = 0
    n_noise = 0
    for i, m in enumerate(messages):
        text = m["text"] if m["text"] is not None else ""
        if not text.strip():
            if "empty" not in m["flags"]:
                m["flags"].append("empty")
            n_empty += 1
        if i > 0:
            prev = messages[i - 1]
            same_speaker = m["_sk"] == prev["_sk"]
            same_text = m["text"] == prev["text"]
            long_enough = len(m["text"] or "") >= 4
            not_auth = m["qq"] not in authority_qqs
            if same_speaker and same_text and long_enough and not_auth:
                if "flood_dup" not in m["flags"]:
                    m["flags"].append("flood_dup")
                n_flood += 1
        if (
            "empty" in m["flags"]
            or "is_bot" in m["flags"]
            or "flood_dup" in m["flags"]
        ):
            if "noise" not in m["flags"]:
                m["flags"].append("noise")
            n_noise += 1
    return {"empty": n_empty, "flood_dup": n_flood, "noise": n_noise}


def drop_tagged(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Physically drop tagged noise; keep mixed_media with stripped body."""
    kept: list[dict[str, Any]] = []
    by_flag: Counter[str] = Counter()
    n_multi = 0
    for m in messages:
        hits = [f for f in DROP_FLAGS if f in m["flags"]]
        if hits:
            for f in hits:
                by_flag[f] += 1
            if len(hits) > 1:
                n_multi += 1
            continue
        if "mixed_media" in m["flags"] and m.get("text_stripped"):
            m["text"] = m["text_stripped"]
        kept.append(m)
    return kept, {
        "dropped": len(messages) - len(kept),
        "kept": len(kept),
        "by_flag": dict(by_flag),
        "multi_flag": n_multi,
    }


def build_speaker_map(messages: list[dict[str, Any]]) -> dict[str, Any]:
    speakers: dict[str, dict[str, Any]] = {}
    for m in messages:
        sk = m["_sk"]
        rec = speakers.get(sk)
        if rec is None:
            rec = {
                "speaker_id": m["speaker_id"],
                "id_type": m["_id_type"],
                "nicks": {},
                "n_messages": 0,
            }
            speakers[sk] = rec
        rec["n_messages"] += 1
        nick = m["nick"] or ""
        slot = rec["nicks"].get(nick)
        if slot is None:
            rec["nicks"][nick] = {
                "nick": nick,
                "count": 0,
                "first_ts": m["ts"],
                "last_ts": m["ts"],
            }
            slot = rec["nicks"][nick]
        slot["count"] += 1
        if m["ts"] < slot["first_ts"]:
            slot["first_ts"] = m["ts"]
        if m["ts"] > slot["last_ts"]:
            slot["last_ts"] = m["ts"]

    out_speakers = {}
    for sk, rec in speakers.items():
        nicks_sorted = sorted(
            rec["nicks"].values(), key=lambda x: (-x["count"], x["first_ts"])
        )
        out_speakers[sk] = {
            "speaker_id": rec["speaker_id"],
            "id_type": rec["id_type"],
            "n_messages": rec["n_messages"],
            "nicks": nicks_sorted,
        }
    return {
        "n_speakers": len(out_speakers),
        "speakers": out_speakers,
    }


def make_clusters(
    messages: list[dict[str, Any]], gap_seconds: int
) -> list[list[int]]:
    """Return clusters as lists of indices into cleaned `messages`."""
    if not messages:
        return []
    clusters: list[list[int]] = [[0]]
    for i in range(1, len(messages)):
        gap = messages[i]["ts"] - messages[i - 1]["ts"]
        if gap > gap_seconds:
            clusters.append([i])
        else:
            clusters[-1].append(i)
    return clusters


def cluster_stats(clusters: list[list[int]]) -> dict[str, Any]:
    sizes = sorted(len(c) for c in clusters)
    if not sizes:
        return {
            "n_clusters": 0,
            "mean": 0,
            "min": 0,
            "max": 0,
            "p25": 0,
            "p50": 0,
            "p75": 0,
            "p90": 0,
            "singletons": 0,
        }
    return {
        "n_clusters": len(clusters),
        "mean": round(sum(sizes) / len(sizes), 2),
        "min": sizes[0],
        "max": sizes[-1],
        "p25": round(percentile(sizes, 25), 2),
        "p50": round(percentile(sizes, 50), 2),
        "p75": round(percentile(sizes, 75), 2),
        "p90": round(percentile(sizes, 90), 2),
        "singletons": sum(1 for s in sizes if s == 1),
    }


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    return [(a, b) for a, b in merged]


def role_of(qq: str, host_qq: str, expert_qqs: set[str]) -> str | None:
    if qq == host_qq:
        return "host"
    if qq in expert_qqs:
        return "expert"
    return None


def msg_blob(m: dict[str, Any]) -> str:
    return m.get("text_stripped") or m.get("text") or ""


def is_fast_anchor(m: dict[str, Any], authority_qqs: set[str]) -> bool:
    if m.get("qq") not in authority_qqs:
        return False
    blob = msg_blob(m)
    return bool(NUM_UNIT_RE.search(blob) or UNPACK_RE.search(blob))


def is_vocab_anchor(m: dict[str, Any], vocab: list[str]) -> bool:
    return bool(hit_terms_in(msg_blob(m), vocab))


def list_size_stats(sizes: list[int]) -> dict[str, Any]:
    sizes_sorted = sorted(sizes)
    if not sizes_sorted:
        return {
            "n": 0,
            "mean": 0,
            "min": 0,
            "max": 0,
            "p25": 0,
            "p50": 0,
            "p75": 0,
            "p90": 0,
            "ge60": 0,
            "in_20_60": 0,
            "lt5": 0,
        }
    return {
        "n": len(sizes_sorted),
        "mean": round(sum(sizes_sorted) / len(sizes_sorted), 2),
        "min": sizes_sorted[0],
        "max": sizes_sorted[-1],
        "p25": round(percentile(sizes_sorted, 25), 2),
        "p50": round(percentile(sizes_sorted, 50), 2),
        "p75": round(percentile(sizes_sorted, 75), 2),
        "p90": round(percentile(sizes_sorted, 90), 2),
        "ge60": sum(1 for s in sizes_sorted if s > 60),
        "in_20_60": sum(1 for s in sizes_sorted if 20 <= s <= 60),
        "lt5": sum(1 for s in sizes_sorted if s < 5),
    }


def slim_recs(
    recs: list[dict[str, Any]],
    slack: int,
    authority_qqs: set[str],
    vocab: list[str],
    max_n: int = SLIM_MAX,
) -> list[dict[str, Any]]:
    """Keep messages within `slack` of a fast-track or vocab-hit anchor.

    If still longer than max_n, center a max_n slice on the first 保送锚
    (else first vocab anchor). No anchors → leave the window unchanged.
    """
    n = len(recs)
    if n == 0:
        return recs
    anchors: list[int] = []
    fast_idx: list[int] = []
    for i, m in enumerate(recs):
        fa = is_fast_anchor(m, authority_qqs)
        va = is_vocab_anchor(m, vocab)
        if fa or va:
            anchors.append(i)
            if fa:
                fast_idx.append(i)
    if not anchors:
        return recs
    keep = [False] * n
    for a in anchors:
        lo = max(0, a - slack)
        hi = min(n - 1, a + slack)
        for j in range(lo, hi + 1):
            keep[j] = True
    kept_i = [i for i in range(n) if keep[i]]
    if len(kept_i) > max_n:
        prefer = fast_idx[0] if fast_idx else anchors[0]
        pos = min(range(len(kept_i)), key=lambda j: abs(kept_i[j] - prefer))
        start = max(0, pos - max_n // 2)
        start = min(start, len(kept_i) - max_n)
        kept_i = kept_i[start : start + max_n]
    return [recs[i] for i in kept_i]


def summarize_window_recs(
    recs: list[dict[str, Any]],
    host_qq: str,
    expert_qqs: set[str],
    authority_qqs: set[str],
    vocab: list[str],
) -> dict[str, Any]:
    auths = []
    seen_sid: set[str] = set()
    fast = False
    term_set: list[str] = []
    seen_terms: set[str] = set()
    n_auth_msgs = 0
    n_mixed = 0
    for r in recs:
        if "mixed_media" in r["flags"]:
            n_mixed += 1
        blob = msg_blob(r)
        for t in hit_terms_in(blob, vocab):
            if t not in seen_terms:
                seen_terms.add(t)
                term_set.append(t)
        if r["qq"] in authority_qqs:
            n_auth_msgs += 1
            sid = r["speaker_id"]
            if sid not in seen_sid:
                seen_sid.add(sid)
                role = role_of(r["qq"], host_qq, expert_qqs) or "authority"
                auths.append({"speaker_id": sid, "role": role})
            if NUM_UNIT_RE.search(blob) or UNPACK_RE.search(blob):
                fast = True
    score = len(term_set) * (2 if n_auth_msgs >= 1 else 1)
    if fast or score >= 3:
        tier = "candidate"
    elif score >= 1:
        tier = "maybe"
    else:
        tier = "ignore"
    mixed_ratio = (n_mixed / len(recs)) if recs else 0.0
    return {
        "authorities": auths,
        "hit_terms": term_set,
        "score": score,
        "tier": tier,
        "fast_track": fast,
        "evidence_lost": mixed_ratio > 0.30,
        "n_auth_msgs": n_auth_msgs,
    }


def build_windows(
    messages: list[dict[str, Any]],
    clusters: list[list[int]],
    k: int,
    host_qq: str,
    expert_qqs: set[str],
    authority_qqs: set[str],
    vocab: list[str],
    slack: int,
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    wid = 0
    for cid, idxs in enumerate(clusters):
        n = len(idxs)
        centers: list[tuple[int, int]] = []
        for pos, mi in enumerate(idxs):
            m = messages[mi]
            if m["qq"] not in authority_qqs:
                continue
            lo = max(0, pos - k)
            hi = min(n - 1, pos + k)
            centers.append((lo, hi))
        if not centers:
            continue
        for lo, hi in merge_intervals(centers):
            slice_idxs = idxs[lo : hi + 1]
            recs = [messages[i] for i in slice_idxs]
            raw = summarize_window_recs(
                recs, host_qq, expert_qqs, authority_qqs, vocab
            )
            raw_n = len(recs)
            slim = slim_recs(recs, slack, authority_qqs, vocab)
            slim_n = len(slim)
            slim_sum = summarize_window_recs(
                slim, host_qq, expert_qqs, authority_qqs, vocab
            )
            # 分档仍按瘦身前全文；仅 <5 条的 candidate 降 maybe。
            tier = raw["tier"]
            demoted = False
            if slim_n < SLIM_DEMOTE_LT and tier == "candidate":
                tier = "maybe"
                demoted = True
            out_recs = slim if slim else recs
            wid += 1
            windows.append(
                {
                    "window_id": f"w{wid:06d}",
                    "cluster_id": cid,
                    "start_ts": out_recs[0]["ts"],
                    "end_ts": out_recs[-1]["ts"],
                    "start_time": out_recs[0]["time_str"],
                    "end_time": out_recs[-1]["time_str"],
                    "n_messages": len(out_recs),
                    "raw_n": raw_n,
                    "slim_n": slim_n,
                    "authorities": slim_sum["authorities"],
                    "hit_terms": raw["hit_terms"],
                    "score": raw["score"],
                    "tier": tier,
                    "raw_tier": raw["tier"],
                    "fast_track": raw["fast_track"],
                    "demoted_short": demoted,
                    "evidence_lost": slim_sum["evidence_lost"],
                    "source_msg_ids": [r["msg_id"] for r in out_recs],
                }
            )
    return windows


def dump_jsonl(path: str, rows: list[dict[str, Any]], drop_keys: tuple[str, ...] = ()) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            if drop_keys:
                out = {k: v for k, v in row.items() if k not in drop_keys}
            else:
                out = row
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


def role_tag(role: str) -> str:
    return {"host": "[主播]", "expert": "[专家]", "authority": "[权威]"}.get(role, "")


def preview_text(text: str, n: int = 80) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) > n:
        return t[:n] + "…"
    return t


def fmt_cluster_stats(label: str, st: dict[str, Any]) -> str:
    return (
        f"- **{label}**：簇数 {st['n_clusters']}，"
        f"大小 mean={st['mean']} / min={st['min']} / max={st['max']}，"
        f"p25={st['p25']} / p50={st['p50']} / p75={st['p75']} / p90={st['p90']}，"
        f"单条簇 {st['singletons']}"
    )


def write_report(
    path: str,
    parse_stats: dict[str, int],
    flag_stats: dict[str, int],
    drop_stats: dict[str, Any],
    extra_bots: list[tuple[str, int]],
    report_counts: Counter,
    bot_qqs: set[str],
    stats_8: dict[str, Any],
    stats_20: dict[str, Any],
    gap_minutes: int,
    k: int,
    slack: int,
    windows: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    host_qq: str,
    expert_qqs: set[str],
    seed: int,
) -> None:
    by_id = {m["msg_id"]: m for m in messages}
    tiers = Counter(w["tier"] for w in windows)
    n_fast = sum(1 for w in windows if w.get("fast_track"))
    n_lost = sum(1 for w in windows if w.get("evidence_lost"))
    top = sorted(
        windows,
        key=lambda w: (-w["score"], -w["n_messages"], w["start_ts"]),
    )[:20]
    ignores = [w for w in windows if w["tier"] == "ignore"]
    rng = random.Random(seed)
    sample_ign = (
        rng.sample(ignores, 10) if len(ignores) >= 10 else list(ignores)
    )
    sample_ign.sort(key=lambda w: w["start_ts"])

    media_ph = flag_stats.get("media_placeholder", 0)
    mixed = flag_stats.get("mixed_media", 0)
    n_msg = parse_stats["logical_messages"]
    n_drop = drop_stats.get("dropped", 0)
    n_kept = drop_stats.get("kept", len(messages))
    by_flag = drop_stats.get("by_flag") or {}
    mixed_kept = sum(1 for m in messages if "mixed_media" in m["flags"])

    lines: list[str] = []
    a = lines.append
    a("# 群聊清洗流水线报告（第 0–4 步）")
    a("")
    a("原文零纠错；身份绑定 QQ（空则 UID）；昵称仅作显示名，本报告用 `speaker_id` 脱敏。")
    a("第 1 步打标后物理删除噪音，切簇/开窗/打分与 `messages_clean.jsonl` 均基于删除后语料。")
    a("第 4 步按保送/词表锚点瘦身，`source_msg_ids` 为瘦身后序列。")
    a("")
    a("## 0. 解析统计")
    a("")
    a(f"- 物理行（含表头）：{parse_stats['physical_lines']}")
    a(f"- 逻辑消息：{parse_stats['logical_messages']}")
    a(f"- 多行消息：{parse_stats['multiline']}")
    a(f"- 时间为空：{parse_stats['empty_time']}（已前后向填充后按时间排序，原序作 tiebreak）")
    a(f"- 文件序乱序（当前条时间 < 上一条有效时间）：{parse_stats['out_of_order']}")
    a(f"- 空 QQ：{parse_stats['empty_qq']}（其中 QQ+UID 皆空：{parse_stats['empty_qq_uid']}）")
    a(f"- 说话人映射条目：见 `speaker_map.json`")
    a("")
    a("## 1. 过滤：打标后物理删除")
    a("")
    a(f"- 解析总条数：{n_msg}")
    a(f"- 物理删除：{n_drop}（{n_drop / n_msg:.1%}）")
    a(f"  - `media_placeholder`：{by_flag.get('media_placeholder', media_ph)}")
    a(f"  - `is_bot`：{by_flag.get('is_bot', flag_stats.get('is_bot', 0))}")
    a(f"  - `flood_dup`：{by_flag.get('flood_dup', flag_stats.get('flood_dup', 0))}（短句 <4 字与权威发言不打，保留首条）")
    a(f"  - `empty`：{by_flag.get('empty', flag_stats.get('empty', 0))}")
    a(f"  - 同时命中多类（去重计入删除总数）：{drop_stats.get('multi_flag', 0)}")
    a(f"- 删除后剩余：{n_kept}")
    a(f"- 保留 `mixed_media`：{mixed_kept}（正文用 `text_stripped`；全量打标 {mixed}）")
    a(f"- `live_session`（删除后仍在语料中）：{sum(1 for m in messages if 'live_session' in m['flags'])}（仅标记，不作为切簇边界）")
    a("")
    a("### Bot 黑名单")
    a("")
    a(f"- 配置 QQ 数：{len(bot_qqs)}")
    a("- 数据内「群分析日报告」检索：按消息含「每日群聊分析报告」/「📊」计次，"
      "最高频账号与可露希尔 LLM bot 为同一 QQ，未发现独立的 ~93 条日报小号。")
    if report_counts:
        a(f"- 日报特征命中最多的已列入黑名单账号次数：{max(report_counts.values())}")
    if extra_bots:
        a("- 额外发现且已并入黑名单：")
        for qq, n in extra_bots:
            a(f"  - speaker `{sha1_8(qq)}`（{n} 条日报特征）")
    else:
        a("- 无额外独立日报 bot QQ 需要并入。")
    a("")
    a("## 2. 弱切簇对比")
    a("")
    a("在删除后语料上，按相邻消息时间间隔切簇。")
    a("")
    a(fmt_cluster_stats("8 分钟", stats_8))
    a(fmt_cluster_stats("20 分钟", stats_20))
    a("")
    a(f"主产物使用 **{gap_minutes} 分钟** 间隔，权威窗半径 K={k}。")
    a("")
    a("## 3. 权威窗召回")
    a("")
    a(f"- 窗总数：{len(windows)}")
    a(f"- 瘦身前 raw_tier candidate/maybe/ignore："
      f"{sum(1 for w in windows if w.get('raw_tier') == 'candidate')} / "
      f"{sum(1 for w in windows if w.get('raw_tier') == 'maybe')} / "
      f"{sum(1 for w in windows if w.get('raw_tier') == 'ignore')}")
    a(f"- 瘦身后 tier `candidate`：{tiers.get('candidate', 0)}")
    a(f"- 瘦身后 tier `maybe`：{tiers.get('maybe', 0)}")
    a(f"- 瘦身后 tier `ignore`：{tiers.get('ignore', 0)}")
    a(f"- 保送（数字+单位 / 拆包词）`fast_track`：{n_fast}")
    a(f"- 因 slim_n<{SLIM_DEMOTE_LT} 从 candidate 降 maybe：{sum(1 for w in windows if w.get('demoted_short'))}")
    a(f"- `evidence_lost`（瘦身后窗内 mixed_media >30%）：{n_lost}")
    a("")
    raw_st = list_size_stats([int(w.get("raw_n") or w["n_messages"]) for w in windows])
    slim_st = list_size_stats([int(w.get("slim_n") or w["n_messages"]) for w in windows])
    a("## 4. 窗口瘦身")
    a("")
    a(f"锚点 = 权威保送消息 ∪ 词表命中消息；连续 {slack} 条无锚即截断；"
      f"超过 {SLIM_MAX} 条时以首个保送（否则首个词表锚）为中心裁到 {SLIM_MAX}。")
    a("")
    a(
        f"- **瘦身前 raw_n**：mean={raw_st['mean']} / min={raw_st['min']} / max={raw_st['max']}，"
        f"p25={raw_st['p25']} / p50={raw_st['p50']} / p75={raw_st['p75']} / p90={raw_st['p90']}，"
        f">60 条 {raw_st['ge60']}，20–60 条 {raw_st['in_20_60']}，<5 条 {raw_st['lt5']}"
    )
    a(
        f"- **瘦身后 slim_n**：mean={slim_st['mean']} / min={slim_st['min']} / max={slim_st['max']}，"
        f"p25={slim_st['p25']} / p50={slim_st['p50']} / p75={slim_st['p75']} / p90={slim_st['p90']}，"
        f">60 条 {slim_st['ge60']}，20–60 条 {slim_st['in_20_60']}，<5 条 {slim_st['lt5']}"
    )
    a("")
    a("### Score Top 20")
    a("")
    for i, w in enumerate(top, 1):
        auth_s = ", ".join(
            f"{x['speaker_id']}{role_tag(x['role'])}" for x in w["authorities"]
        ) or "—"
        hits = ", ".join(w["hit_terms"][:12]) or "—"
        if len(w["hit_terms"]) > 12:
            hits += f" …(+{len(w['hit_terms']) - 12})"
        a(
            f"{i}. `{w['window_id']}` {w['start_time']} ~ {w['end_time']} "
            f"raw_n={w.get('raw_n', w['n_messages'])} slim_n={w.get('slim_n', w['n_messages'])} "
            f"score={w['score']} tier={w['tier']} "
            f"fast={w['fast_track']} lost={w['evidence_lost']}"
        )
        a(f"   - 权威：{auth_s}")
        a(f"   - 命中词：{hits}")
        shown = 0
        for mid in w["source_msg_ids"]:
            m = by_id.get(mid)
            if not m or m["qq"] not in {host_qq, *expert_qqs}:
                continue
            tag = role_tag(role_of(m["qq"], host_qq, expert_qqs) or "authority")
            a(f"   - {tag}`{m['speaker_id']}` {preview_text(m['text'])}")
            shown += 1
            if shown >= 3:
                break
        a("")
    a("### 随机 ignore 窗抽查（seed={}，人工核验误杀）".format(seed))
    a("")
    if not sample_ign:
        a("（无 ignore 窗）")
    for w in sample_ign:
        auth_s = ", ".join(
            f"{x['speaker_id']}{role_tag(x['role'])}" for x in w["authorities"]
        ) or "—"
        a(
            f"- `{w['window_id']}` {w['start_time']} ~ {w['end_time']} "
            f"n={w['n_messages']} score={w['score']} 权威：{auth_s}"
        )
        shown = 0
        for mid in w["source_msg_ids"]:
            m = by_id.get(mid)
            if not m:
                continue
            a(f"  - `{m['speaker_id']}` {preview_text(m['text'], 60)}")
            shown += 1
            if shown >= 3:
                break
    a("")
    a("## 产物")
    a("")
    a("- `qq_info/messages_clean.jsonl`（删除噪音后的唯一消息产物；全量原文见 CSV）")
    a("- `qq_info/speaker_map.json`")
    a("- `qq_info/windows.jsonl`（含 raw_n / slim_n，source_msg_ids 为瘦身结果）")
    a("- `qq_info/gold_sample.md`（分层 50 窗，不入库）")
    a("- `qq_info/pipeline_report.md`（本文件）")
    a("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def speaker_label(m: dict[str, Any], host_qq: str, expert_qqs: set[str]) -> str:
    role = role_of(m["qq"], host_qq, expert_qqs)
    if role == "host":
        return "[主播]"
    if role == "expert":
        return "[专家]"
    return m["speaker_id"]


def clock_of(m: dict[str, Any]) -> str:
    ts = (m.get("time_str") or "").strip()
    if len(ts) >= 8 and " " in ts:
        return ts.split(" ", 1)[1][:8]
    if len(ts) >= 8:
        return ts[-8:]
    return ts or "??:??:??"


def take_sample(pool: list[dict[str, Any]], n: int, rng: random.Random, used: set[str]) -> list[dict[str, Any]]:
    avail = [w for w in pool if w["window_id"] not in used]
    if not avail:
        return []
    k = min(n, len(avail))
    picked = rng.sample(avail, k)
    for w in picked:
        used.add(w["window_id"])
    return picked


def write_gold_sample(
    path: str,
    windows: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    host_qq: str,
    expert_qqs: set[str],
    seed: int,
) -> int:
    by_id = {m["msg_id"]: m for m in messages}
    rng = random.Random(seed)
    used: set[str] = set()
    cand_fast = [w for w in windows if w["tier"] == "candidate" and w.get("fast_track")]
    cand_vocab = [
        w
        for w in windows
        if w["tier"] == "candidate" and not w.get("fast_track")
    ]
    cand_vocab.sort(key=lambda w: (-w["score"], -w.get("slim_n", 0)))
    maybe = [w for w in windows if w["tier"] == "maybe"]
    ignore = [w for w in windows if w["tier"] == "ignore"]

    strata: list[tuple[str, list[dict[str, Any]]]] = []
    strata.append(("candidate 保送", take_sample(cand_fast, 10, rng, used)))
    high = [w for w in cand_vocab if w["window_id"] not in used][:10]
    for w in high:
        used.add(w["window_id"])
    if len(high) < 10:
        rest_cand = [
            w
            for w in windows
            if w["tier"] == "candidate" and w["window_id"] not in used
        ]
        rest_cand.sort(key=lambda w: (-w["score"], -w.get("slim_n", 0)))
        fill = rest_cand[: 10 - len(high)]
        for w in fill:
            used.add(w["window_id"])
        high.extend(fill)
    strata.append(("candidate 词表高分", high))
    strata.append(("maybe", take_sample(maybe, 10, rng, used)))
    strata.append(("ignore", take_sample(ignore, 10, rng, used)))
    strata.append(("随机（ignore 补抽）", take_sample(ignore, 10, rng, used)))

    sampled: list[tuple[str, dict[str, Any]]] = []
    for name, group in strata:
        for w in group:
            sampled.append((name, w))

    lines: list[str] = []
    a = lines.append
    a("# 金标抽样表（机器分层，待人工标注）")
    a("")
    a("共 50 窗：candidate 保送 10、candidate 词表高分 10、maybe 10、ignore 10、随机 ignore 10。")
    a("说话人已脱敏：`[主播]` / `[专家]` / `speaker_id`。请勿把本文件提交到 Git。")
    a("")
    a("## 核对清单")
    a("")
    a("人工标注三列：**真机制 / 闲聊**、**是否被切断上下文**、**建议 tier**（candidate / maybe / ignore）。")
    a("")
    a("| window_id | 分层 | 机器 tier | 真机制/闲聊 | 是否切断上下文 | 建议 tier |")
    a("|---|---|---|---|---|---|")
    for name, w in sampled:
        a(f"| `{w['window_id']}` | {name} | {w['tier']} |  |  |  |")
    a("")
    a("---")
    a("")

    for name, w in sampled:
        hits = ", ".join(w.get("hit_terms") or []) or "—"
        auth_s = ", ".join(
            f"{x['speaker_id']}{role_tag(x['role'])}" for x in (w.get("authorities") or [])
        ) or "—"
        a(f"## `{w['window_id']}` · {name}")
        a("")
        a(
            f"- 时间：{w['start_time']} ~ {w['end_time']}"
        )
        a(
            f"- tier={w['tier']} raw_tier={w.get('raw_tier')} score={w['score']} "
            f"fast_track={w.get('fast_track')} evidence_lost={w.get('evidence_lost')}"
        )
        a(f"- raw_n={w.get('raw_n')} slim_n={w.get('slim_n')} 权威：{auth_s}")
        a(f"- 命中词：{hits}")
        a("")
        for mid in w.get("source_msg_ids") or []:
            m = by_id.get(mid)
            if not m:
                continue
            lab = speaker_label(m, host_qq, expert_qqs)
            text = re.sub(r"\s+", " ", m.get("text") or "").strip()
            a(f"- `[{clock_of(m)}]` {lab} {text}")
        a("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(sampled)


def public_message(m: dict[str, Any]) -> dict[str, Any]:
    out = {
        "msg_id": m["msg_id"],
        "ts": m["ts"],
        "time_str": m["time_str"],
        "qq": m["qq"],
        "uid": m["uid"],
        "nick": m["nick"],
        "text": m["text"],
        "flags": m["flags"],
        "speaker_id": m["speaker_id"],
    }
    if "text_stripped" in m:
        out["text_stripped"] = m["text_stripped"]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="QQ 群聊清洗流水线（第 0–4 步）")
    p.add_argument("--csv", default=DEFAULT_CSV, help="输入 CSV 路径")
    p.add_argument("--outdir", default=DEFAULT_OUTDIR, help="输出目录（默认 qq_info/）")
    p.add_argument("--entities", default=DEFAULT_ENTITIES, help="prts_entities.json")
    p.add_argument("--gap-minutes", type=float, default=20.0, help="主产物切簇间隔（分钟）")
    p.add_argument("--window-k", type=int, default=15, help="权威窗 ±K 条")
    p.add_argument("--slack", type=int, default=8, help="瘦身：连续无锚点截断条数")
    p.add_argument("--host-qq", default=HOST_QQ)
    p.add_argument("--expert-qq", default=EXPERT_QQ, help="逗号分隔")
    p.add_argument("--bot-qq", default=",".join(DEFAULT_BOT_QQS), help="逗号分隔")
    p.add_argument("--seed", type=int, default=42, help="抽查/金标随机种子")
    args = p.parse_args(argv)

    host_qq = args.host_qq.strip()
    expert_qqs = set(parse_id_list(args.expert_qq))
    authority_qqs = {host_qq, *expert_qqs}
    bot_qqs = set(parse_id_list(args.bot_qq))

    os.makedirs(args.outdir, exist_ok=True)

    log("[0] 解析 CSV …")
    messages, parse_stats = parse_csv(args.csv)
    fill_empty_times(messages)
    messages.sort(key=lambda m: (m["ts"], m["_idx"]))

    extra, report_counts = discover_report_bots(messages, bot_qqs)
    for qq, _n in extra:
        bot_qqs.add(qq)

    bot_live = apply_bot_and_live(messages, bot_qqs, host_qq)
    flood = apply_noise_and_flood(messages, authority_qqs)

    flag_counter: Counter[str] = Counter()
    for m in messages:
        flag_counter.update(m["flags"])
    flag_stats = dict(flag_counter)
    flag_stats.update(bot_live)
    flag_stats.update(flood)

    log("[1] 物理删除噪音 …")
    n_parsed = len(messages)
    messages, drop_stats = drop_tagged(messages)

    log("[0] 写 speaker_map / messages_clean.jsonl …")
    speaker_map = build_speaker_map(messages)
    sm_path = os.path.join(args.outdir, "speaker_map.json")
    with open(sm_path, "w", encoding="utf-8") as f:
        json.dump(speaker_map, f, ensure_ascii=False, indent=2)

    stale_full = os.path.join(args.outdir, "messages.jsonl")
    if os.path.exists(stale_full):
        os.remove(stale_full)
    msg_path = os.path.join(args.outdir, "messages_clean.jsonl")
    with open(msg_path, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(public_message(m), ensure_ascii=False) + "\n")

    log("[2] 切簇 8min / 20min …")
    c8 = make_clusters(messages, 8 * 60)
    c20 = make_clusters(messages, 20 * 60)
    st8 = cluster_stats(c8)
    st20 = cluster_stats(c20)
    gap_sec = int(args.gap_minutes * 60)
    if abs(args.gap_minutes - 20.0) < 1e-9:
        main_clusters = c20
    elif abs(args.gap_minutes - 8.0) < 1e-9:
        main_clusters = c8
    else:
        main_clusters = make_clusters(messages, gap_sec)

    log("[3] 词表 + 权威窗打分 …")
    slang_terms = load_shenqi_slangs(args.entities)
    vocab = build_vocab(slang_terms)
    windows = build_windows(
        messages,
        main_clusters,
        k=args.window_k,
        host_qq=host_qq,
        expert_qqs=expert_qqs,
        authority_qqs=authority_qqs,
        vocab=vocab,
        slack=args.slack,
    )

    win_path = os.path.join(args.outdir, "windows.jsonl")
    dump_jsonl(win_path, windows)

    gold_path = os.path.join(args.outdir, "gold_sample.md")
    n_gold = write_gold_sample(
        gold_path, windows, messages, host_qq, expert_qqs, args.seed
    )

    report_path = os.path.join(args.outdir, "pipeline_report.md")
    write_report(
        report_path,
        parse_stats,
        flag_stats,
        drop_stats,
        extra,
        report_counts,
        bot_qqs,
        st8,
        st20,
        args.gap_minutes,
        args.window_k,
        args.slack,
        windows,
        messages,
        host_qq,
        expert_qqs,
        args.seed,
    )

    tiers = Counter(w["tier"] for w in windows)
    log(
        f"[done] parsed={n_parsed} kept={len(messages)} dropped={drop_stats['dropped']} "
        f"windows={len(windows)} "
        f"candidate={tiers.get('candidate', 0)} maybe={tiers.get('maybe', 0)} "
        f"ignore={tiers.get('ignore', 0)} gold={n_gold}"
    )
    log(f"report: {report_path}")
    log(f"gold: {gold_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
