# QQ 轨覆盖扩展 · 阶段一材料（清点 + 80 窗口试批工单）

**状态：** 阶段一（清点与试批材料）已完成，**未执行任何审核判定**。
**生成器：** `kb_curation_qq_expansion_materials.py`（纯本地，无 LLM、无网络、0 外部 API）
**重跑：** `python kb_curation_qq_expansion_materials.py` → `python kb_curation_qq_expansion_materials.py --check`
**批准流程：** `docs/plans/2026-09-21-qq-curation-expansion.md`
**边界：** 本目录只被上述脚本写入；本阶段未改动 `kb_trial/curated_high_quality.json`、未动 `kb/`、未动字幕层、未提交 git。

> **本版更正**：上一版曾断言「QQ 轨从未经过证据审核」，理由是那些审核文件里查不到 QQ 条目。**该断言错误**——它们按 `entry_id` 索引、**没有 `track` 字段**，按 `track` 过滤会静默返回空集。实测 QQ 轨有 **8 条** `supported` 证据判定与 **11 条** `keep` 语义内审。详见 §1.3。

**一句话结论**：worklist 的 851 **行**对应 **713 个窗口**，其中**已逐条读源的是 11 个窗口**；本试批给出 **80 份互斥、且全部未入库**的窗口工单（含 3 份救援样本），每份都附上**本窗 `source_msg_ids` 覆盖的完整消息块（全文未截断、已脱敏）**，供阶段二逐条读源。

---

## 1. 清点结论：851 到底是什么

用户的问题是「851 待核是否真实、有无重复遗漏」。逐项核完后，答案分三部分。

### 1.1 851 不是待核队列，是未去重的候选行

| 项 | 实测 |
|---|---|
| `qq_worklist.json` 行数 | **851** |
| 其中 `qq_window` 行 / `qq_atom` 行 | 706 / 145 |
| 去重后的窗口数 | **713** |
| 多出来的行（同窗的原子行 + 窗卡行） | **138** |
| 单窗最多行数 | 9（`w000118`、`w000929`） |
| 行数 > 1 的窗口数 | 83 |

同一窗口同时贡献一条窗卡行和若干条 `qq_atom` 行——`qq_atom` 是上游 `kb_atomize_qq.py`（D+ 原子化）把该窗口的整卡拆成的单命题，并不是新增讨论。**因此 851 行里大约 138 行是对同一段群聊的重复计数，真实的读源单元是 713 个窗口。**

### 1.2 逐条读源的实际覆盖面

以**窗口**为单位说（行数与窗口数量纲不同，不得相互比较）：

| 项 | 实测 |
|---|---|
| worklist 覆盖的窗口 | **713** |
| 其中**确实被逐条读源**过的窗口 | **11** |
| 其中没有逐条读源记录的窗口 | **702** |
| 有逐条读源记录的窗口明细 | 8 个在 `qq_claim_overlay.json`（标题按 span 重写）+ 3 个在 `qq_claim_held_out.json`（判为不可闭合、隔离） |

「没有逐条读源记录」既不是「851 条待核」，也不是「已判定为无价值」，而是**713 个窗口里约 702 个还未耕地**。

### 1.3 QQ 轨**确实**经过证据审核与语义内审（更正）

本文件上一版曾断言「QQ 轨在 `evidence_verdicts.jsonl` / `evidence_review_worklist.jsonl` 里的条目数为 0，从未经过证据审核」。**该断言是错的**，原因是按一个**并不存在**的 `track` 字段过滤。这三个文件按 `entry_id`（形如 `window:w000044#r0`）索引：

