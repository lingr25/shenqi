#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_rag_prep.py
--------------------
群聊卡片库 RAG 就绪规则修补：冲突 takeaway、canonical 回指、
schema 对齐、实体别名、rag_docs 检索合同。
"""

from __future__ import annotations

import argparse
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
CANON_PATH = os.path.join(ROOT_DIR, "qq_cards", "canonical.jsonl")
ALIAS_PATH = os.path.join(ROOT_DIR, "qq_cards", "entity_aliases.json")
RAG_PATH = os.path.join(ROOT_DIR, "qq_cards", "rag_docs.jsonl")
README_PATH = os.path.join(ROOT_DIR, "qq_cards", "README.md")
REPORT_PATH = os.path.join(ROOT_DIR, "qq_cards", "rag_prep_report.md")
SPEAKERS_PATH = os.path.join(ROOT_DIR, "qq_info", "speaker_map.json")

CONFLICT_ID = "w001186"
CONFLICT_TAKEAWAY = (
    "以录播为准：冷却每帧按当前攻速流失；"
    "群聊曾持「已有冷却不随后续攻速变化」之说，已被录播否决。"
)
SUPERSEDED = {
    "w000021": ["w001522", "w000083"],
}
SEED_MERGES = [
    ["攻速", "攻击速度"],
    ["再部署", "再部署时间"],
    ["嘲讽", "嘲讽等级"],
    ["索敌", "索敌判定", "目标搜索"],
]
INSTANCE_HINTS = re.compile(r"这关|本关|该图|读图|这把")
INSTANCE_TIME = re.compile(r"\d+(?:\.\d+)?\s*(?:s|秒)")
CRED_RANK = {"authoritative": 0, "expert": 1, "lead": 2}
ENTITY_SPLIT = re.compile(r"[（(]([^）)]+)[）)]")


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


def parse_entity(item: str) -> tuple[str, list[str]]:
    s = (item or "").strip()
    if not s:
        return "", []
    en: list[str] = []
    for m in ENTITY_SPLIT.finditer(s):
        raw = m.group(1).strip()
        for part in re.split(r"[/,;；、|]", raw):
            p = part.strip()
            if p and re.search(r"[A-Za-z]", p):
                en.append(p)
    zh = ENTITY_SPLIT.sub("", s).strip()
    zh = re.sub(r"\s+", "", zh)
    return zh, en


class UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def add(self, x: str) -> None:
        self.p.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def credibility_max(card: dict[str, Any]) -> str:
    src = card.get("core_conclusions") or card.get("canonical_conclusions") or []
    ranks = [CRED_RANK.get(cc.get("credibility"), 9) for cc in src]
    if not ranks:
        return ""
    best = min(ranks)
    for k, v in CRED_RANK.items():
        if v == best:
            return k
    return ""


def alias_canonical_of(zh: str, table: dict[str, dict[str, Any]]) -> str:
    if zh in table:
        return table[zh]["canonical"]
    for rec in table.values():
        if zh == rec["canonical"] or zh in rec.get("aliases") or []:
            return rec["canonical"]
    return zh


def build_aliases(cards: list[dict[str, Any]], extra: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[tuple[str, int, int]]]:
    uf = UF()
    zh_en: dict[str, set[str]] = defaultdict(set)
    zh_count: Counter[str] = Counter()
    for blob in cards + extra:
        for item in blob.get("entities") or []:
            zh, en = parse_entity(str(item))
            if not zh:
                continue
            uf.add(zh)
            zh_count[zh] += 1
            for e in en:
                zh_en[zh].add(e)
    for group in SEED_MERGES:
        present = [x for x in group if x in uf.p or True]
        for x in present:
            uf.add(x)
        for x in present[1:]:
            uf.union(present[0], x)
    groups: dict[str, list[str]] = defaultdict(list)
    for zh in list(uf.p):
        groups[uf.find(zh)].append(zh)
    seed_canon = {g[0]: g[0] for g in SEED_MERGES}
    for g in SEED_MERGES:
        root = uf.find(g[0])
        seed_canon[root] = g[0]

    unique: dict[str, dict[str, Any]] = {}
    for root, members in groups.items():
        members = sorted(set(members), key=lambda x: (-zh_count[x], len(x), x))
        canon = seed_canon.get(root, members[0])
        aliases: set[str] = set()
        en: set[str] = set()
        for m in members:
            if m != canon:
                aliases.add(m)
            en |= zh_en.get(m, set())
        rec = {
            "canonical": canon,
            "aliases": sorted(aliases | en, key=lambda x: (len(x), x)),
            "en": sorted(en, key=lambda x: (len(x), x)),
        }
        unique[canon] = rec
        for m in members:
            unique.setdefault(m, rec)
    top = sorted(zh_count.items(), key=lambda x: (-x[1], x[0]))[:30]
    top_rows = []
    for zh, n in top:
        rec = unique.get(zh, {"aliases": []})
        top_rows.append((zh, n, len(rec.get("aliases") or [])))
    return unique, top_rows


def is_instance(card: dict[str, Any]) -> bool:
    if card.get("scope") == "instance":
        return True
    blob = " ".join(
        [str(card.get("topic") or ""), str(card.get("context_question") or "")]
    )
    if not INSTANCE_HINTS.search(blob):
        return False
    return bool(INSTANCE_TIME.search(blob))


def conclusions_text(card: dict[str, Any]) -> str:
    parts = []
    for cc in card.get("core_conclusions") or card.get("canonical_conclusions") or []:
        t = (cc.get("conclusion") or "").strip()
        if t:
            parts.append(t)
    return "\n".join(parts)


def entity_index_names(card: dict[str, Any], aliases: dict[str, dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in card.get("entities") or []:
        zh, _ = parse_entity(str(item))
        if not zh:
            continue
        rec = aliases.get(zh)
        name = rec["canonical"] if rec else zh
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def window_text(card: dict[str, Any], aliases: dict[str, dict[str, Any]]) -> str:
    parts = [
        card.get("topic") or "",
        " ".join(entity_index_names(card, aliases)),
        card.get("context_question") or "",
        card.get("summary_takeaway") or "",
        conclusions_text(card),
    ]
    return "\n".join(p for p in parts if p)


def canon_text(entry: dict[str, Any], aliases: dict[str, dict[str, Any]]) -> str:
    oq = entry.get("open_questions") or []
    oq_s = "\n".join(str(x) for x in oq if x)
    parts = [
        entry.get("title") or "",
        " ".join(entity_index_names(entry, aliases)),
        conclusions_text(entry),
        oq_s,
    ]
    return "\n".join(p for p in parts if p)


def privacy_scan() -> list[str]:
    if not os.path.exists(SPEAKERS_PATH):
        return []
    with open(SPEAKERS_PATH, "r", encoding="utf-8") as f:
        sm = json.load(f)
    qqs = [
        k
        for k in (sm.get("speakers") or {})
        if str(k).isdigit() and len(str(k)) >= 5
    ]
    blob = ""
    d = os.path.join(ROOT_DIR, "qq_cards")
    for name in os.listdir(d):
        path = os.path.join(d, name)
        if os.path.isfile(path) and name.endswith((".jsonl", ".md", ".json")):
            with open(path, "r", encoding="utf-8") as f:
                blob += f.read()
    hits = []
    for qq in qqs:
        if re.search(rf"(?<![0-9]){re.escape(qq)}(?![0-9])", blob):
            hits.append(qq)
    return hits


def patch_readme(n_docs: int, n_alias: int) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    section = f"""
## v3 RAG 合同

