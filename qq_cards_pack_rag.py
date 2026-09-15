#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_pack_rag.py
--------------------
glossary / split / alias 三批 LLM 交接包。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qq_cards_pack import log, write_batches, write_readme

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CARDS_PATH = os.path.join(ROOT_DIR, "qq_cards", "cards.jsonl")
CANON_PATH = os.path.join(ROOT_DIR, "qq_cards", "canonical.jsonl")
ALIAS_PATH = os.path.join(ROOT_DIR, "qq_cards", "entity_aliases.json")
CLUSTERS_PATH = os.path.join(ROOT_DIR, "qq_info", "llm_batch_merge", "clusters.json")

ENTITY_SPLIT = re.compile(r"[（(]([^）)]+)[）)]")
CRED_RANK = {"authoritative": 0, "expert": 1, "lead": 2}

GLOSSARY_MUST = [
    "索敌帧",
    "逻辑帧",
    "格判",
    "碰撞箱",
    "阻挡半径",
    "失衡",
    "选择组",
    "二次过滤器",
    "事件帧",
    "地面规避",
    "近地悬浮",
    "同帧部署",
    "仇恨",
    "嘲讽等级",
    "技力",
    "再部署",
    "落地隐",
    "平整化",
    "避障力",
    "力道",
    "过伤",
    "锁血",
    "永控",
    "入控",
    "免控",
    "攻击间隔",
    "前摇",
    "后摇",
    "无动画",
    "出生状态机",
    "visitNodeCenter",
    "SPFA",
    "Prefab",
    "TypeTree",
    "隐匿",
    "迷彩",
    "反隐",
    "罚站",
    "路径点",
    "出怪",
    "费用尺",
    "阻挡偏移",
    "急停半径",
]

SPLIT_FORCE = {"c0001", "c0002", "c0003", "c0004", "c0005", "c0006", "c0011"}

GLOSSARY_PROMPT = r'''# 机制黑话 glossary — Prompt

一术语一调用。只输出一个 JSON 对象。

给圈外人解释明日方舟机制讨论里的黑话。输入含术语、别名、最多 3 张相关窗卡的摘要。

输出：

```json
{
  "term": "索敌帧",
  "aliases": ["..."],
  "short_def": "≤80字人话",
  "mechanic_def": "机制精确定义，或 unknown",
  "related_terms": ["..."],
  "source_window_ids": ["w000000"],
  "status": "glossary_draft"
}
```

硬约束：

- `short_def` 可以通俗，≤80 字。
- `mechanic_def` **必须能从提供的卡结论推出**；推不出就写 `"unknown"`，并在 related_terms 或 mechanic_def 里说明依据不足。禁止用卡外百科/Wiki 补精确数字或帧数。
- `source_window_ids` 只能来自输入的卡。
- 不要输出 QQ / 真名。

## 使用

读 `batch_XXX.jsonl` 逐行，输出追加到 `cards_glossary_batch_XXX.jsonl`。

## User

{WINDOW_PAYLOAD}
'''

SPLIT_PROMPT = r'''# 大簇拆词条 — Prompt

一簇一调用。只输出一个 **JSON 数组**（2–8 条词条），不要 Markdown 围栏。

把误并/过肥的主题簇拆成真正可入库的 canonical 词条。禁止引入卡外知识。

每条词条：

```json
{
  "title": "...",
  "entities": ["..."],
  "canonical_conclusions": [
    {"speaker": "主播", "credibility": "authoritative", "conclusion": "..."}
  ],
  "parameters": [
    {"name": "...", "value": "...", "unit": "帧", "source_span": "...", "source_window_id": "w000000"}
  ],
  "open_questions": ["..."],
  "source_window_ids": ["w000000"],
  "parent_cluster_id": "c0001",
  "split_reason": "..."
}
```

硬约束：

- 每条 `source_window_ids` 必须 ⊆ 本簇输入的窗 id。
- `parameters.value` 必须能在对应窗卡的 source_spans / 参数 span 里找到。
- **c0001 / 含 w001186**：该窗 `novelty=conflict` 且录播为准——冷却**每帧按当前攻速流失**。群聊「已有冷却不随后续攻速变化」不得写入 canonical_conclusions 当定论，放入 `open_questions` 或单独结论并标明 rejected。
- **c0011**：误并。必须拆成 ≥2 条：阻挡与索敌同帧插入群攻 ≠ 凯尔希两套索敌。
- **c0003**：仇恨公式 5 月量级（约 1e7）与 8 月量级（约 3e8 / 3e11）必须并列，标明 as_of，禁止轧成一条真理。
- 冲突结论并列，带各自 credibility。

## 使用

读 `split_batch_XXX.jsonl` 逐行（一行一簇），输出追加到 `cards_split_batch_XXX.jsonl`（每行一个 JSON 数组）。

## User

{WINDOW_PAYLOAD}
'''