| 已有审核 | 实测 | 说明 |
|---|---|---|
| `evidence_verdicts.jsonl` 总行数 | **620** | 其中 **8 行**是 QQ 窗口：`w000006` `w000012` `w000027` `w000033` `w000037` `w000040` `w000042` `w000044`，全部 `status=supported`、`supports=qq_window_span` |
| `evidence_review_worklist.jsonl` 总行数 | **668** | 其中 **11 行**是 QQ 窗口 |
| `semantic_review.json` | `counts={total:814, keep:670, drop:144}` | 其中 **11 行**是 QQ 窗口，`verdict` 全部为 `keep` |
| `agent_verifications.json` | 与 QQ 轨无交集 | 仍然无 QQ 条目 |

**结论：QQ 轨经过了证据查证（8 条 supported）与语义内审（11 条 keep）。** 读取这些文件必须按 `entry_id`，不能按 `track`——按 `track` 过滤会静默返回 0，从而误报成「从未审核」。`qq_expansion_stats.json` 的 `existing_qq_review_history` 记录了这组数字与本次更正，工单的 `existing_review.stages_that_touched_this_window` 也按 `entry_id` 逐条列明了每个窗口被哪些阶段碰过。

### 1.4 已入选的 8 条不要算新增

| 项 | 实测 |
|---|---|
| 甄选层总条目 | 663 |
| 其中 QQ 轨 | **8**（`source_layer = QQ群聊`） |
| 隔离区 QQ 条目 | 3 |
| `decisions.jsonl` 中 QQ 的 accept 行 | 11 |
| accept 覆盖的窗口 | 11（8 入库 + 3 隔离，无遗漏） |

本轮 80 份工单**已整体排除 `shipped` 窗口**，所以 **`shipped` 数 = 0，80 份全是未入库窗口**。
其中 **3 份是上一轮判为不可闭合的隔离窗口**（`w000031` `w000036` `w000041`，`shipped_status=staged`）。这 3 份是**救援样本**：用于检验「补上完整原始对话后，原来的不可闭合判断是否仍然成立」，**统计新增覆盖时不得计入**。工单里已逐条标出（`selection_rule.is_rescue_sample`）。

### 1.5 遗漏：76 个窗口连候选行都没有

`qq_cards/cards.jsonl` 有 **789** 个窗口，而 worklist 只覆盖 **713** 个——**76 个窗口有原文片段，却因为没有任何候选行而没有进入 worklist**。原因是它们的窗卡行被确定性预筛挡掉了（`too_short` 85、`no_atom_citation` 50、`audit_kind_not_mechanism` 20、`fragment_tail` 2、`chit_chat` 2、`no_condition_stated` 1、`asr_suspect_term` 1，按行计 161 行）。

这 76 个窗口是**真实的覆盖缺口**，不是「已判定为无价值」。本阶段如实计入，**未纳入 80 试批**（试批严格遵守「从 worklist 出发」的口径）；阶段三扩量时应单独评估。

另有参考口径：`qq_cards` 里 16 个窗口带 `status=duplicate` / `canonical_window_id`（指向 `w000178`、`w000083`、`w001797` 等），去掉后是 **773** 个互不重复的窗口，可作为阶段三的窗口基数上限。

**关于「量纲」的纪律**：本文件出现的所有「行数」与「窗口数」量纲不同，**不得相互比较大小或做减法推断覆盖率**。覆盖率一律以窗口为单位计算。

---

## 2. 文件与字段 schema

### 2.1 `qq_worklist_inventory.jsonl` / `.json`

每个**窗口**一条记录（789 条 = 全部 qq_cards 窗口，含 76 个缺口窗口）。`.json` 版是同内容的数组包装，附 `fields` 清单。

