# -*- coding: utf-8 -*-
"""阶段四 b4（441 窗 / 572 条 claim）全量收敛审读的产出器（纯本地，无 API）。

输入：reviews_b4/qq_wo_b4_*.json + workorders_b4/qq_wo_b4_*.json
输出：audit_decisions_b4.json（逐条裁定） + approved_manifest_b4.json（keep 条目）

与 b3 产出器的差别：
  1) 工作单号不是 001..441 连号，按 reviews_b4/ 实际文件名取；
  2) 裁定表不再内嵌，改由 _b4_dec.jsonl（本代理逐条审读台账）载入；keep 仍为缺省。
"""
import hashlib
import json
import os
import re

PLACEHOLDER = re.compile(r"已隐去|已隐藏|\[账号")

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEWS = os.path.join(HERE, "reviews_b4")
WORKORDERS = os.path.join(HERE, "workorders_b4")
LEDGER = os.path.join(HERE, "_b4_dec.jsonl")
OUT_DECISIONS = os.path.join(HERE, "audit_decisions_b4.json")
OUT_MANIFEST = os.path.join(HERE, "approved_manifest_b4.json")
# 对抗性挑刺（faultcheck）落地表：removes=撤下、fixes=按二审建议改写派生文本。
# 由 kb_trial/curation/faultcheck/_faultcheck_apply.py 生成，键为 curated 条目 id。
FAULTCHECK = os.path.join(HERE, "..", "faultcheck", "faultcheck_b4.json")

CRITERIA = {
    "keep": "四项全过：自包含、无未解决争议、明确对象、有效信息",
    "reject": "四项中任一项不过",
    "pending": "证据句存在但判定量被抹掉或口径未收束——「尚未证明」不等于「不可证」，记为材料缺陷而非并入已证集",
}

REJECT_REASONS = {
    "not_self_contained": "claim 把主体/对象留在窗外，原文无法独立支撑",
    "subject_unidentified": "主体在窗内未点名（只说「该干员」「龙」「这个效果」等回指）",
    "source_scope_unresolved": "适用范围在窗内未限定或被说成通用，属外推",
    "scene_specific": "单次操作/单局观察/单实例断言，缺可复用条件",
    "measurement_unresolved": "帧号、数值等测量口径（起算点、基准、单位）未给出，无法复核",
    "unresolved_dispute": "窗内仍有反对、追问或口径未收束",
    "performance_talk": "性能或实现评价、可行性建议、测试方案，不是机制结论",
    "memory_uncertain": "发言者自称不确定/凭回忆，窗内未获确认",
    "conflicting_attribution": "同一现象在窗内有两种互相冲突的归属说法",
    "privacy_redacted": "关键数值被脱敏规则误抹，判定量无法复核",
    "privacy_redacted_number": "关键数值被脱敏规则抹成「[账号已隐去]」占位，原算式/判定量无法复核",
    "not_mechanism": "观感、印象、玩笑话、命名建议或元陈述，不构成机制命题",
    "faultcheck_remove": "对抗性挑刺（faultcheck）二审 verdict=remove：重复、无独立信息量、主体不可锚定或命题未被原文支撑，复核后从本批撤下",
}

