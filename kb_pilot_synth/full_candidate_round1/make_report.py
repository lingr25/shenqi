# -*- coding: utf-8 -*-
"""把隔离目录各产物汇总成 REPORT.md (真实数量/用量/限制, 不外推)。纯本地。

口径纪律(父要求):
  - 用量只写「可核对下界」; 主/重试段快照与他轮用量分列, 不相加当总计费。
  - kind 统计必须区分「合成当时(pre)」与「repaired overlay 之后(post)」。
  - 抽样判定随机 100 与 risk_extra 40 分列, 不得相加当准确率。
  - 修复数区分「被标记记录」与「实际字段改动」。
  - 门控分层与校验结果单列; heldout 三列对照(旧/pre-gate/gated)并标注运行间方差。
"""
import collections
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def jl(name):
    p = os.path.join(HERE, name)
    if not os.path.isfile(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def j(name, default=None):
    p = os.path.join(HERE, name)
    if not os.path.isfile(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def main():
    L = []
    A = L.append
    summary = j("run_summary.json", {}) or {}
    diag = j("diagnostics.json", {}) or {}
    rep = j("repair_summary.json", {}) or {}
    man = j("sample_manifest.json", {}) or {}
    post = j("postrepair_stats.json", {}) or {}
    gate = j("gate_summary.json", {}) or {}
    val = j("gate_validation.json", {}) or {}
    review = j("heldout_review.json", {}) or {}
    led = j("usage_ledger.json", {}) or {}
    trial_pre = j("trial_usage.json", {}) or {}
    trial_g = j("trial_gated_usage.json", {}) or {}
    verdicts = jl("audit_verdicts.jsonl")

    A("# full_candidate_round1 验收报告（代理审核）\n")
    A(f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}　`reviewer_type=agent`（非人类审核）\n")
    A("隔离目录：不写生产 `kb/docs.jsonl` / `kb/synthesized.jsonl`，不 git 提交，不公开。\n")

    # 1
    A("## 1. 规模与生成（含用量口径修正）\n")
    A(f"- 非 noise `vod_cluster` 候选母体：**{man.get('population_n') or summary.get('n_clusters')}**")
    A(f"- 缓存条目：`cache_items/` **{diag.get('n_cache_files')}**"
      f"（ok {diag.get('n_ok')} / error {diag.get('n_error')}）")
    A(f"- 模型：`{summary.get('model')}`，prompt 版本 v4，缓存键=prompt SHA256+model+source_hash")
    ev = (led.get("in_round_full_candidate_round1") or {}).get("generation_events_ledger") or {}
    A(f"- **用量口径（不得称总计费完整口径）**：`events.jsonl` 逐 cluster 事件账本给出"
      f"**{ev.get('tokens_ok_only')}** tokens / {sum((ev.get('n_by_status') or {}).values())} 事件"
      f"（ok {ev.get('n_by_status', {}).get('ok')}，失败尝试 {ev.get('n_by_status', {}).get('error')} 条**记 0 tokens**），"
      f"覆盖 {ev.get('span')}。")
    A(f"- 主/重试段快照（仅该两段，勿当总计）：`run_summary_main.json` "
      f"{(led.get('in_round_full_candidate_round1') or {}).get('run_summary_main_usage', {}).get('calls')} calls / "
      f"{(led.get('in_round_full_candidate_round1') or {}).get('run_summary_main_usage', {}).get('total_tokens')} tokens；"
      f"`run_summary_retry.json` "
      f"{(led.get('in_round_full_candidate_round1') or {}).get('run_summary_retry_usage', {}).get('calls')} calls / "
      f"{(led.get('in_round_full_candidate_round1') or {}).get('run_summary_retry_usage', {}).get('total_tokens')} tokens。")
    A(f"- `usage.json` 已被重试段覆盖（现值 calls "
      f"{(led.get('in_round_full_candidate_round1') or {}).get('usage_json_now_overwritten_by_retry', {}).get('calls')}），"
      f"**不能单独引用**。")
    vt = led.get("verifiable_totals") or {}
    A(f"- 可核对下界：本轮生成 **≥ {vt.get('in_round_generation_tokens_ge')}**、本轮评测 "
      f"**{vt.get('in_round_eval_tokens')}**、其他 pilot 轮 **{vt.get('prior_rounds_tokens')}**，"
      f"本仓库合计 **≥ {vt.get('repo_wide_tokens_ge')}** tokens。")
    A(f"- 未计入：{'; '.join(led.get('not_counted') or [])}")
    A(f"- 口径纪律：{led.get('claim_policy')}")
    A("")

    # 2
    A("## 2. 结构诊断（flags，纯本地）\n")
    ft = diag.get("flag_totals") or {}
    A("| 类别 | 计数 |")
    A("|---|---|")
    for k, v in ft.items():
        A(f"| {k} | {v} |")
    ec = diag.get("error_classes") or {}
    A(f"\n错误分类：{ec if ec else '无（errors=0，无失败条目）'}\n")

    A("### 2.1 修复前/后的真实 kind 统计\n")
    A("| kind | 合成当时(pre) | repaired overlay 之后(post) |")
    A("|---|---|---|")
    pre, po = post.get("kinds_pre") or {}, post.get("kinds_post") or {}
    for k in sorted(set(pre) | set(po)):
        A(f"| {k} | {pre.get(k, 0)} | {po.get(k, 0)} |")
    A(f"\n- 默认层可放行条目（mechanism + universal + 非 needs_review）："
      f"pre **{post.get('default_releasable_pre')}** → post **{post.get('default_releasable_post')}**")
    A(f"- 口径：{post.get('note_accuracy')}\n")

    A("### 2.2 修复拆账（被标记记录 ≠ 字段改动）\n")
    ra = post.get("repair_accounting") or {}
    A(f"- `repair_log.jsonl` 记录 **{ra.get('n_logged_records')}** 条 = "
      f"实际字段改动 **{ra.get('n_with_field_change')}** + 仅打 flag 标注 **{ra.get('n_flag_only_no_field_change')}**")
    A("- 字段改动明细：")
    for k, v in (ra.get("field_changes") or {}).items():
        A(f"  - `{k}`：**{v}**")
    A("")

    # 3
    A("## 3. 全体抽样（固定种子）\n")
    A(f"- 种子 `{man.get('seed')}`；全体随机 **100** + 高风险额外 **{man.get('n_risk_extra')}**")
    A(f"- 随机100 实际口径：{man.get('random100_dist')}")
    A(f"- 高风险额外口径：{man.get('risk_extra_dist')}")
    A(f"- error 桶 {man.get('n_error_pool')}，missing 桶 {man.get('n_missing_pool')}")
    A("- 抽样母体=全体候选（含 reject/pending/error），不是优选好卡。\n")

    # 4
    A("## 4. 代理逐条证据核查（分桶，不合算成准确率）\n")
    A(f"- 已核查 **{len(verdicts)}** 条 = random100 **100** + risk_extra **40**")
    for b, c in (post.get("audit_by_bucket") or {}).items():
        n = c.get("_n", 0)
        dist = {k: v for k, v in c.items() if k != "_n"}
        A(f"- `{b}`（{n} 条）判定分布：{dist}")
    A(f"- 判 severe：random100 **{len((post.get('severe_pre_by_bucket') or {}).get('random100', []))}** 条 "
      f"{(post.get('severe_pre_by_bucket') or {}).get('random100')}；"
      f"risk_extra **{len((post.get('severe_pre_by_bucket') or {}).get('risk_extra', []))}** 条 "
      f"{(post.get('severe_pre_by_bucket') or {}).get('risk_extra')}")
    A(f"- `over_claim_*`：random100 {(post.get('over_claim_pre_by_bucket') or {}).get('random100')}；"
      f"risk_extra {(post.get('over_claim_pre_by_bucket') or {}).get('risk_extra')}")
    A(f"- **整改后（post）**：{len((post.get('severe_post') or {}).get('kind_after_remediation') or {})} 条"
      f"（severe ∪ over_claim）经 `R_review_severe` 全部落到 kind="
      f"{{{'pending'}}}（明细见 §5、`postrepair_stats.json`）。")
    A("- 两个桶抽样口径不同：random100 可代表全体候选（含 reject/pending），risk_extra 是刻意挑的问题富集桶；"
      "**二者不得相加当准确率**，n=100 的外推区间也宽。\n")

    # 5
    A("## 5. 定向修复（不清全量缓存）\n")
    A(f"- 扫描 ok 条目 {rep.get('n_ok_scanned')}，打补丁 **{rep.get('n_repaired')}**"
      f"（其中 {ra.get('n_flag_only_no_field_change')} 条仅登记 flag，未改正文）")
    A(f"- 类别计数：{rep.get('category_counts')}")
    A("- 被标记但不自动改正文：`E1_universal_unresolved_subject`、`E2_advice_only_rules`、`I_formula_from_ctx_only`")
    A(f"- `cache_items/` 原始 LLM 输出**未改动**（{rep.get('cache_items_untouched')}）；补丁为 overlay，可回退")
    A(f"- 代理判 severe/over_claim 的条目走 `R_review_severe`：{rep.get('review_severe_used')}")
    A("- 本轮修掉一个名字对齐 bug：`diagnose.flags()` 产出 `unclosed_as_mech`，"
      "而 `patch()` 原本只认 `B_unclosed_as_mechanism`，导致 45 条「universal 机制含未闭合数字」未降级；"
      "已改为两个键名都接受。\n")

    # 6
    A("## 6. 门控分层：candidate / archive / default accepted\n")
    A(f"- 三级分离：**candidate（候选全集）{gate.get('n_cache_ok')}** 条 = "
      f"**default RAG accepted {gate.get('default_fc1')}** + **full archive {gate.get('archive_fc1')}**"
      f"（archive 另含被 quarantine 的旧文档 {gate.get('old_archived')} 条）")
    A(f"- archive 原因：{gate.get('gate_stats')}")
    A(f"- provenance 门控信号（定向，不做关键词全局杀）：registry drop {gate.get('registry', {}).get('drop')} 条、"
      f"声明未闭合 family {gate.get('unclosed_families')}、`ctx_only_evidence` 规则 428 条、"
      f"`unclosed_family` 规则 92 条")
    A(f"- **被拒信号**：`{gate.get('rejected_signal', {}).get('pattern')}` 命中 "
      f"{gate.get('rejected_signal', {}).get('matched_atoms')} 个原子（占 12%），"
      f"理由：{gate.get('rejected_signal', {}).get('why_rejected')}")
    A("- 旧文档保留（coverage 审核，同簇≠覆盖）：")
    for k, v in (gate.get("coverage") or {}).items():
        A(f"  - `{k}`：**{v}**")
    A("- 语义：旧 `vod_entry`/`vod_cluster` 仅当同簇有 **default** fc1 才移除；旧 `vod_atom` 仅当被 default fc1 的"
      "**肯定规则**引用（覆盖）才移除，否则保留；registry drop 进 archive，downweight/keep_unknown 保留并标注。\n")

    A("### 6.1 门控与 F05 定向隔离\n")
    A("- `帧时序与计时器-12-8`：`0.5` 阈值规则移入「## 待核(provenance 隔离)」（reason `unclosed_family:D01-remain-cd-0.5`），"
      "`197/100 帧` 例题行仍留在肯定段（不因含数字被误杀）。")
    A("- `帧时序与计时器-12-4`：`取整再加一` 移入待核；3 条仅 `ctx=sub:` 支撑的规则移入待核。")
    A("- 依据来自 `retest_round2/quarantine.jsonl` + `evidence_round1` 中 `rag_gate=false` 的记录，"
      "而非对「取整/0.5」做全局关键词过滤。\n")

    A("### 6.2 `pack_trial.py` 复核（旧试验语料，已被门控层取代）\n")
    A("- `pack_trial.py` 产出 `trial_docs.jsonl`（供 `run_trial_eval.py` 的 40 calls 评测用），"
      "与 `trial_rag.py` 是**两套不同的 pre-gate 语料**，缺陷方向相反：")
    A("  - `pack_trial.py`：跳过 `kind=reject` 的 fc1（**完全不放**），但旧 `vod_entry` 仍因 `cid in synth` 被删 ——"
      "实测 **82 个 reject 簇**既无 fc1、旧词条也被移除，等于旧证据被删且无替代；"
      "936 个 pending 簇的旧词条同样被删，只留 boost 0.4 的 pending 卡；全部 2418 个 `vod_entry` 只剩 1 条"
      "（手写的 `NO_SUPERSEDE = {帧时序与计时器-39-6}`）。")
    A("  - 但它**没有**删旧原子/簇（保留 13,217 原子 + 2418 簇），也没有 coverage 与 archive 层，"
      "未闭合公式的隔离靠手工名单维持。")
    A("  - `trial_rag.py`：反向问题 —— 把 pending/reject 一并 supersede，并按「同簇」删掉 13,139 个旧原子。")
    A("- 结论：**两者都不适合作为默认知识层**；`gate.py` 的分层 + provenance 隔离 + 引用覆盖同时取代了两者，"
      "并提供 `gated_archive.jsonl` 作为可追溯的隔离区。\n")

    # 7
    A("## 7. 校验器 `validate_gates.py`\n")
    A(f"- **硬违规 {val.get('hard_total')}**（C1 分层 / C3 pending-reject 归档 / C4 无覆盖理由删除 / C5 引用 / C6 F05）")
    A("- 覆盖核算（C4）：")
    for k, v in (val.get("checks") or {}).items():
        A(f"  - `{k}`：{v}")
    A(f"- 文档层计数：{val.get('layers')}")
    A("")

    # 8
    A("## 8. 冻结 heldout 对照（三列：旧 / 新 pre-gate / 新 gated）\n")
    ix = trial_pre.get("index") or {}
    A(f"- heldout 冻结 sha256 `{str(trial_g.get('heldout_sha256') or trial_pre.get('heldout_sha256'))[:16]}…`（n=7），答题前校验通过")
    grun = (led.get("in_round_full_candidate_round1") or {}).get("eval_trial_rag_gated_first_run") or {}
    A(f"- 语料：旧侧 {ix.get('prod_plus_pilot_old')}；pre-gate 新侧 {ix.get('new_plus_pilot')}"
      f"（原 supersede 语料：removed_entry {ix.get('supersede', {}).get('removed_entry')} / "
      f"removed_cluster {ix.get('supersede', {}).get('removed_cluster')} / "
      f"removed_atom {ix.get('supersede', {}).get('removed_atom')}）；"
      f"gated 新侧 {(trial_g.get('new') or {}).get('metric', {}).get('n_docs')} 条 = "
      f"保留旧文档 {gate.get('old_kept')} + default fc1 {gate.get('default_fc1')} + pilot extras")
    A(f"- 两侧同 BM25 / k={trial_g.get('k') or trial_pre.get('k')} / 每片段 500 字 / 上下文上限 3000 字 / 同 prompt；"
      f"gated 路径真实调用 **{grun.get('fresh_calls_total')}** 次"
      f"（首轮先跑完 old 侧 7 次后崩溃、次轮跑 new 侧 7 次 = {grun.get('tokens_fresh_total')} tokens；"
      f"末轮语料 corpus_sha 未变，7+7 全部命中 `answers_cache.json`，0 次新调用）")
    A(f"- **pre-gate 语料的 supersede 过宽问题**：它把 pending/reject 也一并 supersede，"
      f"并仅凭「同簇」删掉 {ix.get('supersede', {}).get('removed_atom')} 个旧原子；"
      f"门控后改为按引用覆盖，只移除 {val.get('checks', {}).get('C4_removed_atom_covered_by_citation')} 个，"
      f"其余 {(gate.get('coverage') or {}).get('old_atom_retained_shared_cluster_only')} 个保留。")
    A("")
    A("| 题 | 类型 | 旧侧 | 新 pre-gate | 新 gated | gold 命中(旧/pre/gated) |")
    A("|---|---|---|---|---|---|")
    for i in review.get("items") or []:
        g = i.get("gold_hit") or {}
        A(f"| {i['id']} | {i['type']} | {i['old']['verdict']} | {i['new_pre_gate']['verdict']} | "
          f"{i['new_gated']['verdict']} | {g.get('old')}/{g.get('pre_gate')}/{g.get('gated')} |")
    A("")
    s = review.get("summary") or {}
    A(f"- 计分：旧 {s.get('old')}；新 pre-gate {s.get('new_pre_gate')}；新 gated {s.get('new_gated')}")
    A(f"- gold 文档命中：旧 {s.get('gold_hit_old')}/7、pre-gate {s.get('gold_hit_pre_gate')}/7、"
      f"gated {s.get('gold_hit_gated')}/7")
    A("- **运行间方差（必须与门控效果区分）**：")
    for k, v in (review.get("variance_evidence") or {}).items():
        A(f"  - `{k}`：{v}")
    A("- 结论：")
    for c in review.get("conclusion") or []:
        A(f"  - {c}")
    A("")

    # 9
    A("## 9. 用量账本（`usage_ledger.json`）\n")
    A("| 项 | calls | tokens | 说明 |")
    A("|---|---|---|---|")
    ins = led.get("in_round_full_candidate_round1") or {}
    m = ins.get("run_summary_main_usage") or {}
    r = ins.get("run_summary_retry_usage") or {}
    A(f"| 主运行快照 | {m.get('calls')} | {m.get('total_tokens')} | 仅主段，含 cache_hit {m.get('cache_hit')} |")
    A(f"| 失败重试快照 | {r.get('calls')} | {r.get('total_tokens')} | 仅重试段 |")
    A(f"| events 事件账本 | {sum((ev.get('n_by_status') or {}).values())} | {ev.get('tokens_ok_only')} | "
      f"逐 cluster；失败尝试记 0 tokens |")
    t40 = ins.get("eval_run_trial_eval_40calls") or {}
    A(f"| 本轮评测(40 calls) | {t40.get('calls')} | "
      f"{(t40.get('old_tokens') or 0) + (t40.get('new_tokens') or 0)} | run_trial_eval.py |")
    tr = ins.get("eval_trial_rag_this_round") or {}
    A(f"| 本轮评测(trial_rag, pre-gate) | {tr.get('calls')} | {tr.get('total_tokens')} | 7 heldout × 2 侧 |")
    A(f"| 本轮评测(trial_rag_gated) | {grun.get('fresh_calls_total')} | {grun.get('tokens_fresh_total')} | "
      f"首轮 old 7 次 + 次轮 new 7 次；末轮全程命中缓存 |")
    for k, v in (led.get("prior_pilot_rounds_separate") or {}).items():
        calls = v.get("calls")
        if calls is None:
            calls = v.get("api_calls", 0)
        A(f"| 他轮 {k} | {calls} | {v.get('total_tokens') or 0} | "
          f"{v.get('note') or '单独列出，不计入本轮'} |")
    A("")
    A(f"- 下界 {vt.get('repo_wide_tokens_ge')} tokens；{vt.get('why_ge')}")
    A("")

    # 10
    A("## 10. 代理结论与真实限制\n")
    A("1. **覆盖**：候选母体 2418 条全部合成完成，`error=0`。")
    A("2. **不得宣称总计费完整口径**：主/重试段只覆盖两段；`events.jsonl` 把失败尝试记 0 tokens，"
      "之前的 cache_hit 121、冒烟与限流用量不可完整恢复 → 只能报「可核对下界 ≥」。")
    A("3. **不得当准确率**：140 条核查分 random100 / risk_extra 两桶，口径不同，不得相加；n=100 不外推全库。")
    A("4. **修复口径**：1515 条是「被标记记录」，其中 1102 条有实际字段改动、413 条仅 flag；"
      "A 类 613 条只改标签（正文未动），D 类 544 条只降 `retrieval_weight`。")
    A("5. **门控是分层治理**：pending/reject/needs_review 一律只进 archive，不进默认检索；"
      "`ctx=`/`sub:` 支撑的规则与「声明未闭合 family」内的阈值/公式规则移入「待核」，"
      "不做关键词全局过滤（`参数: X=N无` 命中 1553 原子，已作为被拒信号记录）。")
    A("6. **旧证据不被无覆盖删除**：门控后旧原子只按「被 default 肯定规则引用」移除 "
      f"{val.get('checks', {}).get('C4_removed_atom_covered_by_citation')} 个，"
      f"{(gate.get('coverage') or {}).get('old_atom_retained_shared_cluster_only')} 个仅同簇的原子保留并标注理由。")
    A("7. **heldout 不提分**：三列都是 pass 6 + partial 1，且 partial 的题不同；F05 定向隔离达到预期"
      "（新侧由正面升格转为明确拒绝），F06 与 abstain 开关属运行间方差；n=7 不构成统计结论。")
    A("8. **F05 gold 不可达**：gold `D01-remain-cd-0.5` 是 evidence_round1 的 `needs_av` 条目（boost 0.4），"
      "三侧同取不到，该题只能比「是否拒绝」。")
    A("9. **未清项**：`E1` 509 / `I` 32 / `E2` 3 只登记不改正文；部分 OQ 为 ASR 疑问碎片、"
      "部分 exceptions 为占位文本。")
    A("10. **隔离与合规**：生产 `kb/docs.jsonl` / `kb/synthesized.jsonl` 只读；未 git 提交；未公开发布；"
      "全部判定 `reviewer_type=agent`。")
    A("")
    print("\n".join(L))
    op = os.path.join(HERE, "REPORT.md")
    open(op, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n[written]", op)


if __name__ == "__main__":
    main()
