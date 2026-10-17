# -*- coding: utf-8 -*-
"""算 E1 / I / E2 三类语义风险与 gated_default 肯定规则的实际交集 (纯本地, 不调 API)。

E1_universal_unresolved_subject : 卡级 (kind=mechanism & scope=universal & applies_to/title 含「未点名」)
I_formula_from_ctx_only          : 规则级 (规则正文含公式/取整类词, 且该规则证据全为 ctx=/sub:)
E2_advice_only_rules             : 卡级 (kind=mechanism & universal & 所有规则正文都命中建议/评价口播标记)

输出:
  - 卡级 flag 与规则级 flag 分开计数, 并给出唯一 (cluster_id, rule_idx) 集合 (去重);
  - 对每条被 flag 且进入 default 的规则, 记录是否仍在 affirmative_rule_idx (真进肯定段) 还是已被门控移入待核;
  - 记录「可能误报」候选线索 (applies_to 是否真的是占位词), 供下一步回原始上下文人工判定。
"""
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")

ADVICE_MARKERS = ("应该", "建议", "不要", "必须", "基本功", "很重要", "重要", "浪费",
                  "没意义", "意义", "价值", "性价比", "划算", "不值得", "值不值",
                  "最好", "尽量", "必须自己", "必须自己算", "要能")
FORMULA_MARKERS = ("÷", "/", "乘", "×", "公式", "取整", "加一帧", "加1帧")
SPECIAL_EV = ("ctx=", "sub:")


def load_cache():
    cache = {}
    cdir = os.path.join(FC1, "cache_items")
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
        if rec.get("error") or not (rec.get("result") or {}).get("_text"):
            continue
        cache[rec["cluster_id"]] = rec
    return cache


def load_default():
    out = {}
    p = os.path.join(FC1, "gated_default.jsonl")
    for l in open(p, encoding="utf-8"):
        d = json.loads(l)
        out[d["cluster_id"]] = d
    return out


def card_flags(res):
    f = []
    kind, scope = res.get("kind"), res.get("scope")
    rules = [x for x in (res.get("rules") or []) if isinstance(x, dict)]
    if kind == "mechanism" and scope == "universal":
        subj = (res.get("applies_to") or "") + (res.get("title") or "")
        if "未点名" in subj:
            f.append("E1")
        texts = [x.get("text") or "" for x in rules]
        if texts and all(any(m in t for m in ADVICE_MARKERS) for t in texts):
            f.append("E2")
    return f


def rule_flags(res):
    out = []
    for i, x in enumerate(res.get("rules") or []):
        if not isinstance(x, dict):
            continue
        txt = x.get("text") or ""
        ev = [str(e) for e in (x.get("evidence_atom_ids") or [])]
        if any(m in txt for m in FORMULA_MARKERS) and ev and all(e.startswith(SPECIAL_EV) for e in ev):
            out.append(i)
    return out


