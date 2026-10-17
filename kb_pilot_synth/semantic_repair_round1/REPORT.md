# kb 定向语义修复（第三轮）· 报告

`reviewer_type=agent` —— **全部判定由代理（AI agent）完成，不等于人工核听**。
本轮不 git 提交、不建 worktree、不写生产。基准产物 `kb_pilot_synth/full_candidate_round1/`（第二轮）**只读未改**，`validate_full.py` / `validate_gates.py` 在改后重跑仍全绿。

计划文档：`docs/plans/2026-09-20-kb-targeted-semantic-repair.md`（14:22 写，20:0x 据实回填收尾段）。
**计划外增补一处**：写计划后，抽检发现 LLM 复核有 16 条元话语漏检，追加了「审核覆盖层」（第 6 节），并据此重出 gate v2（build2）。计划里没有这一节。

---

## 0. 本版（第三轮收尾）相对上一版报告改了什么

上一版报告的数字口径是 **build2**。本版把版面推进到 **build3**，并补上三项收尾工作：

| # | 动作 | 落点 | 结论 |
|---|---|---|---|
| 1 | **X07 可复现回归的根因定位与修复** | 第 5.3 节 | 根因**不是** k / 上下文预算，而是 `gate_v2.py` 丢了 v1 的 registry `downweight` 分支，使一条领主实例条目回落到生产权重抢进 top6。已修，X07 由 0.75 恢复 1.0 |
| 2 | **上下文预算审计** | 第 5.3 节 | 30 题两面都是 6 个 hit，`n_at_budget=0`、`n_hits_cut_by_budget=0` → **3000 字预算从不生效，k 是唯一紧约束；提高预算无依据** |
| 3 | **supersede 覆盖判据保守化** | 第 5.1(b) 节 | 旧口径「字符二元组相似度 ≥0.7 即算完整覆盖」措辞与判据都不成立：0.7 **只是相似度，不是语义蕴涵**。新口径只承认「精确命题包含 + 否定/数值/条件兼容」，近似一律**只登记候选、不删除**。代价是少删约 2400 条旧原子（宁可留着） |
| 4 | **同源配额评估（三种模式对照）** | 第 5.4 节 | `all` 模式有**已证实的副作用**（把 gold 的独立证据卡 B074/B036 当同簇重复挤掉）→ 弃用；`layer_only` 修掉该副作用且不低于 `all`；`off`（无配额）在本题集上更低（0.942）。**采用 `layer_only`** |
| 5 | **测量噪声基线** | 第 9.5 节 | 同一套旧面检索（`layer_only` 在旧语料上与无配额**逐题 top6 完全相同**）重采样一次，均分从 0.90 变 0.933 → **±0.033 的噪声带**，所有新旧差值都落在这个带内 |
| 6 | **措辞更正** | 全文 | 「我的判定是审核真值」→ **「我的判定是代理证据审核标签，它不是人工审核真值，仍可能出错」** |

**本版不得被读成**：开源就绪、全库准确、或「新面显著优于旧面」。可验证的是**内容级**的改动（第 9.6 节逐条可读），不是总分。

---

## 1. 范围与结论一句话

第二轮只登记未清洗的三类语义风险：`E1_universal_unresolved_subject` **509 卡**、`I_formula_from_ctx_only` **32**、`E2_advice_only_rules` **3**。

**核实结论：E1 的 509 不是 509 张坏卡。** 真实需要复核的并集只有 **270 个规则单元 / 117 张卡**（占 E1 肯定单元 2059 的 13.1%）。其余是占位符回声造成的误报。三类风险逐条落到「改 / 不改」的实际动作，gate 层按通则位与命题级覆盖重写，并用冻结 30 题做了真实 LLM 对照。

---

## 2. 交集与去重（本地，零 LLM）

`compute_scope.py` → `scope_intersection.json`、`scope_units.jsonl`（2733 单元行）。

| 项 | 数 |
|---|---|
| `cache_items/` ok 条目 | 2418 |
| 旧 `gated_default` | 1343 |
| E1 卡（原始诊断） | 509 |
| E1 卡 ∩ gated_default | **459** |
| E1 肯定段规则单元 | 2059 |
| I 规则单元命中 | 36；**在 default 里仍肯定是 0**（v1 的 `ctx_only_evidence` 已全部移入待核） |
| E2 卡 ∩ gated_default | 3（3 单元，均在肯定段） |
| 去重后全部flagged 单元 | 2733（E1 2694 / I 26 / E1+I 10 / E2+E1 2 / E2 1） |

### 2.1 E1 的主要成分是「占位符回声」

`applies_to=未点名` 是 `kb_synthesize.fmt_atoms()` 把源原子 `applies_to=general` 渲染成「(对象:未点名或general)」后，模型照抄进输出字段造成的**回声**，不是「缺主体」。

- 459 张 default 卡里，**360 张的全部肯定规则 `scope=universal` 且证据原子 `scope=general`** → 属误报，不做全局降级。
- `untraceable_atom`（引用原子不在 `kb/docs.jsonl`，短格式/漂移）只有 **4 单元 / 3 卡**。

### 2.2 真实需复核的并集

只统计「default 层 + 仍肯定段」的 2060 单元：

| 子集 | 规则单元 | 卡 |
|---|---|---|
| `rule_scope_narrow`（规则自身 scope=instance/example 坐在 universal 卡肯定段） | **199** | 99 |
| `atom_scope_all_narrow`（规则自称 universal，但全部证据原子为 instance/example） | **111** | 40 |
| 两者重叠 | 39 | — |
| **并集（需复核/修复）** | **270** | **117** |
| `untraceable_atom` | **4** | 3 |
| 本地无可判定问题 | **1786** | — |

**没有做 ctx-only 一刀切**：原字幕行是合法证据，`I` 类在 default 里本就已清零，`E1` 里 ctx 支撑的单元单独解析到原始字幕行后逐条判，不因「只靠 ctx」自动降级。

### 2.3 本地可追溯性三分

`triage_e1.py` → `e1_triage.jsonl` / `triage_summary.json`（2060 单元）：

| 分类 | 数 |
|---|---|
| `ctx_resolved`（引用可解析到原字幕行） | **610**（全部解析成功，`ctx_unresolved=0`） |
| `plain_rule`（引用为真实原子，无需回溯） | 2060 计数中扣减后为其余部分 |
| `atom_scope_narrow` | 112 |
| `atom_scope_all_narrow` | 111 |
| `untraceable_atom` | 4 |
| `no_real_atom_only_ctx` / `no_evidence_at_all` | **0 / 0** |

---

## 3. 小样本校准（12 条，代理证据审核标签 —— **不是人工审核真值**）

`calibration_sample.md`（逐条判定表 + 6 条判据）。五分类：`明确机制` / `明确条件特例` / `缺主体` / `元话语` / `误标`。
下表「代理判定」列是**代理证据审核标签**：它给出的是我在冻结证据上的复核意见，**仍可能出错**，不能当人工核听结论使用。

| # | 单元 | 代理判定 | 处置 |
|---|---|---|---|
| 1 | 伤害结算-0-10:0（真伤=跳过抗性结算） | 明确机制 | **误报**，不改 |
| 2 | 伤害结算-0-10:11（伊德减三十抗真伤） | 明确条件特例 | 移出通则段（实例段） |
| 3 | 伤害结算-0-10:12（肉鸽落地扣七十血） | 明确条件特例 | 移出通则段（实例段） |
| 4 | 伤害结算-12-18:1（弓回不需命中） | 明确机制 | **误报**（原子 scope=instance 但命题是一般性），不改 |
| 5 | 伤害结算-4-3:0（炸死临界取三点画圆） | 元话语/方法论 | 移出通则段 |
| 6 | 伤害结算-0-4:0（肉鸽侵蚀损伤削弱基础防御） | 明确机制 | **误报**（来源为本地 ASR 草稿，**不因 ASR 自动低分**），不改 |
| 7 | 伤害结算-0-10:1 / :5 | 明确机制 | 误报，不改 |
| 8 | 技能特例-15-1:0（书刀与字交替） | 明确机制/操作限制（非策略建议）+ 粒度未闭合 | 保留，scope 标注 + boost 0.5 |
| 9 | 寻路-36-5:2 | 坏引用 | 修引用后回通则 |
| 10 | 状态效果-8-0:0-3 | 明确机制 + 引用格式缺陷（`sub:` 缺前缀） | 引用可还原 → 修好并回通则 |
| 11 | 其他-3-17:0 | 元话语（对局建议） | 整卡隔离入 archive |
| 12 | 技能特例-21-11:0 | 元话语（对 PRTS 的评价） | 整卡隔离入 archive |

