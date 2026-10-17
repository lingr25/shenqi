# -*- coding: utf-8 -*-
"""全体抽样: 2418 非 noise 候选全体, 固定种子 20260920 随机 100 + 高风险额外样本。

与 sample_audit.py 的区别: 抽样母体是**全体候选**(含 error / missing / reject /
pending / experiment), 不是只好卡。error 与 pending/reject 单独成桶, 保证被审。

产出待审清单, 逐条证据核查由代理完成 (reviewer_type=agent)。
"""
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import kb_synthesize as S  # noqa: E402

SEED = 20260920
N_RAND = 100
N_RISK = 40


def load_population():
    """全体非 noise vod_cluster, 与 run_full.load_clusters 同一顺序/口径。"""
    clusters = []
    noise_ids = set()
    with open("kb/docs.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("doc_type") == "vod_atom" and d.get("status") == "noise":
                noise_ids.add(d.get("atom_id"))
            if d.get("doc_type") == "vod_cluster" and d.get("status") != "noise":
                clusters.append(d)
    return clusters


def load_cache():
    cache_dir = os.path.join(HERE, "cache_items")
    rec = {}
    for fn in os.listdir(cache_dir):
        if not fn.endswith(".json"):
            continue
        try:
            r = json.load(open(os.path.join(cache_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        cid = r.get("cluster_id")
        if cid:
            rec[cid] = r
    return rec


def risk_flags(rec, cluster):
    f = []
    if rec is None:
        return ["missing_cache"]
    if rec.get("error"):
        return ["call_error"]
    r = rec.get("result") or {}
    blob = json.dumps(r, ensure_ascii=False)
    kind, scope = r.get("kind"), r.get("scope")
    if kind == "mechanism" and scope == "universal":
        if any(x in blob for x in ("0.05", "补整", "0.5帧", "1/10", "3/30")):
            f.append("quarantine_pattern")
    if r.get("context_incomplete"):
        f.append("incomplete")
    if kind == "mechanism" and not (r.get("rules") or []):
        f.append("empty_rules")
    if r.get("confidence") == "high" and kind != "mechanism":
        f.append("high_on_" + str(kind))
    if kind == "mechanism" and scope in ("instance", "example"):
        f.append("mech_but_narrow_scope")
    for x in r.get("rules") or []:
        if isinstance(x, dict) and not (x.get("evidence_atom_ids") or x.get("subject")):
            f.append("missing_subject_or_evidence")
            break
    if cluster.get("issue_status") == "conflict":
        f.append("conflict_issue")
    if (cluster.get("member_count") or 0) <= 1:
        f.append("single_atom")
    return f


def main():
    clusters = load_population()
    cache = load_cache()
    n = len(clusters)
    by_cid = {S._cluster_id_of(c): c for c in clusters}
    rng = random.Random(SEED)
    order = list(range(n))
    rng.shuffle(order)
    rand_idx = order[: min(N_RAND, n)]

    def rec_for(i):
        c = clusters[i]
        cid = S._cluster_id_of(c)
        return cid, c, cache.get(cid)

    def dump(name, idxs, tag, extra=None):
        outp = os.path.join(HERE, name)
        with open(outp, "w", encoding="utf-8") as f:
            for i in idxs:
                cid, c, rec = rec_for(i)
                res = (rec or {}).get("result") or {}
                row = {
                    "cluster_id": cid,
                    "doc_id": c.get("id"),
                    "category": c.get("category"),
                    "issue_status": c.get("issue_status"),
                    "member_count": c.get("member_count"),
                    "cache_status": ("error" if (rec or {}).get("error")
                                     else "missing" if rec is None else "ok"),
                    "kind": res.get("kind"),
                    "scope": res.get("scope"),
                    "confidence": res.get("confidence"),
                    "title": res.get("title"),
                    "applies_to": res.get("applies_to"),
                    "context_incomplete": res.get("context_incomplete"),
                    "rules": res.get("rules") or [],
                    "conditions": res.get("conditions") or [],
                    "exceptions": res.get("exceptions") or [],
                    "open_questions": res.get("open_questions") or [],
                    "text": res.get("_text") or "",
                    "call_error": (rec or {}).get("error"),
                    "cluster_text": (c.get("text") or "")[:1200],
                    "risk_flags": risk_flags(rec, c),
                    "audit_bucket": tag,
                    "reviewer_type": "agent",
                }
                if extra:
                    row.update(extra(i))
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return outp

    seen = set(rand_idx)
    # 高风险额外: 从全体(含 error/pending/reject)按 flag 数强到弱补齐
    flags_all = {}
    for i in range(n):
        cid, c, rec = rec_for(i)
        flags_all[i] = risk_flags(rec, c)
    err_idx = [i for i in range(n) if (rec_for(i)[2] or {}).get("error")]
    miss_idx = [i for i in range(n) if rec_for(i)[2] is None]
    pool = [i for i in range(n) if i not in seen]
    rng.shuffle(pool)
    extra = sorted(pool, key=lambda i: -len(flags_all[i]))
    extra = [i for i in extra if flags_all[i]][:N_RISK]
    seen |= set(extra)

    dump("sample_random100.jsonl", rand_idx, "random100")
    dump("sample_risk_extra.jsonl", extra, "risk_extra")
    dump("sample_errors.jsonl", err_idx, "call_error")
    dump("sample_missing.jsonl", miss_idx, "missing")

    # 分布统计(真实入审口径)
    def dist(idxs):
        st = {"ok": 0, "error": 0, "missing": 0}
        kd = {}
        istat = {}
        for i in idxs:
            cid, c, rec = rec_for(i)
            st["error" if (rec or {}).get("error") else "missing" if rec is None else "ok"] += 1
            k = ((rec or {}).get("result") or {}).get("kind") or "?"
            kd[k] = kd.get(k, 0) + 1
            iss = c.get("issue_status") or "?"
            istat[iss] = istat.get(iss, 0) + 1
        return {"status": st, "kinds": kd, "issue_status": istat}

    rand_cids = [S._cluster_id_of(clusters[i]) for i in rand_idx]
    man = {
        "seed": SEED,
        "population_n": n,
        "n_random": len(rand_idx),
        "n_risk_extra": len(extra),
        "n_error_pool": len(err_idx),
        "n_missing_pool": len(miss_idx),
        "random100_dist": dist(rand_idx),
        "risk_extra_dist": dist(extra),
        "population_kinds_all": None,
        "reviewer_type": "agent",
        "note": ("随机100来自全体候选(含 reject/pending/error), 不是优选好卡; "
                 "error/missing 全部单独入审, 不因失败而漏审。"),
    }
    json.dump(man, open(os.path.join(HERE, "sample_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(rand_cids, open(os.path.join(HERE, "sample_random100_ids.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(json.dumps(man, ensure_ascii=False))


if __name__ == "__main__":
    main()
