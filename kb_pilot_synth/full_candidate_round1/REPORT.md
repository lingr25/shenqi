# full_candidate_round1 验收报告（代理审核）

生成时间：2026-09-20 14:15:30　`reviewer_type=agent`（非人类审核）

隔离目录：不写生产 `kb/docs.jsonl` / `kb/synthesized.jsonl`，不 git 提交，不公开。

## 1. 规模与生成（含用量口径修正）

- 非 noise `vod_cluster` 候选母体：**2418**
- 缓存条目：`cache_items/` **2418**（ok 2418 / error 0）
- 模型：`deepseek-v4.1-flash`，prompt 版本 v4，缓存键=prompt SHA256+model+source_hash
- **用量口径（不得称总计费完整口径）**：`events.jsonl` 逐 cluster 事件账本给出**6434941** tokens / 2526 事件（ok 2418，失败尝试 108 条**记 0 tokens**），覆盖 ['09-20 11:40:32', '09-20 13:57:01']。
- 主/重试段快照（仅该两段，勿当总计）：`run_summary_main.json` 2297 calls / 6103436 tokens；`run_summary_retry.json` 13 calls / 30469 tokens。
- `usage.json` 已被重试段覆盖（现值 calls 13），**不能单独引用**。
- 可核对下界：本轮生成 **≥ 6434941**、本轮评测 **91845**、其他 pilot 轮 **143718**，本仓库合计 **≥ 6670504** tokens。
- 未计入：108 次失败尝试的真实 tokens (events 记 0, 无 usage 回包); 本轮之前的冒烟测试调用 (无落盘记录); run_summary_main 的 cache_hit 121 条: 主运行计数器未计其 tokens, 但 events 账本计入了 -> 两口径差 301,036; endpoint 侧其他会话/其它仓库的调用 (本地无记录)
- 口径纪律：报告只能写「可核对下界 ≥ N tokens」, 不得写「总计费完整口径」; 主/重试段快照与他轮用量分列, 不相加。

## 2. 结构诊断（flags，纯本地）

| 类别 | 计数 |
|---|---|
| A_mech_but_narrow_scope | 613 |
| D_incomplete | 544 |
| E1_universal_unresolved_subject | 509 |
| unclosed_as_mech | 45 |
| I_formula_from_ctx_only | 32 |
| E2_advice_only_rules | 3 |
| C_high_on_universal_nonmech | 2 |

错误分类：无（errors=0，无失败条目）

### 2.1 修复前/后的真实 kind 统计

| kind | 合成当时(pre) | repaired overlay 之后(post) |
|---|---|---|
| experiment | 158 | 769 |
| mechanism | 1242 | 580 |
| pending | 936 | 987 |
| reject | 82 | 82 |

- 默认层可放行条目（mechanism + universal + 非 needs_review）：pre **629** → post **580**
- 口径：random100 与 risk_extra 是两套不同抽样口径: random100 可代表全体候选(含 reject/pending), risk_extra 是刻意挑选的问题富集桶, 二者不得相加当准确率; n=100 的外推区间宽, 报告中不得表述为全库正确率。

### 2.2 修复拆账（被标记记录 ≠ 字段改动）

- `repair_log.jsonl` 记录 **1515** 条 = 实际字段改动 **1102** + 仅打 flag 标注 **413**
- 字段改动明细：
  - `kind: mechanism -> experiment`：**613**
  - `retrieval_weight: 1.0 -> 0.6`：**544**
  - `kind: mechanism -> pending`：**49**
  - `confidence: high -> mid`：**2**
  - `kind: experiment -> pending`：**2**

## 3. 全体抽样（固定种子）

- 种子 `20260920`；全体随机 **100** + 高风险额外 **40**
- 随机100 实际口径：{'status': {'ok': 100, 'error': 0, 'missing': 0}, 'kinds': {'experiment': 13, 'mechanism': 43, 'pending': 42, 'reject': 2}, 'issue_status': {'open': 62, 'agreed': 34, 'conflict': 4}}
- 高风险额外口径：{'status': {'ok': 40, 'error': 0, 'missing': 0}, 'kinds': {'mechanism': 32, 'pending': 7, 'experiment': 1}, 'issue_status': {'agreed': 21, 'conflict': 11, 'open': 8}}
- error 桶 0，missing 桶 0
- 抽样母体=全体候选（含 reject/pending/error），不是优选好卡。

## 4. 代理逐条证据核查（分桶，不合算成准确率）

