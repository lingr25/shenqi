# -*- coding: utf-8 -*-
"""enrich_atoms.py - 原子卡增强: 稳定 claim_id + PRTS 实体挂接 + 录制日期版本标注

- claim_id: sha1(source_id|parent_idx|proposition)[:12], 跨运行稳定, 不依赖 LLM。
- entity_links: 卡内 entities / 命题正文中出现的 PRTS 词表实体, 带类型与规范名
  (operators/operator_aliases/enemies/devices/status_terms/mechanic_terms/prts_slangs/shenqi_slangs)。
- recorded_at: 视频发布日期(all_search_videos.json created), 作为 game_version 的近似锚点;
  game_version 本身留 null, 待人工或按版本日历补。

输出: knowledge_pilot/{stem}.atoms.enriched.jsonl + enrich_report.md
"""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "knowledge_pilot"

prts = json.loads((ROOT / "prts_entities.json").read_text(encoding="utf-8"))

# 规范名 -> (类型, 规范名) 索引; 别名也指向规范名
INDEX = {}


def add(name, typ, canonical=None):
    if not name or len(name) < 2:
        return
    INDEX[name] = (typ, canonical or name)


for n in prts["operators"]:
    add(n, "operator")
for canon, aliases in prts["operator_aliases"].items():
    for a in aliases:
        add(a, "operator", canon)
for n in prts["enemies"]:
    add(n, "enemy")
for n in prts["devices"]:
    add(n, "device")
for n in prts["status_terms"]:
    add(n, "status")
for n in prts["mechanic_terms"]:
    add(n, "mechanic")
for n in prts["prts_slangs"]:
    add(n, "slang")
for cat, words in prts["shenqi_slangs"].items():
    for w in words:
        add(w, "shenqi_slang")

# 视频 bvid -> 发布日期
videos = json.loads((ROOT / "all_search_videos.json").read_text(encoding="utf-8"))
items = videos if isinstance(videos, list) else videos.get("videos", [])
BVID_DATE = {}
for v in items:
    if isinstance(v, dict) and v.get("bvid") and v.get("created"):
        dt = datetime.fromtimestamp(v["created"], tz=timezone(timedelta(hours=8)))
        BVID_DATE[v["bvid"]] = dt.strftime("%Y-%m-%d")

# 预编译: 长词优先, 避免短词抢匹配
TERMS = sorted(INDEX, key=len, reverse=True)


def link_entities(atom):
    haystacks = set(atom.get("entities") or [])
    conds = atom.get("conditions") or []
    cond_txt = " ".join(
        c if isinstance(c, str) else json.dumps(c, ensure_ascii=False) for c in conds
    )
    text = (atom.get("proposition") or "") + " " + cond_txt
    found = {}
    for t in TERMS:
        if t in text or t in haystacks:
            typ, canon = INDEX[t]
            found[canon] = {"mention": t, "canonical": canon, "type": typ}
    return list(found.values())


def main():
    stats = {"atoms": 0, "with_links": 0, "links": 0, "by_type": {}}
    for f in sorted(OUT_DIR.glob("*.atoms.jsonl")):
        if ".enriched." in f.name:
            continue
        out_lines = []
        for line in f.read_text(encoding="utf-8").splitlines():
            a = json.loads(line)
            bvid = a["source_id"].split("_p")[0]
            a["claim_id"] = hashlib.sha1(
                f"{a['source_id']}|{a['parent_idx']}|{a['proposition']}".encode("utf-8")
            ).hexdigest()[:12]
            a["recorded_at"] = BVID_DATE.get(bvid)
            a["game_version"] = None  # 待版本日历补充; recorded_at 为上界锚点
            links = link_entities(a)
            a["entity_links"] = links
            stats["atoms"] += 1
            if links:
                stats["with_links"] += 1
                stats["links"] += len(links)
                for l in links:
                    stats["by_type"][l["type"]] = stats["by_type"].get(l["type"], 0) + 1
            out_lines.append(json.dumps(a, ensure_ascii=False))
        out_path = OUT_DIR / f.name.replace(".atoms.jsonl", ".atoms.enriched.jsonl")
        out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(f"{out_path.name}: {len(out_lines)} 卡")

    lines = [
        "# 原子卡增强报告",
        "",
        f"- 原子卡: {stats['atoms']}, 挂到实体: {stats['with_links']} ({stats['with_links']/max(stats['atoms'],1):.0%})",
        f"- 实体链接总数: {stats['links']}",
        "- 按类型: " + ", ".join(f"{k}={v}" for k, v in sorted(stats["by_type"].items(), key=lambda x: -x[1])),
        "- game_version 全部留 null, recorded_at 已按视频发布日期填充",
    ]
    (OUT_DIR / "enrich_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
