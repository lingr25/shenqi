# -*- coding: utf-8 -*-
"""结构诊断: 按 category 汇总 v4 缓存条目的问题类别。纯本地, 不调 API, 不写生产。

用途: 为「问题按类别定向修复」提供依据 —— 只重跑被标记的条目, 不清全量缓存。
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

UNCLOSED = ["0.05", "1/10", "3/30", "补整", "0.5帧", "0.5 帧"]


def load_cache(cache_dir):
    recs = []
    for fn in sorted(os.listdir(cache_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            recs.append(json.load(open(os.path.join(cache_dir, fn), encoding="utf-8")))
        except Exception:
            continue
    return recs


ADVICE_MARKERS = ("应该", "建议", "不要", "必须", "基本功", "很重要", "重要", "浪费",
                  "没意义", "意义", "价值", "性价比", "划算", "不值得", "值不值",
                  "最好", "尽量", "必须自己", "必须自己算", "要能")


def flags(r):
    res = r.get("result") or {}
    f = []
    kind, scope = res.get("kind"), res.get("scope")
    rules = res.get("rules") or []
    if kind == "mechanism" and not rules:
        f.append("mech_empty_rules")
    bad = 0
    for x in rules:
        if isinstance(x, dict):
            if not (x.get("subject") or "").strip():
                bad += 1
            elif not (x.get("evidence_atom_ids") or []):
                bad += 1
    if bad:
        f.append("rule_missing_subj_or_ev")
    blob = json.dumps(res, ensure_ascii=False)
    if kind == "mechanism" and scope == "universal" and any(u in blob for u in UNCLOSED):
        f.append("unclosed_as_mech")
    if kind == "mechanism" and scope in ("instance", "example"):
        f.append("A_mech_but_narrow_scope")
    if res.get("confidence") == "high" and kind != "mechanism" and scope == "universal":
        f.append("C_high_on_universal_nonmech")
    if res.get("context_incomplete"):
        f.append("D_incomplete")
    if re.search(r"QQ[:：]?\s*\d{5,}", blob):
        f.append("privacy_qq")
    # E: universal 机制主语未点名 或 规则正文含建议/评价口播标记
    if kind == "mechanism" and scope == "universal":
        subj = (res.get("applies_to") or "") + (res.get("title") or "")
        if "未点名" in subj:
            f.append("E1_universal_unresolved_subject")
        texts = [x.get("text") if isinstance(x, dict) else x for x in rules]
        if texts and all(any(m in (t or "") for m in ADVICE_MARKERS) for t in texts):
            f.append("E2_advice_only_rules")
    # I: 规则里出现公式/计算式, 但该规则的证据只有 ctx= 或 sub: 来源
    for x in rules:
        if not isinstance(x, dict):
            continue
        txt = x.get("text") or ""
        ev = x.get("evidence_atom_ids") or []
        if ("÷" in txt or "/" in txt or "乘" in txt or "×" in txt or "公式" in txt
                or "取整" in txt or "加一帧" in txt or "加1帧" in txt):
            if ev and all(str(e).startswith(("ctx=", "sub:")) for e in ev):
                f.append("I_formula_from_ctx_only")
                break
    return f


def main():
    cache_dir = os.path.join(HERE, "cache_items")
    recs = load_cache(cache_dir)
    ok = [r for r in recs if not r.get("error") and (r.get("result") or {}).get("_text")]
    err = [r for r in recs if r.get("error")]
    by_cat = collections.defaultdict(collections.Counter)
    allf = collections.Counter()
    kind_by_cat = collections.defaultdict(collections.Counter)
    conf_by_kind = collections.defaultdict(collections.Counter)
    for r in ok:
        cat = r.get("category") or "?"
        c = by_cat[cat]
        c["_n"] += 1
        kind_by_cat[cat][r["result"].get("kind")] += 1
        conf_by_kind[r["result"].get("kind")][r["result"].get("confidence")] += 1
        for x in flags(r):
            c[x] += 1
            allf[x] += 1
    rc = collections.Counter()
    for r in err:
        e = r.get("error") or ""
        rc["429" if "429" in e else ("remote_eof" if "closed" in e or "SSL" in e else e[:48])] += 1
    out = {
        "n_cache_files": len(recs),
        "n_ok": len(ok),
        "n_error": len(err),
        "flag_totals": dict(allf.most_common()),
        "error_classes": dict(rc.most_common()),
        "by_category": {
            cat: {"n": c["_n"], "kinds": dict(kind_by_cat[cat]),
                  "flags": {k: v for k, v in c.most_common() if k != "_n"}}
            for cat, c in sorted(by_cat.items(), key=lambda kv: -kv[1]["_n"])
        },
        "conf_by_kind": {k: dict(v) for k, v in conf_by_kind.items()},
        "reviewer_type": "agent",
    }
    op = os.path.join(HERE, "diagnostics.json")
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"ok": len(ok), "err": len(err),
                      "flags": out["flag_totals"], "out": op}, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