- 已核查 **140** 条 = random100 **100** + risk_extra **40**
- `random100`（100 条）判定分布：{'ok_pending': 38, 'ok_reject': 2, 'over_claim_meta': 5, 'ok_content_label': 21, 'ok': 12, 'ok_experiment': 12, 'ok_minor_ctx_mislabel': 1, 'ok_pending_chatter': 1, 'ok_minor_ctx': 1, 'over_claim_formula_from_ctx': 1, 'ok_minor_ctx_formula': 1, 'ok_pending_noisy': 2, 'ok_minor': 2, 'ok_experiment_chatter': 1}
- `risk_extra`（40 条）判定分布：{'ok': 7, 'ok_content_label': 21, 'ok_minor_placeholder': 1, 'ok_pending': 6, 'ok_pending_chatter': 1, 'over_claim_meta': 1, 'thin_reject': 1, 'ok_reject': 1, 'ok_experiment': 1}
- 判 severe：random100 **4** 条 ['其他-16-0', '帧时序与计时器-53-8', '其他-10-6', '帧时序与计时器-12-5']；risk_extra **1** 条 ['帧时序与计时器-11-17']
- `over_claim_*`：random100 ['其他-16-0', '帧时序与计时器-53-8', '其他-10-6', '帧时序与计时器-12-5', '帧时序与计时器-75-11', '技能特例-15-5']；risk_extra ['帧时序与计时器-11-17']
- **整改后（post）**：7 条（severe ∪ over_claim）经 `R_review_severe` 全部落到 kind={pending}（明细见 §5、`postrepair_stats.json`）。
- 两个桶抽样口径不同：random100 可代表全体候选（含 reject/pending），risk_extra 是刻意挑的问题富集桶；**二者不得相加当准确率**，n=100 的外推区间也宽。

## 5. 定向修复（不清全量缓存）

- 扫描 ok 条目 2418，打补丁 **1515**（其中 413 条仅登记 flag，未改正文）
- 类别计数：{'A_mech_but_narrow_scope': 613, 'D_incomplete': 544, 'E1_universal_unresolved_subject': 509, 'unclosed_as_mech': 45, 'I_formula_from_ctx_only': 32, 'R_review_severe': 7, 'E2_advice_only_rules': 3, 'C_high_on_universal_nonmech': 2}
- 被标记但不自动改正文：`E1_universal_unresolved_subject`、`E2_advice_only_rules`、`I_formula_from_ctx_only`
- `cache_items/` 原始 LLM 输出**未改动**（True）；补丁为 overlay，可回退
- 代理判 severe/over_claim 的条目走 `R_review_severe`：['其他-10-6', '其他-16-0', '帧时序与计时器-11-17', '帧时序与计时器-12-5', '帧时序与计时器-53-8', '帧时序与计时器-75-11', '技能特例-15-5']
- 本轮修掉一个名字对齐 bug：`diagnose.flags()` 产出 `unclosed_as_mech`，而 `patch()` 原本只认 `B_unclosed_as_mechanism`，导致 45 条「universal 机制含未闭合数字」未降级；已改为两个键名都接受。

## 6. 门控分层：candidate / archive / default accepted

- 三级分离：**candidate（候选全集）2418** 条 = **default RAG accepted 1343** + **full archive 1075**（archive 另含被 quarantine 的旧文档 12 条）
- archive 原因：{'archive_kind_pending': 987, 'gate_ctx_only_evidence': 428, 'gate_unclosed_family': 92, 'archive_kind_reject': 82, 'archive_all_rules_gated': 6, 'gate_atom_registry_drop': 2}
- provenance 门控信号（定向，不做关键词全局杀）：registry drop 13 条、声明未闭合 family {'D09-radius-number-corrected': ['BV14y8269EbS_p1_41164079923'], 'D01-cd-plus-one-garbled': ['BV199KH6TEra_p1_40136673556'], 'D01-remain-cd-0.5': ['BV14VZCB1EJR_p1_36119907781', 'BV1j4KC6KEse_p1_40109737103']}、`ctx_only_evidence` 规则 428 条、`unclosed_family` 规则 92 条
- **被拒信号**：`参数: X=N无` 命中 1553 个原子（占 12%），理由：这是抽取消歧的通用约定(材料未给单位), 覆盖 12% 原子, 用作门控等于关键词全局误杀
- 旧文档保留（coverage 审核，同簇≠覆盖）：
  - `other_docs_untouched`：**6961**
  - `old_atom_retained_shared_cluster_only`：**6798**
  - `old_atom_removed_covered_by_citation`：**6413**
  - `old_removed_covered_by_default_fc1`：**2684**
  - `old_retained_fc1_not_default`：**2145**
  - `old_quarantined_registry_drop`：**12**
  - `old_downweighted`：**7**
  - `old_keep_unknown`：**1**