# 父对 b4 批 needs_parent_review（28 条）与隐私存疑项的裁决，逐项落地记录。
# 本批 status 即由此从 approved_pending_merge 转为终端态 approved_merged。
PARENT_RULING = {
    "decided_at": "2026-09-21",
    "note": "父对本批 28 条 needs_parent_review 的逐项裁决（降级 5、维持 keep 3、改写批准 7 处/8 条、"
            "其余 20 条维持原判），以及对 037 隐私存疑项的核实结论。台账 _b4_dec.jsonl 已按裁决收敛，"
            "降级项在 decisions 中改判 pending 并在 criterion_note 前置「父裁决（parent_ruling）」。",
    "downgraded_keep_to_pending": [
        {"workorder": "qq_wo_b4_022", "local_id": "c02", "reason_code": "subject_unidentified",
         "basis": "主体「弧光」窗内未定义，父亦无法确指（与同词根的「弧光交通厅」「弧光望」无法区分）。"},
        {"workorder": "qq_wo_b4_322", "local_id": "c03", "reason_code": "subject_unidentified",
         "basis": "「影」只有群内昵称、无法锚定。"},
        {"workorder": "qq_wo_b4_322", "local_id": "c04", "reason_code": "subject_unidentified",
         "basis": "依赖同窗「影」这一昵称，同上。"},
        {"workorder": "qq_wo_b4_395", "local_id": "c02", "reason_code": "memory_uncertain",
         "basis": "承载句发言者窗内自述「我只是这么一说」（seq66），按猜测不入。"},
        {"workorder": "qq_wo_b4_206", "local_id": "c02", "reason_code": "subject_unidentified",
         "basis": "父抽查：「刀」窗内未定义；核心证据 seq21「0.51吗」是疑问句，仅靠 seq22 一个「对」字确认，"
                  "与本批「带问号猜测写成断言」同型。"},
    ],
    "kept": [
        {"workorder": "qq_wo_b4_019", "local_id": "c01", "ruling": "keep",
         "basis": "主命题自足，维持 keep。"},
        {"workorder": "qq_wo_b4_307", "local_id": "c02", "ruling": "keep_with_limitation",
         "basis": "维持 keep，并按要求补「未实战验证」limitations。"},
        {"workorder": "qq_wo_b4_383", "local_id": "c02", "ruling": "keep",
         "basis": "维持 keep，保留 500/1000 数差 audit_note。"},
    ],
    "rewrites_approved": {
        "count": 8,
        "items": ["qq_wo_b4_154/c01", "qq_wo_b4_156/c01", "qq_wo_b4_222/c02", "qq_wo_b4_325/c01",
                  "qq_wo_b4_325/c02", "qq_wo_b4_347/c01", "qq_wo_b4_358/c01", "qq_wo_b4_434/c01"],
        "basis": "父已审阅并按改写后文本入库（claim_original 保留原值）。",
    },
    "upheld_unchanged": "18 条 subject_unidentified / unresolved_dispute 的 pending 与 3 条 reject"
                        "（182/c02、271/c01、370/c01）维持原判，不救回；"
                        "首轮建议的 011/c01 改写 32 帧、259/c03 抽句本批不做，留待以后。",
    "privacy_check": {
        "workorder": "qq_wo_b4_037", "seq": 6,
        "finding": "父已核实：seq6 的 6 位数字来自匿名 speaker_id 的 hex 子串，不是真实 QQ 号；"
                   "且无任何 keep claim 引用 seq6 作证据（本文件 privacy_redacted_number_census 亦记其不在 evidence 内），无需处理。",
    },
}


def load_workorder_ids():
    ids = []
    for f in sorted(os.listdir(REVIEWS)):
        m = re.match(r"(qq_wo_b4_\d{3})\.json$", f)
        if m:
            ids.append(m.group(1))
    return ids


def load_ledger():
    decisions, overrides = {}, {}
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            key = (r["workorder"], r["local_id"])
            if key in decisions:
                raise SystemExit("台账重复键：%s" % (key,))
            decisions[key] = (
                r["verdict"],
                r.get("reason_code"),
                r.get("criterion_note"),
                r.get("needs_parent_review", False),
                r.get("flags", []),
            )
            if "override" in r:
                overrides[key] = r["override"]
    return decisions, overrides


def ledger_census():
    """台账非机械口径的实测分布（keep 行＝需留注的 keep），供 note 引用而非手写。"""
    import collections
    c = collections.Counter()
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                c[json.loads(line)["verdict"]] += 1
    return c


