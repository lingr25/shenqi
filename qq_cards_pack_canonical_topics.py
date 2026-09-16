#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export 6 canonical-topic payloads for subagents (no LLM)."""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Callable

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(ROOT, "qq_cards", "cards.jsonl")
OUT_DIR = os.path.join(ROOT, "qq_info", "subagent_canonical")
CRED_RANK = {"authoritative": 0, "expert": 1, "lead": 2}

HEADER = """# {title}

任务：根据下方窗卡合成 **1 条** canonical 词条。只输出一个 JSON 对象：

```json
{{
  "title": "...",
  "entities": ["..."],
  "canonical_conclusions": [
    {{"speaker": "主播", "credibility": "authoritative", "conclusion": "...", "as_of": "2026-05"}}
  ],
  "parameters": [
    {{"name": "...", "value": "...", "unit": "", "source_span": "...", "source_window_id": "w000000"}}
  ],
  "open_questions": ["..."],
  "source_window_ids": ["w000000"]
}}
```

硬约束：只能归纳本文件内卡片结论，禁止外部知识 / Wiki / 录播记忆。跨月份结论并列并标 `as_of`。窗内未统一的争议必须进 `open_questions`，不得写死成一条真理。duplicate 卡仅作旁证，优先 draft / authoritative / 有参数的卡。

收录 {n} 张（draft {n_draft}，duplicate {n_dup}）。
"""


def load_cards() -> list[dict[str, Any]]:
    rows = []
    with open(CARDS, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def blob(c: dict[str, Any]) -> str:
    parts = [
        c.get("topic") or "",
        c.get("context_question") or "",
        c.get("summary_takeaway") or "",
        " ".join(str(x) for x in (c.get("entities") or [])),
    ]
    for cc in c.get("core_conclusions") or []:
        parts.append(cc.get("conclusion") or "")
    return " ".join(parts)


def has_auth(c: dict[str, Any]) -> bool:
    return any(cc.get("credibility") == "authoritative" for cc in (c.get("core_conclusions") or []))


def n_params(c: dict[str, Any]) -> int:
    p = c.get("underlying_parameters")
    return len(p) if isinstance(p, list) else 0


def rank_key(c: dict[str, Any]) -> tuple:
    creds = [CRED_RANK.get(cc.get("credibility"), 9) for cc in (c.get("core_conclusions") or [])]
    best = min(creds) if creds else 9
    return (
        0 if c.get("status") != "duplicate" else 1,
        best,
        -n_params(c),
        tuple(-ord(ch) for ch in (c.get("as_of") or "")),
        c.get("window_id") or "",
    )


def pick(cards: list[dict[str, Any]], pred: Callable[[dict[str, Any]], bool], limit: int | None, include_dup: bool) -> list[dict[str, Any]]:
    hit = []
    for c in cards:
        st = c.get("status", "draft")
        if st == "duplicate" and not include_dup:
            continue
        if st not in {"draft", "duplicate"}:
            continue
        if pred(c):
            hit.append(c)
    hit.sort(key=rank_key)
    if limit is not None:
        hit = hit[:limit]
    hit.sort(key=lambda c: (c.get("as_of") or "", c.get("window_id") or ""))
    return hit


def write_topic(name: str, title: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    n_draft = sum(1 for c in rows if c.get("status") != "duplicate")
    n_dup = sum(1 for c in rows if c.get("status") == "duplicate")
    path = os.path.join(OUT_DIR, name)
    body = [HEADER.format(title=title, n=len(rows), n_draft=n_draft, n_dup=n_dup), "", "## 卡片", "", "```json"]
    body.append(json.dumps(rows, ensure_ascii=False, indent=2))
    body.append("```")
    body.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))


def kw(*needles: str) -> Callable[[dict[str, Any]], bool]:
    def pred(c: dict[str, Any]) -> bool:
        t = blob(c)
        return any(n in t for n in needles)
    return pred


def gepan_pred(c: dict[str, Any]) -> bool:
    t = blob(c)
    if not any(n in t for n in ("格判", "碰撞箱", "碰撞")):
        return False
    # skip pure flavor / operator showcase
    if re.search(r"格判|碰撞箱|碰撞半径|物理碰撞|相离碰撞", t):
        return True
    return "碰撞" in t and any(x in t for x in ("判定", "半径", "失衡", "阻挡"))


def main() -> int:
    cards = load_cards()
    specs = [
        ("topic_float.md", "近地悬浮", pick(cards, kw("近地悬浮", "近地悬", "悬浮"), None, False)),
        ("topic_cost.md", "费用尺 / 自然回费", pick(cards, kw("费用尺", "自然回费", "一费", "回费", "费用回复"), 15, False)),
        (
            "topic_deploy_hate.md",
            "同帧部署仇恨",
            pick(cards, kw("同帧部署"), None, True),
        ),
        ("topic_gepan.md", "格判 vs 碰撞", pick(cards, gepan_pred, 15, False)),
        ("topic_redeploy.md", "再部署叠算", pick(cards, kw("再部署"), 20, False)),
        ("topic_spawn.md", "出怪时序", pick(cards, kw("出怪", "波次"), 15, False)),
    ]
    # float: also 飞行 if 近地
    float_cards = specs[0][2]
    extra_fly = pick(
        cards,
        lambda c: "飞行" in blob(c) and ("近地" in blob(c) or "悬浮" in blob(c)),
        None,
        False,
    )
    seen = {c["window_id"] for c in float_cards}
    for c in extra_fly:
        if c["window_id"] not in seen:
            float_cards.append(c)
            seen.add(c["window_id"])
    float_cards.sort(key=lambda c: (c.get("as_of") or "", c.get("window_id") or ""))
    specs[0] = ("topic_float.md", "近地悬浮", float_cards)

    print("payloads:")
    for name, title, rows in specs:
        write_topic(name, title, rows)
        print(f"  {name}\t{len(rows)}\tdraft={sum(1 for c in rows if c.get('status')!='duplicate')} dup={sum(1 for c in rows if c.get('status')=='duplicate')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