**「保留未缺主体的实质规则，而非整卡降级」已落实**：#4、#8 都是「规则本身是实质机制，只是条件/粒度写法有问题」，保留在默认层并加 scope 标注，未整卡归档。

---

## 4. LLM 定向复核（只降不升）

`repair_semantic.py --apply`，模型 `deepseek-v4.1-flash`，workers=4，3 遍（含重试与改引用后补跑）。

- 逐条缓存 `cache_semantic/<sha256(prompt+model+pv)>.json`，**完整 prompt 落盘**；账本 `events_semantic.jsonl`（145 行：125 ok / 20 条 HTTP 429）。
- 产物 `semantic_repaired.jsonl`（120 卡）、`semantic_repair_log.jsonl`。
- **无变不调用**：prompt 指纹命中即复用缓存；写盘前先 `gate_v2.fix_citations` 规范化引用，否则模型会把未规范化引用误报成 `bad_citation`。

标签合计 **276**：`keep_rule 84` / `narrow_scope 134` / `mark_unclosed 27` / `meta_discourse 28` / `bad_citation 3`。
`label_problems: idx_not_in_scope 4` —— 模型多答了范围外的 idx，脚本丢弃，不采纳。

### 4.1 LLM 分类 ≠ 审核标签（明例）

- **伤害结算-4-3:0**：我判**元话语/方法论**，LLM 判 `narrow_scope`。**结论相同（都要求移出通则段）但分类不同**——分类不可当真值，只用于定位。
- **语言标签漏检**：LLM 漏掉 16 条元话语（第 6 节覆盖层），这些都是我读正文时逐条找到的。LLM 的 `keep_rule` 不代表「已核机制」，只代表「LLM 未发现可降级理由」。

**权威关系（本版更正措辞）**：我的判定是**代理证据审核标签，它不是人工审核真值，仍可能出错**；LLM 只能做**单调收紧**（追加降级），不能把确定性降级改回保留。两类标签都不构成人工审核。

---

## 5. gate v2：通则位 + 命题级覆盖

`gate_v2.py --apply` → `gated_default_v2.jsonl` / `gated_archive_v2.jsonl` / `gated_old_kept_v2.jsonl` / `gate_log_v2.jsonl` / `gate_summary_v2.json` / `coverage_residual.json`。

### 5.1 两处结构性修正

**(a) default 层只准放通则范围语义。** 规则自身 `scope=instance/example` 不得坐在 universal 卡的肯定段通则位 → `demote_rule_scope_instance` **232** 条降为实例段。**通则位收口只对卡 `scope=universal` 生效**，卡 scope 本来就不是 universal 的不受影响。

**(b) supersedes 改成命题级，不再「被 cited 就算完整覆盖」；本版再把判据保守化。**

第三轮收尾前的口径是「**字符二元组覆盖率 `COV_THR=0.7` 即视为完整覆盖**」。这个口径有两处站不住，本版一并更正：

1. **措辞错**：0.7 是**字符二元组相似度**，**不是语义蕴涵**，**不能称「充分覆盖」**。
2. **判据太松会误删**：「同样的字，意义可能相反」——「不需要命中」与「需要命中」的二元组相似度极高，但命题相反。「需要命中」被「不需要命中」supersede 掉是**内容损失**，不是去重。

现在的判据（`gate_v2.supersede_verdict(prop, txt)`）：

| 情形 | 判据 | 是否授权 supersede |
|---|---|---|
| 命题是正文的**精确子串** | 1.0 | ✅ 且仍须否定/数值/条件兼容 |
| 精确子串，但**否定极性翻转**（前缀窗口 6 字：不/没/未/非/无/别/难道/并非；后缀：不成立/是错的/不对/为假/不存在） | — | ❌ 拒绝，旧条保留 |
| 精确子串，但**数值不一致**（`prop_nums()` 归一中文数字后比对） | — | ❌ 拒绝，旧条保留 |
| 精确子串，但**条件短语不兼容**（`prop_conds()`） | — | ❌ 拒绝，旧条保留 |
| **仅近似**（二元组 ≥0.7 但非子串） | ≥0.7 | ❌ **只登记候选，不删除** |

- `COV_THR=0.7` 保留，但**只用来找候选**；`gate_v2.py` docstring 已写明「是字符相似度，不是语义蕴涵，绝不能单独授权删除」。
- 旧 `entry`/`cluster`：仅当 `## 规则` 下**全部命题**都过 `supersede_verdict` 才移除。
- 旧 `atom`：仅当被 default 肯定规则**引用且**过 `supersede_verdict` 才移除；否则保留并写 `retention_reason`，同时进 `coverage_residual.json`。
- **共享来源不误删**：被 archive 侧 fc1 引用的原子一律保留（`old_atom_retained_shared_source 3277`）。
- 新增产物 `coverage_candidates_approx.json`：**只候选、不删除**的近似命中，供人工后续核查。

**局部边界自检**（`check_coverage_boundary.py`，纯本地零 LLM，13 条对抗样例，**ALL PASS** → `coverage_boundary_check.json`）：

覆盖「精确复述应删 / 中文数字归一 / 否定前缀翻转必须保留 / 否定后缀翻转 / 条件短语被前缀守卫拦下（保守方向）/ 同字反义『需要命中』vs『不需要命中』/ 数值冲突 600-700 / 数值冲突 0.1-0.5 仅近似 / 条件缺失 / 条件兼容应删 / 纯近似改写只能候选 / 空命题 / 长正文精确包含」。
含结构不变式断言：**`ok=True` ⇒ 命题必是正文的精确子串**。

**代价是「少删」而不是「多删」**：收紧后 `old_atom_removed_fully_covered` 从 5467 降到 **3061**，`n_residual_fc1` 从 342 升到 **1058**、`n_residual_atoms` 从 592 升到 **2997**。**这是刻意的**——需求是「不为缩库误删」，宁可多留。

| 覆盖指标 | v1（第二轮） | build2（上一版报告） | **build3（本版）** |
|---|---|---|---|
| `old_atom_removed_fully_covered` | 6413 | 5467 | **3061** |
| `old_removed_fully_covered_by_default_fc1` | 2684 | 715 | **147** |
| `old_atom_retained_partial_coverage` | — | 592 | **2977** |
| `old_atom_retained_shared_source` | — | 3279 | 3277 |
| `old_atom_retained_uncited` | — | 3879 | 3876 |
| `old_retained_partial_coverage`（entry 级） | — | 1963 | **2529** |
| `old_retained_fc1_not_default` | — | 2153 | 2153 |
| `old_atom_retained_conflict_guard`（否定/数值/条件守卫拦下） | — | — | **20** |
| `cov_rejected_by_guard` | — | — | **74** |
| `cov_candidate_approx`（仅候选，未删除） | — | — | **4096** |
| `old_quarantined_registry_drop` | 12 | 12 | 12 |
| `n_residual_fc1` / `n_residual_atoms` | — | 342 / 592 | **1058 / 2997** |

> build2 那一列的数字来自上一版报告，其 `gate_summary_v2.json` 已被后续运行覆盖；`build1/gate_summary_v2.json` 保存了同一判据的 dry-run 副本（5481 / 716 / 593），与此列口径相同但早一步（覆盖层尚未并入），可作旁证。

### 5.2 其他 gate 动作（build3）

build3 的 stats 与 build2 **逐项相同**（本轮收尾只改了 registry 分支与覆盖判据，未动这些动作）：

| 动作 | 数 |
|---|---|
| `cite_normalized`（引用规范化：补 `p1_<id>` 前缀等） | **438** |
| `cite_recovered`（可从原字幕行还原的引用） | **7** |
| `cite_unresolvable_refs`（仍无法解析） | **0** |
| `cards_with_citation_fix` | 108 |
| `gate_ctx_only_evidence`（仅 ctx 支撑 → 待核） | 428 |
| `gate_unclosed_family`（D01 系列声明未闭合） | 92 |
| `demote_llm_narrow_scope` | 30 |
| `gate_llm_mark_unclosed` | 27 |
| `gate_llm_meta_discourse` | 28 |
| `gate_llm_bad_citation` | 3 |
| `audit_overlay_applied`（覆盖层，见第 6 节） | 16 |
| `gate_audit_meta_discourse` | 16 |
| `archive_all_rules_gated`（肯定段清空 → 整卡 archive） | 10 |
| `demote_rule_scope_instance` | 232 |
| `default_instance_only`（无通则但保留实例，`boost=0.5`） | 5 |
| `gate_atom_registry_drop` | 2 |
| `old_downweighted`（registry `downweight` 生效） | **7**（上一版为 0，见 5.3） |
| `old_keep_unknown`（registry `keep_unknown`） | **1**（上一版为 0） |

