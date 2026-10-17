# -*- coding: utf-8 -*-
"""gate v2: 在 v1 分层之上加四件事。

新增:
  1. 引用修复:
     - `sub:<stem>:<sec>` (丢前缀) -> `ctx=sub:<stem>:<sec>`;
     - 短格式漂移原子 id `<stem>:a<n>:<hash>` -> 在同 stem 的 docs.jsonl 原子里唯一找回;
       找不回 -> 该规则进待核 (reason `citation_unresolvable`)。
  2. **通则位收口**: default 层只准放通则语义。规则自身 scope∈{instance,example} 或
     LLM 复核判 narrow_scope -> 移入 `## 实例佐证(非通则)`;LLM 判 mark_unclosed /
     meta_discourse / bad_citation -> 移入 `## 待核`;两者都不再进 affirmative_rule_idx。
  3. **命题级覆盖**: 旧 vod_entry/vod_cluster/vod_atom 只有在「同簇有 default v2 fc1」且
     「其全部命题行在 fc1 正文里被完整复述」时才移除;只被 cited、正文没有完整复述 -> 保留旧文档
     并标 `retention_reason=部分覆盖`, 在 fc1 上记 `residual_atom_ids` (残余)。
  4. **共享来源保护**: 同一原子若还被 archive 侧 fc1 引用, 一律保留, 不因 default 侧覆盖而删。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)
sys.path.insert(0, FC1)
import gate as G  # noqa: E402

PUNCT = "，。、；：（）「」『』“”\"'‘’!！?,.;:;()[]{}<>《》—–-· \t\n"

DEMOTE = {"rule_scope_instance", "llm_narrow_scope"}
TOPENDING = {"llm_mark_unclosed", "llm_meta_discourse", "llm_bad_citation",
             "citation_unresolvable"}


def norm(s):
    s = s or ""
    for ch in PUNCT:
        s = s.replace(ch, "")
    return s


def cn2digit(s):
    m = {"零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6",
         "七": "7", "八": "8", "九": "9", "十": "10", "两": "2"}
    return "".join(m.get(c, c) for c in s)


COV_THR = 0.7   # 命题级覆盖阈值: 旧命题的字符二元组有 >=70% 出现在 fc1 正文里算被复述


def _bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)}


_BG = {}


def cov_bg(txt):
    if txt not in _BG:
        _BG[txt] = _bigrams(txt)
    return _BG[txt]


def cov_ratio(prop, txt):
    """旧命题被 fc1 正文复述的比例(字符二元组覆盖)。精确包含 -> 1.0。

    注意: 这只是**字符相似度**, 不是语义蕴涵。相同字符可以表达相反命题
    (否定、数值、条件不同), 因此 cov_ratio 只用于**找候选**, 绝不能单独授权删除。
    授权删除走 supersede_verdict()。
    """
    if not prop:
        return 1.0
    if prop in txt:
        return 1.0
    p = _bigrams(prop)
    if not p:
        return 1.0
    return len(p & cov_bg(txt)) / len(p)


# ---- 保守覆盖判定: 精确包含 + 否定/数值/条件兼容, 否则一律只作候选不删 ----

_NEG_PRE = ("不", "没", "未", "非", "无", "别", "勿", "难道", "并非")
_NEG_POST = ("不成立", "是错的", "不对", "为假", "不存在")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_COND_CUES = ("时", "如果", "若", "当", "条件", "仅在", "只有", "一旦", "情况下")


def prop_nums(s):
    return set(_NUM_RE.findall(s or ""))


def prop_conds(s):
    return [c for c in _COND_CUES if c in (s or "")]


def polarity_ok(prop, txt):
    """精确包含的前提下, 检查匹配位置附近有没有把命题翻转掉的否定线索。

    例: 命题「阻挡帧立刻归零」出现在正文「…不能理解成阻挡帧立刻归零」里 → 翻转, 拒绝。
    前缀窗口取 6 字: 中文否定常附着在谓语前(「不能理解成」「不需要」), 但偶尔隔一个词,
    窗口太窄会漏(实测 4 字窗口漏掉「不能理解成」)。宁可多拒(保守保留旧证据), 不可错删——
    代价是「非寻路针时避障不会触发」这类**条件短语**也会被拦, 属保守方向的假阳性, 已实测计数
    (cov_rejected_by_guard), 不为省库容而放宽。
    """
    i = txt.find(prop)
    if i < 0:
        return False, "no_exact_match"
    pre = txt[max(0, i - 6):i]
    for cue in _NEG_PRE:
        if cue in pre:
            return False, f"negation_prefix:{cue}"
    post = txt[i + len(prop): i + len(prop) + 6]
    for cue in _NEG_POST:
        if post.startswith(cue):
            return False, f"negation_postfix:{cue}"
    return True, "ok"


def supersede_verdict(prop, txt):
    """是否允许因覆盖而删除旧文档。

    只有「旧命题是 fc1 正文的精确子串」且否定/数值/条件全部兼容才返回 ok=True。
    近似命中(相似度再高)一律 ok=False, 只登记为候选。
    """
    if not prop:
        return {"ok": True, "mode": "empty", "ratio": 1.0, "blockers": []}
    if prop in txt:
        ok, why = polarity_ok(prop, txt)
        return {"ok": ok, "mode": "exact", "ratio": 1.0,
                "blockers": [] if ok else [why]}
    r = cov_ratio(prop, txt)
    blockers = ["not_exact_containment"]
    if prop_nums(prop) - prop_nums(txt):
        blockers.append("number_mismatch")
    missing = [c for c in prop_conds(prop) if c not in txt]
    if missing:
        blockers.append("condition_missing:" + ",".join(missing))
    if any(c in prop for c in _NEG_PRE) and not any(c in txt for c in _NEG_PRE):
        blockers.append("negation_missing")
    return {"ok": False, "mode": "approx", "ratio": round(r, 3), "blockers": blockers}


def rule_line(r):
    t = (r.get("text") or "").strip()
    bits = []
    if r.get("subject"):
        bits.append(f"主语:{r['subject']}")
    if r.get("when"):
        bits.append("条件:" + ";".join(str(w) for w in r["when"]))
    if r.get("scope"):
        bits.append(f"scope:{r['scope']}")
    ids = r.get("evidence_atom_ids") or []
    if ids:
        bits.append("证据:" + ",".join(str(x) for x in ids))
    extra = "  (" + " | ".join(bits) + ")" if bits else ""
    return f"- {t}{extra}"


def resolve_ev(e, trans, atoms, hash_index):
    """把一条证据引用规范化 -> (new_id, kind); kind ∈ {atom, ctx, unresolvable}. 不改数据。"""
    e = str(e).strip()
    if not e:
        return e, "unresolvable"
    # ctx=sub:<stem>:<sec> (可能带前缀垃圾, 如 "cto=ctx=sub:...")
    if "sub:" in e:
        cand = "ctx=" + e[e.index("sub:"):]
        m = re.match(r"^ctx=sub:([^:]+):(\d+)$", cand)
        if m:
            return (cand, "ctx") if m.group(1) in trans else (cand, "unresolvable")
    if e.startswith(G.SPECIAL_EV):
        m = re.match(r"^(?:ctx=)?sub:([^:]+):(\d+)$", e)
        if m and m.group(1) in trans:
            return e, "ctx"
        return e, "unresolvable"
    if e in atoms:
        return e, "atom"
    m = re.match(r"^([^:]+):(\d+)$", e)
    if m and m.group(1) in trans:
        return "ctx=sub:" + e, "ctx"
    # 短格式漂移: <stem>:a<n>:<hash>
    m = re.match(r"^(BV[0-9A-Za-z]+_p\d+):a(\d+):([0-9a-f]{8})$", e)
    if m:
        stem, a, h = m.groups()
        cands = [k for k in atoms if k.startswith(stem + "_") and k.endswith(f":a{a}:{h}")]
        if len(cands) == 1:
            return cands[0], "atom"
    # 尾部粘连: 完整原子 id 后又跟了 ":<数字>" (如 ...:p55:a2:9b5eec21:5515)
    parts = e.split(":")
    for cut in range(len(parts) - 1, 3, -1):
        cand = ":".join(parts[:cut])
        if cand in atoms:
            return cand, "atom"
    # 只保住 8 位 hash 的粘连: <bvid>_a3:<hash>
    hm = re.search(r":([0-9a-f]{8})$", e)
    if hm and not hm.group(1) in ("",):
        cands = hash_index.get(hm.group(1)) or []
        if len(cands) == 1:
            return cands[0], "atom"
    return e, "unresolvable"


def fix_citations(res, trans, atoms, hash_index):
    """就地规范化引用, 返回 (n_normalized, n_recovered, n_unresolvable)。"""
    n_norm = n_rec = n_bad = 0
    for r in res.get("rules") or []:
        if not isinstance(r, dict):
            continue
        cnt = 0
        new = []
        for e in (r.get("evidence_atom_ids") or []):
            rid, kind = resolve_ev(e, trans, atoms, hash_index)
            if kind == "unresolvable":
                n_bad += 1
                cnt += 1
            elif rid != e:
                if kind == "ctx":
                    n_norm += 1
                else:
                    n_rec += 1
            new.append(rid)
        r["evidence_atom_ids"] = new
        r["_citation_unresolvable"] = cnt
    return n_norm, n_rec, n_bad


def classify_v2(res, drops, unclosed_videos, atoms, labels, bad_cite_idx):
    """返回 (affirmative_idx, demoted[list[(i,reason)]], gated[list[(i,reason)]])"""
    aff, dem, gat = [], [], []
    for i, r in enumerate(res.get("rules") or []):
        if not isinstance(r, dict):
            continue
        txt = r.get("text") or ""
        ev = [str(e) for e in (r.get("evidence_atom_ids") or [])]
        real = [e for e in ev if not e.startswith(G.SPECIAL_EV)]
        hit_drop = [e for e in real if f"vod_atom:{e}" in drops]
        reason = None
        if r.get("_citation_unresolvable"):
            reason = "citation_unresolvable"
        elif hit_drop:
            reason = f"atom_registry_drop:{hit_drop[0]}"
        elif not real:
            reason = "ctx_only_evidence"
        elif G.THRESH.search(txt):
            vids = set()
            for e in real:
                a = atoms.get(e)
                m = G.VID.search(e) or (G.VID.search(a.get("id") or "") if a else None)
                if m:
                    vids.add(m.group(1))
            fams = sorted({f for f, vs in unclosed_videos.items() if vids and vids <= vs})
            if vids and fams:
                reason = "unclosed_family:" + ",".join(fams)
        if reason:
            gat.append((i, reason))
            continue
        # 通则位收口: 只对**自称 universal** 的卡生效; 卡本身就是 instance/example 观测的,
        # 其规则本就是实例语义, 不需要再降级(否则整卡会被清空而误归档)。
        universal_card = res.get("scope") == "universal"
        lab = (labels.get(i) or {}).get("label")
        if lab in ("mark_unclosed", "meta_discourse", "bad_citation"):
            why = ("audit_" + lab) if (labels.get(i) or {}).get("authority") == "agent_audit" \
                else ("llm_" + lab)
            gat.append((i, why))
            continue
        if universal_card and r.get("scope") in ("instance", "example"):
            dem.append((i, "rule_scope_instance"))
            continue
        if universal_card and lab == "narrow_scope":
            dem.append((i, "llm_narrow_scope"))
            continue
        aff.append(i)
    return aff, dem, gat


def build_text(rec, res, aff, dem, gat, applies_to_line):
    lines = [f"# {res.get('title')}", f"适用对象: {applies_to_line}"]
    sc = res.get("scope")
    if sc == "instance":
        lines.append("范围: 单关/单次实验观测")
    elif sc == "example":
        lines.append("范围: 演算例题/带数值的演示")
    elif sc == "universal":
        lines.append("范围: 可复用规则")
    rules = res.get("rules") or []
    if aff:
        lines.append("## 规则")
        lines += [rule_line(rules[i]) for i in aff]
    if dem:
        lines.append("## 实例佐证(非通则, 不得当通则引用)")
        for i, why in dem:
            lines.append(rule_line(rules[i]) + f"  [非通则:{why}]")
    if gat:
        lines.append("## 待核(provenance 隔离, 不得当已知)")
        for i, why in gat:
            lines.append("- ⚠未闭合: " + rule_line(rules[i])[2:] + f"  [门控:{why}]")
    if res.get("conditions"):
        lines.append("## 条件")
        lines += [f"- {x}" for x in res["conditions"]]
    if res.get("exceptions"):
        lines.append("## 例外")
        lines += [f"- {x}" for x in res["exceptions"]]
    if res.get("open_questions"):
        lines.append("## 待验证")
        lines += [f"- {x}" for x in res["open_questions"]]
    if rec.get("issue_status") == "conflict":
        lines.append("⚠ 本议题存在争议, 以上规则含存争议内容")
    return "\n".join(lines)


def entry_rules(doc):
    """旧 vod_entry/vod_cluster 的命题行 (## 规则 段)。"""
    out, inr = [], False
    for ln in (doc.get("text") or "").split("\n"):
        if ln.startswith("## "):
            inr = ln.startswith("## 规则")
            continue
        if inr and ln.startswith("- "):
            out.append(ln[2:].strip())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--outdir", default=HERE, help="输出目录(默认本目录; 用于可复现校验)")
    args = ap.parse_args()
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    reg = G.load_registry()
    drops = {k for k, v in reg.items() if v.get("action") == "drop"}
    # v1 的 registry 三分支必须全部保留: drop / downweight / keep_unknown。
    # v2 首版漏了 downweight 与 keep_unknown, 使第二轮定向降权的旧文档(如
    # vod_entry:帧时序与计时器-40-13, 理由「挤占 Q07 top」)被重新抬回生产权重,
    # 从而原地复现了第二轮已修掉的检索挤占。此处恢复对齐, 不新增任何调参。
    downs = {k for k, v in reg.items() if v.get("action") == "downweight"}
    keeps = {k for k, v in reg.items() if v.get("action") == "keep_unknown"}
    _, unclosed, _ = G.family_videos()
    atoms = G.load_atoms()
    trans = set()
    for d in ("transcripts_txt", "asr_drafts"):
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                if fn.endswith(".txt"):
                    trans.add(re.sub(r"(_asr|_asr_draft)?\.txt$", "", fn))

    repaired = {}
    for l in open(os.path.join(FC1, "repaired.jsonl"), encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            repaired[r["cluster_id"]] = r
    sem = {}
    for l in open(os.path.join(HERE, "semantic_repaired.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        sem[r["cluster_id"]] = r
    audit = collections.defaultdict(list)
    audit_path = os.path.join(HERE, "audit_overlay_llm_miss.jsonl")
    if os.path.isfile(audit_path):
        for l in open(audit_path, encoding="utf-8"):
            if not l.strip():
                continue
            a = json.loads(l)
            audit[a["cluster_id"]].append(a)
    v1 = {}
    for l in open(os.path.join(FC1, "gated_default.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        v1[d["cluster_id"]] = d

    cache = {}
    hash_index = collections.defaultdict(list)
    for k in atoms:
        h = k.rsplit(":", 1)[-1]
        if re.fullmatch(r"[0-9a-f]{8}", h):
            hash_index[h].append(k)
    for fn in sorted(os.listdir(os.path.join(FC1, "cache_items"))):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(FC1, "cache_items", fn), encoding="utf-8"))
        if rec.get("error") or not (rec.get("result") or {}).get("_text"):
            continue
        base = repaired.get(rec["cluster_id"], rec)
        rec = dict(base)
        rec["result"] = dict(base["result"])
        rec["result"]["rules"] = [dict(x) if isinstance(x, dict) else x
                                  for x in (base["result"].get("rules") or [])]
        cache[rec["cluster_id"]] = rec

    stats = collections.Counter()
    fc1, arch, glog = {}, [], []
    for cid, rec in cache.items():
        res = rec["result"]
        labels = {d["idx"]: d for d in (sem.get(cid, {}).get("llm_labels") or [])}
        for a in audit.get(cid, []):
            labels[a["idx"]] = {"idx": a["idx"], "label": a["label"],
                                "reason": a.get("reason"), "authority": "agent_audit"}
            stats["audit_overlay_applied"] += 1
        nn, nr, nb = fix_citations(res, trans, atoms, hash_index)
        stats["cite_normalized"] += nn
        stats["cite_recovered"] += nr
        stats["cite_unresolvable_refs"] += nb
        if nn or nr or nb:
            stats["cards_with_citation_fix"] += 1
        kind = res.get("kind")
        base_doc = {"id": "fc1:" + cid, "cluster_id": cid, "source": "cache_items",
                    "layer": "archive"}
        if kind in ("pending", "reject") or res.get("needs_review"):
            base_doc["archive_reason"] = (f"kind_{kind}" if kind in ("pending", "reject")
                                          else "needs_review(代理判 severe)")
            base_doc["text"] = res["_text"]
            arch.append(base_doc)
            stats["archive_kind_or_review"] += 1
            continue
        aff, dem, gat = classify_v2(res, drops, unclosed, atoms, labels, None)
        ao = res.get("applies_to") or ""
        if "未点名" in ao:
            if aff and not dem:
                applies = "未点名（原片未给出具体对象; 现存规则均为一般性表述）"
            else:
                applies = (f"未点名（原片未给出具体对象; 通则 {len(aff)} 条, "
                           f"已移出通则段的实例 {len(dem)} 条, 待核 {len(gat)} 条）")
        else:
            applies = ao
        txt = build_text(rec, res, aff, dem, gat, applies)
        for i, why in gat:
            stats["gate_" + why.split(":")[0]] += 1
        for i, why in dem:
            stats["demote_" + why] += 1
        doc = dict(base_doc)
        doc.update({
            "layer": "default", "doc_type": "pilot_v4_entry", "track": "vod_official",
            "status": "draft", "kind": kind, "scope": res.get("scope"),
            "confidence": res.get("confidence"),
            "context_incomplete": bool(res.get("context_incomplete")),
            "affirmative_rule_idx": aff,
            "demoted_rule_idx": [i for i, _ in dem],
            "gated_rules": [{"idx": i, "reason": r} for i, r in gat],
            "llm_labels": labels,
            "retrieval_boost": (1.5 if (kind == "mechanism" and res.get("scope") == "universal"
                                        and not gat and not dem) else 1.1),
            "retrieval_weight": rec.get("retrieval_weight", 1.0),
            "text": txt,
        })
        if kind == "experiment" or res.get("scope") in ("instance", "example"):
            doc["retrieval_boost"] = 0.85
        if not aff:
            if dem:
                # 卡内只剩「实例佐证」: 不进通则位, 但保留为可检索的实例证据(低权重),
                # 而不是整卡降到隔离区 —— 否则会把确有内容的实例观测一起丢掉。
                doc["instance_only"] = True
                doc["retrieval_boost"] = 0.5
                fc1[cid] = doc
                stats["default_instance_only"] += 1
            else:
                doc["layer"] = "archive"
                doc["archive_reason"] = "all_rules_non_affirmative"
                arch.append(doc)
                stats["archive_all_rules_gated"] += 1
        else:
            fc1[cid] = doc
        glog.append({"cluster_id": cid, "layer": doc["layer"], "kind": kind,
                     "n_affirmative": len(aff), "n_demoted": len(dem), "n_gated": len(gat),
                     "v1_n_affirmative": len(v1.get(cid, {}).get("affirmative_rule_idx") or [])})

    # ---- 覆盖核算 (命题级) ----
    cov_atoms = collections.defaultdict(list)
    for cid, doc in fc1.items():
        txt = norm(cn2digit(doc["text"]))
        for i in doc["affirmative_rule_idx"]:
            for e in (cache[cid]["result"]["rules"][i].get("evidence_atom_ids") or []):
                if not str(e).startswith(G.SPECIAL_EV):
                    cov_atoms[e].append((cid, txt))
    # archive 侧引用 (共享来源保护)
    arch_refs = set()
    for d in arch:
        if d.get("source") != "cache_items":
            continue
        for r in (cache[d["cluster_id"]]["result"].get("rules") or []):
            if isinstance(r, dict):
                for e in (r.get("evidence_atom_ids") or []):
                    if not str(e).startswith(G.SPECIAL_EV):
                        arch_refs.add(str(e))
    fc1_text = {cid: norm(cn2digit(doc["text"])) for cid, doc in fc1.items()}
    residual = collections.defaultdict(list)
    cov_cand = collections.defaultdict(list)
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
                if cid in fc1_text:
                    props = entry_rules(d)
                    txt = fc1_text[cid]
                    verdicts = [(p, supersede_verdict(norm(cn2digit(p)), txt)) for p in props]
                    miss = [(p, v) for p, v in verdicts if not v["ok"]]
                    if props and not miss:
                        cov["old_removed_fully_covered_by_default_fc1"] += 1
                        continue
                    d = dict(d)
                    if not props:
                        d["retention_reason"] = "fc1 存在但该旧文档无可比对的规则行; 保守保留"
                    else:
                        approx = [v for _, v in miss if v["mode"] == "approx"]
                        exact_bad = [v for _, v in miss if v["mode"] == "exact"]
                        bits = []
                        if approx:
                            bits.append(f"{len(approx)} 条仅近似(最高相似度 "
                                        f"{max(v['ratio'] for v in approx):.2f}, 非语义蕴涵)")
                        if exact_bad:
                            bits.append(f"{len(exact_bad)} 条精确包含但被矛盾守卫拒绝 "
                                        f"({exact_bad[0]['blockers'][0]})")
                        d["retention_reason"] = (
                            f"保守保留: fc1:{cid} 存在, 但 {len(miss)}/{len(props)} 条命题未通过"
                            f"保守覆盖判定 — " + "; ".join(bits))
                        for p, v in miss:
                            if v["mode"] == "approx":
                                cov["cov_candidate_approx"] += 1
                            else:
                                cov["cov_rejected_by_guard"] += 1
                                cov_cand[cid].append({"prop": p[:120], "blockers": v["blockers"]})
                    old_keep.append(d)
                    cov["old_retained_partial_coverage"] += 1
                    continue
                if cid in {a["cluster_id"] for a in arch if a.get("source") == "cache_items"}:
                    d = dict(d)
                    d["retention_reason"] = "fc1 只有 archive 层(pending/reject/待核全隔离), 未可靠替代"
                    old_keep.append(d)
                    cov["old_retained_fc1_not_default"] += 1
                    continue
                old_keep.append(d)
                cov["old_retained_no_fc1"] += 1
                continue
            if d.get("doc_type") == "vod_atom":
                aid = did.split(":", 1)[1]
                hits = cov_atoms.get(aid)
                if hits:
                    cid, txt = hits[0]
                    prop = norm(cn2digit((d.get("text") or "").split("\n")[0]))
                    v = supersede_verdict(prop, txt)
                    if v["ok"]:
                        cov["old_atom_removed_fully_covered"] += 1
                        continue
                    d = dict(d)
                    if v["mode"] == "approx":
                        d["retention_reason"] = (
                            f"仅近似命中被 fc1:{cid} 引用, 相似度 {v['ratio']:.2f} 但非精确/非语义蕴涵; "
                            f"保守保留旧证据")
                        cov["old_atom_retained_partial_coverage"] += 1
                    else:
                        d["retention_reason"] = (
                            f"精确包含但矛盾守卫拒绝被 fc1:{cid} 覆盖 "
                            f"({'; '.join(v['blockers'])}); 保守保留旧证据")
                        cov["old_atom_retained_conflict_guard"] += 1
                        cov_cand[cid].append({"prop": prop[:120], "blockers": v["blockers"]})
                    old_keep.append(d)
                    residual[cid].append(aid)
                    continue
                if aid in arch_refs:
                    d = dict(d)
                    d["retention_reason"] = "共享来源: 仍被 archive 侧 fc1 引用, 不因 default 侧覆盖而删"
                    old_keep.append(d)
                    cov["old_atom_retained_shared_source"] += 1
                    continue
                d = dict(d)
                d["retention_reason"] = "未被 default fc1 肯定规则引用; 保留旧证据"
                old_keep.append(d)
                cov["old_atom_retained_uncited"] += 1
                continue
            old_keep.append(d)
            cov["other_docs_untouched"] += 1

    if args.apply:
        for cid, ids in residual.items():
            fc1[cid]["residual_atom_ids"] = sorted(set(ids))
        for name, rows in (("gated_default_v2.jsonl", list(fc1.values())),
                           ("gated_archive_v2.jsonl", arch + old_arch),
                           ("gated_old_kept_v2.jsonl", old_keep),
                           ("gate_log_v2.jsonl", glog)):
            with open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {
        "reviewer_type": "agent",
        "outdir": outdir,
        "n_cache_ok": len(cache),
        "default_fc1": len(fc1), "archive_fc1": len(arch),
        "old_kept": len(old_keep), "old_archived": len(old_arch),
        "v1_default": len(v1),
        "stats": dict(stats.most_common()),
        "coverage": dict(cov.most_common()),
        "n_residual_fc1": len(residual),
        "n_residual_atoms": sum(len(v) for v in residual.values()),
        "apply": args.apply,
    }
    json.dump(out, open(os.path.join(HERE, "gate_summary_v2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(residual, open(os.path.join(HERE, "coverage_residual.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(cov_cand, open(os.path.join(HERE, "coverage_candidates_approx.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
