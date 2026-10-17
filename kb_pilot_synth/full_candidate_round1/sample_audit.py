# -*- coding: utf-8 -*-
"""固定种子从全体结果抽 100 + 高风险额外样本，写出待审清单。"""
import json
import os
import random
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260920
N_RAND = 100
N_RISK = 40


def risk_flags(r):
    blob = json.dumps(r, ensure_ascii=False)
    flags = []
    if r.get("kind") == "mechanism" and r.get("scope") == "universal":
        if any(x in blob for x in ("0.05", "补整", "0.5帧", "1/10", "3/30")):
            flags.append("quarantine_pattern")
    if r.get("context_incomplete"):
        flags.append("incomplete")
    if r.get("kind") == "mechanism" and not (r.get("rules") or []):
        flags.append("empty_rules")
    if r.get("confidence") == "high" and r.get("kind") == "experiment":
        flags.append("high_on_experiment")
    rules = r.get("rules") or []
    if any(isinstance(x, dict) and not (x.get("evidence_atom_ids") or x.get("subject")) for x in rules):
        flags.append("missing_subject_or_evidence")
    return flags


def main():
    rows = [json.loads(l) for l in open(os.path.join(HERE, "synthesized_v4.jsonl"), encoding="utf-8") if l.strip()]
    rng = random.Random(SEED)
    order = list(range(len(rows)))
    rng.shuffle(order)
    rand_idx = order[: min(N_RAND, len(rows))]
    risky = [i for i, r in enumerate(rows) if risk_flags(r)]
    rng.shuffle(risky)
    extra = []
    seen = set(rand_idx)
    for i in risky:
        if i in seen:
            continue
        extra.append(i)
        if len(extra) >= N_RISK:
            break
    def dump(name, idxs, tag):
        outp = os.path.join(HERE, name)
        with open(outp, "w", encoding="utf-8") as f:
            for i in idxs:
                r = dict(rows[i])
                r["audit_bucket"] = tag
                r["risk_flags"] = risk_flags(rows[i])
                r["reviewer_type"] = "agent"
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return outp
    dump("sample_random100.jsonl", rand_idx, "random100")
    dump("sample_risk_extra.jsonl", extra, "risk_extra")
    h = hashlib.sha256(open(os.path.join(HERE, "synthesized_v4.jsonl"), "rb").read()).hexdigest()
    man = {
        "seed": SEED,
        "n_synth": len(rows),
        "n_random": len(rand_idx),
        "n_risk_pool": len(risky),
        "n_risk_extra": len(extra),
        "synth_sha256": h,
        "reviewer_type": "agent",
        "note": "随机100来自全体结果，不是只好卡。",
    }
    json.dump(man, open(os.path.join(HERE, "sample_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(man, ensure_ascii=False))


if __name__ == "__main__":
    main()