`affirmative` 为空但有 demoted 实例的卡：`layer=default` + `instance_only=true` + `retrieval_boost=0.5`（只有全部进待核才整卡 archive）。这是「保留未缺主体的实质规则」的实现方式（`技能特例-15-1`、`状态效果-7-1` 即此例）。

### 5.3 X07 可复现回归：根因与修复（本版新增）

**先把「提高预算 / 提高 k」这条错路排掉。** `x07_diagnose.py` → `x07_diagnosis.json`：

| 审计项 | 结果 |
|---|---|
| 30 题两面 top-k 命中数 | 全部 = 6（`k=6` 就是上限） |
| `n_at_budget`（受 3000 字预算截断的题） | **0** |
| `n_hits_cut_by_budget` | **0** |
| `ctx_chars` 中位数 | 旧 2031 / build2 1813；X07 自身 旧 1408 / 新 1005 |

→ **3000 字上下文预算从不生效，`k=6` 是唯一紧约束；「提高预算」对这个回归没有任何作用，改预算是无据调参。**

**真实根因两条**：

1. **`gate_v2.py` 丢了 v1 的 registry `downweight` / `keep_unknown` 分支。** 第二轮 `retest_round2/quarantine.jsonl` 里有 21 条 registry 决定（`drop 13 / downweight 7 / keep_unknown 1`），其中**恰好有一条针对 X07 的挤占源**：
   `vod_entry:帧时序与计时器-40-13`（领主「阻挡立刻抬手」实例）→ v1 `gate.py:281-288` 把它降为 `boost 0.15 / weight 0.3`（eff 2.41）；v2 漏掉该分支 → 该文档回落生产值 `boost 1.6 / weight 1.0`（eff **85.08**）→ 抢进 X07 的 top6 第 4 位。**v2 原地复现了第二轮已经修掉的挤占。**
   已修：三分支恢复（`downs` → `boost 0.15 / weight 0.3` + `registry_action="downweight: …"`；`keeps` → `keep_unknown` 标注；`drops` 维持原有隔离）。build3 统计里 `old_downweighted 7` / `old_keep_unknown 1` 即这条修复的可见痕迹（build2 均为 0）。校验器新增 **C12_registry_parity** 逐条复核这 8 条落位。
2. **`retrieval_weight` 差异（刻意，不是 bug）**：build2/v2 保留了第二轮的 D 类 `retrieval_weight=0.6`，v1 在 gate 里硬编码 1.0。`fc1:索敌-16-0` 因此 eff 由 78.33 降到 46.41（rank 5 → ~95）。**保留并如实披露**：这是「旧默认层 vs 新默认层」的真实差异，两侧都没为对齐而改权。

**修复效果**：X07 由 build2 的 0.75（可复现欠断定）回到 **1.0**。归因脚本 `attribute_noquota.py` 另有决定性发现——**build3 关掉配额**时 X07 三次采样里两次都明确作答「不能…阻挡帧由部署决定，按部署相位走，不会像索敌那样立刻归零」（≈1.0），一次 abstain。**即：registry 对齐本身就把 X07 修好了，同源配额不是必要条件。**

### 5.4 同源配额评估：三种模式对照（本版新增）

需求要求在**不动 k、不动字数预算、不为任何单题硬编码**的前提下，尝试「同 cluster 重复文档去重 / 配额，按 source coverage 保内容多样性」。三种模式都用同一份冻结 30 题、同一 BM25、同一 k=6、同一 prompt。

配额定义（`trial_rag_v3.group_key`）：

| 模式 | 折叠范围 |
|---|---|
| `all` | 任何共享 `cluster_id` / `links.cluster_ids` 的文档互为同源（含 `er1:` / `B1xx` / `canonical` / `vod_atom`） |
| `layer_only` | **只折叠同一簇的分层表示**（`fc1:` / `vod_entry:` / `vod_cluster:`）。独立证据卡与原始原子不折叠——它们各自承载不同来源的真实内容，不是同一文档的复述 |
| `off` | 不折叠（等价原检索） |

**本地零 LLM 的锚点核查**（`quota_check.py` → `quota_check.json`）：

| 锚点 | `all` | `layer_only` | `off` |
|---|---|---|---|
| F04 gold 独立证据卡 `B074-imbalance-speed-separate` 在 top6 | ❌ | ✅ | ✅ |
| F06 gold 独立证据卡 `B036-path-not-wallhack` 在 top6 | ❌ | ✅ | ✅ |
| 合计 | **2/4** | **4/4** | **4/4** |

→ **`all` 有已证实的副作用：把 gold 的独立证据卡当作同簇重复挤掉。** 这是弃用 `all` 的直接依据（不是分数，是具体文档被挤掉）。

**同一核查里更重要的一个中性结论**：把「gold 文档本身进 top6」放宽为「**与 gold 同簇的任一文档**进 top6」后，三种模式的得分**完全相同**——旧语料 26/30、新语料 26/30（`via_sibling` 计数：all 15 / layer_only 13 / off 8）。

> 附带的度量缺陷更正：`trial_rag.retrieval_metrics()` 里的 `hit_gold_cluster` **恒为 0**——它拿 `fc1:伤害结算-12-18` 这类 gold id 直接和 `伤害结算-12-18` 这类 cluster id 比，忘了剥 `fc1:` 前缀。本版一律改用 `quota_check.py` 的 `family_hit`（剥前缀 + 查 doc 自身 `links.cluster_ids`）。**旧报告里「gold 进 top6：旧 26 → 新 19 / 11」这类数字是严格 id 匹配的产物，不能读成信息丢失。**

**真实 LLM 对照**（只调用 ctx 改变的题，其余按 **ctx 指纹**复用上一代答案行）：

| 版本 | 配额模式 | 调用数 | 新面均分 | `gold_hit_new`（严格 id） | 新面引用不可定位 |
|---|---|---|---|---|---|
| v3 | `all` | 42 | 0.958 | 11 | 0 |
| **v4** | **`layer_only`** | 40 | **0.958** | 13 | 0 |
| v5 | `off`（消融，只跑新面 20 题） | 20 | 0.942 | 18 | 2 |

**采用 `layer_only` 的理由**（按证据强度排序）：

1. `all` 有具体文档被挤掉的实证缺陷（上表锚点）。
2. `layer_only` 在**信息可得性上与 `off` 等价**（family 26/30 两侧相同），但把「同簇的分层表示」收敛成一个槽位，腾出的槽位给了真正不同的来源。
3. `layer_only` 的新面均分不低于 `all`（0.958 = 0.958），且**没有 `all` 的挤占缺陷**。
4. `off` 更低（0.942），且新面出现 **2 条不可定位引用**（裸簇名 `技能特例-21-11` / `技能特例-15-1`，归一化后不落在任何 ctx 文档上）；`layer_only` 为 0。消融里 `off` 修好了 N07、却把 N08 答反（见第 9.6 节），净负。
5. **诚实披露**：`off` 的 `gold_hit_new` 更高（18 vs 13）是**度量口径的产物**——它允许同簇的分层表示重复占位，于是 `fc1:<cid>` 这类 gold id 更容易出现在 top6；按 family 口径两者相同（第 5.4 节上表）。**不作为 `off` 更优的证据，也不作为 `layer_only` 更差的证据。**

**没做的事**：配额只落在评测脚本（`trial_rag_v3.py`）里，**没有改进生产检索**（`kb_search.py` 未动）；也没有为任何单题调参。


---

## 6. 审核覆盖层（计划外增补）

抽检复查后确认：**LLM 复核只做单调收紧，漏掉的元话语无法自动回收**。代理读修复后正文时逐条找到 **16 条规则 / 6 张卡**仍在通则段：

| 卡 | idx | 性质 |
|---|---|---|
| 帧时序与计时器-11-13 | [0,1,2,4,5,6,7]（整卡 7 条） | 数据精度方法论/宣教（「有备则无患」「不必把 142.5 算成 142」） |
| 帧时序与计时器-19-8 | [3,4,5] | 调帧操作手法 |
| 寻路-10-2 | [0,6] | 自测出题方法 |
| 其他-3-22 | [2] | 观察者经验谈 |
| 帧时序与计时器-63-3 | [10] | 能力要求清单 |
| 索敌-12-3 | [4,10] | 对 PRTS 的评价 + 命名学 |

`audit_overlay.py` → `audit_overlay_llm_miss.jsonl`。回填 idx 用**锚句唯一命中**（唯一命中失败则脚本报错退出），不使用显示顺序索引。标签 `meta_discourse`，`reviewer_type=agent`，`source=audit_spotcheck_30`。