def main():
    cache = load_cache()
    default = load_default()
    card_hits = collections.defaultdict(list)
    unit_cases = {}          # (cid, idx) -> detail
    n_card = collections.Counter()
    for cid, rec in cache.items():
        res = rec["result"]
        cf = card_flags(res)
        for f in cf:
            card_hits[f].append(cid)
            n_card[f] += 1
        d = default.get(cid)
        aff = set(d["affirmative_rule_idx"]) if d else set()
        gated_idx = {g["idx"]: g["reason"] for g in (d["gated_rules"] if d else [])}
        # E1/E2 是卡级: 受影响规则 = 该卡的肯定规则 (E1) 或全部规则 (E2)
        if "E2" in cf:
            for i, x in enumerate(res.get("rules") or []):
                if isinstance(x, dict):
                    unit_cases[(cid, i)] = {"flag": "E2", "in_default": bool(d),
                                            "affirmative": i in aff,
                                            "gated": gated_idx.get(i),
                                            "text": x.get("text"), "ev": x.get("evidence_atom_ids")}
        if "E1" in cf:
            for i, x in enumerate(res.get("rules") or []):
                if not isinstance(x, dict):
                    continue
                key = (cid, i)
                if key in unit_cases:
                    unit_cases[key]["flag"] += "+E1"
                    continue
                unit_cases[key] = {"flag": "E1", "in_default": bool(d),
                                   "affirmative": i in aff,
                                   "gated": gated_idx.get(i),
                                   "text": x.get("text"), "ev": x.get("evidence_atom_ids")}
        for i in rule_flags(res):
            key = (cid, i)
            if key in unit_cases:
                unit_cases[key]["flag"] += "+I"
                continue
            x = res["rules"][i]
            unit_cases[key] = {"flag": "I", "in_default": bool(d),
                               "affirmative": i in aff, "gated": gated_idx.get(i),
                               "text": x.get("text"), "ev": x.get("evidence_atom_ids")}

    # ---- 统计 ----
    by_flag_units = collections.Counter()
    by_flag_affirm = collections.Counter()
    default_units = collections.Counter()
    default_affirm = collections.Counter()
    only_flag = collections.Counter()     # 出现在卡上但规则已被门控/整卡未进 default
    for (cid, i), v in unit_cases.items():
        for f in v["flag"].split("+"):
            by_flag_units[f] += 1
            if v["in_default"]:
                default_units[f] += 1
                if v["affirmative"]:
                    by_flag_affirm[f] += 1
                    default_affirm[f] += 1
            else:
                only_flag[f] += 1

    # 卡级去重
    uniq_cards = {f: len(set(v)) for f, v in card_hits.items()}
    # 卡级 ∩ default 卡
    cards_in_default = {f: len(set(v) & set(default)) for f, v in card_hits.items()}

    rows = []
    for (cid, i), v in sorted(unit_cases.items()):
        rec = cache[cid]
        res = rec["result"]
        d = default.get(cid)
        real_ev = [str(e) for e in (v.get("ev") or []) if not str(e).startswith(SPECIAL_EV)]
        rows.append({
            "cluster_id": cid, "category": rec.get("category"), "rule_idx": i,
            "flag": v["flag"], "in_gated_default": v["in_default"],
            "still_affirmative": bool(v["in_default"] and v["affirmative"]),
            "gated_reason": v["gated"], "layer": (d or {}).get("layer"),
            "applies_to": res.get("applies_to"), "title": res.get("title"),
            "kind": res.get("kind"), "scope": res.get("scope"),
            "rule_text": v.get("text"), "evidence": v.get("ev"),
            "n_real_evidence": len(real_ev), "real_evidence": real_ev,
            "n_rules": len([x for x in (res.get("rules") or []) if isinstance(x, dict)]),
            "card_all_rules_flagged": v["flag"] in ("E1", "E2") or
                                      sum(1 for (c2, _2), v2 in unit_cases.items()
                                          if c2 == cid and "I" in v2["flag"]) == len(
                                          [x for x in (res.get("rules") or []) if isinstance(x, dict)]),
        })

    out = {
        "reviewer_type": "agent",
        "n_cache_ok": len(cache),
        "n_gated_default": len(default),
        "card_level": {
            "E1_cards_on_vod": n_card.get("E1", 0),
            "E1_unique_cards": uniq_cards.get("E1", 0),
            "E1_cards_in_gated_default": cards_in_default.get("E1", 0),
            "E2_cards_on_vod": n_card.get("E2", 0),
            "E2_unique_cards": uniq_cards.get("E2", 0),
            "E2_cards_in_gated_default": cards_in_default.get("E2", 0),
        },
        "rule_level_units_flagged": dict(by_flag_units),
        "units_flagged_and_in_default": dict(default_units),
        "units_flagged_and_still_affirmative": dict(default_affirm),
        "units_flagged_but_not_in_default": dict(only_flag),
        "dedup_all_units": len(unit_cases),
        "dedup_units_flagged_and_still_affirmative": sum(
            1 for v in unit_cases.values() if v["in_default"] and v["affirmative"]),
        "dedup_units_flagged_and_in_default": sum(1 for v in unit_cases.values() if v["in_default"]),
    }
    json.dump(out, open(os.path.join(HERE, "scope_intersection.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    with open(os.path.join(HERE, "scope_units.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