| 字段 | 含义 |
|---|---|
| `window_id` | 窗口标识，如 `w000006` |
| `worklist_row_count` / `doc_ids` / `doc_types` | 该窗口在 worklist 里的行数与行 id（0 行表示缺口窗口） |
| `kind` | `window`（有窗卡行）/ `qq_atom_only` / `no_worklist_row` |
| `candidate_atom_count` | 上游原子化产出的原子数 |
| `claim_topics` | worklist 允许检索的候选标题（**不是**机制结论） |
| `category` / `as_of` / `card_*` | 原窗卡的分类、时间与状态（`status` / `origin` / `novelty` / `scope` / `canonical_ids`） |
| `n_source_spans` / `source_spans` | 已脱敏原文片段全文 |
| `source_msg_ids` | **仅内部定位**，不得转发 |
| `window_tier` / `window_raw_tier` / `window_score` / `window_hit_terms` / `window_n_messages` | 上游窗口打分与命中词 |
| `has_host_authority` | 该窗口是否有主播（`role=host`）发言 |
| `decisions[]` | 每个 doc_id 的确定性闸门判定（`decision` / `reject_reason` / `review_status`） |
| `reviewed_source_by_source` | **是否被逐条读源过**（仅 11 个窗口为 true） |
| `shipped` | `status`（`shipped` / `staged` / `overlay_rewritten_not_a_verdict` / `not_reviewed`）、`entry_ids`、`overlay`、`held_out` |
| `classification` | 机械分组 `group` / `label` / `reason` |

### 2.2 `qq_expansion_stats.json`

顶层：`note` / `seed` / `sources` / `reconciliation` / `classification` / `workorders` / `review_state_legend` / `existing_qq_review_history` / `category_schema` / `privacy` / `worked_examples`。

`reconciliation` 直接回答清点问题（`headline`、`row_counts_are_not_comparable_to_window_counts`、`is_it_a_deduplicated_queue`、`queue_status_note`、`windows_never_read_source_by_source`、`windows_missing_from_worklist*`、`accepted_docs_*`、`rows_outside_worklist_*`）。
`existing_qq_review_history` 是 QQ 轨已有审核的实数与**本次更正记录**（见 §1.3）。
`review_state_legend` 说明四种 `shipped_status` 的含义，并给出「必须按 `entry_id` 而非 `track` 读取审核记录」的读法。
`worked_examples` 给出两条真实工单，用来证明机械分组**不是**判定（见 §4）。

### 2.3 `workorders/qq_wo_001.json` … `qq_wo_080.json`

工单以 `raw_messages` 为**主要读材料**（不是唯一材料：上游片段、原窗卡、旧判定也都在）。审核方不需要再读其他文件，但要注意 **`source_spans_excerpts` 只是摘录片段，不是完整对话**（见下）。

| 字段 | 含义 |
|---|---|
| `workorder_id` / `phase` | `qq_wo_NNN` / `phase1_trial_batch` |
| `group` / `group_label` / `selection_rule` | 四组归属与该窗的入选规则（含 `pool_size`、`rank` / `shuffled_index`、`is_rescue_sample`） |
| `window` | `window_id` / `as_of` / `category` / `kind` / 上游打分 / `has_host_authority` / 窗卡状态 |
| `source_spans_excerpts` | 上游 `qq_cards` 给该窗口的原文片段（**摘录，可能被截断**，例：原文 `@群友 我记得有些群攻能力…` 被截成 `我记得有些群攻能力…`）。附 `source_spans_note` 说明这一点 |
| **`raw_messages`** | **本窗 `source_msg_ids` 覆盖的完整有序原始消息块（全文，未截断）**，见 §2.3.1 |
| `original_card` | 原窗卡：`topic` / `context_question` / `core_conclusions`（**含每条的 speaker 与 credibility**）/ `underlying_parameters` / `summary_takeaway` / `vod_evidence` |
| `atoms_from_this_window` | 该窗的 `qq_atom`（`atom_text` / `claim_type` / `applies_to` / `conditions` / `credibility`）与窗卡文本 |
| `old_decisions` | 该窗每行的旧判定（`decision` / `reject_reason` / `review_status` / `claim_as_decided` / `audit_kind` / `flags`） |
| `existing_review` | `shipped_status` / `shipped_entry_ids` / `stages_that_touched_this_window`（按 `entry_id` 索引的已有审核阶段）/ `stage_records` / `qq_claim_overlay`（原 `from`→`to` 与理由）/ `qq_claim_held_out`（原判定理由） |
| `classification_reason` | **为什么被分到这一组**，人话写明 |
| `review_instructions` | 判定取值、必填字段、引文规则、数字规则、语境规则、隐私规则 |
| `review_limits` | 置信上限 `text-source-supported` 的说明 |
| `internal_source` | 上游文件路径、`worklist_rows`、`raw_message_file`、`window_file`、`evidence_verdicts`、`source_msg_ids`（**内部定位用**） |

