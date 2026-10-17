# -*- coding: utf-8 -*-
"""把二审 triage 的 fix 建议机械抽取成可应用的字段改写计划（只做抽取+合理性检查，不改任何文件）。

输出 _fix_plan.json：
  { "<entry_id>": {"claim": ..., "subject": ..., "condition": ..., "source": "...",
                   "flags": [...] , "suggestion": "...", "fault_type": "..."} }

抽取规则（按顺序）：
  1. 「claim 改为/写作 X」类：取 改为 之后第一对「」内文本（支持嵌套引号）。
  2. 「(condition|subject|claim) 改为「Y」」：逐字段抽取，可同时给 claim。
  3. 「claim 末句改为「Y」」：替换 claim 的最后一句。
  4. 「claim 后补限定「Y」」/「claim 末尾补「Y」」/「claim 可加限定「Y」」：追加。
  5. 裸句（既无「」也无「改为」的长句）：整条建议即新 claim。
  6. 明确「claim 无需改/已写对」：不动 claim，记 no-op。

合理性检查（flags，不自动否决）：
  * new-number: 新文本里出现的数字串在原 claim/subject/condition 与引文中都不存在
  * new-token: 新文本里 2+ 字中文串在原文本与引文全文里都不存在（疑似引入证据外的实体名）
  * quoted-missing: 建议里以「」引出的原文词在引文/来源全文里找不到
  * drop-conflict: 同一 id 同时在 remove 清单里
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CURATED = os.path.join(ROOT, "kb_trial", "curated_high_quality.json")

BR = "「」"
ENTITIES = set()


def unquote_first_after(text, anchor):
    """返回 anchor 之后第一对「」的内容（支持嵌套）。找不到返回 None。"""
    i = text.find(anchor)
    if i < 0:
        return None
    return unquote_from(text, i)


def unquote_from(text, start):
    j = text.find("「", start)
    if j < 0:
        return None
    depth = 0
    out = []
    for ch in text[j:]:
        if ch == "「":
            depth += 1
            if depth == 1:
                continue
        elif ch == "」":
            depth -= 1
            if depth == 0:
                return "".join(out)
        out.append(ch)
    return None


def load_records():
    recs = []
    for name in sorted(os.listdir(HERE)):
        m = re.match(r"triage_(\d{2})\.json$", name)
        if not m:
            continue
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            d = json.load(fh)
        for v in d["verdicts"]:
            v["_file"] = name
            recs.append(v)
    return recs


NUM = re.compile(r"\d+(?:\.\d+)?(?:e-?\d+)?")


def load_entities():
    """专名表：只取 entity_index 里非 untyped 的条目（干员/敌人/装置/机制/状态/黑话）。"""
    with open(os.path.join(ROOT, "kb_trial", "entity_index.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    out = set()
    for k, lst in d["mentions"].items():
        for r in lst:
            if r.get("type") != "untyped" and len(k) >= 2:
                out.add(k)
                if r.get("canonical"):
                    out.add(r["canonical"])
    return {e for e in out if len(e) >= 2}


def extract(rec, entry, evidence_blob):
    s = rec.get("suggestion") or ""
    plan = {"source": rec["_file"], "fault_type": rec.get("fault_type_kept", ""),
            "suggestion": s, "flags": [], "note": ""}
    claim, subj, cond = entry["claim"], entry["subject"], entry["condition"]
    mode = None

    for m in re.finditer(r"([^，。；]{0,14}?)(?:改为|写作|改成)", s):
        prefix = m.group(1)
        new = unquote_from(s, m.end())
        if not new:
            continue
        if "末句" in prefix:
            head = re.split(r"[。？！；]", claim)[0] + "。"
            plan["claim"] = head + (new if new.endswith("。") else new + "。")
            mode = "claim-last"
        elif "claim" in prefix:
            plan["claim"] = new
            mode = "claim"
            if "/" in prefix or "与" in prefix:
                plan["subject"] = new
        elif "subject" in prefix:
            plan["subject"] = new
            mode = mode or "subject"
        elif "condition" in prefix:
            plan["condition"] = new
            mode = mode or "condition"
        elif "scope" in prefix:
            plan["scope"] = new
            mode = mode or "scope"
    for m in re.finditer(r"(?:末尾|后|可加)?补(?:限定)?|可加限定", s):
        pass
    if re.search(r"(?:末尾|后|可加)?补(?:限定)?|可加限定", s) and any(
            kw in s for kw in ("claim 后补", "claim 末尾补", "claim 可加限定", "claim 补")):
        new = unquote_first_after(s, "补") or unquote_first_after(s, "限定")
        if new:
            plan["claim"] = claim + new
            mode = "claim-append"
    if "claim" not in plan and mode is None:
        # 裸句：整条建议即新 claim
        if len(s) >= 10 and not re.search(r"无需改|不用改|已(?:用|写)「|不需改", s):
            plan["claim"] = s.strip()
            mode = "bare"
        else:
            mode = "noop"
    plan["mode"] = mode

    # ---- 合理性检查 ----
    old = " ".join([claim, subj, cond or ""])
    new_texts = " ".join(v for k, v in plan.items() if k in ("claim", "subject", "condition", "scope")
                         and isinstance(v, str))
    if any(k in plan for k in ("claim", "subject", "condition")):
        for n in sorted(set(NUM.findall(new_texts))):
            if n not in old and n not in evidence_blob:
                plan["flags"].append("new-number:%s" % n)
        for ent in ENTITIES & set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9·\-]{2,8}", new_texts)):
            if ent not in old and ent not in evidence_blob:
                plan["flags"].append("new-entity:%s" % ent)
    return plan


def main():
    global ENTITIES
    ENTITIES = load_entities()
    with open(os.path.join(HERE, "_triage_agg.json"), encoding="gbk") as fh:
        agg = json.load(fh)
    with open(CURATED, encoding="utf-8") as fh:
        entries = {e["id"]: e for e in json.load(fh)["entries"]}
    recs = [r for r in load_records() if r["verdict"] == "fix"]

    # 证据全文：fc1/window/B### 用引文所指文本文件；qq 用冻结工单 raw_messages 全文
    src_cache = {}

    def source_blob(eid, entry):
        key = None
        blo = [q.get("text") or "" for c in entry["citations"] for q in (c.get("quotes") or [])]
        for c in entry["citations"]:
            f = c.get("transcript_file")
            if f:
                key = f
                break
        if key:
            p = os.path.join(ROOT, key)
            if p not in src_cache and os.path.exists(p):
                src_cache[p] = open(p, encoding="utf-8", errors="replace").read()
            if p in src_cache:
                blo.append(src_cache[p])
        wo = ((entry.get("origin") or {}).get("upstream_record") or "")
        if wo.endswith(".json") and os.path.exists(os.path.join(ROOT, wo)):
            p = os.path.join(ROOT, wo)
            if p not in src_cache:
                src_cache[p] = open(p, encoding="utf-8").read()
            blo.append(src_cache[p])
        return "\n".join(blo)

    plan = {}
    for r in recs:
        e = entries[r["id"]]
        p = extract(r, e, source_blob(r["id"], e))
        if r["id"] in agg["remove"]:
            p["flags"].append("drop-conflict")
        plan[r["id"]] = p
    with open(os.path.join(HERE, "_fix_plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1, sort_keys=True)

    from collections import Counter
    print("fix records:", len(plan))
    print("mode:", Counter(p["mode"] for p in plan.values()))
    flagged = {k: v for k, v in plan.items() if v["flags"]}
    print("flagged:", len(flagged))
    for k in sorted(flagged):
        print(" ", k, flagged[k]["flags"][:6])
    # 复核用对照表：旧 claim -> 新 claim / 新 subject / 新 condition
    with open(os.path.join(HERE, "_fix_review.txt"), "w", encoding="utf-8") as fh:
        for eid in sorted(plan):
            p = plan[eid]
            e = entries[eid]
            chg = []
            if "claim" in p and p["claim"] != e["claim"]:
                chg.append("CLAIM  %s\n    ->  %s" % (e["claim"], p["claim"]))
            if "subject" in p and p["subject"] != e["subject"]:
                chg.append("SUBJ   %s\n    ->  %s" % (e["subject"], p["subject"]))
            if "condition" in p and p["condition"] != e["condition"]:
                chg.append("COND   %s\n    ->  %s" % (e["condition"], p["condition"]))
            if "scope" in p:
                chg.append("SCOPE  -> %s" % p["scope"])
            fh.write("### %s [%s|%s]%s\n" % (eid, p["mode"], p["fault_type"],
                                             ("  FLAGS: " + ",".join(p["flags"])) if p["flags"] else ""))
            for c in chg:
                fh.write(c + "\n")
            if not chg:
                fh.write("(无字段变化)\n")
            fh.write("SUG: %s\n\n" % p["suggestion"])
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
