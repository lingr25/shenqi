# -*- coding: utf-8 -*-
"""门控分层: candidate / full archive / default accepted RAG 三分离 + provenance 定向隔离。

要点(与报告口径对应):
  1. 分层:
     - default  = 只放 kind∈{mechanism,experiment} 且非 needs_review 的 fc1 条目, 且正文里
                  没有「肯定语气」的未闭合规则;
     - archive  = pending / reject / needs_review / 规则全被隔离的条目 + 被 quarantine 的旧文档,
                  默认检索不到, 只能显式 --include-archive 取。
  2. provenance 定向隔离(不做关键词全局杀):
     - G1 规则的证据原子在 retest_round2/quarantine.jsonl 的 drop 名单里;
     - G2 规则无真实原子(只有 ctx=/sub:)且断言数值/公式;
     - G3 规则断言数值/公式且其全部真实原子都落在「已声明未闭合」的 provenance family 视频里
          (family 只取 evidence_round1 中 rag_gate=false 的 er1 记录);
     - 不采用 `参数: X=N无` 作为门控信号: 实测命中 1553 个原子(泛指「材料未给单位」的通用约定),
       用它门控等于关键词全局误杀, 故仅记录为 rejected_signal。
  3. 旧文档保留(coverage 审核):
     - 旧 vod_entry/vod_cluster 仅当同 cid 有 **default** fc1 时才移除; 只有 archive fc1 则保留;
     - 旧 vod_atom 仅当该原子 id 被 default fc1 的**肯定规则**引用(覆盖)时才移除;
       仅「同簇」不算覆盖 -> retained_shared_cluster_only;
     - registry drop -> quarantine; downweight/keep_unknown -> 保留并降权/标注。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PILOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

REG_PATH = os.path.join(PILOT, "retest_round2/quarantine.jsonl")
ER1_DIR = os.path.join(PILOT, "evidence_round1")
THRESH = re.compile(r"小于|大于|取整|加一|加1|补整|四舍五入|除以|倍|阈值|换算|下取|上取")
VID = re.compile(r"(BV[0-9A-Za-z]+_p\d+_\d+)")
SPECIAL_EV = ("ctx=", "sub:", "ctx:")


def safe(c):
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", c)[:180]


def load_registry():
    reg = {}
    if os.path.isfile(REG_PATH):
        for l in open(REG_PATH, encoding="utf-8"):
            r = json.loads(l)
            reg[r["id"]] = r
    return reg


def family_videos():
    """provenance family: 由 registry 的 supersedes_by(er1 id) + er1 记录自身证据文件反查视频。"""
    import ast
    recs = {}
    for f in ("mechanisms.jsonl", "experiments.jsonl"):
        p = os.path.join(ER1_DIR, f)
        if not os.path.isfile(p):
            continue
        for l in open(p, encoding="utf-8"):
            m = json.loads(l)
            recs[m["id"]] = m
    fam = collections.defaultdict(set)
    for rid, r in load_registry().items():
        for s in r.get("supersedes_by") or []:
            if not s.startswith("er1:"):
                continue
            eid = s[4:]
            m = VID.search(rid)
            if m:
                fam[eid].add(m.group(1))
            rec = recs.get(eid)
            if rec:
                try:
                    for e in ast.literal_eval(rec["evidence"]):
                        mm = VID.search(str(e.get("file") or ""))
                        if mm:
                            fam[eid].add(mm.group(1))
                except Exception:
                    pass
    unclosed = {k: v for k, v in fam.items()
                if recs.get(k) and not recs[k].get("rag_gate")
                and recs[k].get("eligibility") in ("needs_av", "context_only")}
    return fam, unclosed, recs


def load_atoms():
    """atom id -> 文档文本, 用于定位视频与 registry 命中。"""
    atoms = {}
    with open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("doc_type") == "vod_atom":
                atoms[d["id"].split(":", 1)[1]] = d
    return atoms


def classify_rules(res, drops, unclosed_videos, atoms):
    """逐规则判 -> (affirmative_idx, gated[list of (i, reason)])"""
    keep, gated = [], []
    for i, r in enumerate(res.get("rules") or []):
        if not isinstance(r, dict):
            continue
        txt = r.get("text") or ""
        ev = [str(e) for e in (r.get("evidence_atom_ids") or [])]
        real = [e for e in ev if not e.startswith(SPECIAL_EV)]
        hit_drop = [e for e in real if f"vod_atom:{e}" in drops]
        reason = None
        if hit_drop:
            reason = f"atom_registry_drop:{hit_drop[0]}"
        elif not real:
            reason = "ctx_only_evidence"
        elif THRESH.search(txt):
            vids = set()
            for e in real:
                a = atoms.get(e)
                m = VID.search(e) or (VID.search(a.get("id") or "") if a else None)
                if m:
                    vids.add(m.group(1))
            fams = sorted({f for f, vs in unclosed_videos.items() if vids and vids <= vs})
            if vids and fams:
                reason = "unclosed_family:" + ",".join(fams)
        if reason:
            gated.append((i, reason))
        else:
            keep.append(i)
    return keep, gated


def rebuild_text(text, res, gated_idx):
    """把被隔离的规则行从 ## 规则 段搬进新增的 ## 待核(provenance 隔离) 段。"""
    lines = (text or "").splitlines()
    move, missed = [], []
    used = set()
    for i, reason in gated_idx:
        t = ((res.get("rules") or [{}])[i] or {}).get("text") or ""
        probe = t.replace("\n", " ").strip()
        hit = None
        for cand in (probe, probe[:40], probe[:18]):
            if not cand:
                continue
            for j, ln in enumerate(lines):
                if j in used or not ln.startswith("- "):
                    continue
                if cand in ln:
                    hit = j
                    break
            if hit is not None:
                break
        if hit is None:
            missed.append((i, reason))
        else:
            used.add(hit)
            move.append((hit, t, reason))
    if not move:
        return text, len(gated_idx), missed
    out, drop_lines = [], {h for h, _, _ in move}
    for j, ln in enumerate(lines):
        if j not in drop_lines:
            out.append(ln)
    sec = ["", "## 待核(provenance 隔离, 不得当已知)"]
    for _, t, reason in sorted(move):
        sec.append(f"- ⚠未闭合: {t}  [门控:{reason}]")
    ins = len(out)
    for j, ln in enumerate(out):
        if ln.startswith("## 条件") or ln.startswith("## 待验证"):
            ins = j
            break
    out = out[:ins] + sec + out[ins:]
    return "\n".join(out), len(move), missed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    reg = load_registry()
    drops = {k for k, v in reg.items() if v.get("action") == "drop"}
    downs = {k for k, v in reg.items() if v.get("action") == "downweight"}
    keeps = {k for k, v in reg.items() if v.get("action") == "keep_unknown"}
    _, unclosed, _ = family_videos()
    atoms = load_atoms()
    # repaired overlay 优先
    repaired = {}
    p = os.path.join(HERE, "repaired.jsonl")
    if os.path.isfile(p):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                repaired[r["cluster_id"]] = r
    cache, fc1, arch, glog = {}, {}, [], []
    cdir = os.path.join(HERE, "cache_items")
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
        if rec.get("error") or not (rec.get("result") or {}).get("_text"):
            continue
        cid = rec["cluster_id"]
        cache[cid] = repaired.get(cid, rec)
    gate_stats = collections.Counter()
    for cid, rec in cache.items():
        res = dict(rec["result"])
        kind = res.get("kind")
        base = {"id": "fc1:" + cid, "cluster_id": cid, "source": "cache_items",
                "layer": "archive"}
        if kind in ("pending", "reject"):
            base["archive_reason"] = f"kind_{kind}"
            base["text"] = res["_text"]
            arch.append(base)
            gate_stats[f"archive_kind_{kind}"] += 1
            continue
        if res.get("needs_review"):
            base["archive_reason"] = "needs_review(代理判 severe)"
            base["text"] = res["_text"]
            arch.append(base)
            gate_stats["archive_needs_review"] += 1
            continue
        keep_i, gated = classify_rules(res, drops, unclosed, atoms)
        new_text, moved, missed = rebuild_text(res["_text"], res, gated)
        for i, reason in gated:
            gate_stats["gate_" + reason.split(":")[0]] += 1
        if missed:
            gate_stats["gate_line_not_found"] += len(missed)
        doc = dict(base)
        doc["layer"] = "default"
        doc["doc_type"] = "pilot_v4_entry"
        doc["track"] = "vod_official"
        doc["status"] = "draft"
        doc["kind"] = kind
        doc["scope"] = res.get("scope")
        doc["confidence"] = res.get("confidence")
        doc["context_incomplete"] = bool(res.get("context_incomplete"))
        doc["affirmative_rule_idx"] = keep_i
        doc["gated_rules"] = [{"idx": i, "reason": r} for i, r in gated]
        doc["retrieval_boost"] = (1.5 if (kind == "mechanism" and res.get("scope") == "universal"
                                          and not gated) else 1.1)
        if kind == "experiment" or res.get("scope") in ("instance", "example"):
            doc["retrieval_boost"] = 0.85
        doc["retrieval_weight"] = 1.0
        doc["text"] = new_text
        if not keep_i:
            doc["layer"] = "archive"
            doc["archive_reason"] = "all_rules_gated"
            arch.append(doc)
            gate_stats["archive_all_rules_gated"] += 1
        else:
            fc1[cid] = doc
        glog.append({"cluster_id": cid, "layer": doc["layer"], "kind": kind,
                     "n_rules": len(res.get("rules") or []), "n_affirmative": len(keep_i),
                     "gated": doc["gated_rules"], "reason": doc.get("archive_reason")})
    # 旧文档: coverage 审核
    cov_atoms = set()
    for cid, doc in fc1.items():
        res = cache[cid]["result"]
        keep_i = set(doc["affirmative_rule_idx"])
        for i in keep_i:
            for e in (res["rules"][i].get("evidence_atom_ids") or []):
                if not str(e).startswith(SPECIAL_EV):
                    cov_atoms.add(str(e))
    cov_clusters = set(fc1)
    arch_clusters = {d["cluster_id"] for d in arch if d["source"] == "cache_items"}
    old_keep, old_arch = [], []
    cov = collections.Counter()
    with open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("status") == "noise":
                continue
            did = d.get("id") or ""
            if did in drops:
                d = dict(d)
                d["layer"] = "archive"
                d["archive_reason"] = "registry_drop: " + (reg[did].get("reason") or "")[:80]
                old_arch.append(d)
                cov["old_quarantined_registry_drop"] += 1
                continue
            if did in downs:
                d = dict(d)
                d["retrieval_boost"] = 0.15
                d["retrieval_weight"] = 0.3
                d["registry_action"] = "downweight: " + (reg[did].get("reason") or "")[:80]
                old_keep.append(d)
                cov["old_downweighted"] += 1
                continue
            if did in keeps:
                d = dict(d)
                d["registry_action"] = "keep_unknown: " + (reg[did].get("reason") or "")[:80]
                old_keep.append(d)
                cov["old_keep_unknown"] += 1
                continue
            if d.get("doc_type") in ("vod_entry", "vod_cluster"):
                cid = (d.get("links") or {}).get("cluster_id") or did.split(":", 1)[-1]
                if cid in cov_clusters:
                    cov["old_removed_covered_by_default_fc1"] += 1
                    continue
                if cid in arch_clusters:
                    d = dict(d)
                    d["retention_reason"] = "fc1_只有 archive 层(pending/reject/needs_review), 未可靠替代"
                    old_keep.append(d)
                    cov["old_retained_fc1_not_default"] += 1
                    continue
                old_keep.append(d)
                cov["old_retained_no_fc1"] += 1
                continue
            if d.get("doc_type") == "vod_atom":
                aid = did.split(":", 1)[1]
                if aid in cov_atoms:
                    cov["old_atom_removed_covered_by_citation"] += 1
                    continue
                d = dict(d)
                if aid.split(":")[0] in arch_clusters or any(
                        aid in (cache[c]["result"].get("_text") or "") for c in ()):
                    d["retention_reason"] = "同簇但未被 default 肯定规则引用(shared-cluster 不算覆盖)"
                d["retention_reason"] = "未被 default fc1 肯定规则引用; 保留旧证据"
                old_keep.append(d)
                cov["old_atom_retained_shared_cluster_only"] += 1
                continue
            old_keep.append(d)
            cov["other_docs_untouched"] += 1
    out = {
        "reviewer_type": "agent",
        "n_cache_ok": len(cache),
        "default_fc1": len(fc1), "archive_fc1": len(arch),
        "old_kept": len(old_keep), "old_archived": len(old_arch),
        "gate_stats": dict(gate_stats.most_common()),
        "coverage": dict(cov.most_common()),
        "registry": {"drop": len(drops), "downweight": len(downs), "keep_unknown": len(keeps)},
        "unclosed_families": {k: sorted(v) for k, v in unclosed.items()},
        "rejected_signal": {
            "pattern": "参数: X=N无",
            "matched_atoms": 1553,
            "why_rejected": "这是抽取消歧的通用约定(材料未给单位), 覆盖 12% 原子, 用作门控等于关键词全局误杀",
        },
        "dry_run": args.dry_run,
    }
    if not args.dry_run:
        with open(os.path.join(HERE, "gated_default.jsonl"), "w", encoding="utf-8") as f:
            for cid, doc in fc1.items():
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        with open(os.path.join(HERE, "gated_archive.jsonl"), "w", encoding="utf-8") as f:
            for doc in arch + old_arch:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        with open(os.path.join(HERE, "gated_old_kept.jsonl"), "w", encoding="utf-8") as f:
            for doc in old_keep:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        with open(os.path.join(HERE, "gate_log.jsonl"), "w", encoding="utf-8") as f:
            for r in glog:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(out, open(os.path.join(HERE, "gate_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False)[:1400])


if __name__ == "__main__":
    main()