ALIAS_PROMPT = r'''# 实体消歧 — Prompt

一实体一调用。只输出一个 JSON 对象。

为群聊机制实体补规范中英名。不要把不同机制并成一个词。

硬约束：

- **禁止**把 隐匿(Stealth) 和 迷彩(Camouflage) 并成一个。
- **仇恨** 与 **嘲讽等级** 保持区分（嘲讽是仇恨的数量级加成，不是同义词）。
- `canonical_en` 允许空字符串，但不能缺字段。
- `merge_into`：仅当本词确定是另一主词的别名时填对方 canonical_zh，否则 `null`。

输出：

```json
{
  "zh": "隐匿",
  "canonical_zh": "隐匿",
  "canonical_en": "Stealth",
  "merge_into": null,
  "note": ""
}
```

## 使用

读 `batch_XXX.jsonl` 逐行，输出追加到 `cards_alias_batch_XXX.jsonl`。

## User

{WINDOW_PAYLOAD}
'''


def zh_of(item: str) -> str:
    s = (item or "").strip()
    z = ENTITY_SPLIT.sub("", s).strip()
    return re.sub(r"\s+", "", z)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def card_entities_zh(card: dict[str, Any]) -> set[str]:
    return {zh_of(x) for x in (card.get("entities") or []) if zh_of(x)}


def pick_conclusion(card: dict[str, Any]) -> dict[str, Any] | None:
    cons = list(card.get("core_conclusions") or [])
    cons.sort(key=lambda cc: CRED_RANK.get(cc.get("credibility"), 9))
    return cons[0] if cons else None


def related_cards_for_term(
    term: str, cards: list[dict[str, Any]], limit: int = 3
) -> list[dict[str, Any]]:
    hits: list[tuple[int, dict[str, Any]]] = []
    for c in cards:
        if c.get("status") == "duplicate":
            continue
        ents = card_entities_zh(c)
        blob = " ".join(
            [
                c.get("topic") or "",
                c.get("summary_takeaway") or "",
                " ".join(ents),
            ]
        )
        if term not in blob and term not in ents:
            continue
        score = 0
        if term in ents:
            score += 10
        if any(cc.get("credibility") == "authoritative" for cc in (c.get("core_conclusions") or [])):
            score += 5
        if term in (c.get("topic") or ""):
            score += 3
        hits.append((score, c))
    hits.sort(key=lambda x: -x[0])
    out = []
    for _, c in hits[:limit]:
        cc = pick_conclusion(c)
        out.append(
            {
                "window_id": c.get("window_id"),
                "topic": c.get("topic"),
                "summary_takeaway": c.get("summary_takeaway"),
                "conclusion": cc,
            }
        )
    return out


