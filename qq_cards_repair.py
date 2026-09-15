#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_repair.py
------------------
对 qq_cards/cards.jsonl 做规则修补：credibility 对齐、空话结论删除、
不确定参数剔除、近重复主题去重。原地更新并写 repair_report.md / README.md。
"""

from __future__ import annotations

import argparse
import difflib
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
DEFAULT_CARDS = os.path.join(ROOT_DIR, "qq_cards", "cards.jsonl")
DEFAULT_README = os.path.join(ROOT_DIR, "qq_cards", "README.md")
DEFAULT_REPORT = os.path.join(ROOT_DIR, "qq_cards", "repair_report.md")

CRED_OF = {"主播": "authoritative", "专家": "expert", "群友": "lead"}

# 宁窄勿宽：只打纯响应、不含机制内容的短句。
EMPTY_PATTERNS = [
    re.compile(r"予以认可"),
    re.compile(r"表示同意，未补充"),
    re.compile(r"探讨了.{0,24}术语"),
    re.compile(r"^对相关讨论予以"),
    re.compile(r"未补充新的(?:机制)?(?:细节|内容|信息)"),
    re.compile(r"仅表示同意"),
    re.compile(r"未给出实质性"),
]

UNCERTAIN_MARKERS = ("分不清", "不确定", "可能", "示例", "测算", "比如", "假设")

FORCE_CLUSTERS = [
    ("肉鸽典训", ["w001109", "w001110"]),
    ("近地悬浮", ["w002063", "w002074", "w002075"]),
    (
        "同帧部署仇恨",
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
    ),
]

CAT_ORDER = ["索敌", "帧时序", "位移", "寻路", "伤害结算", "拆包数据", "其他"]
CRED_RANK = {"authoritative": 0, "expert": 1, "lead": 2}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_cards(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def dump_cards(path: str, cards: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def is_empty_conclusion(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return any(p.search(t) for p in EMPTY_PATTERNS)


def entity_zh(item: str) -> str:
    s = (item or "").strip()
    m = re.match(r"^([^（(]+)", s)
    return (m.group(1) if m else s).strip()


def entity_set(card: dict[str, Any]) -> set[str]:
    return {entity_zh(x) for x in (card.get("entities") or []) if entity_zh(x)}


def has_authoritative(card: dict[str, Any]) -> bool:
    return any(
        (cc.get("credibility") == "authoritative")
        for cc in (card.get("core_conclusions") or [])
    )


def n_params(card: dict[str, Any]) -> int:
    p = card.get("underlying_parameters")
    return len(p) if isinstance(p, list) else 0


def canonical_key(card: dict[str, Any]) -> tuple:
    as_of = card.get("as_of") or ""
    return (
        0 if has_authoritative(card) else 1,
        -n_params(card),
        tuple(-ord(ch) for ch in as_of),
        card.get("window_id") or "",
    )


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

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for x in self.p:
            out[self.find(x)].append(x)
        return dict(out)


def repair_credibility(cards: list[dict[str, Any]]) -> int:
    n = 0
    for c in cards:
        for cc in c.get("core_conclusions") or []:
            sp = cc.get("speaker")
            want = CRED_OF.get(sp or "")
            if want and cc.get("credibility") != want:
                cc["credibility"] = want
                n += 1
    return n


def repair_empty_conclusions(cards: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    dropped = 0
    emptied = 0
    details: list[str] = []
    for c in cards:
        cons = list(c.get("core_conclusions") or [])
        keep = []
        for cc in cons:
            if is_empty_conclusion(cc.get("conclusion") or ""):
                dropped += 1
                details.append(
                    f"{c.get('window_id')} [{cc.get('speaker')}] {cc.get('conclusion')}"
                )
            else:
                keep.append(cc)
        if len(keep) != len(cons):
            c["core_conclusions"] = keep
            if not keep:
                c["status"] = "empty"
                emptied += 1
    return dropped, emptied, details


def repair_params(cards: list[dict[str, Any]]) -> tuple[int, list[str]]:
    n = 0
    details: list[str] = []
    for c in cards:
        params = c.get("underlying_parameters")
        if not isinstance(params, list) or not params:
            continue
        keep = []
        for p in params:
            blob = " ".join(
                [
                    str(p.get("source_span") or ""),
                    str(p.get("name") or ""),
                ]
            )
            if any(m in blob for m in UNCERTAIN_MARKERS):
                n += 1
                details.append(
                    f"{c.get('window_id')} name={p.get('name')!r} value={p.get('value')!r}"
                )
            else:
                keep.append(p)
        if len(keep) != len(params):
            c["underlying_parameters"] = keep
    return n, details


def topic_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a or "", b or "").ratio()


def repair_dedup(cards: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {c.get("window_id"): c for c in cards if c.get("window_id")}
    ids = list(by_id)
    uf = UnionFind(ids)
    forced_used: list[tuple[str, list[str]]] = []
    for name, members in FORCE_CLUSTERS:
        present = [w for w in members if w in by_id]
        if len(present) < 2:
            continue
        for x in present[1:]:
            uf.union(present[0], x)
        forced_used.append((name, present))

    auto_pairs = 0
    for i, ida in enumerate(ids):
        ca = by_id[ida]
        if ca.get("status") in {"empty", "duplicate"}:
            continue
        ea = entity_set(ca)
        if len(ea) < 2:
            continue
        for idb in ids[i + 1 :]:
            cb = by_id[idb]
            if ca.get("category") != cb.get("category"):
                continue
            if cb.get("status") in {"empty", "duplicate"}:
                continue
            shared = ea & entity_set(cb)
            if len(shared) < 2:
                continue
            if topic_ratio(ca.get("topic") or "", cb.get("topic") or "") <= 0.6:
                continue
            uf.union(ida, idb)
            auto_pairs += 1

    clusters = [g for g in uf.groups().values() if len(g) >= 2]
    n_marked = 0
    cluster_rows: list[str] = []
    for g in clusters:
        ranked = sorted((by_id[w] for w in g), key=canonical_key)
        canon = ranked[0]
        cid = canon.get("window_id")
        cluster_rows.append(
            f"- canonical `{cid}` ← {', '.join('`'+x.get('window_id')+'`' for x in ranked[1:])}"
            f"  ({canon.get('category')} / {canon.get('topic')})"
        )
        for other in ranked[1:]:
            if other.get("status") == "empty":
                continue
            other["status"] = "duplicate"
            other["canonical_window_id"] = cid
            n_marked += 1
    return {
        "n_clusters": len(clusters),
        "n_marked": n_marked,
        "auto_pairs": auto_pairs,
        "forced": forced_used,
        "rows": cluster_rows,
    }


def rewrite_readme(path: str, cards: list[dict[str, Any]], repair_date: str) -> None:
    draft = [c for c in cards if c.get("status", "draft") == "draft"]
    n_empty = sum(1 for c in cards if c.get("status") == "empty")
    n_dup = sum(1 for c in cards if c.get("status") == "duplicate")
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in draft:
        by_cat[c.get("category") or "其他"].append(c)

    def top_cred(c: dict[str, Any]) -> str:
        ranks = [
            CRED_RANK.get(cc.get("credibility"), 9)
            for cc in (c.get("core_conclusions") or [])
        ]
        if not ranks:
            return "—"
        best = min(ranks)
        for k, v in CRED_RANK.items():
            if v == best:
                return k
        return "—"

    lines: list[str] = []
    a = lines.append
    a("# 群聊机制知识卡片（draft）")
    a("")
    a(f"修补日期：{repair_date}。规则见同目录 `repair_report.md`。")
    a("")
    a("来源：桃大将军粉丝群机制讨论窗，经 LLM 提炼后机器验收，再经规则修补。")
    a("")
    a("**数据边界**")
    a("")
    a("- 语料是群聊补充层，不是录播逐字稿；与录播讲解冲突时 **以录播为准**。")
    a("- 发言人已脱敏（主播/专家/群友）；有效卡 `status=draft`，`novelty=unknown`。")
    a("- 主播结论 credibility 对齐为 authoritative，专家 expert，群友 lead。")
    a("- 含「可能/测算/假设」等的参数已从表中剔除；近重复卡标 `duplicate` 并指向 canonical。")
    a("- 参数必须能在窗内原文中找到；无过硬数字的卡 `underlying_parameters` 为空。")
    a("")
    a(
        f"共 **{len(cards)}** 张入库卡：draft **{len(draft)}**，"
        f"duplicate **{n_dup}**，empty **{n_empty}**。"
    )
    a("")
    a("## 分类统计（draft）")
    a("")
    for cat in CAT_ORDER:
        n = len(by_cat.get(cat) or [])
        if n:
            a(f"- {cat}：{n}")
    for cat, group in by_cat.items():
        if cat not in CAT_ORDER and group:
            a(f"- {cat}：{len(group)}")
    a("")
    for cat in CAT_ORDER:
        group = by_cat.get(cat) or []
        if not group:
            continue
        group = sorted(
            group, key=lambda c: (c.get("as_of") or "", c.get("window_id") or "")
        )
        a(f"## {cat}（{len(group)}）")
        a("")
        for c in group:
            as_of = (c.get("as_of") or "")[:10]
            topic = (c.get("topic") or "").replace("|", "/")
            a(
                f"- {as_of} | {topic} | {top_cred(c)} | `{c.get('window_id')}`"
            )
        a("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_report(
    path: str,
    n_cred: int,
    n_empty_conc: int,
    n_emptied_cards: int,
    empty_details: list[str],
    n_params: int,
    param_details: list[str],
    dedup: dict[str, Any],
    cards: list[dict[str, Any]],
    repair_date: str,
) -> None:
    st = Counter(c.get("status", "draft") for c in cards)
    lines = [
        "# 知识卡片规则修补报告",
        "",
        f"日期：{repair_date}",
        "",
        "## 1. credibility 对齐",
        "",
        f"- 改写条数：{n_cred}（主播→authoritative，专家→expert，群友→lead）",
        "",
        "## 2. 空话结论",
        "",
        f"- 删除结论：{n_empty_conc}",
        f"- 因此整卡 status=empty：{n_emptied_cards}",
        "",
    ]
    if empty_details:
        lines.append("明细：")
        lines.append("")
        for d in empty_details:
            lines.append(f"- {d}")
        lines.append("")
    lines += [
        "## 3. 不确定参数剔除",
        "",
        f"- 移除参数：{n_params}（source_span/name 含 分不清/不确定/可能/示例/测算/比如/假设）",
        "",
    ]
    if param_details:
        lines.append("明细：")
        lines.append("")
        for d in param_details:
            lines.append(f"- {d}")
        lines.append("")
    lines += [
        "## 4. 主题去重",
        "",
        f"- 合并簇数：{dedup['n_clusters']}",
        f"- 标为 duplicate 的卡：{dedup['n_marked']}",
        f"- 自动配对（ratio>0.6 且共享≥2 实体）：{dedup['auto_pairs']}",
        "",
        "强制簇：",
        "",
    ]
    for name, members in dedup["forced"]:
        lines.append(f"- {name}：{', '.join('`'+m+'`' for m in members)}")
    lines.append("")
    lines.append("簇列表：")
    lines.append("")
    lines.extend(dedup["rows"] or ["（无）"])
    lines += [
        "",
        "## 修补后 status",
        "",
        f"- draft：{st.get('draft', 0)}",
        f"- duplicate：{st.get('duplicate', 0)}",
        f"- empty：{st.get('empty', 0)}",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="规则修补 qq_cards/cards.jsonl")
    p.add_argument("--cards", default=DEFAULT_CARDS)
    p.add_argument("--readme", default=DEFAULT_README)
    p.add_argument("--report", default=DEFAULT_REPORT)
    args = p.parse_args(argv)

    cards = load_cards(args.cards)
    log(f"loaded {len(cards)}")
    n_cred = repair_credibility(cards)
    n_empty_conc, n_emptied, empty_details = repair_empty_conclusions(cards)
    n_params, param_details = repair_params(cards)
    dedup = repair_dedup(cards)

    cards.sort(key=lambda c: (c.get("as_of") or "", c.get("window_id") or ""))
    dump_cards(args.cards, cards)
    today = date.today().isoformat()
    write_report(
        args.report,
        n_cred,
        n_empty_conc,
        n_emptied,
        empty_details,
        n_params,
        param_details,
        dedup,
        cards,
        today,
    )
    rewrite_readme(args.readme, cards, today)
    print(
        f"cred={n_cred} empty_conc={n_empty_conc} empty_cards={n_emptied} "
        f"params_removed={n_params} dup_clusters={dedup['n_clusters']} "
        f"dup_cards={dedup['n_marked']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
