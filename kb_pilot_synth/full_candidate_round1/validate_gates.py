# -*- coding: utf-8 -*-
"""门控校验: 默认层不放 pending/reject、隔离规则不留肯定句、旧文档删除必须有覆盖理由、引用有效。

校验项:
  C1 分层: default 层只能有 mechanism/experiment 且非 needs_review, 且至少留 1 条肯定规则;
  C2 规则账: 肯定 + 被隔离 == 原始规则数; 被隔离规则文本不得留在肯定段; 肯定规则文本必须在正文里;
  C3 归档完整性: pending/reject/needs_review 的簇全部在 archive 且不在 default;
  C4 删除审计: kb 非 noise 文档凡被移除者, 必须能归因到
       (a) vod_entry/vod_cluster 且其簇在 default 层, 或
       (b) vod_atom 且被 default 层肯定规则引用(覆盖), 或
       (c) registry drop 隔离;
     否则记「无覆盖理由删除」违规。保留的原子必须带 retention_reason;
  C5 引用有效性: 回答的 cite_ids 必须来自其检索上下文; 且被引 fc1 必须存在于 default 层;
  C6 F05 provenance: 帧时序与计时器-12-4/12-8 的「0.5 阈值」「取整加一」不得出现在肯定段。
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PILOT = os.path.dirname(HERE)
SPECIAL = ("ctx=", "sub:", "ctx:")


def load(name):
    p = os.path.join(HERE, name)
    if not os.path.isfile(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def safe(c):
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", c)[:180]


def affirmative_section(text):
    """截取正文里 ## 规则 段(到下一个 ## 头)。"""
    out, on = [], False
    for ln in (text or "").splitlines():
        if ln.startswith("## "):
            if on:
                break
            on = ln.startswith("## 规则")
            continue
        if on:
            out.append(ln)
    return "\n".join(out)