def cmd_glossary(args: argparse.Namespace) -> int:
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))
    cards = load_jsonl(args.cards)
    zh_count: Counter[str] = Counter()
    for c in cards:
        if c.get("status") == "duplicate":
            continue
        for e in c.get("entities") or []:
            z = zh_of(e)
            if z:
                zh_count[z] += 1
    terms: list[str] = []
    seen: set[str] = set()
    for t in GLOSSARY_MUST:
        if t not in seen:
            seen.add(t)
            terms.append(t)
    for zh, _n in zh_count.most_common(40):
        rec = aliases.get(zh) or {}
        canon = rec.get("canonical") or zh
        if canon not in seen:
            seen.add(canon)
            terms.append(canon)
        if len(terms) >= args.max_terms:
            break
    terms = terms[: args.max_terms]
    rows = []
    for t in terms:
        rec = aliases.get(t) or {}
        rows.append(
            {
                "term": t,
                "aliases": rec.get("aliases") or [],
                "en": rec.get("en") or [],
                "cards": related_cards_for_term(t, cards),
            }
        )
    n_batches = write_batches(args.out_dir, rows, args.batch_size, "batch")
    with open(os.path.join(args.out_dir, "PROMPT.md"), "w", encoding="utf-8") as f:
        f.write(GLOSSARY_PROMPT.lstrip("\n"))
    write_readme(
        args.out_dir,
        f"""glossary 术语包
输入：batch_XXX.jsonl（每行一术语）
输出：cards_glossary_batch_XXX.jsonl
验收：python -X utf8 qq_cards_validate.py --mode glossary --cards-dir {args.out_dir}
术语数={len(rows)} 批次数={n_batches}
""",
    )
    print(f"glossary terms={len(rows)} batches={n_batches} out={args.out_dir}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    clusters = json.load(open(args.clusters, encoding="utf-8"))
    cards = {c["window_id"]: c for c in load_jsonl(args.cards)}
    in_canon: set[str] = set()
    if os.path.exists(args.canonical):
        for e in load_jsonl(args.canonical):
            in_canon.add(e.get("cluster_id"))
    selected = []
    for cl in clusters:
        cid = cl.get("cluster_id")
        src = list(cl.get("source_window_ids") or [])
        if cid in SPLIT_FORCE or (len(src) > 4 and cid not in in_canon):
            if cid not in in_canon:
                selected.append(cl)
    rows = []
    for cl in selected:
        src = [w for w in (cl.get("source_window_ids") or []) if w in cards]
        members = [cards[w] for w in src]
        rows.append(
            {
                "cluster_id": cl.get("cluster_id"),
                "size": len(members),
                "source_window_ids": src,
                "notes": {
                    "has_w001186": "w001186" in src,
                    "must_split_c0011": cl.get("cluster_id") == "c0011",
                    "hate_formula_c0003": cl.get("cluster_id") == "c0003",
                },
                "cards": members,
            }
        )
    os.makedirs(args.out_dir, exist_ok=True)
    n_batches = (len(rows) + args.batch_size - 1) // args.batch_size if rows else 0
    for b in range(n_batches):
        chunk = rows[b * args.batch_size : (b + 1) * args.batch_size]
        path = os.path.join(args.out_dir, f"split_batch_{b + 1:03d}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for obj in chunk:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        log(f"  {os.path.basename(path)}  {len(chunk)}")
    with open(os.path.join(args.out_dir, "clusters.json"), "w", encoding="utf-8") as f:
        json.dump(
            [{"cluster_id": r["cluster_id"], "source_window_ids": r["source_window_ids"]} for r in rows],
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(os.path.join(args.out_dir, "PROMPT.md"), "w", encoding="utf-8") as f:
        f.write(SPLIT_PROMPT.lstrip("\n"))
    write_readme(
        args.out_dir,
        f"""大簇拆词条
输入：split_batch_XXX.jsonl（每行一簇，含 cards[]）
输出：cards_split_batch_XXX.jsonl（每行一个 JSON 数组）
验收：python -X utf8 qq_cards_validate.py --mode split --cards-dir {args.out_dir}
簇={', '.join(r['cluster_id'] for r in rows)} 批次数={n_batches}
""",
    )
    print(
        f"split clusters={len(rows)} ids={[r['cluster_id'] for r in rows]} "
        f"batches={n_batches} out={args.out_dir}"
    )
    return 0


def cmd_alias(args: argparse.Namespace) -> int:
    aliases = json.load(open(ALIAS_PATH, encoding="utf-8"))
    cards = load_jsonl(args.cards)
    zh_count: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    for c in cards:
        if c.get("status") == "duplicate":
            continue
        topic = c.get("topic") or ""
        for e in c.get("entities") or []:
            z = zh_of(e)
            if not z:
                continue
            rec = aliases.get(z) or {}
            canon = rec.get("canonical") or z
            zh_count[canon] += 1
            if topic and len(samples[canon]) < 3 and topic not in samples[canon]:
                samples[canon].append(topic)
    en_map: dict[str, set[str]] = defaultdict(set)
    for zh, rec in aliases.items():
        for e in rec.get("en") or []:
            en_map[e.lower()].add(rec.get("canonical") or zh)
    conflict_en = {e: zhs for e, zhs in en_map.items() if len(zhs) > 1}

    picked: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        rec = aliases.get(term) or {}
        canon = rec.get("canonical") or term
        if canon not in seen:
            seen.add(canon)
            picked.append(canon)

    top80 = [zh for zh, _n in zh_count.most_common(80)]
    for zh in top80:
        add(zh)
    top_set = set(top80)
    for _e, zhs in conflict_en.items():
        hot = [z for z in zhs if zh_count.get(z, 0) >= 3 or z in top_set]
        if len(hot) >= 2 or any(z in top_set for z in zhs):
            for z in sorted(zhs, key=lambda x: -zh_count.get(x, 0)):
                if zh_count.get(z, 0) >= 2 or z in top_set:
                    add(z)
    empty_en = []
    for zh, n in zh_count.most_common():
        rec = aliases.get(zh) or {}
        if n >= 5 and not (rec.get("en") or []):
            empty_en.append(zh)
        if len(empty_en) >= 30:
            break
    for zh in empty_en:
        add(zh)

    rows = []
    for zh in picked:
        rec = aliases.get(zh) or {"canonical": zh, "aliases": [], "en": []}
        rows.append(
            {
                "zh": zh,
                "aliases": rec.get("aliases") or [],
                "en_candidates": rec.get("en") or [],
                "sample_usages": samples.get(zh) or [],
                "freq": zh_count.get(zh, 0),
                "en_conflict_with": sorted(
                    {
                        other
                        for e in (rec.get("en") or [])
                        for other in conflict_en.get(e.lower(), set())
                        if other != zh
                    }
                ),
            }
        )
    n_batches = write_batches(args.out_dir, rows, args.batch_size, "batch")
    with open(os.path.join(args.out_dir, "PROMPT.md"), "w", encoding="utf-8") as f:
        f.write(ALIAS_PROMPT.lstrip("\n"))
    write_readme(
        args.out_dir,
        f"""实体消歧包
输入：batch_XXX.jsonl（每行一中文主词）
输出：cards_alias_batch_XXX.jsonl
验收：python -X utf8 qq_cards_validate.py --mode alias --cards-dir {args.out_dir}
条目={len(rows)} 批次数={n_batches}
隐匿 vs 迷彩、仇恨 vs 嘲讽等级禁止合并。
""",
    )
    print(f"alias terms={len(rows)} batches={n_batches} out={args.out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="glossary / split / alias 交接包")
    sub = p.add_subparsers(dest="cmd", required=True)

    pg = sub.add_parser("glossary")
    pg.add_argument("--cards", default=CARDS_PATH)
    pg.add_argument("--batch-size", type=int, default=10)
    pg.add_argument("--max-terms", type=int, default=50)
    pg.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "qq_info", "llm_batch_glossary"),
    )

    ps = sub.add_parser("split")
    ps.add_argument("--cards", default=CARDS_PATH)
    ps.add_argument("--canonical", default=CANON_PATH)
    ps.add_argument("--clusters", default=CLUSTERS_PATH)
    ps.add_argument("--batch-size", type=int, default=1)
    ps.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "qq_info", "llm_batch_split"),
    )

    pa = sub.add_parser("alias")
    pa.add_argument("--cards", default=CARDS_PATH)
    pa.add_argument("--batch-size", type=int, default=20)
    pa.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "qq_info", "llm_batch_alias"),
    )

    args = p.parse_args(argv)
    if args.cmd == "glossary":
        return cmd_glossary(args)
    if args.cmd == "split":
        return cmd_split(args)
    if args.cmd == "alias":
        return cmd_alias(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
