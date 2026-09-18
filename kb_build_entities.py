# -*- coding: utf-8 -*-
"""kb_build_entities.py - 阶段B: 统一实体索引 + docs.jsonl 实体回填

主表: prts_entities.json (typed)。别名表: qq_cards/entity_aliases.json (无类型)。
同名多义时保留全部候选并记 ambiguous。产出:
  kb/entity_index.json      mention -> [{canonical, type, source}]
  kb/entity_suggestions.json QQ 俗称等未进 PRTS 的候选 (仅记录, 人工确认后再入 entity_corrector.py)
  kb/docs.jsonl             entities 字段回填归一化 (in-place 重写)
  kb/entity_report.md
"""
import json
import re
from collections import Counter

TYPE_OF_LIST = [
    ("operators", "operator"),
    ("enemies", "enemy"),
    ("devices", "device"),
    ("status_terms", "status"),
    ("mechanic_terms", "mechanic"),
    ("prts_slangs", "slang"),
]

PAREN_RE = re.compile(r"^(.+?)（([^（）]*)）$")


def add(index, mention, canonical, typ, source):
    mention = (mention or "").strip()
    if not mention:
        return
    entries = index.setdefault(mention, [])
    for e in entries:
        if e["canonical"] == canonical and e["type"] == typ:
            if source not in e["source"]:
                e["source"].append(source)
            return
    entries.append({"canonical": canonical, "type": typ, "source": [source]})


def build_index():
    prts = json.load(open("prts_entities.json", encoding="utf-8"))
    index = {}
    for key, typ in TYPE_OF_LIST:
        for name in prts.get(key) or []:
            add(index, name, name, typ, "prts")
    for canon, aliases in (prts.get("operator_aliases") or {}).items():
        add(index, canon, canon, "operator", "prts")
        for a in aliases:
            add(index, a, canon, "operator", "prts_alias")
    for cat, terms in (prts.get("shenqi_slangs") or {}).items():
        for t in terms:
            add(index, t, t, "shenqi_slang", "prts")

    qq_alias = json.load(open("qq_cards/entity_aliases.json", encoding="utf-8"))
    suggestions = {}
    for main, info in qq_alias.items():
        canon = info.get("canonical") or main
        names = [main, canon] + (info.get("aliases") or []) + (info.get("en") or [])
        hit = any(n in index for n in {main, canon})
        # QQ 主词的中文部分若已在 PRTS, 继承其 type; 否则 untyped
        zh = PAREN_RE.match(canon)
        zh_name = zh.group(1).strip() if zh else canon
        typ = None
        if zh_name in index:
            typ = index[zh_name][0]["type"]
        elif canon in index:
            typ = index[canon][0]["type"]
        if typ is None:
            typ = "untyped"
            suggestions[canon] = {"aliases": info.get("aliases") or [], "en": info.get("en") or []}
        for n in names:
            add(index, n, canon, typ, "qq_alias" if hit or typ != "untyped" else "qq")
        if zh_name != canon:
            add(index, zh_name, canon, typ, "qq_alias")
    return index, suggestions


def resolve(mention, index):
    """返回 {mention, canonical, type, ambiguous}"""
    m = (mention or "").strip()
    p = PAREN_RE.match(m)
    aliases = []
    if p:
        m = p.group(1).strip()
        aliases = [a for a in (p.group(2) or "").split("/") if a.strip()]
    entries = index.get(m)
    if not entries:
        return {"mention": mention, "canonical": m, "type": None, "aliases": aliases}
    ambiguous = len({(e["canonical"], e["type"]) for e in entries}) > 1
    best = entries[0]
    out = {"mention": mention, "canonical": best["canonical"], "type": best["type"], "aliases": aliases}
    if ambiguous:
        out["ambiguous"] = [{"canonical": e["canonical"], "type": e["type"]} for e in entries]
    return out


def main():
    index, suggestions = build_index()
    amb = {m: es for m, es in index.items() if len({(e["canonical"], e["type"]) for e in es}) > 1}
    json.dump({"mentions": index,
               "stats": {"mentions": len(index), "ambiguous": len(amb)}},
              open("kb/entity_index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(suggestions, open("kb/entity_suggestions.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 回填 docs.jsonl
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    cov = Counter()
    for d in docs:
        ents = []
        seen = set()
        for e in d.get("entities") or []:
            r = resolve(e.get("mention") or e.get("canonical") or "", index)
            key = (r["canonical"], r["type"])
            if key not in seen:
                seen.add(key)
                ents.append(r)
        d["entities"] = ents
        cov[d["doc_type"] + ("_linked" if any(e.get("type") for e in ents) else "_none")] += 1

    # 文本回扫: 对无链接文档, 用统一索引 mention 做子串匹配补挂实体
    scan_mentions = sorted((m for m in index if len(m) >= 2), key=len, reverse=True)
    n_scan_added = 0
    for d in docs:
        if any(e.get("type") for e in d["entities"]):
            continue
        text = d.get("text") or ""
        seen = {(e.get("canonical"), e.get("type")) for e in d["entities"]}
        added = 0
        for m in scan_mentions:
            if m in text:
                for e in index[m][:1]:
                    key = (e["canonical"], e["type"])
                    if key not in seen:
                        seen.add(key)
                        d["entities"].append({"mention": m, "canonical": e["canonical"],
                                              "type": e["type"], "via": "text_scan"})
                        added += 1
                        n_scan_added += 1
                if added >= 15:
                    break
        if added:
            cov[d["doc_type"] + "_scan_linked"] += 1

    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    lines = ["# 阶段B 统一实体索引报告", "",
             f"- mention 总数: **{len(index)}**",
             f"- 同名多义 mention: **{len(amb)}**（保留全部候选, 检索不强制消歧）",
             f"- QQ 未入 PRTS 候选(待人工确认入 entity_corrector): **{len(suggestions)}**",
             f"- 文本回扫补挂实体: **{n_scan_added}** 处", "",
             "## docs.jsonl 回填覆盖", ""]
    for k, v in sorted(cov.items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## 同名多义示例(前20)", ""]
    for m, es in list(amb.items())[:20]:
        lines.append(f"- {m}: " + ", ".join(f"{e['canonical']}({e['type']})" for e in es))
    open("kb/entity_report.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({"mentions": len(index), "ambiguous": len(amb),
                      "suggestions": len(suggestions), "coverage": cov},
                     ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