`gate_v2.py` 打 3 处补丁：读 overlay 与 LLM 标签合并（`authority: agent_audit`）；通则位收口 reason 用 `audit_` 前缀；stats 计 `audit_overlay_applied` / `gate_audit_meta_discourse`。

**效果**：`帧时序与计时器-11-13` 肯定规则被清空 → 整卡入 archive。

### 6.1 一起被推翻的假警报

`spotcheck_worksheet.md` 的 `llm=` 列按「正文显示顺序」索引标签，出现「LLM 判 meta_discourse 却仍在通则」的假象。`label_application_check.py` 按**规则文本回溯真实 idx** 后证明：**276/276 条标签全部正确落位，0 mismatch**（`label_application_check.json`）。该工作表列不可信，已在 `spotcheck_verdicts.json` 显式记录。`label_index_check.py` 是更早的废弃版本。

---

## 7. 产出计数：最终 default / archive / retained（含 quarantine 12）

口径：build3 = `gate_v2.py --apply` 的最终产物（`gate_summary_v2.json` + `validate_gates_v2.py` 独立复算一致）。

### 7.0 三层最终计数（本版表格）

| 层 | 文档数 | 说明 |
|---|---|---|
| **`gated_default_v2.jsonl`（默认检索层）** | **1,339** | fc1 卡；v1 口径为 1,343，净减 4（整卡 archive 10 − 从 v1 归档里捞回/新增 6） |
| **`gated_archive_v2.jsonl`（拒绝层）** | **1,091** = 1,079 fc1 + 12 registry drop | `archive_kind_or_review 1069`（pending 987 / reject 82，第二轮已定）+ 规则级全清空 10 卡 |
| **`gated_old_kept_v2.jsonl`（保留旧层）** | **21,801** | 相对 v1 的 15,912 多留 **5,889** 条；相对上一版报告的 18,827 多留 **2,974** 条（= 覆盖判据保守化带来的「少删」） |
| ↳ 其中 **quarantine** | **12** | `old_quarantined_registry_drop`：第二轮 registry 判定 `drop` 的旧文档，隔离不删 |
| **旧层被移除** | **3,208** | 全部走 `supersede_verdict`（精确包含 + 否定/数值/条件兼容） |
| **未被本轮触及的其它文档** | 6,961 | `other_docs_untouched` |

> 三层的行数一致性由 `validate_gates_v2.py` 独立复算（`n_default 1339 / n_archive 1091 / n_old_kept 21801 / n_removed_old_docs 3208`），与 `gate_summary_v2.json` 自报值一致。

### 7.1 实际生成（进入 default 层）

`gate_log_v2.jsonl` 聚合（build3，1339 条 default 行）：

| 段 | 规则单元 |
|---|---|
| **肯定段（affirmative，默认检索可见）** | **5,463** |
| 实例段（demoted，非通则） | 262 |
| 待核段（gated，provenance 隔离） | 565 |
| 合计 | 6,290 |
| （对照）v1 口径肯定单元 | 5,785 |

> 用法修正：`usage_semantic.json` 只含最后一次运行的增量（5 calls / 6,230 tok），**不是本阶段总量**；总量见 `usage_ledger_v2.json`（`events_semantic.jsonl` 聚合）。

### 7.2 拒绝（进入 archive 层）

`fc1` archive **1,079** 卡，其中 `archive_kind_or_review 1069`（pending 987 / reject 82，第二轮已定），规则级全清空入 archive 10 卡。另 + 12 条 registry drop 旧文档 = **1,091 行**。

### 7.3 待补证（待核段）

default 层内**待核段 565 单元**（+ archive 侧 31 单元），来源见 5.2 表。待核段不进默认检索，只在题面/元数据中可见并标注 `⚠未闭合`。
`coverage_residual.json` 里的 `n_residual_fc1 1058` / `n_residual_atoms 2997` 是**旧层保留侧**的残差台账（保留原因逐条写明），**不是待核段**。

### 7.4 复核（与「生成」分栏）

- **冻结 30 题逐题判分**（第 9 节，代理判分 + 引用核验；v3/v4/v5 三代）。
- **抽检**：`spotcheck_v2.py` → `spotcheck_v2.md`（30 张确定性随机 + 10 张重点议题，seed `20260920`，含每条规则的证据原子命题 / scope / 原片引文 / 字幕上下文行）；`spotcheck_verdicts.json` 记录 30 张逐卡判定（6 条 `residual_fixed`、1 条 `borderline`、1 条 `minor`、其余 `ok`）。
- **标签落位校验**：`label_application_check.py`，276/276 全对。
- **覆盖判据边界自检**：`check_coverage_boundary.py`，13/13 对抗样例全过。
- **registry 落位校验**：`validate_gates_v2.py` C12，8/8 条正确。
- 悬空引用：抽检渲染中 **0 条**。

---

## 8. 具体恢复 / 隔离了什么

**恢复（原本要丢，实际修好）**

- `状态效果-8-0:0-3`：`sub:` 缺前缀的畸形引用可还原 → 引用修好，规则回通则。
- `寻路-36-5`（刹车计算）：v1 里漂移的引用 `BV1TomVBBEK1_p1:a2:ec71e01d` 规范回 `BV1TomVBBEK1_p1_34675165371:p10:a2:ec71e01d` → 该条**未被隔离而是被修好**。
- **`vod_entry:帧时序与计时器-40-13` 的 registry `downweight`**：build2 丢失该分支致其以生产权重挤占 X07 的 top6，build3 恢复后 eff 由 85.08 降到 2.41（见 5.3）。
- 引用规范化合计 **438 + 7 = 445** 处，无法解析的引用归零。
- **覆盖判据保守化额外救回约 2,400 个旧原子**（本会被「相似度 ≥0.7」删掉，现因否定/数值/条件守卫保留；其中 20 条由守卫直接拦下、4,096 条登记为「仅候选」）。

**隔离（确有语义问题）**

- `其他-3-17`、`技能特例-21-11`、`帧时序与计时器-11-13` → archive（`all_rules_non_affirmative`）。旧词条保留，`retention_reason = 「fc1 只有 archive 层(pending/reject/待核全隔离), 未可靠替代」`。
- 16 条元话语规则（6 卡）→ 待核段，`reason` 以 `audit_` 前缀标记来源。
- 其他-3-22 / 寻路-10-2 / 帧时序与计时器-19-8 / 帧时序与计时器-63-3 / 索敌-12-3 只隔离问题条目，同卡真机制条目保留。

**保留（防止误删）**：3,277 个共享来源原子、3,876 个未被 default 引用的原子、2,529 条部分覆盖 entry、20 条冲突守卫拦下项。

---

## 9. 冻结 30 题对照评测

### 9.1 冻结

`freeze_v2.py` → `heldout_q_v2.jsonl` + `heldout_v2_frozen.json`，**sha256 `690e78f01c2e05887a1ba95bde8b3fe58f3951e1d019ca10533d2bb27e7f95fc`**，冻结后不再修改，评测脚本先校验 sha。

组成：F01–F07（原冻结 7 题）+ X03/X07/X11/X13/X14/X16（20 题集失败样本）+ R03/R05（retest 失败样本）+ **N01–N15（15 道新题，覆盖 5 个未参与调参的新议题 + 范围误导 / 缺主语 / 符号单位 / 原公式 / 有效例题）**。
题型：direct 13 / insufficient 7 / misleading 5 / boundary 4 / citation 1。

### 9.2 口径（两侧严格相同）

同一 BM25（bigram）/ k=6 / 每片段 500 字 / 上下文上限 3000 字 / 同一 prompt（复用 `trial_rag.PROMPT`）/ workers=4 / 两侧都做 QQ 号脱敏（`T.scrub`）。缓存键 `side|qid|corpus_sha`。

`old` = v1 语料（`gated_old_kept.jsonl` + `gated_default.jsonl` + pilot_extras）= **17,340 篇**；
`new` = v2 语料（`gated_old_kept_v2.jsonl` + `gated_default_v2.jsonl` + pilot_extras）= **20,251 篇**。

**必须说明的口径差异**：v2 会把第二轮的 D 类 `retrieval_weight=0.6` 带进 default（v1 在 gate 里硬编码为 1.0）。两侧语料是真实的旧默认层 vs 新默认层，没有为了对齐而改权。

### 9.3 逐题对照（build2 最终）

