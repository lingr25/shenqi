# -*- coding: utf-8 -*-
"""gate v2 校验器。硬违规必须为 0。

C1 分层        : default_v2 全部 layer=default; archive_v2 全部 layer=archive
C2 通则位收口  : default_v2 的肯定规则里不得有 scope∈{instance,example} 或 LLM 判
                 mark_unclosed/meta_discourse/bad_citation/citation_unresolvable
C3 归档纪律    : v2 里 kind∈{pending,reject} 或 needs_review 的 fc1 不得出现在 default
C4 覆盖有据    : 被判「已覆盖」而移除的旧文档必须能复算出覆盖依据
C5 引用有效性  : default_v2 的证据 id 必须是 docs.jsonl 真原子或可解析的 ctx=sub 引用
C6 F05 定向    : `帧时序与计时器-12-8` 的 0.5 阈值规则不得留在通则段
C7 残余标注    : coverage_residual.json 里的 fc1 必须有 residual_atom_ids 且互为一致
C8 共享来源    : 仍被 archive 侧 fc1 引用的旧原子不得被移除
C9 可复现      : 重跑 gate_v2 --apply --outdir _repro 后三个产物 sha256 与本目录一致
C10 输入只读   : cache_items/ 与生产 kb/docs.jsonl 的 sha256 与 inputs_sha256.json 一致
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
import gate as G  # noqa: E402
import gate_v2 as V2  # noqa: E402

BAD_LABELS = {"mark_unclosed", "meta_discourse", "bad_citation"}


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha_dir(p):
    h = hashlib.sha256()
    for fn in sorted(os.listdir(p)):
        h.update(fn.encode())
        h.update(open(os.path.join(p, fn), "rb").read())
    return h.hexdigest()


def main():
    rules, notes = [], {}
    default = [json.loads(l) for l in open(os.path.join(HERE, "gated_default_v2.jsonl"), encoding="utf-8")]
    arch = [json.loads(l) for l in open(os.path.join(HERE, "gated_archive_v2.jsonl"), encoding="utf-8")]
    kept = [json.loads(l) for l in open(os.path.join(HERE, "gated_old_kept_v2.jsonl"), encoding="utf-8")]
    residual = json.load(open(os.path.join(HERE, "coverage_residual.json"), encoding="utf-8"))
    gsum = json.load(open(os.path.join(HERE, "gate_summary_v2.json"), encoding="utf-8"))

    cache = {}
    for fn in sorted(os.listdir(os.path.join(FC1, "cache_items"))):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(FC1, "cache_items", fn), encoding="utf-8"))
        if not rec.get("error") and (rec.get("result") or {}).get("_text"):
            cache[rec["cluster_id"]] = rec
    repaired = {}
    for l in open(os.path.join(FC1, "repaired.jsonl"), encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            repaired[r["cluster_id"]] = r
    sem = {}
    for l in open(os.path.join(HERE, "semantic_repaired.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        sem[r["cluster_id"]] = r
    atoms = G.load_atoms()
    hash_index = {}
    for k in atoms:
        h = k.rsplit(":", 1)[-1]
        if re.fullmatch(r"[0-9a-f]{8}", h):
            hash_index.setdefault(h, []).append(k)
    trans = set()
    for d in ("transcripts_txt", "asr_drafts"):
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                if fn.endswith(".txt"):
                    trans.add(re.sub(r"(_asr|_asr_draft)?\.txt$", "", fn))
    fixed_cache = {}

    def fixed_result(cid):
        """与 gate_v2 同一条代码路径: repaired overlay + 引用规范化。"""
        if cid in fixed_cache:
            return fixed_cache[cid]
        base = dict(repaired.get(cid, cache[cid])["result"])
        base["rules"] = [dict(x) if isinstance(x, dict) else x
                         for x in (repaired.get(cid, cache[cid])["result"].get("rules") or [])]
        V2.fix_citations(base, trans, atoms, hash_index)
        fixed_cache[cid] = base
        return base

    # C1
    bad = [d["cluster_id"] for d in default if d.get("layer") != "default"]
    rules.append(("C1_default_layer", len(bad), bad[:5]))
    bad = [d.get("cluster_id") for d in arch if d.get("layer") != "archive"]
    rules.append(("C1_archive_layer", len(bad), bad[:5]))

    # C2 / C5
    c2, c5 = [], []
    for d in default:
        cid = d["cluster_id"]
        res = fixed_result(cid)
        labels = {x["idx"]: x["label"] for x in (sem.get(cid, {}).get("llm_labels") or [])}
        card_universal = res.get("scope") == "universal"
        for i in d.get("affirmative_rule_idx") or []:
            r = res["rules"][i] if i < len(res["rules"]) else {}
            if card_universal and (r or {}).get("scope") in ("instance", "example"):
                c2.append(f"{cid}:{i}(card=universal, rule scope={r.get('scope')})")
            if labels.get(i) in BAD_LABELS:
                c2.append(f"{cid}:{i}(label={labels.get(i)})")
        for i in d.get("gated_rules") or []:
            if str(i.get("reason", "")).startswith("citation_unresolvable"):
                if i["idx"] in (d.get("affirmative_rule_idx") or []):
                    c2.append(f"{cid}:{i['idx']}(unresolvable_in_affirmative)")
        for i in (d.get("affirmative_rule_idx") or []):
            r = res["rules"][i] if i < len(res["rules"]) else {}
            for e in (r or {}).get("evidence_atom_ids") or []:
                _rid, kind = V2.resolve_ev(e, trans, atoms, hash_index)
                if kind == "unresolvable":
                    c5.append(f"{cid}:{i} -> {e}")
    rules.append(("C2_affirmative_violations", len(c2), c2[:6]))
    rules.append(("C5_bad_citation", len(c5), c5[:6]))

    # C3
    c3 = []
    for d in default:
        cid = d["cluster_id"]
        r = repaired.get(cid, cache[cid])["result"]
        if r.get("kind") in ("pending", "reject") or r.get("needs_review"):
            c3.append(f"{cid}(kind={r.get('kind')})")
    rules.append(("C3_pending_reject_in_default", len(c3), c3[:6]))

    # C4/C6/C8: 复算覆盖
    fc1_text = {d["cluster_id"]: V2.norm(V2.cn2digit(d["text"])) for d in default}
    arch_refs = set()
    arch_cids = set()
    for d in arch:
        if d.get("source") != "cache_items":
            continue
        arch_cids.add(d["cluster_id"])
        for r in (cache[d["cluster_id"]]["result"].get("rules") or []):
            if isinstance(r, dict):
                for e in (r.get("evidence_atom_ids") or []):
                    if not str(e).startswith(G.SPECIAL_EV):
                        arch_refs.add(str(e))
    cov_atoms = set()
    for d in default:
        cid = d["cluster_id"]
        res = fixed_result(cid)
        for i in d.get("affirmative_rule_idx") or []:
            for e in (res["rules"][i] or {}).get("evidence_atom_ids") or []:
                if not str(e).startswith(G.SPECIAL_EV):
                    cov_atoms.add(str(e))
    dropped_entries, dropped_atoms = set(), set()
    kept_ids = {d.get("id") for d in kept}
    arch_ids = {d.get("id") for d in arch}
    all_old = []
    for l in open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        if d.get("status") != "noise":
            all_old.append(d)
    old_ids = {d.get("id") for d in all_old}
    dropped = old_ids - kept_ids - arch_ids
    c4, c8 = [], []
    for d in all_old:
        did = d.get("id")
        if did not in dropped:
            continue
        if d.get("doc_type") in ("vod_entry", "vod_cluster"):
            cid = (d.get("links") or {}).get("cluster_id") or did.split(":", 1)[-1]
            props = V2.entry_rules(d)
            txt = fc1_text.get(cid, "\0")
            # 用与 gate 完全相同的授权函数复算: 仅「精确包含 + 否定/数值/条件兼容」才算有据。
            # (旧版这里用 cov_ratio>=0.7 的宽松口径, 比 gate 实际执行的判据弱, 已收紧。)
            miss = [p for p in props if not V2.supersede_verdict(V2.norm(V2.cn2digit(p)), txt)["ok"]]
            if not (props and not miss and cid in fc1_text):
                c4.append(f"{did} (props={len(props)}, miss={len(miss)})")
        elif d.get("doc_type") == "vod_atom":
            aid = did.split(":", 1)[1]
            if aid in arch_refs:
                c8.append(did)
                continue
            prop = V2.norm(V2.cn2digit((d.get("text") or "").split("\n")[0]))
            covered = False
            for cid, txt in fc1_text.items():
                if aid in cov_atoms and V2.supersede_verdict(prop, txt)["ok"]:
                    covered = True
                    break
            if not covered:
                c4.append(f"{did} (atom 未获保守覆盖却被移除)")
    rules.append(("C4_removed_without_coverage", len(c4), c4[:6]))
    rules.append(("C8_shared_source_wrongly_removed", len(c8), c8[:6]))

    # C6 F05
    c6 = []
    d = next((x for x in default if x["cluster_id"] == "帧时序与计时器-12-8"), None)
    if d:
        for i in d.get("affirmative_rule_idx") or []:
            t = (cache["帧时序与计时器-12-8"]["result"]["rules"][i].get("text") or "")
            if "0.5" in t or "0.5" in str(cache["帧时序与计时器-12-8"]["result"]["rules"][i]):
                c6.append(f"帧时序与计时器-12-8:{i} -> {t[:60]}")
    else:
        c6.append("帧时序与计时器-12-8 不在 default v2")
    rules.append(("C6_F05_in_affirmative", len(c6), c6[:6]))

    # C7 残余一致
    c7 = []
    cand = {d["cluster_id"]: d for d in default}
    for cid, ids in residual.items():
        if cid not in cand:
            c7.append(f"{cid} 有残余但不在 default v2")
            continue
        got = set(cand[cid].get("residual_atom_ids") or [])
        if got != set(ids):
            c7.append(f"{cid} residual 不一致 ({len(got)} vs {len(ids)})")
    for d in default:
        if d.get("residual_atom_ids") and d["cluster_id"] not in residual:
            c7.append(f"{d['cluster_id']} 有 residual_atom_ids 但 coverage_residual.json 缺登记")
    rules.append(("C7_residual_consistency", len(c7), c7[:6]))

    # C9 可复现
    repro = os.path.join(HERE, "_repro")
    c9 = []
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "gate_v2.py"), "--apply",
                            "--outdir", repro], capture_output=True, cwd=HERE)
        if r.returncode != 0:
            c9.append("gate_v2 --outdir 重跑失败: " + r.stderr.decode("utf-8", "replace")[-200:])
        else:
            for name in ("gated_default_v2.jsonl", "gated_archive_v2.jsonl",
                         "gated_old_kept_v2.jsonl", "gate_log_v2.jsonl"):
                a = sha_file(os.path.join(HERE, name))
                b = sha_file(os.path.join(repro, name))
                if a != b:
                    c9.append(f"{name} 不可复现 {a[:12]} != {b[:12]}")
    except Exception as e:
        c9.append("repro 异常: " + str(e)[:200])
    rules.append(("C9_not_reproducible", len(c9), c9[:6]))

    # C10 输入只读
    fp = json.load(open(os.path.join(HERE, "inputs_sha256.json"), encoding="utf-8"))
    c10 = []
    if sha_dir(os.path.join(FC1, "cache_items")) != fp["fc1"]["cache_items"]["sha256"]:
        c10.append("cache_items/ 已被改动")
    for f in ("kb/docs.jsonl", "kb/synthesized.jsonl"):
        if sha_file(os.path.join(ROOT, f)) != fp["inputs"][f]["sha256"]:
            c10.append(f + " 已被改动")
    rules.append(("C10_input_mutated", len(c10), c10[:6]))

    # C11 审核覆盖层: 每条 overlay 判定必须真的落到 gated_rules 且不在 affirmative
    c11 = []
    ap = os.path.join(HERE, "audit_overlay_llm_miss.jsonl")
    if os.path.isfile(ap):
        by_cid = {}
        for d in default + arch:
            if d.get("cluster_id"):
                by_cid[d["cluster_id"]] = d
        for l in open(ap, encoding="utf-8"):
            if not l.strip():
                continue
            a = json.loads(l)
            d = by_cid.get(a["cluster_id"])
            if not d:
                c11.append(f"{a['cluster_id']}:{a['idx']}(card_missing_from_v2_output)")
                continue
            if a["idx"] in (d.get("affirmative_rule_idx") or []):
                c11.append(f"{a['cluster_id']}:{a['idx']}(overlay_but_affirmative)")
            gr = {g["idx"]: g.get("reason") for g in (d.get("gated_rules") or [])}
            if a["idx"] not in gr:
                c11.append(f"{a['cluster_id']}:{a['idx']}(overlay_but_not_gated)")
            elif not str(gr[a["idx"]]).startswith("audit_"):
                c11.append(f"{a['cluster_id']}:{a['idx']}(reason={gr[a['idx']]})")
    rules.append(("C11_audit_overlay_applied", len(c11), c11[:6]))

    # C12 registry 三分支对齐: drop 必须隔离, downweight 必须降权, keep_unknown 必须标注。
    # 这条是为第三轮真实发生过的回归加的守卫 —— gate_v2 首版漏了 downweight/keep_unknown,
    # 使第二轮已定向降权的 vod_entry:帧时序与计时器-40-13(理由「挤占 Q07 top」)被重新抬回
    # 生产权重, 原地复现了第二轮已修掉的检索挤占。
    c12 = []
    try:
        reg = V2.G.load_registry()
        downs = {k for k, v in reg.items() if v.get("action") == "downweight"}
        keeps = {k for k, v in reg.items() if v.get("action") == "keep_unknown"}
        for d in kept:
            did = d.get("id")
            if did in downs:
                if not (abs(float(d.get("retrieval_boost") or 1) - 0.15) < 1e-9
                        and abs(float(d.get("retrieval_weight") or 1) - 0.3) < 1e-9):
                    c12.append(f"{did}(downweight 未生效: boost={d.get('retrieval_boost')} "
                               f"weight={d.get('retrieval_weight')})")
            elif did in keeps:
                if not str(d.get("registry_action") or "").startswith("keep_unknown"):
                    c12.append(f"{did}(keep_unknown 未标注)")
        notes["c12_checked"] = len(downs) + len(keeps)
    except Exception as e:
        c12.append("registry 校验异常: " + str(e)[:160])
    rules.append(("C12_registry_parity", len(c12), c12[:6]))

    hard = sum(n for _k, n, _e in rules if n)
    out = {"reviewer_type": "agent", "hard_violations": hard,
           "checks": [{"check": k, "n": n, "examples": e} for k, n, e in rules],
           "n_default": len(default), "n_archive": len(arch), "n_old_kept": len(kept),
           "n_removed_old_docs": len(dropped),
           "gate_summary_reported": {"default_fc1": gsum.get("default_fc1"),
                                     "archive_fc1": gsum.get("archive_fc1"),
                                     "old_kept": gsum.get("old_kept")},
           "notes": notes}
    json.dump(out, open(os.path.join(HERE, "gate_validation_v2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for k, n, e in rules:
        print(f"{'OK ' if n == 0 else 'BAD'} {k}: {n} {e if n else ''}")
    print("HARD_VIOLATIONS", hard)
    return out


if __name__ == "__main__":
    main()
