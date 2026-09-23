# QQ 轨覆盖扩展 Implementation Plan

> 用户已批准的流程。**阶段一（清点 + 80 窗口试批材料）** 已完成，产物在 `kb_trial/curation/qq_expansion/`。
> 阶段二（父审 80）尚未开始；本阶段**不执行审核、不修改 `kb_trial/curated_high_quality.json`、不调外部 API、不提交 git、不动 `kb/` 与字幕层**。

**Goal:** 把 QQ 群聊轨从当前 8 条入选（11 条 accept 中 3 条被隔离）扩展为经过逐条读源的成规模规则层，全程保留"文本层可支撑、非核听"这一诚实置信上限。

**为什么需要这一步：** `kb_trial/curation/qq_worklist.json` 有 851 **行**候选（对应 **713 个窗口**，因为 138 行是同窗原子造成的重复计数），但上一轮的 QQ 审核只逐条读过 11 个窗口（`kb_curation_evidence_close.py` 的 `QQ_REPAIRS` / `QQ_PENDING` 两张手写表）。851 从未被当作待核池处理过。所以本阶段先把「到底还剩多少窗口没读过、有没有重复与遗漏」核清楚，再给出一份可被外部审核模型（DeepSeek）直接分派的试批工单。

**核清后的关键数字（实测，非估计）：**

| 项 | 数 |
|---|---|
| worklist 行数 / 去重后窗口数 | 851 / **713**（138 行是同窗原子造成的重复计数；**行数与窗口数量纲不同，不得相互比较**） |
| 没有逐条读源记录的窗口 | **702** |
| 真正被逐条读源过的窗口 | 11（8 入库 + 3 隔离） |
| 有原文片段却因预筛没有候选行、从而未进 worklist 的窗口 | **76**（覆盖缺口） |
| QQ 轨在 `evidence_verdicts.jsonl` / `evidence_review_worklist.jsonl` 的条目（**按 `entry_id` 统计**） | **8 / 11**（另 `semantic_review.json` 11 条 `keep`） |
| `agent_verifications.json` 中属 QQ 的条目 | **0**（与 QQ 轨确无交集） |
| `qq_canonical`(51) 与 `glossary`(50) 的证据形态 | 只带窗口 id、**不带 span** |

> **更正记录**：本文件上一版把最后两行写成「QQ 轨在 `evidence_verdicts.jsonl` / `evidence_review_worklist.jsonl` / `agent_verifications.json` 的条目 = **0 / 0 / 0**」，并据此断言「QQ 轨从未经过证据审核」。**该断言是错的**：前两个文件按 `entry_id`（形如 `window:w000044#r0`）索引，**没有 `track` 字段**，用 `d.get('track') == 'qq'` 过滤会静默返回 0，从而误报。实测 QQ 轨有 8 条 `status=supported` 证据判定、11 条证据工单行、11 条 `keep` 语义内审，并且这些判定分布在 8 个已入库窗口上（`w000006` `w000012` `w000027` `w000033` `w000037` `w000040` `w000042` `w000044`）。只有 `agent_verifications.json` 确与 QQ 轨无交集。

> **更正记录 2（材料缺陷修复，本版）**：审核方指出阶段一材料有三处缺陷，已逐条实测并修复：
> 1. **正文曾按 280 字符截断**，因此上一版 README 里的「完整原始对话」不成立。**实测更正**：旧版取数范围内的消息**没有一条超过 280 字符**，故截断是**潜在**缺陷、**未实际切掉任何已交付 seq**；现改为全文载入（本版最长单条 4405 字符）。
> 2. **数据源过窄**：正文原取自 `qq_info/messages_clean.jsonl`（**158285** 条），而全量导出 `qq_info/1097395794_桃大将军粉丝群_聊天记录.csv` 有 **227129** 行。现改用 CSV（`speaker_id` 仍从 `messages_clean.jsonl` join，CSV 无此字段）。
> 3. **取数锚点错误**：原按 `windows.jsonl` 的声明 `start_ts`/`end_ts` 取数。**实测更正**：声明区间与实测差 +3600 秒，但新旧范围**重叠 2700/2707 条**，偏移在两侧相互抵消——所以**不是「取错时段」，而是时间范围过窄导致漏取**。现锚定本窗自己的 `source_msg_ids`（窗口成员表，为窗卡引用集的超集）。修复后 80 份合计 **3206** 条（旧 2707）。
> 4. **隐私口径过窄**：上一版「0 命中」只覆盖 8–9 位 QQ 号，漏掉了 `@匿名id` 后残留的身份数字（`@凌弥lemmi 365489981`）与日报 `参与者:` 名单行里的昵称。现已抹除全部 6–12 位连续数字（`[账号已隐去]`）并整行匿名名单，且**逐行**处理一条报告里的多条名单行（旧版只改第一条，另 11 条带昵称出厂）。实测真实 QQ 号与群号各 **0 命中**，残留数字无一是真实 QQ。
> 5. 由 1–4 引起的材料变更**不静默交付**：新增 `review_impact_manifest.json` 列明受影响工单与 `changed_seq`（仅 seq 与原因，无隐私），供审核员只重读受影响部分。
> **边界**：本轮未编辑 `kb_trial/curation/qq_expansion/reviews/`、未改动 `kb_trial/curated_high_quality.json`、未做任何审核判定。