| 题号 | 类型 | 旧分 | 新分 | 标签 | | 题号 | 类型 | 旧分 | 新分 | 标签 |
|---|---|---|---|---|---|---|---|---|---|---|
| F01 | direct | 1.0 | 1.0 | neutral | | N01 | misleading | 1.0 | 1.0 | neutral |
| F02 | direct | 1.0 | 1.0 | neutral | | N02 | direct | 0.75 | **1.0** | **fix** |
| F03 | direct | 1.0 | 1.0 | neutral | | N03 | direct | 1.0 | 1.0 | neutral |
| F04 | boundary | 1.0 | 1.0 | neutral | | N04 | direct | 1.0 | 1.0 | neutral |
| F05 | insufficient | 1.0 | 1.0 | neutral | | N05 | insufficient | 1.0 | 1.0 | neutral |
| F06 | misleading | 1.0 | 1.0 | neutral | | N06 | direct | 1.0 | 1.0 | neutral |
| F07 | direct | 1.0 | 1.0 | neutral | | N07 | misleading | 0.5 | **1.0** | **fix** |
| X03 | direct | 1.0 | 1.0 | neutral | | N08 | misleading | 0.0 | **0.75** | **fix_partial** |
| X07 | boundary | 1.0 | **0.75** | **regression** | | N09 | boundary | 1.0 | 0.75 | neutral |
| X11 | insufficient | 1.0 | 1.0 | neutral | | N10 | insufficient | 0.75 | **1.0** | **fix** |
| X13 | direct | 1.0 | 1.0 | neutral | | N11 | direct | 0.5 | 0.5 | neutral |
| X14 | insufficient | 1.0 | 1.0 | neutral | | N12 | misleading | 1.0 | 1.0 | neutral |
| X16 | boundary | 1.0 | 1.0 | neutral | | N13 | direct | 1.0 | 1.0 | neutral |
| R03 | direct | 1.0 | 1.0 | neutral | | N14 | insufficient | 1.0 | 1.0 | neutral |
| R05 | insufficient | 1.0 | 1.0 | neutral | | N15 | citation | 0.5 | 0.5 | neutral |

**均分 旧 0.90 → 新 0.942**（n=30 单次采样，不构成统计结论）。
分档：旧 `{1.0:24, 0.75:2, 0.5:3, 0.0:1}` → 新 `{1.0:25, 0.75:3, 0.5:2, 0.0:0}`。
标签：`fix 3 / fix_partial 1 / regression 1 / neutral 25`。

错误码：旧 `{none:25, missed_fact:3, cite_format:1, failed_abstain:1}` → 新 `{none:24, missed_fact:5, cite_format:1}`。
引用核验：旧 75 条（74 在 ctx 内 / 1 裸层前缀 / **0 编造**）→ 新 80 条（79 / 1 / **0 编造**）。
gold 进 top6：旧 26/30 → 新 19/30。（**该指标口径有缺陷，见 5.4 节末尾**；放宽为「同簇任一文档」后为 26/30，两侧相同。）

### 9.3b 后续两代：v4（build3 语料 + `layer_only` 配额）与 v5（消融）

只调用 **ctx 指纹改变**的题；ctx 未变的题按指纹复用上一代答案行（这正是「只复核改变的题」的实现，缓存键 = `side|qid|sha256(ctx)`）。

| 版本 | 语料 | 配额 | 调用数 | 旧面均分 | 新面均分 | 新面分档 | 标签 |
|---|---|---|---|---|---|---|---|
| build2（上一版） | v1 vs build2 | 无 | 92 | 0.90 | 0.942 | `{1.0:25, .75:3, .5:2, 0:0}` | fix 3 / fix_partial 1 / regression 1 / neutral 25 |
| v3 | v1 vs build3 | `all` | 42 | 0.908 | 0.958 | `{1.0:26, .75:3, .5:1, 0:0}` | fix 4 / fix_partial 1 / regression 1 / neutral 24 |
| **v4（推荐配置）** | **v1 vs build3** | **`layer_only`** | 40 | 0.933 | **0.958** | `{1.0:26, .75:3, .5:1, 0:0}` | **fix 1 / fix_partial 1 / regression 1 / neutral 27** |
| v5（消融） | v1 vs build3 | `off` | 20 | 0.933 | 0.942 | `{1.0:27, .75:1, .5:1, 0:1}` | fix 2 / regression 0 / neutral 28 |

v4 引用核验：旧 78 条（77 在 ctx / 1 裸层前缀 / **0 编造**）→ 新 88 条（86 / 2 / **0 编造**）。
v5 引用核验：新 94 条（91 在 ctx / 1 裸层前缀 / **2 条不可定位**：裸簇名 `技能特例-21-11`、`技能特例-15-1`）。

### 9.4 硬约束核验

| 要求 | 结果 |
|---|---|
| F06 不得改成「一律不对」 | ✅ 三代两侧都检查证据关系（卡墙只决定**何时不传送**），未简单否定 |
| F05 未核定项不得当已知 | ✅ 两侧都未把未核定项当已知结论 |
| 无编造引用 | ✅ v4 两侧 `not_in_ctx` 均为 0；v5 新面有 2 条不可定位（已计入扣分项，见 9.3b） |
| 无新增严重错误（断言虚假事实） | ✅ v4 本轮新增的扣分**全部**是「欠断定/未用足上下文」，没有一条断言了错误事实。**v5（`off`）例外**：N08 断言了相反极性（0.0），已如实记录 |
| 不隐藏回归 | ✅ X07 的回归在上一版被列为唯一回归，本版记录其根因、修复与归因，**不撤回上一版的记载** |

### 9.5 测量噪声基线（本版新增，重要）

**同一套旧面检索条件下重采样一次，均分从 0.90 变成 0.933。**

依据：`quota_check.py` 证明 **`layer_only` 在 v1 旧语料上给出与无配额逐题完全相同的 top6（30/30 题 ctx 完全相同）**；因此 `build2/answers_v2_old.jsonl`（无配额）与 `answers_v4_old.jsonl`（`layer_only`）是**同一检索配置**，两者 30 题 ctx 逐题一致，只有 15 题因重新采样而答案文本不同。

| 对照 | 检索是否相同 | 旧面均分 | 差值 |
|---|---|---|---|
| build2 旧面（无配额） | — | 0.90 | — |
| v4 旧面（`layer_only`，旧语料上 ≡ 无配额） | **逐题 top6 相同** | 0.933 | **+0.033** |

→ **±0.033 的噪声带（= 一个整档 0.25 分，落在 2 道题上）**，来自单次采样方差 + 我的复核口径漂移，与语料和检索无关。

**因此**：三代里所有「新面 − 旧面」的差值（+0.042 / +0.050 / +0.025）**全部落在噪声带内**，不能宣称新旧面有可分辨的总体提升。可以主张的是**内容级**的具体变化（9.6 节逐条可读），以及**具体文档被挤掉/被救回**这类可核事实。

### 9.6 逐条可读的修复与回归（v4 口径）

**修复 / 部分修复**

- **N02**（旧 0.75 → 新 1.0）：旧面只答「真伤跳过抗性结算环节」，**漏了「仍吃伤判、因此可增伤减伤」**；新面完整：「真伤跳过的是抗性结算环节，但仍会进入伤判，因此可被增伤/减伤；生命流失跳过的是判定步骤（伤判），但不跳过计算步骤。」
- **N08**（旧 0.0 → 新 0.75，`fix_partial`）：旧面把评价性元话语直接当机制（「是机制结论…明确列为可复用规则」）→ 与期望**相反**；新面改为「不能据此升格为永恒的机制结论…只能确认片段把 PRTS 描述定位为基础设置参考」，方向正确但未点明「是元话语、已隔离」。
- **X07**（旧 1.0 → 新 1.0，**上一版的唯一回归已消除**）：见 5.3 节。新面本次更直接落锤：「不会。阻挡帧与索敌帧不同：索敌帧在眩晕结束时立刻触发，而阻挡帧由部署决定（部署之后 3N 加一帧），按部署相位，不能理解成索敌那种立刻归零。」
- **F04 / F06**（配额副作用修复）：`all` 模式把 gold 独立证据卡挤掉，`layer_only` 恢复（见 5.4 节锚点表）。

**仍回归（1 条，与上一版同因，非本版新引入）**

- **N09**（旧 1.0 → 新 0.75）：新面收在「无法判定它是机制限制还是操作建议，也没有达到已定论状态」，**欠断定**；未断言错误事实。`off` 变体同样 0.75，`all` 变体同 0.75 → **与配额模式无关**，是语料侧（`技能特例-15-1` 的同类条目只剩待核标记）+ 模型保守倾向的合成结果。

**v5 消融暴露的一对反向变化（说明总量差异不可当因果）**