检索用 `rag_docs.jsonl`（{n_docs} 条：draft 窗卡 + canonical；**duplicate 不进索引**）。

- embedding 只用 `text`（topic/title + 别名主名实体 + context_question + takeaway + 结论 + canonical 的 open_questions）。
- 过滤只用 `metadata`（category / novelty / scope / credibility_max / canonical_id / origin / status）。
- 冲突以录播为准：`novelty=conflict` 且 `conflict_resolution=vod_wins` 时听录播，勿把群聊假结论当现行规则。
- `novelty=unknown` 不是低质量，只表示尚未对照逐字稿。
- `scope=instance` 不得当全局规则（单图/单干员数字）。
- 本库是群聊补充层，非 PRTS、非录播百科；与录播冲突以录播为准。
- 实体别名见 `entity_aliases.json`（{n_alias} 个主词）。

建议系统提示：优先引用 canonical 词条；遇 conflict 听 vod_wins；黑话（索敌帧、平整化、阻挡偏移等）需用卡片结论解释，勿用泛游戏常识替换。

"""
    if "## v3 RAG 合同" in text:
        text = re.sub(
            r"\n## v3 RAG 合同\n.*?(?=\n## |\n\*\*数据边界\*\*)",
            "\n" + section,
            text,
            count=1,
            flags=re.S,
        )
    else:
        needle = "**数据边界**"
        if needle in text:
            text = text.replace(needle, section + needle, 1)
        else:
            text = text[: text.find("\n## ")] + section + text[text.find("\n## ") :]
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="RAG 就绪修补")
    p.parse_args(argv)

    cards = load_jsonl(CARDS_PATH)
    canon = load_jsonl(CANON_PATH)
    by_id = {c.get("window_id"): c for c in cards}

    # 1 conflict takeaway
    conflict = by_id.get(CONFLICT_ID)
    old_takeaway = ""
    if conflict:
        old_takeaway = conflict.get("summary_takeaway") or ""
        conflict["summary_takeaway"] = CONFLICT_TAKEAWAY

    # 2 reverse pointers
    n_back = 0
    missing_src = []
    for entry in canon:
        cid = entry.get("cluster_id")
        for wid in entry.get("source_window_ids") or []:
            card = by_id.get(wid)
            if not card:
                missing_src.append((cid, wid))
                continue
            card["canonical_id"] = cid
            n_back += 1

    # 3 schema
    n_vod = 0
    n_conf = 0
    n_scope = 0
    n_origin = 0
    for c in cards:
        if "vod_evidence" not in c:
            c["vod_evidence"] = []
            n_vod += 1
        if "novelty_confidence" not in c:
            c["novelty_confidence"] = None
            n_conf += 1
        if not c.get("scope"):
            c["scope"] = "general"
            n_scope += 1
        if not c.get("origin"):
            c["origin"] = "main"
            n_origin += 1

    # 4 superseded
    skipped_super: list[str] = []
    n_super = 0
    for wid, targets in SUPERSEDED.items():
        card = by_id.get(wid)
        if not card:
            skipped_super.append(f"{wid} missing")
            continue
        exist = [t for t in targets if t in by_id]
        skip = [t for t in targets if t not in by_id]
        skipped_super.extend(f"{wid}: skip {t}" for t in skip)
        card["superseded_by"] = exist
        n_super += 1

    # 5 instance
    n_inst_keep = sum(1 for c in cards if c.get("scope") == "instance")
    n_inst_new = 0
    inst_ids = []
    for c in cards:
        if c.get("scope") == "instance":
            inst_ids.append(c.get("window_id"))
            continue
        if is_instance(c):
            c["scope"] = "instance"
            n_inst_new += 1
            inst_ids.append(c.get("window_id"))

    # 6 aliases
    aliases, top30 = build_aliases(cards, canon)

    # persist cards + canon
    dump_jsonl(CARDS_PATH, cards)
    dump_jsonl(CANON_PATH, canon)
    alias_dump = {rec["canonical"]: rec for rec in aliases.values()}
    with open(ALIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(alias_dump, f, ensure_ascii=False, indent=2)

    # 7 rag docs
    docs: list[dict[str, Any]] = []
    for c in cards:
        if c.get("status") == "duplicate":
            continue
        docs.append(
            {
                "id": f"window:{c.get('window_id')}",
                "doc_type": "window",
                "text": window_text(c, aliases),
                "metadata": {
                    "category": c.get("category"),
                    "credibility_max": credibility_max(c),
                    "novelty": c.get("novelty") or "unknown",
                    "as_of": c.get("as_of"),
                    "scope": c.get("scope") or "general",
                    "canonical_id": c.get("canonical_id"),
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
                "text": canon_text(e, aliases),
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
                },
            }
        )
    dump_jsonl(RAG_PATH, docs)

    n_draft = sum(1 for c in cards if c.get("status", "draft") == "draft")
    n_dup = sum(1 for c in cards if c.get("status") == "duplicate")
    expected = n_draft + len(canon)
    # empty/other non-duplicate also indexed
    n_non_dup = sum(1 for c in cards if c.get("status") != "duplicate")
    expected_all = n_non_dup + len(canon)

    patch_readme(len(docs), len(alias_dump))

    hits = privacy_scan()
    today = date.today().isoformat()
    report = [
        "# RAG 预备修补报告",
        "",
        f"日期：{today}",
        "",
        "## 1. 冲突 takeaway",
        "",
        f"- `{CONFLICT_ID}` 旧：{old_takeaway}",
        f"- 新：{CONFLICT_TAKEAWAY}",
        "",
        "## 2. canonical 回指",
        "",
        f"- 写入 canonical_id 的窗卡：{n_back}",
        f"- 缺失源窗：{missing_src or '无'}",
        "",
        "## 3. schema",
        "",
        f"- 补 vod_evidence=[]：{n_vod}",
        f"- 补 novelty_confidence=null：{n_conf}",
        f"- 补 scope=general：{n_scope}",
        f"- 补 origin=main：{n_origin}",
        "",
        "## 4. superseded_by",
        "",
        f"- 写入卡数：{n_super}",
        f"- 跳过：{skipped_super or '无'}",
        "",
        "## 5. instance",
        "",
        f"- 原有 instance：{n_inst_keep}",
        f"- 新打标：{n_inst_new}",
        f"- 现 instance ids：{inst_ids}",
        "",
        "## 6. 别名表",
        "",
        f"- 主词数：{len({rec['canonical'] for rec in aliases.values()})}",
        "",
        "频次 top 30 中文主词：",
        "",
    ]
    for zh, n, na in top30:
        report.append(f"- {zh}：{n} 次，别名 {na}")
    report += [
        "",
        "## 7. rag_docs",
        "",
        f"- 条数：{len(docs)}（非 duplicate 窗卡 {n_non_dup} + canonical {len(canon)}）",
        f"- draft 窗卡 {n_draft} + canonical {len(canon)} = {expected}；duplicate {n_dup} 未进索引",
        "",
        f"隐私 hits：{len(hits)} {hits[:10] if hits else ''}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print(
        f"rag_docs={len(docs)} expected_non_dup={expected_all} draft+canon={expected} "
        f"aliases={len(alias_dump)} backrefs={n_back} instance_new={n_inst_new} "
        f"privacy={len(hits)}"
    )
    print(f"w001186 takeaway={CONFLICT_TAKEAWAY}")
    if hits:
        return 1
    if len(docs) != expected_all:
        log(f"rag_docs count {len(docs)} != {expected_all}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