**Architecture:** 纯本地 Python 3，无 LLM、无网络。单个材料脚本 `kb_curation_qq_expansion_materials.py` 只读 `kb_trial/`、`qq_info/`、`qq_cards/`，只写 `kb_trial/curation/qq_expansion/`。审核判定由下游 agent 完成，本阶段不产出任何自动判定。

**Tech Stack:** Python 3 标准库（json / hashlib / pathlib / re）。无新增依赖，无测试框架，脚本自带 `--check` 自检。

---

## 四个阶段的流程（已批准）

| 阶段 | 内容 | 闸门 |
|---|---|---|
| **1. 清点 + 80 试批材料** | 本地关联窗口/原子/候选/判定/已入选/已有审核；核清 851 的真实含义、重复与遗漏；按四类各 20 个互斥窗口（seed 固定）生成 80 份工单 | 本目录 inventory/stats 可复现；四类互斥、类别不凑 |
| **2. 父审 80** | 父 agent 把 80 份工单分派给 DeepSeek 逐条读源；每条给出 claim/subject/condition/scope 与 verdict（keep / repair / reject / pending），**必须引用工单内的原文片段**，不得只看标题 | 80 全部有回执；回执里出现未在工单中出现的引用即判无效工单 |
| **3. 稳定后批量 150–250 窗口** | 用阶段 2 暴露的口径（什么算自足、什么必须 pending）扩充到 150–250 窗口，仍逐条读源 | 口径未稳定前不扩量；扩量后抽检回执与源文逐字一致 |
| **4. 单 JSON 合并 + 检索/隐私验证** | 合并进 `kb_trial/curated_high_quality.json`（保持单 JSON、schema `curated-1.0`），重跑 `kb_curation_evidence_close.py → kb_curation_build.py → kb_curation_validate.py → kb_curated_search.py --self-test`，并做隐私扫描（群号 / QQ 号 / 昵称 / 6–12 位数字） | 校验与自检全绿；隐私扫描 0 命中；`CURATED_OVERVIEW.md` 与 AGENTS.md §6.1 条数同步 |

---

## 阶段一实际做了什么（可复现）

**输入（只读）**

| 文件 | 作用 |
|---|---|
| `kb_trial/curation/qq_worklist.json` | 851 行预筛候选（含窗口 span、类别、as_of、n_msgs） |
| `kb_trial/curation/decisions.jsonl` | 4574 条确定性闸门判定，其中 qq 1012 条 |
| `kb_trial/curation/candidates.json` | 4574 行预筛池，其中 qq 1012 行 |
| `kb_trial/curation/evidence_verdicts.jsonl` | 620 条证据判定（612 VOD + 8 QQ supported），QQ 侧无 reject |
| `kb_trial/curation/qq_claim_overlay.json` / `qq_claim_held_out.json` | 上一轮 8 条重写 + 3 条隔离 |
| `kb_trial/curation/curated_staging.json` / `kb_trial/curated_high_quality.json` | 已入选 663 条（QQ 8 条）与隔离区 |
| `kb_trial/curation/agent_verifications.json` | 49 条代理复核（VOD 轨，与 QQ 侧无交集） |
| `qq_cards/cards.jsonl` | 789 张 QQ 窗卡（原卡，含 source_spans / speaker credibility） |
| `qq_info/windows.jsonl` | 2080 个窗口的打分与候选层级 |
| `kb_trial/docs.jsonl` | 统一文档层（QQ 轨 6274 篇） |

**输出（`kb_trial/curation/qq_expansion/`）**

- `qq_worklist_inventory.json` / `.jsonl` —— 逐个窗口的关联记录（见下 schema）
- `qq_expansion_stats.json` —— 对账数字与分类统计
- `workorders/qq_wo_001.json` … `qq_wo_080.json` —— 80 份工单，**全部是未入库窗口**（`shipped` = 0），其中 3 份为救援样本
- `workorders/index.json` —— 工单索引与分组
- `review_impact_manifest.json` —— **材料改动前后差异清单**（受影响工单 + `changed_seq` + 原因；只列 seq 与原因，无隐私），供审核员只重读受影响部分
- `privacy_scan.json` —— **隐私扫描结果**（扫 87 产物 + 83 个 `reviews/`；只记文件/字段/类别，不回显号码与昵称）
- `README.md` —— 字段 schema、`raw_messages` 结构、四类口径、隐私实测与更正、已知局限