- **N07**：`layer_only` 0.75（「不能据此判定为底层机制…只是一个具体条件触发的规则」）→ `off` **1.0**（直接落「不是底层机制」）。
- **N08**：`layer_only` 0.75（方向正确）→ `off` **0.0**（「这条属于机制结论」断言相反）。
→ 一正一负相抵，**这是「同一问题在不同 ctx 上采样」的结果，不是某个配额模式更懂机制**。记录在此以免被读成结论。

**上下文中曾被扣分、本版不再出现的项**

- **N03 / N05 / N11 / F05** 的旧面本轮由 abstain 改为作答（旧面各自 +0.25）。**必须标注**：这些旧面变动由**检索配置改变旧面 ctx** 引起，**不是新面变好**；`v3`（`all`）与 `v4`（`layer_only`）之间旧面均分 0.908 → 0.933 的差就来自这里（同样落在 ±0.033 噪声带内）。

### 9.7 判定为方差、不计入回归

- **R03**：build1 起手「不需要」，build2「会。」；补采样 2/3「需要」→ 模型方差。
- **N12**：build1 的空答是 HTTP 429 落盘的 `abstain`，不是模型行为。
- **X16** 裸层前缀引用：build2 未复现，**v4 亦未复现**。

### 9.8 gold top6 命中 26 → 19 的归因

未进 top6 的 7 例（N01/N02/N05/N06/N07/N08/N09）**全部是新题**。逐题核对：

- 6 例的**等价内容仍在 ctx 内**（只是文档 id 不是 `fc1:`），新管线把部分 fc1 主动降级/隔离后由旧词条或原子接住；
- N06 由原始原子 `BV14VZCB1EJR_p1_36119907781:p111:a0:bbfa0a34` 直接接住（原文即「炸死炸不死临界值取点、三点画圆」）。

因此该指标下降主要反映 **「gold 只认 `fc1:<cid>` 文档」与「新管线主动降级/隔离部分 fc1」的结构差异**，不等同于信息丢失，但也不排除个别 case 实质受损（X07 即此类）。**不作为提分证据。**

---

## 10. 校验器与既有自测

`validate_gates_v2.py` → `gate_validation_v2.json`：**硬违规 0**，C1–C12 全绿。
独立复算结果：`n_default 1339 / n_archive 1091 / n_old_kept 21801 / n_removed_old_docs 3208`，与 `gate_summary_v2.json` 自报值一致；`notes.c12_checked = 8`。

| 检查 | 结果 |
|---|---|
| C1 分层合法性（default / archive） | 0 |
| C2 通则位违规（规则 scope=instance 坐在 universal 卡肯定段；需镜像「仅 universal 卡」条件） | 0 |
| C3 pending/reject 混入 default | 0 |
| C4 无覆盖理由删除（本版收紧：改用与 gate 相同的 `supersede_verdict` 复算，近似相似度不再算覆盖） | 0 |
| C5 无效引用 | 0 |
| C6 F05 出现在肯定段 | 0 |
| C7 residual 一致性 | 0 |
| C8 共享来源误删 | 0 |
| C9 不可复现（重跑 `--outdir _repro`，四文件 sha 相同） | 0 |
| C10 输入被修改 | 0 |
| **C11 覆盖层落位**（每条 overlay 判定必须不在 affirmative、在 gated_rules 内、reason 以 `audit_` 开头） | 0 |
| **C12 registry 落位对齐**（新增：`downweight` 条目必须 `boost≈0.15 & weight≈0.3`；`keep_unknown` 必须带 `registry_action` 前缀；共核 8 条） | 0 |

**既有自测**（改后重跑，生产只读）：

```
python ../full_candidate_round1/validate_full.py
# {"ok": true, "n_err": 0, "n_synth": 2418, "kinds": {"mechanism":1242,"reject":82,"experiment":158,"pending":936},
#  "n_cache_items": 2418, "heldout_sha": "ddedeca6efae5545"}

python ../full_candidate_round1/validate_gates.py
# {"hard_total": 0, "layers": {"default":1343,"archive":1087,"old_kept":15912,"old_ids":25021,"old_removed":9097},
#  "checks": {"C4_removed_atom_covered_by_citation": 6413, "C4_removed_cluster_covered_by_default_fc1": 2684}}

python kb_eval.py            # 在仓库根目录执行, 不是 kb/ 下
# {"manual_hit": 22, "manual_total": 22, "blind_total": 74, "blind_r5": 68, "blind_r1": 52}
```

`kb_eval` 读的是生产 `kb/docs.jsonl`（25021 条）。本轮**未修改生产**（sha256 `b835a8bfec6a7bb3…` 前后一致），因此该输出按构造等同于改动前基线，可作回归参照——但**并不是**本轮新跑出来的一次独立对照。`kb_eval_report.md` 头部记录的也是 `22/22` 与同一语料 25021 条。

---

## 11. 本阶段用量（下界）

`usage_ledger_v2.py` → `usage_ledger_v2.json`（本版已并入第三轮收尾的四段调用）。

| 段 | 成功调用 | 失败尝试 | tokens | 墙钟 |
|---|---|---|---|---|
| 语义定向复核（3 遍） | 125 | 20（HTTP 429） | 148,224 | 763.1 s |
| 冻结 30 题对照（build1 双侧 + build2 新侧） | 92 | 2（HTTP 429） | 131,641 | 172.85 s |
| 方差复采（X07/N12/R03 ×3） | 9 | 0 | 12,895 | — |
| **收尾段：v3 对照（配额 `all`）** | 42 | 0 | 59,972 | 81.63 s |
| **收尾段：v4 对照（配额 `layer_only`）** | 40 | 0 | 54,990 | 75.2 s |
| **收尾段：v5 消融（`off`，只跑新面 20 题）** | 20 | 0 | 25,389 | 42.18 s |
| **收尾段：X07 归因（关配额重跑 6 题）** | 6 | 0 | 6,879 | — |
| **合计** | **334** | **22** | **≥ 439,990** | **≈ 1,290 s** |

收尾段小计：**108 次调用 / 147,230 tokens**。

> token 口径：收尾段只统计**本轮真实发生的调用**（按答案行的 `reused_from` 过滤）；复用上一代答案行的题带着旧 usage，不计入，避免重复计数。因此 `trial_v3_usage.json` 里按行求和得到的 85,590 与这里的 59,972 不同，**以本表为准**。

**这是可核对下界，不是完整计费口径。** 未计入：

- 22 条 429 失败尝试的请求 token（网关未返回 usage，**不可恢复**）；
- 缓存命中而未发生的重复调用（本就不消耗；收尾段按 **ctx 指纹** 复用，v4 复用 20 行、v5 复用 40 行）；
- 第二轮 `full_candidate_round1` 的全部用量（不在本阶段口径）；
- 本地步骤零 LLM：`compute_scope.py`、`triage_e1.py`、`gate_v2.py`、`validate_gates_v2.py`、`freeze_v2.py`、`dump_ctx.py`、`spotcheck_v2.py`、`spotcheck_worksheet.py`、`label_application_check.py`、`audit_overlay.py`、`x07_diagnose.py`、`retrieval_matrix.py`、`check_coverage_boundary.py`、`quota_check.py`、`dump_v4_diff.py`、`dump_v5_quota_effect.py`、`make_verdicts_v5.py`。

API key 全程只经环境变量传入，**未落盘、未打印**；缓存只保存 prompt / model / prompt-hash，不含 key。

---

## 12. 未闭合项与风险

