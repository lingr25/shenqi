# -*- coding: utf-8 -*-
"""纯本地: 比较三种配额模式(all / layer_only / off)下 top-k 与 ctx, 零 LLM 调用。

目的: 证实 `all` 模式会把 gold 的独立证据卡当作同簇重复挤掉, 而 `layer_only` 不会,
同时不破坏 X07 需要的 on-point 原子。
"""
import json
import os

import trial_rag_v3 as V
import trial_rag as T

HERE = os.path.dirname(os.path.abspath(__file__))
QS = {q["id"]: q for q in V.load(V.QF)}
WATCH = ["X07", "F04", "F05", "F06", "N07", "N08", "N09", "N02", "N03", "N05",
         "X11", "X14", "R05", "N11"]
WS = os.path.join(HERE, "quota_check_watch.json")

ANCHORS = {
    # 只保留可证实的锚点: 被 all 模式挤掉的 gold 独立证据卡
    "F04": ["B074-imbalance-speed-separate"],
    "F06": ["B036-path-not-wallhack"],
}

CLUSTER_MAP = {}


def build_cluster_map(docs):
    for d in docs:
        did = str(d.get("id") or "").replace("er1:", "")
        st = set()
        if d.get("cluster_id"):
            st.add(d["cluster_id"])
        for c in ((d.get("links") or {}).get("cluster_ids") or []):
            st.add(c)
        CLUSTER_MAP[did] = st


def clusters_of(gid):
    g = gid.replace("er1:", "")
    st = set(CLUSTER_MAP.get(g) or [])
    for pre in ("fc1:", "vod_entry:", "vod_cluster:"):
        if g.startswith(pre):
            st.add(g[len(pre):])
    return st


def family_hit(q, hits):
    """更公平的「信息是否可用」代理:
       gold 文档本身进 top-k, 或与 gold 同簇的**任何**文档进 top-k。
       (原始 retrieval_metrics.hit_gold_cluster 忘了剥 fc1:/vod_entry: 前缀, 恒为 0, 不可用。)
    """
    ids = [h["id"].replace("er1:", "") for h in hits]
    cids = {h.get("cluster_id") for h in hits if h.get("cluster_id")}
    for g in (q.get("gold_ids") or []):
        if g in ids:
            return True, g, "gold_id"
        if clusters_of(g) & cids:
            return True, g, "gold_cluster"
    return False, (q.get("gold_ids") or [None])[0], "miss"


def analyze(idx, qid, mode):
    q = QS[qid]
    hits = V.search_quota(idx, q["q"], mode=mode)
    ctx, used, nc = T.pack_ctx(hits)
    ok, gid, how = family_hit(q, hits)
    return {"top6": used,
            "clusters": [h.get("cluster_id") for h in hits],
            "ctx_chars": nc, "ctx_sig": V.ctx_sig(ctx),
            "gold_family_hit": ok, "gold_id": gid, "gold_hit_kind": how,
            "gold_clusters": sorted(clusters_of(gid or ""))}


def gold_hit(qid, used):
    q = QS[qid]
    want = set(q.get("gold_ids") or [])
    return sorted(want & set(used)), sorted(want - set(used))


def main():
    out = {"reviewer_type": "agent", "note": "纯本地, 零 LLM", "modes": {}, "gold_compare": {}}
    corpora = {"old_gated_v1": V.corpus("old_gated_v1"), "new_gated_v3": V.corpus("new_gated_v3")}
    idxs = {s: T.Index(d) for s, d in corpora.items()}
    build_cluster_map(corpora["old_gated_v1"] + corpora["new_gated_v3"])
    allq = [q["id"] for q in V.load(V.QF)]
    for mode in ("all", "layer_only", "off"):
        out["modes"][mode] = {}
        for side, idx in idxs.items():
            out["modes"][mode][side] = {qid: analyze(idx, qid, mode) for qid in allq}
    # 锚点断言
    checks = []
    for qid, anchors in ANCHORS.items():
        for side in ("old_gated_v1", "new_gated_v3"):
            for mode in ("all", "layer_only", "off"):
                got = out["modes"][mode][side][qid]["top6"]
                for a in anchors:
                    checks.append({"qid": qid, "side": side, "mode": mode, "anchor": a,
                                   "in_topk": a in got})
    # 汇总
    out["summary"] = {}
    for side in corpora:
        for mode in ("all", "layer_only", "off"):
            rows = out["modes"][mode][side]
            fam = sum(1 for r in rows.values() if r["gold_family_hit"])
            out["summary"].setdefault(side, {})[mode] = {
                "n_q": len(rows),
                "n_gold_family_hit": fam,
                "n_gold_id_miss": [k for k, r in rows.items() if not r["gold_family_hit"]],
                "n_gold_family_via_sibling": sum(1 for r in rows.values()
                                                 if r["gold_hit_kind"] == "gold_cluster"),
            }
    # 与 v3(all) 的 ctx 差异: 决定哪些题需要重调 LLM
    diffs = {}
    for side in corpora:
        for mode in ("layer_only", "off"):
            d = [qid for qid in allq
                 if out["modes"][mode][side][qid]["ctx_sig"]
                 != out["modes"]["all"][side][qid]["ctx_sig"]]
            diffs.setdefault(side, {})[mode] = {"n_ctx_changed_vs_v3all": len(d), "qids": d}
    out["ctx_diff_vs_v3all"] = diffs
    out["anchor_checks"] = checks
    out["verdict"] = {
        "all_breaks_gold": [c for c in checks if c["mode"] == "all" and not c["in_topk"]],
        "layer_only_breaks_gold": [c for c in checks if c["mode"] == "layer_only" and not c["in_topk"]],
        "off_breaks_gold": [c for c in checks if c["mode"] == "off" and not c["in_topk"]],
    }
    json.dump(out, open(os.path.join(HERE, "quota_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    brief = {
        "anchor_checks": {m: sum(1 for c in checks if c["mode"] == m and c["in_topk"])
                          for m in ("all", "layer_only", "off")},
        "anchor_checks_total": sum(1 for c in checks if c["mode"] == "all"),
        "summary": {s: {m: {"n_gold_family_hit": v["n_gold_family_hit"],
                            "via_sibling": v["n_gold_family_via_sibling"],
                            "n_miss": len(v["n_gold_id_miss"]), "miss": v["n_gold_id_miss"]}
                        for m, v in out["summary"][s].items()} for s in out["summary"]},
        "ctx_diff_vs_v3all": {s: {m: v["n_ctx_changed_vs_v3all"]
                                  for m, v in out["ctx_diff_vs_v3all"][s].items()}
                              for s in out["ctx_diff_vs_v3all"]},
    }
    print(json.dumps(brief, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