**重跑命令**

```
python kb_curation_qq_expansion_materials.py              # 生成工单与清点
python kb_curation_qq_expansion_materials.py --check      # 自检（含 sha256 对比）
python kb_curation_qq_expansion_diff.py                   # 材料改动差异清单
python kb_curation_qq_expansion_privacy_scan.py           # 隐私扫描
```

**四类分组口径（互斥，seed=20260921，固定）**

| 组 | 口径（机械谓词，可复现） | 池 | 取 |
|---|---|---|---|
| A 完整机制 | `kind=window` 且无未闭合疑问、无 hedge 词，且**同时**出现定义词（就是/指的是/是指/定义为/叫做/称为/等价于/不等于）与时序词（先/再/然后/之后/最后/同帧/结算顺序/优先级/顺序…），且全部片段合计 ≥ 24 字 | 35 | 20 |
| B 数值/公式/代码 | 命中数值单位（帧/针/秒/格/倍/%/费/层/次…）、算式字面（`数字 * 数字` 等）或代码标识符（`snake_case` / `CamelCase` / 含点路径 / `.prefab` `.json` 等） | 381 | 20 |
| C 混合/猜测/整窗拒绝 | 命中未闭合疑问标记（`? ？ 吗 呢 是不是 有没有 怎么 为啥 多少…`）或 hedge 词（可能/应该/大概/我记得/好像/估计/不确定/理论上/据说…） | 169 | 20 |
| D 其余随机 | A∪B∪C 的补集，`random.Random(20260921).shuffle` 后取前 20 | 196 | 20 |

**候选池已排除 8 个已入库窗口**，所以四组池合计 35+381+169+196 = 781（= 789 个窗卡窗口 − 8 个 `shipped`）。四组都满 20，`shortfalls = {}`（若不足会如实留空，不跨组借窗口凑数）。**80 份工单里 `shipped` = 0。**

分组在**窗口**粒度互斥（一个窗口只进一组），组内按 `(kind_rank, window_id)` 排序，kind_rank 取该窗口内最强的文档类型（window=0 < qq_atom=1）。

**重要口径澄清**：A/B/C/D 不是机制主题分类，而是**审核难度分桶**。上游窗卡的 `category`（帧时序/索敌/伤害结算/位移/寻路/干员机制/技能特例/数值与读图/关卡与出怪/其他）才是主题；同一个 `category` 会同时出现在四个组里。

**分组不是判定**（`stats.worked_examples` 用真实工单给了实证，两条都按 `window_id` 选取以免疫工单编号重排）：
- `w000013` A 组谓词全过，但上游片段全是对话残句；补上 60 条原始消息后仍定不出一条干净机制，说明「谓词齐备」≠「可判读」；
- `w000077` 只因出现 hedge 词（不确定/可能/应该）被归到 C 组，实为「同帧命中伤害结算顺序」这一真实机制议题，说明「有疑问词」≠「整窗无价值」。

同样，`old_decisions` 的 `reject_reason`（`asr_only_needs_agent` / `too_short` / `fragment_tail` 等）只表示"确定性引擎不肯自动通过、需要代理读"，**不表示内容没价值**；QQ 轨恒带 `no_official_layer` 标志，所以绝大多数行都落到 `asr_only_needs_agent`。

---

## 阶段二（父审 80）交接要点

1. **工单以 `raw_messages` 为主要读材料**：它是本窗**自己 `source_msg_ids`（窗口成员表，为窗卡引用集的超集）覆盖的连续消息块**，按导出顺序、时间升序、speaker 匿名、**全文未截断**，能把「提问 / 假设 / 结论」区分开。工单另外还带原卡、原子、旧判定、overlay/held_out 历史与已入库状态，一般不需要再读其他文件（`qq_worklist.json` 仅供交叉核对）。
   **但工单不是「自包含」的**：`source_spans_excerpts` 只是上游挑选并裁切过的片段（例：原文 `@群友 我记得有些群攻能力…` 被截成 `我记得有些群攻能力…`），阅读时必须以 `raw_messages` 为准。