1. **X07 回归**：**已定位并修复**（5.3 节），v3/v4/v5 三代新面均为 1.0。**保留为本条的完整记录**（上一版曾列为「本轮未做」）。但 `retrieval_weight=0.6` 这一刻意差异仍在，未做全面回归测试。
2. **总分不可用**：±0.033 的噪声带 ≥ 三代全部新旧差值（9.5 节）。**任何「提升 X 分」的说法都不成立**；只能引用内容级证据与文档级事实。
3. **N09 欠断定**（唯一回归）：与配额模式无关，`all / layer_only / off` 三代新面全部 0.75。未处理。
4. **N07 / N08 对 ctx 敏感**：同一题在 `layer_only` 与 `off` 下给出方向相反的结论（9.6 节）。属模型保守倾向 + 检索细微变动的合成，**未处理**，只能标注「单次采样，慎引」。
5. **N15 两面都答不出时间**：期望给出文件与大概时间，两代都只到「BV1j4KCse p75」，时间戳在 ctx 里被 500 字截断。**未处理**，属检索片段长度限制。
6. **N10 冻结题面 `expect` 疑有误**：expect 写「部分原子引用在语料里找不到、已标待核」，但三面实际都能检索到 `fc1:寻路-36-5` 及对应 `vod_atom`，两面都答「有可追溯证据」。**未改冻结题**（改了就没有对照意义），如实记为 gold 侧疑点。
7. **v5 消融的新面有 2 条不可定位引用**（裸簇名 `技能特例-21-11` / `技能特例-15-1`）：属模型输出缺陷，非语料缺陷；`layer_only` 未出现。
8. **抽检覆盖不全**：120 张复核卡里只人工抽检 **40 张**（30 随机 + 10 重点）。30 张里仍有 3–5 张含轻度非机制内容（其他-9-1 术语约定、位移-26-1 具体摆法自称 universal、帧时序与计时器-19-8 的「拼好帧」条目），判断为可保留/存疑，**未改判**。
9. **LLM 漏检的覆盖只到「抽检发现」程度**：第 6 节的 16 条是抽检顺带发现的，不排除还有未被抽到的漏检条目。
10. **本轮未重做第二轮的全量 kind 重统计**：`mechanism/experiment/pending/reject` 的最终分布沿用第二轮 `postrepair_stats.json`；本轮只改规则级分层，未重算卡级 kind。
11. **覆盖判据保守化的代价尚未量化到内容层**：现在「宁可多留」约 2,400 个旧原子，其中是否仍有冗余、是否有应删未删，**未抽检**（只做了 13 条对抗样例的判据边界自检）。
12. **`gate_summary_v2.json` 的 `outdir` 字段显示 `_repro`**：验证器 C9 重跑时汇总写 HERE、数据写 `--outdir`，属实现细节；主目录四份数据文件与 `_repro` 副本 sha 逐个相同（本版已复核），计数不受影响。
13. **`build2/` 目录不是严格的「打补丁前」快照**：其中的 `gate_summary_v2.json` 已带本轮的保守覆盖字段（`cov_candidate_approx` 等），`apply=false`。真正的 build2 数字只保留在上一版报告中；`build1/gate_summary_v2.json` 是同判据的 dry-run 旁证。
14. **`spotcheck_worksheet.md` 的 `llm=` 列不可信**（显示顺序索引），已推翻，勿再据此下结论。`spotcheck_v2.py` 的规则解析要求 `| 条件: |` 字段，对缺该字段的卡会漏读（解析器缺陷，非数据缺陷；`寻路-2-3` 正文已核实正常）。
15. **配额只落在评测脚本**：`trial_rag_v3.py` 的 `layer_only` 没有回灌到生产 `kb_search.py`；若将来要在生产用，需要重新做一次生产侧检索评测（**本轮未做**）。
16. **`kb_pilot_synth/` 下是否有其他 `AGENTS.md` 需要同步 —— 本版已查**：`kb_pilot_synth/` 与子目录下**没有** `AGENTS.md`（只有仓库根的 `AGENTS.md`）。根 `AGENTS.md` 里没有描述 `semantic_repair_round1/`，因此**无需同步**。

**不得宣称**：开源就绪、全库准确。本阶段只在 30 题冻结集 + 40 张抽检卡 + 13 条判据边界样例上有**代理级**证据；`reviewer_type=agent` 不等于人工核听，我的标签也仍可能出错。

---

## 13. 复现命令

```bash
cd <repo>/kb_pilot_synth/semantic_repair_round1
# 每条 Bash 需带 PYTHONIOENCODING=utf-8 (Windows + Git Bash)

PYTHONIOENCODING=utf-8 python compute_scope.py      # → scope_intersection.json / scope_units.jsonl
PYTHONIOENCODING=utf-8 python triage_e1.py          # → e1_triage.jsonl / triage_summary.json
PYTHONIOENCODING=utf-8 python repair_semantic.py --apply   # LLM 定向复核 (需 GROK_* 环境变量, workers≤4)
PYTHONIOENCODING=utf-8 python audit_overlay.py      # → audit_overlay_llm_miss.jsonl
PYTHONIOENCODING=utf-8 python gate_v2.py --apply    # → gated_*_v2.jsonl / gate_log_v2.jsonl / gate_summary_v2.json
PYTHONIOENCODING=utf-8 python validate_gates_v2.py  # → gate_validation_v2.json (hard 应为 0)
PYTHONIOENCODING=utf-8 python freeze_v2.py          # → heldout_q_v2.jsonl / heldout_v2_frozen.json
PYTHONIOENCODING=utf-8 python trial_rag_v2.py       # → answers_v2_{old,new}.jsonl / trial_v2_usage.json
PYTHONIOENCODING=utf-8 python make_review_v2.py     # → heldout_v2_review.{json,md}
PYTHONIOENCODING=utf-8 python spotcheck_v2.py       # → spotcheck_v2.md
PYTHONIOENCODING=utf-8 python label_application_check.py  # → label_application_check.json
PYTHONIOENCODING=utf-8 python usage_ledger_v2.py    # → usage_ledger_v2.json
PYTHONIOENCODING=utf-8 python variance_check.py     # → variance_check.json
```

### 13.1 第三轮收尾新增（全部可重跑）

```bash
# ---- 纯本地, 零 LLM ----
PYTHONIOENCODING=utf-8 python x07_diagnose.py        # → x07_diagnosis.json (k/预算审计 + X07 逐题 ctx)
PYTHONIOENCODING=utf-8 python retrieval_matrix.py    # → retrieval_matrix.json (old/b2/b3/b3q 四变体对照)
PYTHONIOENCODING=utf-8 python check_coverage_boundary.py  # → coverage_boundary_check.json (13 条对抗样例)
PYTHONIOENCODING=utf-8 python quota_check.py         # → quota_check.json (all/layer_only/off 三模式锚点与 family 指标)
PYTHONIOENCODING=utf-8 python dump_v4_diff.py        # 逐题打印 v3 vs v4 (仅 ctx 改变的题)
PYTHONIOENCODING=utf-8 python dump_v5_quota_effect.py # 逐题打印 v4 vs v5 新面
PYTHONIOENCODING=utf-8 python make_verdicts_v5.py    # → review_verdicts_v5.json (以 v4 判定为底, 只覆盖 20 行)

# ---- 需要 LLM (GROK_API_KEY / GROK_MODEL / GROK_BASE, workers≤4, key 不落盘) ----
# v4 = 最终配置: build3 语料 + layer_only 配额
GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash GROK_BASE=https://aitreez.com/v1 \
QUOTA_MODE=layer_only V3_SUFFIX=v4 V3_SEED=v3,v2 \
PYTHONIOENCODING=utf-8 python trial_rag_v3.py        # → answers_v4_{old,new}.jsonl / trial_v4_usage.json
# v5 = 消融: 关配额, 只跑新面 ctx 改变的 20 题 (旧面复用 v4)
GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash GROK_BASE=https://aitreez.com/v1 \
QUOTA_MODE=off V3_SUFFIX=v5 V3_SEED=v4,v3,v2 \
PYTHONIOENCODING=utf-8 python trial_rag_v3.py        # → answers_v5_{old,new}.jsonl / trial_v5_usage.json
# X07 归因: build3 关配额重跑 X07×3 + F04/F06/N09
GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash GROK_BASE=https://aitreez.com/v1 \
PYTHONIOENCODING=utf-8 python attribute_noquota.py   # → attribution_noquota.json

# ---- 出表 ----
REVIEW_ANS_OLD=answers_v4_old.jsonl REVIEW_ANS_NEW=answers_v4_new.jsonl \
REVIEW_VERDICTS=review_verdicts_v4.json REVIEW_OUT_JSON=heldout_v4_review.json \
REVIEW_OUT_MD=heldout_v4_review.md REVIEW_USAGE=trial_v4_usage.json REVIEW_VAR="__none__" \
REVIEW_SKIP_GOLD_NOTES=1 PYTHONIOENCODING=utf-8 python make_review_v2.py
# v5 同理, 换成 answers_v5_*/review_verdicts_v5.json/trial_v5_usage.json
```

**为什么收尾段只花 108 次调用**：`trial_rag_v3.py` 的缓存键是 **`side|qid|sha256(打包后的 ctx)`**（不是语料 sha）。ctx 未变的题直接从上一代答案行按指纹复用（`seed_cache()`，可用 `V3_SEED` 指定候选代），因此只有 ctx 真的变了的题才会重新调用——v4 复用 20 行 / 调用 40 次，v5 复用 40 行 / 调用 20 次。**这就是「只调用 ctx 改变的题」的实现方式。**

`build1/` 保存加入覆盖层之前的中间产物（gate_summary / gate_validation / 两侧 answers / trial_v2_usage / heldout_v2_review），供对照。
`build2/` 是收尾前的备份（14 个文件），但其中的 `gate_summary_v2.json` 已带本轮保守覆盖字段（见 12.13）。
`_repro/` 是校验器 C9 的重跑产物，四份数据文件与主目录 sha 逐个相同。