def main():
    default = {d["cluster_id"]: d for d in load("gated_default.jsonl")}
    archive = load("gated_archive.jsonl")
    arch_cids = {d["cluster_id"] for d in archive if d.get("cluster_id")}
    kept = load("gated_old_kept.jsonl")
    kept_ids = {d["id"] for d in kept}
    cache = {}
    for fn in sorted(os.listdir(os.path.join(HERE, "cache_items"))):
        if fn.endswith(".json"):
            rec = json.load(open(os.path.join(HERE, "cache_items", fn), encoding="utf-8"))
            if not rec.get("error") and (rec.get("result") or {}).get("_text"):
                cache[rec["cluster_id"]] = rec["result"]
    v = collections.Counter()
    details = collections.defaultdict(list)

    # C1
    for cid, d in default.items():
        r = cache.get(cid) or {}
        if d.get("kind") not in ("mechanism", "experiment"):
            v["C1_non_accepted_kind_in_default"] += 1
            details["C1"].append(cid)
        if r.get("needs_review"):
            v["C1_needs_review_in_default"] += 1
            details["C1"].append(cid)
        if not d.get("affirmative_rule_idx"):
            v["C1_no_affirmative_rule"] += 1
            details["C1"].append(cid)

    # C2
    for cid, d in default.items():
        r = cache.get(cid) or {}
        rules = r.get("rules") or []
        aff = d.get("affirmative_rule_idx") or []
        gat = [g["idx"] for g in (d.get("gated_rules") or [])]
        if len(aff) + len(gat) != len(rules):
            v["C2_rule_account_mismatch"] += 1
            details["C2"].append(cid)
        sec = affirmative_section(d.get("text") or "")
        aff_texts = {(rules[i].get("text") or "").strip() for i in aff}
        for g in d.get("gated_rules") or []:
            t = (rules[g["idx"]].get("text") or "").strip()
            # 用整条规则文本判定; 若该文本本身就是另一条肯定规则(同前缀不同内容), 不算违规
            if t and t in sec and t not in aff_texts:
                # 再确认不是被同前缀的其它规则行误判
                same_prefix = [x for x in aff_texts if x and x[:40] == t[:40]]
                if not same_prefix:
                    v["C2_gated_rule_still_affirmative"] += 1
                    details["C2"].append(f"{cid}#{g['idx']}")
                else:
                    v["C2_prefix_collision_benign"] += 1
        for i in aff:
            t = (rules[i].get("text") or "")[:18]
            if t and t not in (d.get("text") or ""):
                v["C2_affirmative_rule_missing_in_text"] += 1
                details["C2"].append(f"{cid}#{i}")

    # C3
    for cid, r in cache.items():
        bad = r.get("kind") in ("pending", "reject") or r.get("needs_review")
        if bad and cid in default:
            v["C3_pending_reject_in_default"] += 1
            details["C3"].append(cid)
        if bad and cid not in arch_cids:
            v["C3_pending_reject_not_archived"] += 1
            details["C3"].append(cid)

    # C4
    cov_atoms = set()
    for cid, d in default.items():
        r = cache.get(cid) or {}
        for i in (d.get("affirmative_rule_idx") or []):
            for e in ((r.get("rules") or [{}])[i].get("evidence_atom_ids") or []):
                if not str(e).startswith(SPECIAL):
                    cov_atoms.add(str(e))
    reg = {}
    p = os.path.join(PILOT, "retest_round2/quarantine.jsonl")
    if os.path.isfile(p):
        for l in open(p, encoding="utf-8"):
            x = json.loads(l)
            reg[x["id"]] = x
    arch_ids = {d["id"] for d in archive if d.get("id")}
    all_ids, removed = [], []
    for l in open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        if d.get("status") == "noise":
            continue
        all_ids.append(d["id"])
        if d["id"] not in kept_ids and d["id"] not in arch_ids:
            removed.append(d)
    for d in removed:
        did = d["id"]
        if did in reg and reg[did].get("action") == "drop":
            v["C4_removed_registry_drop"] += 1
            continue
        if d.get("doc_type") in ("vod_entry", "vod_cluster"):
            cid = (d.get("links") or {}).get("cluster_id") or did.split(":", 1)[-1]
            if cid in default:
                v["C4_removed_cluster_covered_by_default_fc1"] += 1
                continue
        if d.get("doc_type") == "vod_atom":
            aid = did.split(":", 1)[1]
            if aid in cov_atoms:
                v["C4_removed_atom_covered_by_citation"] += 1
                continue
        v["C4_REMOVED_WITHOUT_COVERAGE"] += 1
        details["C4"].append(did)
    # 保留原子是否带 retention_reason
    for d in kept:
        if (d.get("doc_type") == "vod_atom" and "retention_reason" not in d
                and "registry_action" not in d):
            v["C4_kept_atom_without_retention_reason"] += 1
            if len(details["C4_kept"]) < 5:
                details["C4_kept"].append(d["id"])

    # C5
    for f in ("answers_old_gatedrun.jsonl", "answers_new_gated.jsonl", "answers_new_gated_archive.jsonl"):
        for r in load(f):
            for c in r.get("cite_ids") or []:
                if c not in (r.get("hit_ids") or []):
                    v["C5_cite_not_in_context"] += 1
                    details["C5"].append(f"{f}:{r['id']}:{c}")
                elif c.startswith("fc1:") and c.split(":", 1)[1] not in default:
                    v["C5_cite_fc1_not_in_default_layer"] += 1
                    details["C5"].append(f"{f}:{r['id']}:{c}")

    # C6
    for cid in ("帧时序与计时器-12-4", "帧时序与计时器-12-8"):
        d = default.get(cid)
        if not d:
            v["C6_cluster_absent_from_default"] += 1
            continue
        sec = affirmative_section(d.get("text") or "")
        if re.search(r"取整.{0,4}加一|加一帧", sec):
            v["C6_unclosed_formula_still_affirmative"] += 1
            details["C6"].append(cid + ":取整加一")
        if re.search(r"小于0\.5", sec):
            v["C6_unclosed_0.5_still_affirmative"] += 1
            details["C6"].append(cid + ":小于0.5")
        if "## 待核" not in (d.get("text") or ""):
            v["C6_no_quarantine_section"] += 1

    viol = sum(n for k, n in v.items() if "REVOMED" in k.upper() or k.split("_")[-1].startswith("y"))
    hard = {k: n for k, n in v.items() if k.startswith(("C1_", "C3_")) or k == "C4_REMOVED_WITHOUT_COVERAGE"
            or k.startswith("C5_") or k.startswith("C6_")}
    out = {"reviewer_type": "agent", "checks": dict(v.most_common()),
           "hard_violations": hard, "hard_total": sum(hard.values()),
           "details": {k: v2[:10] for k, v2 in details.items()},
           "layers": {"default": len(default), "archive": len(archive), "old_kept": len(kept),
                      "old_ids": len(all_ids), "old_removed": len(removed)}}
    json.dump(out, open(os.path.join(HERE, "gate_validation.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"checks": out["checks"], "hard_total": out["hard_total"],
                      "layers": out["layers"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