- 语义：旧 `vod_entry`/`vod_cluster` 仅当同簇有 **default** fc1 才移除；旧 `vod_atom` 仅当被 default fc1 的**肯定规则**引用（覆盖）才移除，否则保留；registry drop 进 archive，downweight/keep_unknown 保留并标注。

### 6.1 门控与 F05 定向隔离

- `帧时序与计时器-12-8`：`0.5` 阈值规则移入「## 待核(provenance 隔离)」（reason `unclosed_family:D01-remain-cd-0.5`），`197/100 帧` 例题行仍留在肯定段（不因含数字被误杀）。
- `帧时序与计时器-12-4`：`取整再加一` 移入待核；3 条仅 `ctx=sub:` 支撑的规则移入待核。
- 依据来自 `retest_round2/quarantine.jsonl` + `evidence_round1` 中 `rag_gate=false` 的记录，而非对「取整/0.5」做全局关键词过滤。

### 6.2 `pack_trial.py` 复核（旧试验语料，已被门控层取代）

- `pack_trial.py` 产出 `trial_docs.jsonl`（供 `run_trial_eval.py` 的 40 calls 评测用），与 `trial_rag.py` 是**两套不同的 pre-gate 语料**，缺陷方向相反：
  - `pack_trial.py`：跳过 `kind=reject` 的 fc1（**完全不放**），但旧 `vod_entry` 仍因 `cid in synth` 被删 ——实测 **82 个 reject 簇**既无 fc1、旧词条也被移除，等于旧证据被删且无替代；936 个 pending 簇的旧词条同样被删，只留 boost 0.4 的 pending 卡；全部 2418 个 `vod_entry` 只剩 1 条（手写的 `NO_SUPERSEDE = {帧时序与计时器-39-6}`）。
  - 但它**没有**删旧原子/簇（保留 13,217 原子 + 2418 簇），也没有 coverage 与 archive 层，未闭合公式的隔离靠手工名单维持。
  - `trial_rag.py`：反向问题 —— 把 pending/reject 一并 supersede，并按「同簇」删掉 13,139 个旧原子。
- 结论：**两者都不适合作为默认知识层**；`gate.py` 的分层 + provenance 隔离 + 引用覆盖同时取代了两者，并提供 `gated_archive.jsonl` 作为可追溯的隔离区。

## 7. 校验器 `validate_gates.py`

- **硬违规 0**（C1 分层 / C3 pending-reject 归档 / C4 无覆盖理由删除 / C5 引用 / C6 F05）
- 覆盖核算（C4）：
  - `C4_removed_atom_covered_by_citation`：6413
  - `C4_removed_cluster_covered_by_default_fc1`：2684
- 文档层计数：{'default': 1343, 'archive': 1087, 'old_kept': 15912, 'old_ids': 25021, 'old_removed': 9097}

## 8. 冻结 heldout 对照（三列：旧 / 新 pre-gate / 新 gated）

- heldout 冻结 sha256 `ddedeca6efae5545…`（n=7），答题前校验通过
- 语料：旧侧 25106；pre-gate 新侧 9549（原 supersede 语料：removed_entry 2418 / removed_cluster 2418 / removed_atom 13139）；gated 新侧 17340 条 = 保留旧文档 15912 + default fc1 1343 + pilot extras
- 两侧同 BM25 / k=6 / 每片段 500 字 / 上下文上限 3000 字 / 同 prompt；gated 路径真实调用 **14** 次（首轮先跑完 old 侧 7 次后崩溃、次轮跑 new 侧 7 次 = 18835 tokens；末轮语料 corpus_sha 未变，7+7 全部命中 `answers_cache.json`，0 次新调用）
- **pre-gate 语料的 supersede 过宽问题**：它把 pending/reject 也一并 supersede，并仅凭「同簇」删掉 13139 个旧原子；门控后改为按引用覆盖，只移除 6413 个，其余 6798 个保留。

| 题 | 类型 | 旧侧 | 新 pre-gate | 新 gated | gold 命中(旧/pre/gated) |
|---|---|---|---|---|---|
| F01 | direct | pass | pass | pass | True/True/True |
| F02 | direct | pass | pass | pass | True/True/True |
| F03 | direct | pass | pass | pass | True/True/True |
| F04 | boundary | pass | pass | pass | True/True/True |
| F05 | insufficient | partial | partial | pass | False/False/False |
| F06 | misleading | pass | pass | partial | True/True/True |
| F07 | direct | pass | pass | pass | True/True/True |

