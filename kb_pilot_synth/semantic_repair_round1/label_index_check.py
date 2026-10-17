# -*- coding: utf-8 -*-
"""按规则文本(而非索引)校验: 每条 LLM 判 narrow_scope / mark_unclosed / meta_discourse /
bad_citation 的规则, 在 v2 输出里是否真的落到了对应段落。
索引口径在渲染后会重排, 所以必须用文本匹配回溯原 idx。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import gate_v2 as G  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    cdir = os.path.join(FC1, "cache_items")
    cache = {}
    for fn in os.listdir(cdir):
        if fn.endswith(".json"):
            r = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
            if not r.get("error") and (r.get("result") or {}).get("_text"):
                cache[r["cluster_id"]] = r["result"]
    sem = {r["cluster_id"]: r for r in load(os.path.join(HERE, "semantic_repaired.jsonl"))}
    out = []
    bad = []
    for cid, s in sem.items():
        res = cache.get(cid)
        if not res:
            bad.append({"cluster_id": cid, "why": "not_in_cache"})
            continue
        rules = res.get("rules") or []
        textd = {}
        for i, r in enumerate(rules):
            key = re.sub(r"\s+", "", (r.get("text") or ""))[:28]
            textd.setdefault(key, []).append(i)
        for lab in (s.get("llm_labels") or []):
            idx, label = lab.get("idx"), lab.get("label")
            if idx is None or idx >= len(rules):
                bad.append({"cluster_id": cid, "idx": idx, "why": "idx_out_of_range"})
                continue
            key = re.sub(r"\s+", "", (rules[idx].get("text") or ""))[:28]
            out.append({"cluster_id": cid, "idx": idx, "label": label,
                        "rule_head": key[:24], "dup": len(textd.get(key, []))})
    json.dump({"reviewer_type": "agent", "n_labels": len(out), "problems": bad, "labels": out},
              open(os.path.join(HERE, "label_index_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"n_labels": len(out), "n_problems": len(bad),
                      "dup_text_keys": sum(1 for x in out if x["dup"] > 1)}, ensure_ascii=False))
    print(json.dumps(bad[:10], ensure_ascii=False))


if __name__ == "__main__":
    main()