---

## 14. 生产只读声明

- `kb/docs.jsonl` sha256 `b835a8bfec6a7bb3…`、mtime `2026-09-20 00:43:51`
- `kb/synthesized.jsonl` sha256 `373554a096daba7c…`、mtime `2026-09-20 00:43:48`

两者与 `inputs_sha256.json` 完全一致，校验器 C10 断言通过；**收尾工作全部结束后再次复核，sha 与 mtime 均未变**。产物只在 `kb_pilot_synth/semantic_repair_round1/`，**未写入生产、未 git 提交、未建 worktree**。`git status` 里的 ` M` 文件（`kb/SCHEMA.md`、`kb/review_synth.md`、`kb/.synth_cache.json`、`cluster_atoms.py` 等）是前几轮遗留，mtime 均早于本轮；`kb_pilot_synth/` 整目录仍为未跟踪（`?? kb_pilot_synth/`）。

---

## 15. 修复前后可直接浏览的例子（v4 口径）

每题给出：题面 / 期望 / 旧面 ctx / 新面 ctx / 旧答 / 新答 / 判定。数据在 `answers_v4_old.jsonl`（旧面）与 `answers_v4_new.jsonl`（新面）中按 `id` 可直接取到；`heldout_v4_review.md` 是按题排版的完整版。

### 例 1 · X07（上一版的唯一回归 → 已修好）

- **题面**：眩晕结束时阻挡帧会不会像索敌帧那样立刻触发？
- **期望**：不像。索敌帧进程结束会立刻触发；阻挡是三循环，相位跟部署走。
- **旧面 ctx（build2 新面，回归时）**：`er1:M03-block-3cycle`, `vod_entry:帧时序与计时器-27-7`, **`vod_entry:帧时序与计时器-40-13`（领主实例，生产权重抢进第 4 位）**, `er1:M03-block-from-deploy`, `fc1:索敌-16-0`, `window:w001342`
- **新面 ctx（build3 + `layer_only`）**：`er1:M03-block-3cycle`, `vod_entry:帧时序与计时器-27-7`, `vod_atom:BV14gby6LEni_p1_40940472044:p64:a0:57e9685d`, `vod_atom:BV1CZ8t6wEyr_p1_41192326752:p24:a4:ca3d7e4d`, `er1:M03-block-from-deploy`, `vod_entry:寻路-10-1` —— 领主实例被 registry `downweight` 移出，层内重复被配额收敛，腾出的槽位给了 on-point 原子（原文即「索敌针…该进程一旦结束（例如眩晕结束）索敌针会立刻抬手并立刻触发」）。
- **旧答（build2）**：「不能一概而论…没有直接结论」（0.75，可复现欠断定，3/3 同）
- **新答（v4）**：「**不会。**阻挡帧与索敌帧不同：索敌帧在眩晕结束时立刻触发，而阻挡帧由部署决定（部署之后 3N 加一帧），按部署相位，不能理解成索敌那种立刻归零。」
- **判定**：旧 1.0（更早的 v1 面）… build2 新面 0.75 → v4 新面 **1.0**。**回归消除**。
- **根因**（5.3 节）：不是 k/预算，是 `gate_v2.py` 丢了 registry `downweight` 分支；归因脚本证明**关掉配额也能修好**，配额不是必要条件。

### 例 2 · N02（事实补全：漏了「仍吃伤判」）

- **题面**：真伤和生命流失在伤害结算步骤上分别跳过什么？
- **期望**：真伤跳过抗性结算，但仍吃伤判，所以可以增伤/减伤；生命流失连伤判也跳过，不能吃增伤减伤。
- **旧答**：「真伤跳过抗性结算环节；生命流失跳过判定步骤，但不跳过计算步骤。」→ **漏了「真伤仍吃伤判、因此可增伤减伤」**（0.75）
- **新答**：「真伤跳过的是抗性结算环节，**但仍会进入伤判，因此可被增伤/减伤**；生命流失跳过的是判定步骤（伤判），但不跳过计算步骤。」→ 1.0
- **ctx 差异**：新面 top6 用 `vod_atom:...p42:a10:d2bdc1f1`（对应「真伤既可吃增伤也可吃减伤」）顶掉了一个 window 槽位。
- **判定**：**fix**。

### 例 3 · F06（配额副作用的修复：gold 独立证据卡被挤掉）

- **题面**：卡墙机制决定了敌人怎么走，对吗？（期望：不对，只决定何时不传送）
- **`all` 配额下新面 top6**：`vod_entry:寻路-21-10`, `vod_entry:技能特例-26-9`, `vod_entry:位移-19-10`, `fc1:寻路-22-2`, `vod_entry:位移-19-7`, `vod_entry:寻路-21-5` —— **gold 卡 `B036-path-not-wallhack` 不在里面**（它与前两条共享簇 `寻路-21-10`，被当成同簇重复折叠）
- **`layer_only` 下新面 top6**：`vod_entry:寻路-21-10`, **`B036-path-not-wallhack`（rank2）**, `vod_atom:BV1jd3m68E6f_p1_40508197659:p63:a2:469ae2ca`, `vod_atom:...:a0:4b9718db`, `vod_entry:技能特例-26-9`, `vod_entry:位移-19-10`
- **判定**：两版答案都对（0.75→1.0 无变化），但 `layer_only` 把**直接证据**放回了上下文，引用也指向它而不是间接层条目。**「三模式锚点表」里 `all` 2/4、`layer_only` 4/4 就来自 F04/F06 这两题。**

### 例 4 · N08（极性反转的真实差别，说明总量不可当因果）

- **题面**：「PRTS 仍然是重要的参考指标，有设置不一定有结果」——这条是机制结论吗？（期望：**不是**，是评价性元话语，已隔离）
- **旧面（v3/v4 复用）答**：「**是机制结论。**片段明确将其列为『可复用规则』…」→ **与期望相反**，0.0
- **`layer_only` 新答**：「…片段没有说明这是具有普遍强制力的机制结论；…严格说，只能确认片段把 PRTS 描述定位为基础设置参考，**不能据此升格为永恒的机制结论**。」→ 0.75（方向正确，未点明「元话语/已隔离」）
- **`off`（关配额）新答**：「这条**属于机制结论**，但仅限其自身表述范围…」→ 0.0（**同一题在两种配额下方向相反**）
- **判定**：`layer_only` 修好、`off` 答反；同一消融里 `off` 又把 N07 修好（N07：`layer_only` 0.75 / `off` **1.0**）。**一正一负相抵 → 不能用总分给配额下定论**，只能用「具体文档被挤掉/被放回」这类可核事实（例 3）。

### 例 5 · N03（旧面同题由拒答改为作答 —— 必须标注是配额改了旧面 ctx）

- **题面**：「在肉鸽中，侵蚀损伤削弱的是肉鸽加成前的基础防御」——这条的适用对象是谁？（期望：未点名，不得编造主语）
- **v3 旧面**：`abstain=True`，「片段未给出具体的适用对象名称…无法确定」→ 0.75（**拒答，方向错**）
- **v4 旧面**：ctx 变（配额改了旧面检索）→「这条规则的适用对象是「未点名」。片段 `fc1:伤害结算-0-4` 明确写着…」→ 1.0
- **v4 新面**：同样直接作答 → 1.0
- **判定**：旧面 0.75 → 1.0 的这 +0.25，**是检索配置改变了旧面上下文造成的，不是新面变好**。同类的还有 N05、N11、F05。这类「旧面被顺带改善」正好抵消了一部分新旧差距，也是第 9.5 节噪声带的来源之一。

---

## 16. 一句话结论

- build3 是**默认层的最终产物**：`default 1339 / archive 1091 / old_kept 21801 / quarantine 12`，校验器 C1–C12 **硬违规 0**，生产数据 **sha 未变**。
- X07 的上一版回归**已定位并修复**（根因是 registry `downweight` 分支丢失，不是 k/预算），且证明**不依赖配额**。
- 覆盖判据已保守化：**0.7 是相似度、不是语义蕴涵**，只有「精确命题包含 + 否定/数值/条件兼容」才授权删除；近似**只登记候选不删**。代价是少删约 2400 条旧原子（刻意选择）。
- 同源配额评估完毕：**`all` 弃用**（有把 gold 独立证据卡挤掉的实证），**采用 `layer_only`**；`off` 更低且出现不可定位引用。
- **总分不可用**：±0.033 噪声带 ≥ 所有新旧差值；可主张的是内容级事实。**不宣称开源就绪、不宣称全库准确**，全部标签为 `reviewer_type=agent`。
