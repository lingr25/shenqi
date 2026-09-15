#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_merge_results.py
-------------------------
把 ignore / maybe / novelty / merge 四批 LLM 结果并入 qq_cards/。
"""

from __future__ import annotations

import argparse
import difflib
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

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CARDS_PATH = os.path.join(ROOT_DIR, "qq_cards", "cards.jsonl")
README_PATH = os.path.join(ROOT_DIR, "qq_cards", "README.md")
CANON_PATH = os.path.join(ROOT_DIR, "qq_cards", "canonical.jsonl")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "merge_v2_report.md")
SPEAKERS_PATH = os.path.join(ROOT_DIR, "qq_info", "speaker_map.json")

CRED_OF = {"主播": "authoritative", "专家": "expert", "群友": "lead"}
CRED_RANK = {"authoritative": 0, "expert": 1, "lead": 2}
CAT_ORDER = ["索敌", "帧时序", "位移", "寻路", "伤害结算", "拆包数据", "其他"]

SKIP_MERGE_CLUSTERS = {"c0001", "c0002", "c0003", "c0011"}
INSTANCE_IDS = {"w000380", "w000403", "w000244"}
KEEP_VERSION_IDS = {"w000021"}
CONFLICT_ID = "w001186"
NOTE_IDS = {
    "w000111": "主播的根号平方数(√0.45/√0.6708)为急停半径，与阻挡半径0.5/0.8不同套",
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


def load_glob(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(glob.glob(pattern)):
        rows.extend(load_jsonl(path))
    return rows


def dump_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def entity_zh(item: str) -> str:
    s = (item or "").strip()
    m = re.match(r"^([^（(]+)", s)
    return (m.group(1) if m else s).strip()


def entity_set(card: dict[str, Any]) -> set[str]:
    return {entity_zh(x) for x in (card.get("entities") or []) if entity_zh(x)}


def align_cred(card: dict[str, Any]) -> int:
    n = 0
    for cc in card.get("core_conclusions") or []:
        want = CRED_OF.get(cc.get("speaker") or "")
        if want and cc.get("credibility") != want:
            cc["credibility"] = want
            n += 1
    return n


def top_cred(card: dict[str, Any]) -> str:
    ranks = [
        CRED_RANK.get(cc.get("credibility"), 9)
        for cc in (card.get("core_conclusions") or [])
    ]
    if not ranks:
        return "—"
    best = min(ranks)
    for k, v in CRED_RANK.items():
        if v == best:
            return k
    return "—"


def prepare_incoming(card: dict[str, Any], origin: str) -> dict[str, Any]:
    out = dict(card)
    out.pop("skip", None)
    out["origin"] = origin
    out.setdefault("status", "draft")
    out.setdefault("novelty", "unknown")
    align_cred(out)
    return out


def apply_novelty(cards: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, int]:
    by_id = {c.get("window_id"): c for c in cards}
    stats = {"applied": 0, "missing_card": 0, "conflict": 0}
    for lab in labels:
        if lab.get("skip"):
            continue
        wid = lab.get("window_id")
        card = by_id.get(wid)
        if not card:
            stats["missing_card"] += 1
            continue
        card["novelty"] = lab.get("novelty") or "unknown"
        card["vod_evidence"] = lab.get("vod_evidence") or []
        card["novelty_confidence"] = lab.get("confidence") or lab.get("novelty_confidence")
        stats["applied"] += 1
        if wid == CONFLICT_ID:
            card["conflict_resolution"] = "vod_wins"
            stats["conflict"] += 1
            for cc in card.get("core_conclusions") or []:
                conc = cc.get("conclusion") or ""
                if "已有" in conc and "冷却" in conc:
                    cc["conflict_note"] = (
                        "曾持此说，录播已否（novelty=conflict，vod_wins）"
                    )
    return stats


def best_main_match(
    card: dict[str, Any], pool: list[dict[str, Any]]
) -> tuple[str, float, int] | None:
    ea = entity_set(card)
    topic = card.get("topic") or ""
    cat = card.get("category")
    best: tuple[str, float, int] | None = None
    for other in pool:
        if other.get("window_id") == card.get("window_id"):
            continue
        if other.get("category") != cat:
            continue
        shared = len(ea & entity_set(other))
        if shared < 2:
            continue
        ratio = difflib.SequenceMatcher(None, topic, other.get("topic") or "").ratio()
        if ratio <= 0.4:
            continue
        if best is None or (ratio, shared) > (best[1], best[2]):
            best = (other["window_id"], ratio, shared)
    return best


def mark_maybe_dups(
    maybe_cards: list[dict[str, Any]], main_draft: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for card in maybe_cards:
        wid = card.get("window_id")
        if wid in KEEP_VERSION_IDS:
            topic = card.get("topic") or ""
            if not topic.startswith("[旧数值"):
                card["topic"] = "[旧数值2026-05] " + topic
            continue
        hit = best_main_match(card, main_draft)
        if not hit:
            continue
        canon, ratio, shared = hit
        card["status"] = "duplicate"
        card["duplicate_of"] = canon
        card["canonical_window_id"] = canon
        details.append(
            {
                "window_id": wid,
                "canonical": canon,
                "ratio": round(ratio, 3),
                "shared": shared,
            }
        )
    return details


def keep_canonical(entry: dict[str, Any]) -> bool:
    cid = entry.get("cluster_id")
    src = list(entry.get("source_window_ids") or [])
    if cid in SKIP_MERGE_CLUSTERS:
        return False
    if len(src) > 4:
        return False
    if CONFLICT_ID in src:
        return False
    return True


def rewrite_readme(
    path: str,
    cards: list[dict[str, Any]],
    canon: list[dict[str, Any]],
    stats: dict[str, Any],
    today: str,
) -> None:
    draft = [c for c in cards if c.get("status", "draft") == "draft"]
    n_dup = sum(1 for c in cards if c.get("status") == "duplicate")
    n_empty = sum(1 for c in cards if c.get("status") == "empty")
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in draft:
        by_cat[c.get("category") or "其他"].append(c)
    nov = Counter(c.get("novelty") or "unknown" for c in cards)
    origin = Counter(c.get("origin") or "main" for c in cards)

    lines: list[str] = []
    a = lines.append
    a("# 群聊机制知识卡片（draft）")
    a("")
    a(f"## v2 合并说明（{today}）")
    a("")
    a(
        f"来源构成：主库 484（含修补后 13 张 duplicate）+ maybe 非 skip {stats['n_maybe']} "
        f"+ ignore 非 skip {stats['n_ignore']} = **{len(cards)}** 张窗卡。"
    )
    a("")
    a("- 窗卡（`cards.jsonl`）是 citation：指向具体讨论窗。")
    a("- 词条（`canonical.jsonl`）是合并后的机制条目，仅收源窗 ≤4 的小簇；大簇留给人工拆。")
    a(
        f"- novelty 标注覆盖主库 draft 卡：group_only {stats['nov_group']} / "
        f"also_in_vod {stats['nov_vod']} / unknown {stats['nov_unknown']} / "
        f"conflict {stats['nov_conflict']}。"
    )
    a(
        f"- 唯一 conflict 卡 `{CONFLICT_ID}`：录播否决「已有冷却不随后续攻速变化」；"
        f"`conflict_resolution=vod_wins`，结论加 `conflict_note`，原文保留。"
    )
    a(
        f"- maybe 近重复标记 duplicate {stats['n_maybe_dup']} 张；"
        f"单图/单干员数字卡 scope=instance {stats['n_instance']} 张；"
        f"`w000021` 保留为「旧数值」而非 duplicate。"
    )
    a("")
    a("**数据边界**")
    a("")
    a("- 语料是群聊补充层，不是录播逐字稿；与录播讲解冲突时 **以录播为准**。")
    a("- 发言人已脱敏（主播/专家/群友）。")
    a("- 参数必须能在窗内原文中找到；无过硬数字的卡 `underlying_parameters` 为空。")
    a("")
    a(
        f"窗卡 **{len(cards)}**：draft **{len(draft)}**，duplicate **{n_dup}**，"
        f"empty **{n_empty}**。canonical_draft 词条 **{len(canon)}**。"
    )
    a("")
    a("origin：" + "，".join(f"{k} {v}" for k, v in sorted(origin.items())))
    a("")
    a("novelty：" + "，".join(f"{k} {v}" for k, v in sorted(nov.items())))
    a("")
    a("## 分类统计（draft）")
    a("")
    for cat in CAT_ORDER:
        n = len(by_cat.get(cat) or [])
        if n:
            a(f"- {cat}：{n}")
    a("")
    for cat in CAT_ORDER:
        group = by_cat.get(cat) or []
        if not group:
            continue
        group = sorted(group, key=lambda c: (c.get("as_of") or "", c.get("window_id") or ""))
        a(f"## {cat}（{len(group)}）")
        a("")
        for c in group:
            as_of = (c.get("as_of") or "")[:10]
            topic = (c.get("topic") or "").replace("|", "/")
            a(f"- {as_of} | {topic} | {top_cred(c)} | `{c.get('window_id')}`")
        a("")
    if canon:
        a("## canonical 词条")
        a("")
        for e in canon:
            src = ", ".join(f"`{w}`" for w in (e.get("source_window_ids") or []))
            a(f"- `{e.get('cluster_id')}` {e.get('title')} ← {src}")
        a("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def privacy_scan(dir_path: str, speakers_path: str) -> list[str]:
    if not os.path.exists(speakers_path):
        return []
    with open(speakers_path, "r", encoding="utf-8") as f:
        sm = json.load(f)
    qqs = [
        k
        for k in (sm.get("speakers") or {})
        if str(k).isdigit() and len(str(k)) >= 5
    ]
    blob = ""
    for name in os.listdir(dir_path):
        path = os.path.join(dir_path, name)
        if os.path.isfile(path) and name.endswith((".jsonl", ".md", ".json")):
            with open(path, "r", encoding="utf-8") as f:
                blob += f.read()
    hits = []
    for qq in qqs:
        if re.search(rf"(?<![0-9]){re.escape(qq)}(?![0-9])", blob):
            hits.append(qq)
    return hits


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="合并四批 LLM 卡片结果")
    p.add_argument("--cards", default=CARDS_PATH)
    args = p.parse_args(argv)

    main_cards = load_jsonl(args.cards)
    for c in main_cards:
        c.setdefault("origin", "main")
    n_main = len(main_cards)
    main_ids = {c.get("window_id") for c in main_cards}
    draft_pool = [c for c in main_cards if c.get("status", "draft") == "draft"]

    ignore_raw = [
        c
        for c in load_glob(os.path.join(ROOT_DIR, "qq_info", "llm_batch_ignore", "cards_batch_*.jsonl"))
        if not c.get("skip")
    ]
    maybe_raw = [
        c
        for c in load_glob(os.path.join(ROOT_DIR, "qq_info", "llm_batch_maybe", "cards_batch_*.jsonl"))
        if not c.get("skip")
    ]
    novelty = load_glob(
        os.path.join(ROOT_DIR, "qq_info", "llm_batch_novelty", "cards_novelty_batch_*.jsonl")
    )
    merge_entries = load_glob(
        os.path.join(ROOT_DIR, "qq_info", "llm_batch_merge", "cards_merge_batch_*.jsonl")
    )

    ignore_cards = [prepare_incoming(c, "ignore") for c in ignore_raw if c.get("window_id") not in main_ids]
    maybe_cards = [prepare_incoming(c, "maybe") for c in maybe_raw if c.get("window_id") not in main_ids]

    nov_stats = apply_novelty(main_cards, novelty)
    nov_counts = Counter(
        (c.get("novelty") or "unknown")
        for c in main_cards
        if c.get("origin", "main") == "main" and c.get("status", "draft") == "draft"
    )

    dup_details = mark_maybe_dups(maybe_cards, draft_pool)
    n_instance = 0
    for c in maybe_cards:
        if c.get("window_id") in INSTANCE_IDS:
            c["scope"] = "instance"
            n_instance += 1
        note = NOTE_IDS.get(c.get("window_id") or "")
        if note:
            c["note"] = note

    cards = main_cards + ignore_cards + maybe_cards
    cards.sort(key=lambda c: (c.get("as_of") or "", c.get("window_id") or ""))

    canonical: list[dict[str, Any]] = []
    skipped_clusters: list[str] = []
    for entry in merge_entries:
        if not keep_canonical(entry):
            skipped_clusters.append(entry.get("cluster_id") or "?")
            continue
        row = dict(entry)
        row["status"] = "canonical_draft"
        row["origin"] = "merge"
        canonical.append(row)
    canonical.sort(key=lambda e: e.get("cluster_id") or "")

    dump_jsonl(args.cards, cards)
    dump_jsonl(CANON_PATH, canonical)

    today = date.today().isoformat()
    stats = {
        "n_maybe": len(maybe_cards),
        "n_ignore": len(ignore_cards),
        "n_maybe_dup": len(dup_details),
        "n_instance": n_instance,
        "nov_group": nov_counts.get("group_only", 0),
        "nov_vod": nov_counts.get("also_in_vod", 0),
        "nov_unknown": nov_counts.get("unknown", 0),
        "nov_conflict": nov_counts.get("conflict", 0),
    }
    rewrite_readme(README_PATH, cards, canonical, stats, today)

    st = Counter(c.get("status", "draft") for c in cards)
    origin = Counter(c.get("origin") or "main" for c in cards)
    nov = Counter(c.get("novelty") or "unknown" for c in cards)
    report = [
        "# v2 合并报告",
        "",
        f"日期：{today}",
        "",
        f"- 主库原卡：{n_main}",
        f"- ignore 追加：{len(ignore_cards)}",
        f"- maybe 追加：{len(maybe_cards)}",
        f"- 合计 cards.jsonl：{len(cards)}（期望 {n_main + len(ignore_raw) + len(maybe_raw)}）",
        f"- novelty 写回：{nov_stats['applied']}（缺卡 {nov_stats['missing_card']}，conflict {nov_stats['conflict']}）",
        f"- maybe duplicate 标记：{len(dup_details)}",
        f"- instance：{n_instance}",
        f"- canonical 收录：{len(canonical)}（跳过簇 {', '.join(skipped_clusters)}）",
        "",
        "## maybe duplicate 明细",
        "",
    ]
    if not dup_details:
        report.append("（无）")
    else:
        for d in dup_details:
            report.append(
                f"- `{d['window_id']}` → `{d['canonical']}` ratio={d['ratio']} shared={d['shared']}"
            )
    report += [
        "",
        "## status / origin / novelty",
        "",
        f"- status {dict(st)}",
        f"- origin {dict(origin)}",
        f"- novelty {dict(nov)}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    hits = privacy_scan(os.path.join(ROOT_DIR, "qq_cards"), SPEAKERS_PATH)
    expected = n_main + len(ignore_raw) + len(maybe_raw)
    print(
        f"cards={len(cards)} expected={expected} ignore={len(ignore_cards)} "
        f"maybe={len(maybe_cards)} maybe_dup={len(dup_details)} instance={n_instance} "
        f"canonical={len(canonical)} novelty_applied={nov_stats['applied']} "
        f"privacy_hits={len(hits)}"
    )
    if hits:
        log("privacy hits: " + ",".join(hits[:10]))
        return 1
    if len(cards) != expected:
        log(f"count mismatch {len(cards)} != {expected}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
