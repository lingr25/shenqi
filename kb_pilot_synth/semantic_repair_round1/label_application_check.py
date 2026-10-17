# -*- coding: utf-8 -*-
"""校验 gate_v2 是否把每条 LLM 标签真的落到了对应段落 (按规则文本回溯, 不依赖索引重排)。

对每个被复核的 cluster:
  1. 从 cache_items 取原始 rules(按原 idx);
  2. 从 semantic_repaired.jsonl 取该卡的 LLM 标签;
  3. 从 gated_default_v2.jsonl / gated_archive_v2.jsonl 取渲染后的正文, 解析出
     每条规则落在哪个 `## ` 段落;
  4. 比对「标签 => 期望段落」与「实际段落」。
输出 label_application_check.json。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


HEAD = re.compile(r"^- (?:⚠未闭合: )?(.*?)\s*\(主语:.*$")


def sections_of(text):
    """{规范化规则头 -> 段落名}"""
    out, sect = {}, None
    for line in (text or "").split("\n"):
        if line.startswith("## "):
            sect = line[3:].strip()
            continue
        m = HEAD.match(line)
        if m:
            out.setdefault(re.sub(r"\s+", "", m.group(1))[:24], sect)
    return out


def main():
    cdir = os.path.join(FC1, "cache_items")
    cache = {}
    for fn in os.listdir(cdir):
        if fn.endswith(".json"):
            r = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
            if not r.get("error") and (r.get("result") or {}).get("_text"):
                cache[r["cluster_id"]] = r["result"]
    sem = {r["cluster_id"]: r for r in load(os.path.join(HERE, "semantic_repaired.jsonl"))}
    v2 = {}
    for f in ("gated_default_v2.jsonl", "gated_archive_v2.jsonl"):
        for x in load(os.path.join(HERE, f)):
            if x.get("cluster_id"):
                v2[x["cluster_id"]] = x

    rows, mismatch, missing = [], [], []
    for cid, s in sem.items():
        res = cache.get(cid)
        card = v2.get(cid)
        if not res or not card:
            missing.append(cid)
            continue
        secs = sections_of(card.get("text"))
        rules = res.get("rules") or []
        universal_card = res.get("scope") == "universal"
        for lab in (s.get("llm_labels") or []):
            idx, label = lab.get("idx"), lab.get("label")
            if idx is None or idx >= len(rules):
                mismatch.append({"cluster_id": cid, "idx": idx, "why": "idx_out_of_range"})
                continue
            key = re.sub(r"\s+", "", (rules[idx].get("text") or ""))[:24]
            actual = secs.get(key)
            if label in ("mark_unclosed", "meta_discourse", "bad_citation"):
                want = "待核"
            elif label == "narrow_scope":
                want = "实例" if universal_card else "规则"
            else:
                want = "规则"
            ok = actual is not None and actual.startswith(want)
            if label == "keep_rule":
                # keep_rule 只表示「LLM 未要求降级」, 不阻止确定性层的 rule_scope_instance 降级
                ok = actual is not None
            rows.append({"cluster_id": cid, "idx": idx, "label": label, "want": want,
                         "actual": actual, "ok": bool(ok)})
            if not ok:
                mismatch.append(rows[-1])
    out = {"reviewer_type": "agent", "n_checked": len(rows),
           "n_mismatch": len(mismatch), "n_missing_card": len(missing),
           "by_label": {}, "mismatches": mismatch, "rows": rows}
    for r in rows:
        d = out["by_label"].setdefault(r["label"], {"n": 0, "ok": 0})
        d["n"] += 1
        d["ok"] += 1 if r["ok"] else 0
    json.dump(out, open(os.path.join(HERE, "label_application_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in ("n_checked", "n_mismatch", "n_missing_card")},
                     ensure_ascii=False))
    print(json.dumps(out["by_label"], ensure_ascii=False))
    for m in mismatch[:12]:
        print(json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