#### 2.3.1 `raw_messages` 结构

```jsonc
"raw_messages": {
  "mapping_status": "ok",              // ok | ok_with_gaps
                                       //   | no_cited_ids_in_raw_export
  "mapping_note": "…",                 // 说明取数口径（锚点=本窗 source_msg_ids）
  "declared_range": {                  // 本窗在 qq_info/windows.jsonl 里声明的区间
    "start_time": "2026-05-07 23:38:18",
    "end_time":   "2026-05-07 23:45:22",
    "note": "…"                        // 声明区间与实测相差 +3600 秒，仅供参考、不作取数依据
  },
  "declared_range_seconds": [1778171898, 1778172322],
  "message_count": 71,
  "cited_count": 12,                   // 该窗上游窗卡引用的消息条数
  "cited_missing_from_raw": [],        // 引用了但不在原始导出里的 id（非空即为 ok_with_gaps）
  "messages": [
    {
      "seq": 1,                        // 1..N，连续，按 ts 升序
      "speaker_id": "0d9cadda",        // 匿名标识（源数据已有），不是 QQ 号
      "time": "2026-05-07 23:38:18",
      "ts": 1778171898,
      "is_cited_by_card": false,       // 该消息是否被上游窗卡引用
      "text": "…",                     // 全文，不截断
      "mentions_speaker_id": ["589e9b6d"],      // 回复指向（能唯一解析时），仅在有 @ 时出现
      "mentions_nick_unresolved": true,         // 解析不到时为 true，仅在有 @ 时出现
      "account_numbers_redacted": 3             // 本条被抹去的账号数字个数，仅在有时出现
    }
  ]
}
```

**取数口径（重要）**：`messages` 是**本窗自己 `source_msg_ids` 在导出里覆盖的连续消息块**（取首末 id 之间的全部消息，按导出顺序、时间升序）。锚点用的是**窗口成员表**（它是窗卡引用集的**超集**），所以上游没引用的消息也在。**不从邻近窗口推断来源**，**绝不把别的窗口的 `source_spans` 当成本窗的**；本窗 id 若全无法定位，`mapping_status` 如实记为 `no_cited_ids_in_raw_export` 并留空 `messages`，而不是猜。

**文本来源**：正文取自 `qq_info/1097395794_桃大将军粉丝群_聊天记录.csv`（**227129 行**，全量导出），而不是只有 158285 条的 `qq_info/messages_clean.jsonl`——后者是瘦身后的版本，会漏掉消息。`speaker_id` 只能从 `messages_clean.jsonl` join（CSV 无此字段）。**文本一律全文载入，无 280 字符截断**（实测最长单条 4405 字符）。

**回复指向**：源数据**没有结构化 reply 字段**；`@昵称` 只是纯文本。因此把 `@昵称` 归一为：能唯一解析到某发言者时写 `@<speaker_id>` 并置 `mentions_speaker_id`；解析不到时写 `@某人` 并置 `mentions_nick_unresolved=true`。昵称包含 `@` 时（如 `@调零@提丰单推人`）两段都按 `@某人` 处理。

**仍不等于完整线程**：块之外的对答不在 `messages` 里（本窗成员表未覆盖的邻近对话不属于本窗）。窗口边界由上游声明，本阶段不做扩窗。

