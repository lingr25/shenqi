# -*- coding: utf-8 -*-
"""repaired overlay 之后的真实 kind 统计 + 抽样判定分桶(不混算随机准确率) + 修复口径拆账。

口径:
  - pre  = cache_items/ 原始 LLM 输出 (合成当时)
  - post = repaired.jsonl overlay 叠加之后 (2716 只有补丁的以 overlay 为准)
  - flag 类 (E1/E2/I) 只登记不改正文, 必须与「实际字段改动」分开报。
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diagnose as D  # noqa: E402


def safe(c):
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", c)[:180]


def main():
    cache = {}
    for fn in sorted(os.listdir(os.path.join(HERE, "cache_items"))):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(HERE, "cache_items", fn), encoding="utf-8"))
        if rec.get("error") or not (rec.get("result") or {}).get("_text"):
            continue
        cache[rec["cluster_id"]] = rec
    repaired = {}
    p = os.path.join(HERE, "repaired.jsonl")
    if os.path.isfile(p):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                repaired[r["cluster_id"]] = r
    post = dict(cache)
    post.update(repaired)

    pre_kinds = collections.Counter(r["result"].get("kind") for r in cache.values())
    post_kinds = collections.Counter(r["result"].get("kind") for r in post.values())
    pre_scope = collections.Counter((r["result"].get("kind"), r["result"].get("scope"))
                                    for r in cache.values())
    post_scope = collections.Counter((r["result"].get("kind"), r["result"].get("scope"))
                                     for r in post.values())
    pre_conf = collections.Counter(r["result"].get("confidence") for r in cache.values())
    post_conf = collections.Counter(r["result"].get("confidence") for r in post.values())
    # 默认语料可用性 (kind=mechanism & universal & 非 needs_review)
    def defaultable(r):
        res = r["result"]
        return (res.get("kind") == "mechanism" and res.get("scope") == "universal"
                and not res.get("needs_review"))
    n_def_pre = sum(1 for r in cache.values() if defaultable(r))
    n_def_post = sum(1 for r in post.values() if defaultable(r))

    # 修复拆账: flags-only vs 实际字段改动
    n_flag_only = 0
    field_changes = collections.Counter()
    cat_field = collections.Counter()
    for l in open(os.path.join(HERE, "repair_log.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        ch = d.get("changes") or []
        if not ch:
            n_flag_only += 1
        for c in ch:
            field_changes[f"{c.get('field')}: {c.get('from')} -> {c.get('to')}"] += 1
            cat_field[",".join(d.get("categories") or [])] += 1
    n_logged = sum(1 for _ in open(os.path.join(HERE, "repair_log.jsonl"), encoding="utf-8"))

    # 抽样判定: random100 / risk_extra 分开, pre/post 整改各报
    buckets = collections.defaultdict(collections.Counter)
    sev_by_bucket = collections.defaultdict(list)
    over_by_bucket = collections.defaultdict(list)
    for l in open(os.path.join(HERE, "audit_verdicts.jsonl"), encoding="utf-8"):
        v = json.loads(l)
        b = v["bucket"]
        buckets[b][v["verdict"]] += 1
        buckets[b]["_n"] += 1
        if v.get("severe"):
            sev_by_bucket[b].append(v["cluster_id"])
        if str(v.get("verdict") or "").startswith("over_claim"):
            over_by_bucket[b].append(v["cluster_id"])
    remediated = set()
    for b, ids in sev_by_bucket.items():
        remediated.update(ids)
    for b, ids in over_by_bucket.items():
        remediated.update(ids)
    post_kind_of_severe = {cid: (post.get(cid, {}).get("result") or {}).get("kind")
                           for cid in sorted(remediated)}

    diag = D.flags
    out = {
        "reviewer_type": "agent",
        "n_ok": len(cache),
        "kinds_pre": dict(pre_kinds),
        "kinds_post": dict(post_kinds),
        "scope_pre": {f"{k[0]}/{k[1]}": v for k, v in pre_scope.most_common()},
        "scope_post": {f"{k[0]}/{k[1]}": v for k, v in post_scope.most_common()},
        "confidence_pre": dict(pre_conf),
        "confidence_post": dict(post_conf),
        "default_releasable_pre": n_def_pre,
        "default_releasable_post": n_def_post,
        "repair_accounting": {
            "n_logged_records": n_logged,
            "n_flag_only_no_field_change": n_flag_only,
            "n_with_field_change": n_logged - n_flag_only,
            "field_changes": dict(field_changes.most_common()),
            "note": "1515 是「被标记记录数」, 不等于字段改动数; flags-only 记录只登记不改正文",
        },
        "audit_by_bucket": {b: dict(c) for b, c in buckets.items()},
        "severe_pre_by_bucket": {b: ids for b, ids in sev_by_bucket.items()},
        "over_claim_pre_by_bucket": {b: ids for b, ids in over_by_bucket.items()},
        "severe_post": {"n": len(post_kind_of_severe),
                        "kind_after_remediation": post_kind_of_severe},
        "note_accuracy": ("random100 与 risk_extra 是两套不同抽样口径: random100 可代表全体候选"
                          "(含 reject/pending), risk_extra 是刻意挑选的问题富集桶, 二者不得相加当准确率; "
                          "n=100 的外推区间宽, 报告中不得表述为全库正确率。"),
    }
    json.dump(out, open(os.path.join(HERE, "postrepair_stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in ("kinds_pre", "kinds_post", "default_releasable_pre",
                                          "default_releasable_post", "repair_accounting",
                                          "severe_pre_by_bucket", "sev_post"
                                          if False else "severe_post")},
                     ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
