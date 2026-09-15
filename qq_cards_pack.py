#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_pack.py
----------------
三批离线 LLM 交接包：
  ignore  — 低分窗误杀复核
  novelty — draft 卡 vs 录播逐字稿
  merge   — 同主题多卡合并词条
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qq_cards_export import (
    DEFAULT_MESSAGES,
    DEFAULT_WINDOWS,
    format_line,
    load_jsonl,
    load_messages_index,
    window_payload,
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPTS_DIR = os.path.join(ROOT_DIR, "transcripts_txt")
CARDS_PATH = os.path.join(ROOT_DIR, "qq_cards", "cards.jsonl")

TS_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*)$")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def write_batches(out_dir: str, rows: list[dict[str, Any]], batch_size: int, prefix: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    n_batches = (len(rows) + batch_size - 1) // batch_size if rows else 0
    for b in range(n_batches):
        chunk = rows[b * batch_size : (b + 1) * batch_size]
        path = os.path.join(out_dir, f"{prefix}_{b + 1:03d}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for obj in chunk:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        log(f"  {os.path.basename(path)}  {len(chunk)}")
    return n_batches


def write_readme(out_dir: str, text: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(text.lstrip("\n") + ("" if text.endswith("\n") else "\n"))


def entity_zh(item: str) -> str:
    s = (item or "").strip()
    m = re.match(r"^([^（(]+)", s)
    return (m.group(1) if m else s).strip()


# ----- ignore -----

IGNORE_PROMPT = r'''# ignore 档误杀复核 — Prompt

离线交接包。一窗一调用；只输出一个 JSON 对象。

这些窗被规则判为 **ignore（低分）**。任务是误杀复核，**从严**：

- 只有窗内出现**具体机制结论 / 实测数据 / 拆包信息**（数字+单位、拆包路径、明确因果）时才出卡。
- 闲聊、梗、纯表情、空转讨论一律：
  `{"skip": true, "window_id": "...", "reason": "..."}`
- 预期 skip 率 >90%。拿不准就 skip。
- 若 `truncated=true`，只根据载荷里的截断消息判断，不要假设窗外还有内容。

出卡时 schema 与主包完全相同（topic/category/entities/context_question/core_conclusions/underlying_parameters/summary_takeaway/window_id/as_of/status="draft"/novelty="unknown"/source_msg_ids/source_spans）。
禁止外部知识；`underlying_parameters.value` 必须逐字出现在某条 source_spans 里，否则该字段留 []。
禁止输出 QQ 号与真实昵称。

## 使用

1. 读 `batch_XXX.jsonl` 逐行。
2. 将整行 JSON 作为 user 输入。
3. 输出追加到 `cards_batch_XXX.jsonl`。

## User

{WINDOW_PAYLOAD}
'''


def truncate_ignore_window(w: dict[str, Any], msg_idx: dict[str, dict[str, Any]], radius: int = 60) -> dict[str, Any]:
    ids = list(w.get("source_msg_ids") or [])
    payload = window_payload(w, msg_idx)
    missing = int(payload.pop("_missing_msgs", 0))
    n = len(ids)
    if n <= 200:
        payload["truncated"] = False
        payload["raw_n"] = n
        payload["_missing_msgs"] = missing
        return payload
    terms = [t for t in (w.get("hit_terms") or []) if t]
    best_i, best_s = n // 2, -1
    for i, mid in enumerate(ids):
        m = msg_idx.get(mid) or {}
        blob = (m.get("text_stripped") or m.get("text") or "")
        s = sum(1 for t in terms if t and t in blob)
        if s > best_s:
            best_s, best_i = s, i
    lo = max(0, best_i - radius)
    hi = min(n, best_i + radius + 1)
    cut_ids = ids[lo:hi]
    w2 = dict(w)
    w2["source_msg_ids"] = cut_ids
    payload = window_payload(w2, msg_idx)
    missing = int(payload.pop("_missing_msgs", 0))
    payload["truncated"] = True
    payload["raw_n"] = n
    payload["anchor_index"] = best_i
    payload["source_msg_ids"] = cut_ids
    payload["_missing_msgs"] = missing
    return payload


def cmd_ignore(args: argparse.Namespace) -> int:
    windows = load_jsonl(args.windows)
    selected = [w for w in windows if w.get("tier") == "ignore"]
    selected.sort(key=lambda w: w.get("window_id") or "")
    log(f"ignore 窗 {len(selected)}")
    msg_idx = load_messages_index(args.messages)
    rows = []
    n_trunc = 0
    missing = 0
    for w in selected:
        p = truncate_ignore_window(w, msg_idx)
        missing += int(p.pop("_missing_msgs", 0))
        if p.get("truncated"):
            n_trunc += 1
        rows.append(p)
    out_dir = args.out_dir
    n_batches = write_batches(out_dir, rows, args.batch_size, "batch")
    with open(os.path.join(out_dir, "PROMPT.md"), "w", encoding="utf-8") as f:
        f.write(IGNORE_PROMPT.lstrip("\n"))
    write_readme(
        out_dir,
        f"""ignore 档误杀复核
输入：batch_XXX.jsonl（每行一窗）
输出：cards_batch_XXX.jsonl（每行一 JSON，window_id 对齐）
验收：python -X utf8 qq_cards_validate.py --mode ignore --cards-dir {out_dir}
窗数={len(rows)} 批次数={n_batches} truncated={n_trunc}
""",
    )
    print(
        f"ignore windows={len(rows)} batches={n_batches} truncated={n_trunc} "
        f"missing_msgs={missing} out={out_dir}"
    )
    return 0


# ----- novelty -----

NOVELTY_PROMPT = r'''# 卡片 novelty 标注 — Prompt

一卡一调用。只输出一个 JSON 对象。

判断这张群聊机制卡的结论是否已经在录播逐字稿（vod_excerpts）里出现过。

novelty 只能是：

- `group_only`：结论只在群聊，逐字稿没有对应讲解（或 excerpts 为空）
- `also_in_vod`：逐字稿有实质相同的机制结论
- `conflict`：群聊结论与逐字稿明确冲突
- `unknown`：excerpts 为空或太残，无法判断（**禁止编造逐字稿内容**）

规则：

- `vod_excerpts` 为空时，只能输出 `group_only` 或 `unknown`，且 `vod_evidence` 必须为 `[]`。
- `vod_evidence` 若非空，必须是 excerpts 或你看到的逐字稿行的原文子串，不要改写。
- 不要用训练记忆补录播内容。
- 不要输出 QQ / 真实昵称。

输出 schema：

```json
{
  "window_id": "w000000",
  "novelty": "group_only",
  "vod_evidence": ["..."],
  "confidence": "low"
}
```

`confidence` ∈ {high, medium, low}。

## 使用

读 `batch_XXX.jsonl` 逐行，输出追加到 `cards_novelty_batch_XXX.jsonl`。

## User

{WINDOW_PAYLOAD}
'''


def load_transcripts(dir_path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in sorted(os.listdir(dir_path)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(dir_path, name)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        out.append({"file": name, "lines": lines})
    return out


STOP_TERMS = {
    "判定",
    "位移",
    "阻挡",
    "碰撞",
    "技能",
    "冷却",
    "攻击",
    "动画",
    "坐标",
    "敌人",
    "干员",
    "机制",
    "数值",
    "效果",
}


def search_terms_for_card(card: dict[str, Any], window: dict[str, Any] | None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for e in card.get("entities") or []:
        z = entity_zh(str(e))
        if len(z) >= 2 and z not in seen and z not in STOP_TERMS:
            seen.add(z)
            terms.append(z)
    for t in (window or {}).get("hit_terms") or []:
        t = str(t).strip()
        if len(t) >= 2 and t not in seen and t not in STOP_TERMS:
            seen.add(t)
            terms.append(t)
    terms.sort(key=len, reverse=True)
    return terms


def excerpt_segments(
    transcripts: list[dict[str, Any]], terms: list[str], max_segs: int = 3
) -> list[dict[str, Any]]:
    if not terms:
        return []
    cands: list[tuple[int, str, int, int, list[str], list[str]]] = []
    for tr in transcripts:
        lines = tr["lines"]
        hits: list[int] = []
        hit_terms_at: dict[int, list[str]] = defaultdict(list)
        for i, line in enumerate(lines):
            matched = [t for t in terms if t in line]
            if matched:
                hits.append(i)
                hit_terms_at[i] = matched
        if not hits:
            continue
        clusters: list[list[int]] = [[hits[0]]]
        for h in hits[1:]:
            if h - clusters[-1][-1] <= 20:
                clusters[-1].append(h)
            else:
                clusters.append([h])
        for cl in clusters:
            start = max(0, min(cl) - 10)
            end = min(len(lines), max(cl) + 11)
            if end - start > 40:
                densest = min(cl)
                start = max(0, densest - 15)
                end = min(len(lines), start + 40)
            used = sorted({t for i in cl for t in hit_terms_at[i]})
            distinctive = [t for t in used if t not in STOP_TERMS and len(t) >= 2]
            if not distinctive:
                continue
            score = sum(len(t) for t in distinctive) * 20 + len(cl)
            snippet = lines[start:end]
            cands.append((score, tr["file"], start, end, distinctive, snippet))
    cands.sort(key=lambda x: -x[0])
    segs = []
    seen_files: set[str] = set()
    for score, fn, start, end, used, snippet in cands:
        if len(segs) >= max_segs:
            break
        key = f"{fn}:{start}"
        if key in seen_files:
            continue
        seen_files.add(key)
        segs.append(
            {
                "source": fn,
                "start_line": start + 1,
                "end_line": end,
                "terms_hit": used,
                "lines": snippet,
            }
        )
    return segs


def novelty_payload(
    card: dict[str, Any],
    window: dict[str, Any] | None,
    transcripts: list[dict[str, Any]],
) -> dict[str, Any]:
    terms = search_terms_for_card(card, window)
    excerpts = excerpt_segments(transcripts, terms)
    return {
        "window_id": card.get("window_id"),
        "topic": card.get("topic"),
        "category": card.get("category"),
        "entities": card.get("entities") or [],
        "summary_takeaway": card.get("summary_takeaway"),
        "core_conclusions": card.get("core_conclusions") or [],
        "search_terms": terms,
        "vod_excerpts": excerpts,
    }


def cmd_novelty(args: argparse.Namespace) -> int:
    cards = [
        c
        for c in load_jsonl(args.cards)
        if c.get("status", "draft") == "draft"
    ]
    cards.sort(key=lambda c: (c.get("as_of") or "", c.get("window_id") or ""))
    windows = {w["window_id"]: w for w in load_jsonl(args.windows)}
    log(f"draft 卡 {len(cards)}；读逐字稿 {args.transcripts}")
    transcripts = load_transcripts(args.transcripts)
    log(f"逐字稿文件 {len(transcripts)}")
    if args.pilot:
        prefer = ["w000569", "w000307", "w000027", "w001263", "w000006"]
        by = {c["window_id"]: c for c in cards}
        picked = [by[i] for i in prefer if i in by]
        for c in cards:
            if len(picked) >= args.pilot:
                break
            if c not in picked:
                picked.append(c)
        picked = picked[: args.pilot]
        rows = [novelty_payload(c, windows.get(c["window_id"]), transcripts) for c in picked]
        os.makedirs(args.out_dir, exist_ok=True)
        path = os.path.join(args.out_dir, "_pilot.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for obj in rows:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        for obj in rows:
            nseg = len(obj.get("vod_excerpts") or [])
            nlines = sum(len(s.get("lines") or []) for s in (obj.get("vod_excerpts") or []))
            terms = ",".join((obj.get("search_terms") or [])[:6])
            log(
                f"pilot {obj['window_id']} segs={nseg} lines={nlines} "
                f"terms={terms} topic={obj.get('topic')}"
            )
        print(f"novelty pilot n={len(rows)} path={path}")
        return 0

    rows = [
        novelty_payload(c, windows.get(c["window_id"]), transcripts) for c in cards
    ]
    n_empty = sum(1 for r in rows if not r.get("vod_excerpts"))
    n_batches = write_batches(args.out_dir, rows, args.batch_size, "batch")
    with open(os.path.join(args.out_dir, "PROMPT.md"), "w", encoding="utf-8") as f:
        f.write(NOVELTY_PROMPT.lstrip("\n"))
    write_readme(
        args.out_dir,
        f"""novelty 标注包
输入：batch_XXX.jsonl（每行一卡载荷，含 vod_excerpts）
输出：cards_novelty_batch_XXX.jsonl
验收：python -X utf8 qq_cards_validate.py --mode novelty --cards-dir {args.out_dir} --transcripts transcripts_txt
卡数={len(rows)} 批次数={n_batches} 无逐字稿命中={n_empty}
""",
    )
    print(
        f"novelty cards={len(rows)} batches={n_batches} empty_excerpts={n_empty} out={args.out_dir}"
    )
    return 0


# ----- merge -----

MERGE_PROMPT = r'''# 主题簇词条合并 — Prompt

一簇一调用。只输出一个 JSON 对象。

把同一机制的多张群聊卡合并成一张 canonical 词条。禁止引入卡外知识。

规则：

- 冲突结论并列保留，各自带 credibility（authoritative / expert / lead）。
- `parameters[].value` 必须能在某张源卡的 `source_spans` 或参数 `source_span` 里找到；找不到就不要进 parameters。
- `source_window_ids` 列出本簇全部 window_id。
- 不要编数字、不要补 Wiki。

输出 schema：

```json
{
  "cluster_id": "c0001",
  "title": "...",
  "entities": ["中文（English）"],
  "canonical_conclusions": [
    {"speaker": "主播", "credibility": "authoritative", "conclusion": "..."}
  ],
  "parameters": [
    {"name": "...", "value": "...", "unit": "帧", "source_span": "...", "source_window_id": "w000000"}
  ],
  "open_questions": ["..."],
  "source_window_ids": ["w000000"]
}
```

## 使用

读 `batch_XXX.jsonl` 逐行，输出追加到 `cards_merge_batch_XXX.jsonl`。

## User

{WINDOW_PAYLOAD}
'''


class UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.p = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra

    def groups(self) -> list[list[str]]:
        g: dict[str, list[str]] = defaultdict(list)
        for x in self.p:
            g[self.find(x)].append(x)
        return list(g.values())


FORCE_MERGE = [
    [
        "w000034",
        "w000046",
        "w000162",
        "w000178",
        "w000180",
        "w000427",
        "w000577",
        "w000976",
        "w001182",
        "w001317",
    ],
    ["w002063", "w002074", "w002075"],
]


def cmd_merge(args: argparse.Namespace) -> int:
    cards = [
        c
        for c in load_jsonl(args.cards)
        if c.get("status", "draft") == "draft"
    ]
    by = {c["window_id"]: c for c in cards}
    ids = list(by)
    uf = UnionFind(ids)
    for grp in FORCE_MERGE:
        present = [w for w in grp if w in by]
        for x in present[1:]:
            uf.union(present[0], x)
    for i, a in enumerate(ids):
        ca = by[a]
        ea = {entity_zh(x) for x in ca.get("entities") or []}
        for b in ids[i + 1 :]:
            cb = by[b]
            if ca.get("category") != cb.get("category"):
                continue
            eb = {entity_zh(x) for x in cb.get("entities") or []}
            shared = len(ea & eb)
            ratio = difflib.SequenceMatcher(
                None, ca.get("topic") or "", cb.get("topic") or ""
            ).ratio()
            if shared >= 2 or ratio > 0.5:
                uf.union(a, b)
    clusters = [g for g in uf.groups() if len(g) >= 2]
    clusters.sort(key=lambda g: (-len(g), min(g)))
    rows = []
    cluster_index = []
    for i, g in enumerate(clusters, 1):
        cid = f"c{i:04d}"
        members = [by[w] for w in sorted(g)]
        payload = {
            "cluster_id": cid,
            "category": members[0].get("category"),
            "size": len(members),
            "source_window_ids": [m["window_id"] for m in members],
            "cards": members,
        }
        rows.append(payload)
        cluster_index.append(
            {"cluster_id": cid, "source_window_ids": payload["source_window_ids"]}
        )
    n_batches = write_batches(args.out_dir, rows, args.batch_size, "batch")
    with open(os.path.join(args.out_dir, "clusters.json"), "w", encoding="utf-8") as f:
        json.dump(cluster_index, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out_dir, "PROMPT.md"), "w", encoding="utf-8") as f:
        f.write(MERGE_PROMPT.lstrip("\n"))
    write_readme(
        args.out_dir,
        f"""主题簇合并包
输入：batch_XXX.jsonl（每行一簇，含 cards[]）
输出：cards_merge_batch_XXX.jsonl
簇清单：clusters.json
验收：python -X utf8 qq_cards_validate.py --mode merge --cards-dir {args.out_dir}
簇数={len(rows)} 批次数={n_batches} 每批最多 {args.batch_size} 簇
""",
    )
    print(f"merge clusters={len(rows)} batches={n_batches} out={args.out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ignore / novelty / merge 交接包")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ig = sub.add_parser("ignore")
    p_ig.add_argument("--windows", default=DEFAULT_WINDOWS)
    p_ig.add_argument("--messages", default=DEFAULT_MESSAGES)
    p_ig.add_argument("--batch-size", type=int, default=25)
    p_ig.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "qq_info", "llm_batch_ignore"),
    )

    p_nv = sub.add_parser("novelty")
    p_nv.add_argument("--cards", default=CARDS_PATH)
    p_nv.add_argument("--windows", default=DEFAULT_WINDOWS)
    p_nv.add_argument("--transcripts", default=TRANSCRIPTS_DIR)
    p_nv.add_argument("--batch-size", type=int, default=20)
    p_nv.add_argument("--pilot", type=int, default=0)
    p_nv.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "qq_info", "llm_batch_novelty"),
    )

    p_mg = sub.add_parser("merge")
    p_mg.add_argument("--cards", default=CARDS_PATH)
    p_mg.add_argument("--batch-size", type=int, default=5)
    p_mg.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "qq_info", "llm_batch_merge"),
    )

    args = p.parse_args(argv)
    if args.cmd == "ignore":
        return cmd_ignore(args)
    if args.cmd == "novelty":
        return cmd_novelty(args)
    if args.cmd == "merge":
        return cmd_merge(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