### 2.4 `workorders/index.json`

`seed` / `count` / `shortfalls` / `by_group` / `by_shipped_status` / `workorders[]`（每条含 `file`、`group`、`window_id`、`kind`、`category`、`as_of`、`n_source_spans_excerpts`、`n_raw_messages`、`raw_mapping_status`、`n_atoms`、`n_old_decisions`、`shipped_status`、`is_rescue_sample`、**`sha256`**）。

### 2.5 `review_impact_manifest.json`（材料改动前后差异清单）

生成器：`kb_curation_qq_expansion_diff.py`（纯本地）。用途：**本版材料相对上一版有变**，审核员据此**只重读受影响的部分**，不必整批重来。**只列 seq 与原因，不含任何昵称/QQ 号/群号**。

| 字段 | 含义 |
|---|---|
| `what_changed` | 四类原因的口径说明（`was_truncated` / `identity_redacted` / `missing_before` / `dropped_before_only`） |
| `truncation_verified` | 实测：旧版取数范围内超 280 字符的消息 **0** 条——截断是**潜在**缺陷，未实际切掉任何已交付 seq |
| `participant_roster_note` | 日报 `参与者:` 名单行的修复说明（只改名单行文本，不改条数与 seq，故不计入 `affected`） |
| `anchoring_note` | 取数锚点从「声明时间区间」改为「本窗成员表连续块」的原因 |
| `sources` | `messages_before_total` **2707** → `messages_after_total` **3206** |
| `affected_counts` | 原因→条数：`missing_before` **75**、`identity_redacted` **5**、`dropped_before_only` **7** |
| `entries[]` | 每份受影响工单：`workorder_id` / `window_id` / `message_count_before` / `message_count_after` / `changed_seq` / `reasons` / `needs_reread` |

**实测**：`affected_workorders` = **80/80**，`total_changed_messages` = **899**。因取数口径整体改变，覆盖面普遍变化，故全部 80 份都需要重读。

### 2.6 `privacy_scan.json`（隐私扫描结果）

生成器：`kb_curation_qq_expansion_privacy_scan.py`（纯本地）。扫 **87 个产物文件**（`workorders/*.json`、`workorders/index.json`、`qq_worklist_inventory.json[l]`、`qq_expansion_stats.json`、两份清单 JSON）+ **83 个 `reviews/` 文件**（只读，不修改）。结果见 §5.2。**只记录命中的文件/字段/seq 与类别，不回显号码或昵称。**

---

## 3. 80 份工单怎么分的（可复现）

四组**各 20 个互斥窗口**，`seed = 20260921`。分组在**窗口**粒度互斥、窗口是审核单元。组由机械谓词判定，**不跨组借窗口凑数**；若某组不足 20 会如实留空并在 `shortfalls` 记明（本次四组都满 20，`shortfalls = {}`）。

**候选池已排除 `shipped` 窗口**（8 个已入库窗口不在池内），因此 80 份工单里 **`shipped` = 0**。

| 组 | 谓词（`kb_curation_qq_expansion_materials.py::classify`） | 池 | 取 |
|---|---|---|---|
| **A 完整机制** | `kind=window` 且无未闭合疑问、无 hedge 词，且**同时**出现定义词（就是/指的是/是指/定义为/叫做/称为/等价于/不等于）与时序词（先/再/然后/之后/最后/同帧/结算顺序/优先级/顺序…），且全部片段合计 ≥ 24 字 | 35 | 20 |
| **B 数值/公式/代码** | 命中数值单位（帧/针/秒/格/倍/%/费/层/次…）、算式字面（`数字 * 数字` 等）或代码标识符（`snake_case` / `CamelCase` / 含点路径 / `.prefab` `.json` 等） | 381 | 20 |
| **C 混合机制猜测或整窗拒绝** | 命中未闭合疑问标记（`? ？ 吗 呢 是不是 有没有 怎么 为啥 多少…`）或 hedge 词（可能/应该/大概/我记得/好像/估计/不确定/理论上/据说…） | 169 | 20 |
| **D 其余随机** | A∪B∪C 的补集，`random.Random(20260921).shuffle` 后取前 20 | 196 | 20 |