2. **上下文取数纪律**：`raw_messages` 只从本窗自己的 `source_msg_ids` 取连续消息块，**不从邻近窗口推断来源**，也**不会把别的窗口的 `source_spans` 当成本窗的**。若 `mapping_status` 不是 `ok`（如 `no_cited_ids_in_raw_export`），按上下文缺失处理并写明，不得用邻近窗口替代。既往基于「邻近两窗」推断的 `context_needed` 字段**已删除**；既往基于窗口**声明时间区间**取数的做法**也已废弃**（见下）。
   **两次口径更正**：① `windows.jsonl` 的 `start_ts/end_ts` 与本窗实测相差 +3600 秒——实测新旧范围**重叠 2700/2707 条**，偏移在两侧相互抵消，所以**不是「取错时段」，而是时间范围过窄导致漏取**；② 正文曾按 280 字符截断，**实测旧版取数范围内没有一条超过 280 字符，故未实际切掉任何已交付 seq**（该缺陷是潜在的），现已全文载入。修复后 80 份合计 **3206** 条（旧 2707）。
3. **工单随附 `privacy_note`**：`source_spans_excerpts` 与 `raw_messages[].text` 均已脱敏，不含群号/QQ 号/昵称（`@昵称` 已归一为 `@<speaker_id>` 或 `@某人`；日报 `参与者:` 名单行整行匿名；6–12 位连续数字抹为 `[账号已隐去]`）；`source_msg_ids` 只用于内部定位，**下游如需日志或回传，不得转发 `source_msg_ids` 与 `internal_source` 字段**。
   **隐私口径更正（重要）**：上一版称「拿全部 417 个真实 QQ 号 + 群号 + 昵称扫本目录，命中 0」——**该说法判据过窄、不成立**：它只覆盖 8–9 位 QQ 号，漏掉了 `@匿名id` 后残留的身份数字（如 `@凌弥lemmi 365489981`）、以及日报名单行里的昵称。
   **本版实测**（`qq_curation_qq_expansion_privacy_scan.py`，扫 87 产物 + 83 个 `reviews/`）：真实 QQ 号 **0 命中**、群号 **0 命中**；残留的 6–12 位数字逐条核过，**无一是真实发送者 QQ**（是机制数值、消息 id，或我们自己的 `@<speaker_id>`）；昵称命中均为**同形误报**（命中词是常用语或整句，如「没有人」「标记了一块芝士」）。详见 `kb_trial/curation/qq_expansion/privacy_scan.json` 与 `README.md` §5。**不得据此声称「已彻底脱敏」**——置信上限仍是文本层，未核听、未实测。
4. 回执必须**逐字引用 `raw_messages[].text`**；引用 `source_spans_excerpts` 里的截断片段、或引用不在工单中的文本，即判无效回执。
5. **80 份工单全部是未入库窗口（`shipped` = 0）**；其中 3 份（`w000031` `w000036` `w000041`）是 `staged` **救援样本**——上一轮判为 `source_cannot_settle_claim` 已隔离，本轮用于复核该判断是否仍成立，**不得计为新增覆盖**。注意区分历史动作：`qq_claim_overlay` 的 8 个窗口是「标题被重写过、但从未做过逐条读源之外的判定」，与「已入库」不是一回事；而这 8 个窗口**确实在 `evidence_verdicts.jsonl` 里有 8 条 `supported` 证据判定**（按 `entry_id` 可查到，见 §更正记录）。
6. 审核上限仍是 `text-source-supported`：基于脱敏文本，未核听原片、未做游戏内实测。C 组大概率大量 pending，这正是这一组要证明的事——**不要为了凑产出而把 pending 写成 keep**。
7. **材料相对上一版有变，先读 `review_impact_manifest.json` 再决定重读范围**（生成器 `kb_curation_qq_expansion_diff.py`）：`affected_workorders` **80/80**，`total_changed_messages` **899**，原因分布 `missing_before` 75 / `identity_redacted` 5 / `dropped_before_only` 7；每条列出 `changed_seq` 与 `reasons`，**只含 seq 与原因，不含隐私**。
8. 阶段三扩量前，先看阶段二暴露的口径分歧；**76 个覆盖缺口窗口**与 **`qq_canonical`(51) / `glossary`(50) 两族**需要在阶段三单独决策是否纳入（本阶段均未纳入试批）。

## 阶段四（合并）注意事项

- `kb_trial/curated_high_quality.json` 必须保持**单个 JSON 对象**且 `schema_version` 仍为 `curated-1.0`；新增 QQ 条目沿用 `citations[].status = "resolved_qq_span"` 与 `claim_derivation` 字段结构。
- 合并后必须重跑四件套并同步 `kb_trial/CURATED_OVERVIEW.md` 与 `AGENTS.md` §6.1 的条数（不得背旧数字）。
- QQ 引文始终脱敏；`source_msg_ids` 不得进入任何发布层。