def faultcheck_remove_ids():
    """本轮 faultcheck 的移除 id（qq 三批读 faultcheck_*.json，录播轨读 decisions.jsonl 的 reject 标记）。"""
    ids = set()
    for name in ("faultcheck_phase2.json", "faultcheck_b3.json", "faultcheck_b4.json"):
        path = os.path.join(HERE, "..", "faultcheck", name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                ids |= set((json.load(fh).get("removes") or {}))
    dec = os.path.join(HERE, "..", "decisions.jsonl")
    if os.path.exists(dec):
        with open(dec, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("audit_kind") == "faultcheck_remove":
                    ids.add("%s#r%s" % (row["doc_id"], row["rule_idx"]))
    return ids


def merged_result_entry_count(batch_entry_count, label):
    """本轮追加进 curated_high_quality.json 之后的发布条目总数（现算，不写死）。

    取发布文件里「非本批」的条目数（本批条目以 manifest 路径标识），扣掉其中本轮被
    faultcheck 移除的、再加本批当前的 keep 数：两边时点同值（并批前后 others 不变）。
    """
    path = os.path.abspath(os.path.join(HERE, "..", "..", "curated_high_quality.json"))
    try:
        data = json.load(open(path, encoding="utf-8"))
    except OSError:
        return batch_entry_count
    removed = faultcheck_remove_ids()
    others = sum(1 for e in data["entries"]
                 if ((e.get("origin") or {}).get("trial_manifest_outputs") != label
                     and e["id"] not in removed))
    return others + batch_entry_count


def load_faultcheck():
    """读 faultcheck 落地表，键换成 (window_id, local_id)（条目 id 为 qq_expansion:<window>:<local>）。

    一个窗口可能有多条，故键必须带 local_id。
    """
    removes, fixes, meta = {}, {}, {}
    if not os.path.exists(FAULTCHECK):
        return removes, fixes, meta
    with open(FAULTCHECK, encoding="utf-8") as fh:
        d = json.load(fh)
    meta = {k: d.get(k) for k in ("applied_at", "counts", "policy", "source", "script")}
    for eid, spec in (d.get("removes") or {}).items():
        _, win, lid = eid.split(":", 2)
        removes[(win, lid)] = dict(spec, local_id=lid)
    for eid, spec in (d.get("fixes") or {}).items():
        _, win, lid = eid.split(":", 2)
        fixes[(win, lid)] = dict(spec, local_id=lid)
    return removes, fixes, meta


def build():
    wids = load_workorder_ids()
    decisions_table, overrides_table = load_ledger()
    cen = ledger_census()

    claims, excluded = [], []
    raw_by_wo, reviews_by_wo, as_of = {}, {}, {}
    for wid in wids:
        with open(os.path.join(REVIEWS, wid + ".json"), encoding="utf-8") as fh:
            rv = json.load(fh)
        with open(os.path.join(WORKORDERS, wid + ".json"), encoding="utf-8") as fh:
            wo = json.load(fh)
        reviews_by_wo[wid] = rv
        raw_by_wo[wid] = wo
        as_of[wid] = wo["window"]["as_of"]
        for c in rv.get("claims") or []:
            claims.append((wid, rv, wo, c))
        for e in rv.get("excluded") or []:
            excluded.append((wid, rv, e))

    windows_with_claims = sorted({c[0] for c in claims})
    windows_without_claims = [w for w in wids if w not in set(windows_with_claims)]

    ev_by_wo = {}
    for wid, rv, wo, c in claims:
        ev_by_wo.setdefault(wid, set()).update(e["seq"] for e in c["evidence"])
    privacy_census = []
    for wid in wids:
        hit = [m["seq"] for m in raw_by_wo[wid]["raw_messages"]["messages"]
               if PLACEHOLDER.search(m["text"])]
        if not hit:
            continue
        insc = sorted(set(hit) & ev_by_wo.get(wid, set()))
        privacy_census.append({
            "workorder": wid,
            "window": raw_by_wo[wid]["window"]["window_id"],
            "placeholder_seqs": hit,
            "in_claim_evidence_seqs": insc,
            "action": "claim 移 pending（privacy_redacted_number）" if insc else "占位仅出现在未裁定的上下文里，不进入收敛",
        })

    decisions, entries = [], []
    counts = {"keep": 0, "reject": 0, "pending": 0}
    keep_with_note = 0
    parent_review = []

    # ---- 对抗性挑刺（faultcheck）落地：条目 id -> (workorder_id, local_id)
    fc_rm_raw, fc_fix_raw, fc_meta = load_faultcheck()
    wo_to_win = {wid: raw_by_wo[wid]["window"]["window_id"] for wid in raw_by_wo}
    win_to_wo = {win: wid for wid, win in wo_to_win.items()}
    fc_remove, fc_fix = {}, {}
    for (win, lid), spec in fc_rm_raw.items():
        fc_remove[(win_to_wo[win], lid)] = spec
    for (win, lid), spec in fc_fix_raw.items():
        fc_fix[(win_to_wo[win], lid)] = spec
    fc_removed = []

    for wid, rv, wo, c in claims:
        key = (wid, c["local_id"])
        if key in decisions_table:
            verdict, reason_code, note, needs_parent, flags = decisions_table[key]
        else:
            verdict, reason_code, note, needs_parent, flags = "keep", None, None, False, []
        ov = overrides_table.get(key)
        fc = fc_fix.get(key)
        fcr = fc_remove.get(key)
        if fcr is not None:
            # 二审 verdict=remove：从本批撤下（不再进 manifest），裁定留在 audit
            verdict, reason_code = "reject", "faultcheck_remove"
            flags = list(flags) + ["faultcheck_remove"]
            fc_removed.append({"window": rv["window_id"], "workorder": wid,
                               "local_id": c["local_id"], "fault_type": fcr.get("fault_type", ""),
                               "reason": fcr.get("reason", ""), "source": fcr.get("source", "")})
        claim_text = ((fc or {}).get("claim") or (ov or {}).get("claim") or c["claim"])
        subject_text = ((fc or {}).get("subject") or (ov or {}).get("subject") or c["subject"])
        condition_text = ((fc or {}).get("condition") or (ov or {}).get("condition") or c["condition"])
        # An override may change only the limitations (父裁决对 307/c02 就是这样)。只有正文真的被
        # 改写时才算 claim_corrected_by_audit，否则会把「只补了 limitations」的条目误报成改写条。
        text_rewritten = ((ov is not None or fc is not None)
                          and (claim_text != c["claim"] or subject_text != c["subject"]
                               or condition_text != c["condition"]))
        counts[verdict] += 1
        if verdict == "keep" and note:
            keep_with_note += 1
        if needs_parent:
            parent_review.append({"workorder": wid, "local_id": c["local_id"],
                                  "verdict": verdict, "reason_code": reason_code})
        d = {
            "workorder": wid,
            "window": rv["window_id"],
            "local_id": c["local_id"],
            "kind": "claim",
            "verdict": verdict,
            "claim": claim_text,
            "scope": c["scope"],
            "criterion_note": note,
        }
        if fcr is not None:
            d["criterion_note"] = "对抗性挑刺二审 remove（%s）：%s" % (
                fcr.get("fault_type", ""), fcr.get("reason", ""))
        elif fc is not None:
            d["criterion_note"] = "%s对抗性挑刺修复（%s）：%s" % (
                (note + "；") if note else "",
                fc.get("fault_type", ""), fc.get("note") or fc.get("suggestion", ""))
        if verdict != "keep":
            d["reason_code"] = reason_code
            d["reason"] = REJECT_REASONS[reason_code]
        if text_rewritten:
            d["claim_corrected_by_audit"] = True
            d["claim_original"] = c["claim"]
        if fc is not None:
            d["claim_repaired_by_faultcheck"] = {
                "fault_type": fc.get("fault_type", ""), "suggestion": fc.get("suggestion", ""),
                "note": fc.get("note", ""), "source": fc.get("source", ""),
            }
        if flags:
            d["flags"] = flags
        if needs_parent:
            d["needs_parent_review"] = True
        decisions.append(d)

        if verdict != "keep":
            continue

        msgs = {m["seq"]: m for m in wo["raw_messages"]["messages"]}
        ev = []
        for item in c["evidence"]:
            m = msgs.get(item["seq"])
            if m is None:
                raise SystemExit("seq %s 不在 %s 的 raw_messages" % (item["seq"], wid))
            if m["text"] != item["text"]:
                raise SystemExit("evidence 文本与 raw_messages 不一致：%s seq%s" % (wid, item["seq"]))
            ev.append({
                "seq": item["seq"],
                "speaker_id": m.get("speaker_id"),
                "time": m.get("time"),
                "text": item["text"],
            })
        payload = json.dumps(
            [{"seq": e["seq"], "speaker_id": e["speaker_id"],
              "time": e["time"], "text": e["text"]} for e in ev],
            ensure_ascii=False, sort_keys=True,
        )
        lims = list(c.get("limitations") or [])
        if ov is not None:
            lims = lims + list(ov.get("limitations_append") or [])
        if fc is not None:
            lims = lims + ["对抗性挑刺（faultcheck）修复（%s）：%s"
                           % (fc.get("fault_type", ""), fc.get("note") or fc.get("suggestion", ""))]
        entry = {
            "workorder_id": wid,
            "window_id": rv["window_id"],
            "local_id": c["local_id"],
            "claim": claim_text,
            "subject": subject_text,
            "condition": condition_text,
            "scope": c["scope"],
            "category": c["category"],
            "as_of": as_of[wid],
            "evidence": ev,
            "evidence_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "reviewer_model": rv.get("reviewer_model"),
            "review_reason": c["reason"],
            "review_limitations": lims,
            "audit_note": note or "",
            "claim_corrected_by_audit": text_rewritten,
            "claim_original": c["claim"] if text_rewritten else None,
        }
        if flags:
            entry["audit_flags"] = flags
        if needs_parent:
            entry["needs_parent_review"] = True
        entries.append(entry)

    kept_wo = []
    for e in entries:
        if e["workorder_id"] not in kept_wo:
            kept_wo.append(e["workorder_id"])

    audit = {
        "note": "阶段四 b4 批（441 窗 / 572 条 claim）的逐条收敛审读裁定。候选＝reviews_b4 的 claims[]（572 条全部有裁定，keep 为缺省），逐窗回读同窗 workorders_b4 的 raw_messages（全文、原序、含 speaker_id 与 time）核实 evidence 逐字一致，再按与阶段二/阶段三同一套四项判据（自包含、无未解决争议、明确对象、有效信息）裁定 keep/reject/pending。本批 128 个窗口的 reviews 无候选，故不在本文件产生 claim 级裁定（窗口总数为 441）。excluded[] 一律不进入收敛，也不据此反向支持任何 claim。**本轮对抗性挑刺（faultcheck）**：二审对已发布条目逐条挑刺，本批 12 条 verdict=remove 已撤下（不再进 manifest）、121 条 verdict=fix 已按建议改写 claim/subject/condition（引文一字未动），本批 keep 由 508 变为 %d（见 faultcheck 块）。" % len(entries),
        "inputs": {
            "workorders": "kb_trial/curation/qq_expansion/workorders_b4/qq_wo_b4_*.json",
            "final_reviews": "kb_trial/curation/qq_expansion/reviews_b4/qq_wo_b4_*.json",
            "final_reviews_count": len(wids),
            "windows_with_claims": len(windows_with_claims),
            "windows_without_claims": len(windows_without_claims),
        },
        "audit_method": "逐条回读原文裁定：以 reviews_b4 的 claims[] 为候选，逐窗核对 evidence 的 seq 与文本是否与 raw_messages 逐字相同（0 处不一致），对 claim 中的数值、标识符、专名再回原文核对。裁定台账为 kb_trial/curation/qq_expansion/_b4_dec.jsonl（%d 行：keep 留注 %d、reject %d、pending %d），本文件由该台账机械生成；台账已按父裁决收敛，降级项在 criterion_note 前置「父裁决（parent_ruling）」。**本轮对抗性挑刺（faultcheck）**：二审对已发布条目逐条挑刺，只改 claim/subject/condition 三类派生文本，引文（evidence 文本与 evidence_sha256）一字未动；verdict=remove 的条目从本批撤下（reason_code=faultcheck_remove），verdict=fix 的条目按建议改写并把 faultcheck 说明追加进 review_limitations，逐条留在 decisions[].claim_repaired_by_faultcheck。"
                         % (sum(cen.values()), cen["keep"], cen["reject"], cen["pending"]),
        "criteria": CRITERIA,
        "reject_reasons": REJECT_REASONS,
        "speaker_policy": "本批不按发言者身份加权，只据原文是否闭合；但 speaker_id 为空的 assistant 段（小晓/可露希尔/贝拉/日报等 LLM bot 输出）与含分节排版、自述「查阅/反编译」的生成物一律不作为机制证据，凡仅由该类文本承载的候选一律不收（例：b4-036/c02 的 PRTS 装置数据段、b4-253/c03 的 bot 加速度模型反证）。",
        "decisions": decisions,
        "kept_summary": {
            "count": len(entries),
            "workorders": kept_wo,
            "keep_with_audit_note": keep_with_note,
            "note": "keep 为缺省（台账只列非 keep 与需留注项）；本批不移除任何证据句，只做收/不收的裁定。",
        },
        "needs_parent_review": {"count": len(parent_review), "items": parent_review},
        "parent_ruling": PARENT_RULING,
        "excluded_summary": {
            "excluded_reviewed": len(excluded),
            "note": "本轮只收敛 claims[]，excluded[] 不逐条复裁，保持 reviews_b4 原样；本文件不把任何 excluded 项升为 keep，也不以之为依据反向支持 claims[]。",
        },
        "privacy_redacted_number_census": {
            "note": "占位形态为「[账号已隐去]」一类（隐私脚本把 6–12 位连续数字整体替换）。这里列出全部含占位的工单，以及占位是否落在被判 claim 自身的 evidence 文本内——只有后者才触发 privacy_redacted_number。",
            "claim_evidence_hit_workorders": sorted({r["workorder"] for r in privacy_census if r["in_claim_evidence_seqs"]}),
            "claim_evidence_hit_windows": sorted({r["window"] for r in privacy_census if r["in_claim_evidence_seqs"]}),
            "context_only_workorders": sorted({r["workorder"] for r in privacy_census if not r["in_claim_evidence_seqs"]}),
            "workorder_count_with_placeholder": len(privacy_census),
            "claim_evidence_hit_count": sum(1 for r in privacy_census if r["in_claim_evidence_seqs"]),
            "windows": privacy_census,
        },
        "faultcheck": {
            "applied_at": fc_meta.get("applied_at") or "2026-09-22",
            "script": "kb_trial/curation/faultcheck/_faultcheck_apply.py",
            "source": "kb_trial/curation/faultcheck/faultcheck_b4.json"
                      "（由 kb_trial/curation/faultcheck/_faultcheck_apply.py 汇总批 16 份 triage_*.json 的二审结论）",
            "note": "对抗性挑刺（faultcheck）本轮落地：二审逐条对已发布条目挑刺，verdict=remove 的撤下、"
                    "verdict=fix 的按建议改写 claim/subject/condition（引文一个字不动）。"
                    "removes 全量列于本块，fixes 逐条记在 decisions[].claim_repaired_by_faultcheck，"
                    "并作为 limitations 追加到对应条目。本批 keep 由 508 变为 %d。"
                    % len(entries),
            "remove_count": len(fc_removed),
            "removes": sorted(fc_removed, key=lambda r: r["workorder"]),
            "fix_count": len(fc_fix),
            "fixes": sorted(
                [{"window": wo_to_win[wo], "workorder": wo, "local_id": lid,
                  "fault_type": spec.get("fault_type", ""),
                  "fields": sorted(k for k in ("claim", "subject", "condition") if k in spec)}
                 for (wo, lid), spec in fc_fix.items()],
                key=lambda r: (r["workorder"], r["local_id"])),
        },
        "counts": counts,
    }
    with open(OUT_DECISIONS, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    manifest = {
        "note": "阶段四 b4 批（441 窗 / 572 条 claim）全量收敛审读后的批准产物，只含逐条回读 raw_messages 后认可的命题；每条 evidence 与冻结工单 raw_messages 逐字校验（evidence_sha256 可复核，算法=对 evidence 各条 {seq,speaker_id,time,text} 的 JSON（ensure_ascii=False、sort_keys=True、默认分隔符）取 sha256，与阶段二/阶段三同式）。父已对 needs_parent_review 与隐私存疑项逐项裁决（降级 5 条、维持 keep 3 条、批准 7 处改写、其余维持原判），本批因此由 approved_pending_merge 转为终端态 approved_merged，并已追加进 kb_trial/curated_high_quality.json。**本轮对抗性挑刺（faultcheck，2026-09-22）**：二审逐条挑刺后本批撤下 12 条（reason_code=faultcheck_remove）、按建议改写 121 条派生文本（引文一字未动），本批 keep 由 508 变为 %d；见 audit_decisions_b4.json 的 faultcheck 块。" % len(entries),
        "parent_ruling": PARENT_RULING,
        "schema": "qq-expansion-approved-1.0",
        "phase": "phase4_b4_full_convergence",
        "criteria": CRITERIA,
        "windows_reviewed": len(wids),
        "windows_with_claims": len(windows_with_claims),
        "source": {
            "workorders": "kb_trial/curation/qq_expansion/workorders_b4/",
            "final_reviews": "kb_trial/curation/qq_expansion/reviews_b4/",
            "audit_decisions": "kb_trial/curation/qq_expansion/audit_decisions_b4.json",
        },
        "status": "approved_merged",
        "entry_count": len(entries),
        "hard_exclusions_enforced": [
            "%s %s/%s %s" % (d["window"], d["workorder"], d["local_id"], d["reason_code"])
            for d in decisions if d["verdict"] != "keep"
        ],
        "entries": entries,
        "approved_by": "parent ruling 2026-09-21: 28 条 needs_parent_review 逐项裁决"
                       "（022/c02、322/c03、322/c04、395/c02、206/c02 → pending；019/c01、307/c02、383/c02 → keep；"
                       "154/c01、156/c01、222/c02、325/c01、325/c02、347/c01、358/c01、434/c01 → 按改写入库；"
                       "其余 pending/reject 维持原判），037 隐私存疑项经核实无需处理；keep=508。"
                       "父裁定 2026-09-22：批准对抗性挑刺（faultcheck）二审结论，本批 12 条 verdict=remove "
                       "撤下、121 条 verdict=fix 改写派生文本（引文与 evidence_sha256 未动），keep=%d。" % len(entries),
        "merged_at": "2026-09-21",
        "merged_into": "kb_trial/curated_high_quality.json",
        "merged_entries": len(entries),
        "merged_result_entry_count": merged_result_entry_count(
            len(entries), "kb_trial/curation/qq_expansion/" + os.path.basename(OUT_MANIFEST)),
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print("workorders=%d windows_with_claims=%d claims=%d keep=%d(with_note=%d) reject=%d pending=%d entries=%d excluded=%d" % (
        len(wids), len(windows_with_claims), len(claims), counts["keep"], keep_with_note,
        counts["reject"], counts["pending"], len(entries), len(excluded)))
    print("needs_parent_review=%d" % len(parent_review))


if __name__ == "__main__":
    build()