组内排序：`(kind_rank, window_id)`，`kind_rank` 取该窗口内最强的文档类型（`window`=0 < `qq_atom_only`=1）。四个池合计 35+381+169+196 = **781**（= 789 个窗口减去 8 个已入库窗口）。

**关于「四类」的口径**（`stats.category_schema` 也记了一份）：这四类不是机制主题分类。上游窗卡的 `category`（帧时序 / 索敌 / 伤害结算 / 位移 / 寻路 / 干员机制 / 技能特例 / 数值与读图 / 关卡与出怪 / 其他）才是主题；本阶段的 A/B/C/D 是**审核难度分桶**——看的是这段片段能不能自足地定出一条机制。同一个 `category` 会同时出现在四个组里，这是预期的，不是分类冲突。

分组**决定下游的处理口径**：只有 A 组允许直接认可可枚举数字；B 组必须逐字给出数字出处；C、D 组一律不得写入片段里没有的数字与适用范围。

---

## 4. 这份材料**没有**做的判定（重要）

本目录里**没有任何一条机制判定**。所有分组都是正则谓词，`worked_examples` 用两条真实工单证明了这一点（两条例子都**按 `window_id` 选取**，不受工单编号重排影响）：

- **A 组的 `qq_wo_001`（`w000013`）**：机械谓词全过（定义词「就是」、时序词「先/再」、`kind=window`、最长 span 15 字），但上游片段全是残句；`raw_messages` 补出本窗 71 条消息后可以看到，这段对话是多人同时在追索敌分支、夹着「我今天不是萝莉控」这类闲聊，**即使拿到完整上下文，也仍然定不出一条干净机制**。旧判定是 4 行全 reject。这正是「不把审核模拟成正则判决」的实证。
- **C 组的 `qq_wo_043`（`w000077`）**：只因片段里出现 hedge 词（`不确定` / `可能` / `应该`）就被归到 C 组，但它讨论的是**同帧命中的伤害结算顺序**（火陈技能平A与龙同帧、连续攻击与首次攻击结算不同、`陈的创建比弹道早`）——这是一个真实的机制议题，`raw_messages` 的 27 条消息显示讨论里有「先决定打数」「索到了」这类具体推导。**「有疑问词」不等于「整窗无价值」。**

> 说明：上一版的 C 组例子是 `w000033`。该窗口条目已入库（`shipped`），本轮已按「80 份全为未入库窗口」的口径把它整体移出候选池，例子随之换成同为 C 组、且未入库的 `w000077`。

结论：**分组只能当分派线索，不能当判决**。阶段二必须逐条读源。

同理，`old_decisions` 里的 `reject_reason` 也**不是**内容质量结论：`kb_curation_rules.py` 里的确定性理由（`asr_only_needs_agent` / `too_short` / `fragment_tail` / `basic_definition_needs_agent` / `numeric_needs_agent` / `context_incomplete` 等）只表示「引擎不肯自动通过、需要代理读」，不表示「这条没价值」。80 份工单里绝大多数行的 `reject_reason` 是 `asr_only_needs_agent`，那只是因为 QQ 轨恒带 `no_official_layer` 标志。

---

## 5. 隐私