- 计分：旧 {'pass': 6, 'partial': 1}；新 pre-gate {'pass': 6, 'partial': 1}；新 gated {'pass': 6, 'partial': 1}
- gold 文档命中：旧 6/7、pre-gate 6/7、gated 6/7
- **运行间方差（必须与门控效果区分）**：
  - `F06`：三次运行结果不一致: pre-gate 旧侧=「对，」(partial) / 门控旧侧=「不对」(pass) / pre-gate 新侧=「不对」(pass) / 门控新侧=「对，但…」(partial)。同一 gold 片段, 说明该误导题在多次采样间不稳定, 与门控无关。
  - `F05_abstain_flag`：pre-gate 旧侧 abstain=true; 门控旧侧 abstain=false(正文同样是拒绝)。abstain 开关本身在运行间不稳。
  - `no_score_claim`：n=7, 三次运行合计 21 条回答; 只作一致性与上下文对照, 不构成提分或显著结论。
- 结论：
  - F05 的定向修复达到预期: 门控后新侧由「正面升格」转为明确拒绝(partial -> pass), 且是按 provenance 隔离(未核 family)而非关键词全局杀实现。
  - F06 与 abstain 开关属模型方差, 不归因于门控; 不得据此宣称提分。

## 9. 用量账本（`usage_ledger.json`）

| 项 | calls | tokens | 说明 |
|---|---|---|---|
| 主运行快照 | 2297 | 6103436 | 仅主段，含 cache_hit 121 |
| 失败重试快照 | 13 | 30469 | 仅重试段 |
| events 事件账本 | 2526 | 6434941 | 逐 cluster；失败尝试记 0 tokens |
| 本轮评测(40 calls) | 40 | 53229 | run_trial_eval.py |
| 本轮评测(trial_rag, pre-gate) | 14 | 19781 | 7 heldout × 2 侧 |
| 本轮评测(trial_rag_gated) | 14 | 18835 | 首轮 old 7 次 + 次轮 new 7 次；末轮全程命中缓存 |
| 他轮 v1_v2_v3_pilot | 34 | 70353 | 单独列出，不计入本轮 |
| 他轮 batch100_round2 | 0 | 0 | batch100 纯本地抽段+代理逐条证据审核，未调用 LLM。审核墙钟未测。 |
| 他轮 retest_round2_26calls | 26 | 30723 | 单独列出，不计入本轮 |
| 他轮 cross_eval_round1_40calls | 40 | 42642 | 单独列出，不计入本轮 |
| 他轮 evidence_round1 | 0 | 0 | 纯本地证据整理, 无 usage 文件 |

- 下界 6670504 tokens；events.jsonl 把 108 次失败尝试(429/SSL)记为 0 tokens, 其真实消耗不可恢复; events 早于主运行开始(12-worker 波次), 故不能与主/重试快照相加当总计费。

## 10. 代理结论与真实限制

1. **覆盖**：候选母体 2418 条全部合成完成，`error=0`。
2. **不得宣称总计费完整口径**：主/重试段只覆盖两段；`events.jsonl` 把失败尝试记 0 tokens，之前的 cache_hit 121、冒烟与限流用量不可完整恢复 → 只能报「可核对下界 ≥」。
3. **不得当准确率**：140 条核查分 random100 / risk_extra 两桶，口径不同，不得相加；n=100 不外推全库。
4. **修复口径**：1515 条是「被标记记录」，其中 1102 条有实际字段改动、413 条仅 flag；A 类 613 条只改标签（正文未动），D 类 544 条只降 `retrieval_weight`。
5. **门控是分层治理**：pending/reject/needs_review 一律只进 archive，不进默认检索；`ctx=`/`sub:` 支撑的规则与「声明未闭合 family」内的阈值/公式规则移入「待核」，不做关键词全局过滤（`参数: X=N无` 命中 1553 原子，已作为被拒信号记录）。
6. **旧证据不被无覆盖删除**：门控后旧原子只按「被 default 肯定规则引用」移除 6413 个，6798 个仅同簇的原子保留并标注理由。
7. **heldout 不提分**：三列都是 pass 6 + partial 1，且 partial 的题不同；F05 定向隔离达到预期（新侧由正面升格转为明确拒绝），F06 与 abstain 开关属运行间方差；n=7 不构成统计结论。
8. **F05 gold 不可达**：gold `D01-remain-cd-0.5` 是 evidence_round1 的 `needs_av` 条目（boost 0.4），三侧同取不到，该题只能比「是否拒绝」。
9. **未清项**：`E1` 509 / `I` 32 / `E2` 3 只登记不改正文；部分 OQ 为 ASR 疑问碎片、部分 exceptions 为占位文本。
10. **隔离与合规**：生产 `kb/docs.jsonl` / `kb/synthesized.jsonl` 只读；未 git 提交；未公开发布；全部判定 `reviewer_type=agent`。