- `source_spans_excerpts` 只含**消息文本**，不含群号、QQ 号、昵称。
- `raw_messages[].text` 里的 `@昵称` 已**去掉昵称**：能唯一解析到某发言者时写成 `@<speaker_id>`，解析不到时写成 `@某人`，并置 `mentions_nick_unresolved=true`。
- **日报机器人的 `参与者:` 名单行**是昵称唯一出现在 `@` 之外的位置，已整行匿名（`@speaker_id` / `某人`）。**一条报告里有多条名单行**，逐行都改写。不进行全文昵称替换——183 个昵称本身就是常用词（「前进」「仙人」「一人」），全文替换会把 `每日来群大学习` 毁成 `每日来@某人大学习`。
- **6–12 位连续数字一律抹为 `[账号已隐去]`**；已被 `[]` 包起来的（`[3461316146]`）整体替换，避免出现 `[[账号已隐去]]`。机制数值（`1/3`、`0.5`、`1帧`、`23 48 73 98`、`0.0333333`）不受影响。

### 5.1 本版更正：上一版的隐私说法是错的

上一版曾写「把 messages_clean 里全部 417 个真实 QQ 号与群号拿去扫，命中 0」，并据此暗示已清干净。**该结论建立在过窄的判据上，不成立**：

- 判据只覆盖 8–9 位 QQ 号，**漏掉了 `@匿名id` 后面残留的身份数字**（例如 `@凌弥lemmi 365489981`，该数字不在 417 个 QQ 号里，但仍是群友身份信息）。
- 判据只查「回复位昵称」，**漏掉了日报名单行里的昵称**。
- 文本来源本身漏消息（`messages_clean.jsonl` 158285 条 vs CSV 227129 条），所以「扫了全部」名不副实。

### 5.2 本版实测（`privacy_scan.py`）

`kb_curation_qq_expansion_privacy_scan.py` 扫 **87 个产物文件 + 83 个 `reviews/` 文件**，输出 `kb_trial/curation/qq_expansion/privacy_scan.json`。判据来自 CSV 的 **437** 个真实 `发送人QQ` + `messages_clean` 的 **562** 个昵称 + 全部 `speaker_id`。

| 类别 | 命中 | 说明 |
|---|---|---|
| `qq_number` | **0** | 真实 QQ 号在产物中 **0 命中** |
| `group_id` | **0** | 群号 **0 命中** |
| `bare_digit_run` | 47 | 逐条核过：**全部不是**真实发送者 QQ；是机制数值、消息 id、或我们自己的 `@<speaker_id>`（含 8 个纯数字 speaker_id） |
| `at_token_not_an_id` | 89 | 82 条是我自己 `mapping_note` 里的示例文字（`@昵称`）；其余是 1 条日报（`@` 被正则连同 `、` 一起截断）与审核员自己的 `reviews/` 文本 |
| `nickname_exact` / `nickname_in_text` | 2 / 10 | 全部是**同形误报**：命中词是常用语或整句（「没有人」「标记了一块芝士」「好叭，凌弥认了」），不是身份泄漏。其中 5 条在 `reviews/`（只读，未改） |

**独立复核**：把产物里**残留的全部 6–12 位数字**抽出，去重后仅 **7 种**，**无一是真实发送者 QQ**——它们是我们写出的 `@<speaker_id>`（`@47477077` 这类纯数字 id）或 8 位 hex id 的一截。判据比扫描器更严，结论一致。

**结论**：真实 QQ 号与群号 **0 命中**；昵称命中均为同形误报。**但不得据此声称「已彻底脱敏」**——置信上限仍是文本层，未核听、未实测。
- `source_msg_ids` 与 `internal_source` 只用于内部定位原消息，**不得转发、不得写入任何公开层或日志**。工单的 `review_instructions.privacy` 已写明这一条。

---

## 6. 交给父 agent 分派时要知道的事

1. **80 份工单可直接分派审核**，无需补充材料；主要读材料是 `raw_messages`（本窗 `source_msg_ids` 覆盖的完整消息块，全文未截断），`source_spans_excerpts` 只作对照。
2. 回执必填：`verdict`（`keep_with_claim` / `repair_claim` / `reject_window` / `pending_source_cannot_settle`）、`claim`、`subject`、`condition`、`scope`、`evidence_quote_spans`、`reason`。
3. **`evidence_quote_spans` 必须逐字引用 `raw_messages[].text`**（不要再引用 `source_spans_excerpts` 的片段，因为它们是截断过的）；引用不到原文的引文判无效回执。
4. 数字规则：claim 里出现任何帧/秒/倍/格/百分比数字，必须给出该数字所在的原始消息原文。
5. **80 份全部是未入库窗口（`shipped` = 0）**；其中 3 份（`w000031` `w000036` `w000041`）是**救援样本**，上一轮被判为不可闭合而隔离，本轮用于复核该判断是否仍成立，**不得计为新增覆盖**。
6. 审核上限仍是 `text-source-supported`：基于脱敏文本，未核听原片、未做游戏内实测。C 组大概率大量 `pending_source_cannot_settle`——**这正是这一组要证明的事，不要为了凑产出把 pending 写成 keep**。
7. 若某窗 `raw_messages.mapping_status` 不是 `ok`，按「上下文缺失」处理并在 `reason` 里写明，**不得用邻近窗口的内容代替**。
8. **若材料已改过（本版即如此）**，先读 `review_impact_manifest.json` 判断哪些工单需要重读、哪些不受影响，**不要整批重读**：
   - `affected_workorders`：**80 / 80**（因取数口径从「声明时间区间」改为「本窗成员表连续块」，覆盖面普遍变化）
   - `total_changed_messages`：**899**
   - 原因分布：`missing_before` **75**、`identity_redacted` **5**、`dropped_before_only` **7**
   - 每条受影响工单给出 `changed_seq` 与 `reasons`，**只列 seq 与原因，不含任何隐私**。
9. 阶段三扩量前，先看阶段二暴露的口径分歧；`windows_missing_from_worklist` 的 76 个缺口窗口需要在阶段三单独决策是否纳入。

---

## 7. 已知局限

- **未做任何审核**：本阶段只清点、只分派。所有「能/不能成条」的结论都还没有。
- **分组谓词是启发式**：`worked_examples` 已给出两处明显误分（A 组含不可判读窗口、C 组含真实机制窗口）。分组只用于抽样分派，不用于统计意义上的「机制占比」。
- **`raw_messages` 以窗口成员表为界**：本窗成员未覆盖的邻近对答不在其中，跨窗的语义断裂仍未处理（本阶段刻意不扩窗，以免把别的窗口的内容混进来）。
- **本轮已删除「邻近两窗推断上下文」的做法**：上一版工单里的旧上下文字段是按「找时间最近的 2 个窗口」推断的，这既可能张冠李戴，也无法证明来源，故删除，改为窗口自身成员表对应的消息块。
- **上一版还有三处口径问题，本版一并改正**：① 正文曾按 280 字符截断——**实测旧版取数范围内的消息没有一条超过 280 字符，因此并未实际切掉任何已交付 seq**，该缺陷是**潜在**的、「完整」这一说法不成立，现已全文载入（本版最长单条 4405 字符）；② 上一版称 `windows.jsonl` 的 `start_ts/end_ts` 与实测差 +3600 秒是「取错时段」——**更正**：新旧范围其实重叠 2700/2707 条，偏移在两侧相互抵消，真正的问题是**时间范围过窄导致漏取**，故锚点改为窗口成员表（旧 2707 条 → 新 **3206** 条）；③ §5 的「0 隐私命中」判据过窄，见 §5.1。
- **76 个缺口窗口未纳入试批**，覆盖不全。
- **`qq_canonical`（51）与 `glossary`（50）两族的证据形态未单独处理**：它们在 `kb_trial/docs.jsonl` 里带的 `evidence` 只有窗口 id、没有 span，本轮未把它们纳入工作清单；这是阶段三的待办。
- **本目录产物不是权威层**，也不得复述为「QQ 轨已扩展完成」。
