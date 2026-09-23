# kb 定向语义修复（第三轮）：E1/I/E2 交集 + gate 层通则/覆盖修正 + 冻结新题对照

状态：**已完成**（代理执行 + 第三轮收尾）。基准产物：`kb_pilot_synth/full_candidate_round1/`（第二轮，已验收）。
本轮工作目录：`kb_pilot_synth/semantic_repair_round1/`。
生产 `kb/docs.jsonl` / `kb/synthesized.jsonl` 全程只读（sha `b835a8bf…` / `373554a0…`，mtime 保持 `09-20 00:43`，收尾后再次复核未变）。不 git 提交。

**结果一句话**：最终产物 build3 = `default 1339 / archive 1091（含 quarantine 12）/ old_kept 21801`，`validate_gates_v2.py` 硬违规 0（C1–C12 全绿），30 题冻结集 v4 口径 旧 0.933 / 新 0.958（但差值落在 ±0.033 噪声带内，**不构成提升主张**）。
**计划外的增补另见第 7 节**（审核覆盖层 / registry 对齐 / 覆盖判据保守化 / 同源配额评估 / X07 根因）。

## 1. 目标（可验收）

1. 把第二轮只登记、未改正文的三类语义风险（`E1_universal_unresolved_subject` 509、
   `I_formula_from_ctx_only` 32、`E2_advice_only_rules` 3）**落到实际进入 `gated_default` 的最小交集**，
   标出误报，并只对真有问题的那部分做定向补证或隔离。
2. 修 `gate.py` 两处结构性缺陷：
   - default 层只准放**通则范围**语义（规则自身 `scope=instance/example` 不得占肯定段通则位）；
   - supersedes 覆盖改成**命题级**：仅因被 cited 不得声称完整覆盖；部分覆盖要保留旧原子并标残余；
     共享来源（同一原子被 archive 侧簇引用）不得误删。
3. 冻结**至少 12 道新题**（覆盖未参与调参的议题 + 范围误导/缺主语/符号单位/原公式/有效例题），
   加原冻结 7 题与 20 题集里的失败样本，做「旧 gated vs 新 gated」真实 LLM 对照，代理逐题判分。
4. 报告分栏记录「实际生成 / 拒绝 / 待补证」与「代理复核」，统计本阶段 calls/tokens/墙钟，
   不得宣称开源就绪或全库准确。

## 2. 已核实的交集（`compute_scope.py` → `scope_intersection.json`）

| 项 | 数 |
|---|---|
| `cache_items/` ok 条目 | 2418 |
| `gated_default.jsonl` | 1343 |
| E1 卡（原始诊断） | 509 |
| E1 卡 ∩ gated_default | 459 |
| E1 肯定段规则单元 | 2059 |
| E2 卡 ∩ gated_default | 3（3 规则单元，仍在肯定段） |
| I 规则单元命中 | 36；**在 default 里仍肯定是 0**（G2 `ctx_only_evidence` 已全部移入待核） |

去重后（`e1_triage.jsonl`，只统计 default+仍肯定段 2060 单元）：

| 子集 | 规则单元 | 卡 |
|---|---|---|
| `rule_scope_narrow`（规则自身 scope=instance/example 坐在 universal 卡肯定段） | **199** | 99 |
| `atom_scope_all_narrow`（规则自称 universal，但全部证据原子为 instance/example） | **111** | 40 |
| 两者重叠 | 39 | — |
| **并集（需要复核/修复）** | **270** | **117** |
| `untraceable_atom`（引用原子不在 `kb/docs.jsonl`，短格式/漂移） | **4** | 3 |
| 本地无可判定问题（按「prompt 占位符回声」处理） | **1786** | — |

判定：**E1 的 509 不是 509 张坏卡**。`applies_to` 里的 `未点名` 是 `kb_synthesize.fmt_atoms()` 把源原子
`applies_to=general` 渲染成「(对象:未点名或general)」后模型照抄的**占位回声**；459 张 default 卡里
360 张全部肯定规则为 universal 且证据原子 scope=general → 属误报（须在报告中以证据说明，不做全局降级）。
真正的缺陷集中在上表 270 单元 + 4 坏引用 + 3 张 E2 卡。

## 3. 小样本校准（12 条，代理证据审核标签）

结论五分类：`明确机制` / `明确条件特例` / `缺主体` / `元话语` / `误标`。明细见 `calibration_sample.md`。
**措辞更正（收尾）**：下表「判定」是**代理证据审核标签**——它不是人工审核真值，**仍可能出错**；下文凡写作「真值」处均按此理解。

| # | 单元 | 判定 | 处置方向 |
|---|---|---|---|
| 1 | 伤害结算-0-10:0（真伤=跳过抗性结算） | 明确机制（误报） | 不改 |
| 2 | 伤害结算-0-10:11（伊德减三十抗真伤） | 明确条件特例 | 移出通则段 |
| 3 | 伤害结算-0-10:12（肉鸽落地扣七十血） | 明确条件特例 | 移出通则段 |
| 4 | 伤害结算-12-18:1（弓回不需命中） | 明确机制（误报；原子 instance 但命题是一般性） | 不改 |
| 5 | 伤害结算-4-3:0（炸死临界取三点画圆） | 元话语/方法论 | 移出通则段 |
| 6 | 伤害结算-0-4:0（肉鸽侵蚀损伤削弱基础防御） | 明确机制（误报；来源为本地 ASR 草稿，**不降分**） | 不改 |
| 7 | 寻路-36-5:2（速度改高怪会超过去） | 坏引用 + 表述过泛 | 待核 |
| 8 | 状态效果-8-0:3（拉力来源维持失衡） | 明确机制 + 引用格式缺陷（`sub:` 缺前缀） | 修引用 |
| 9 | 其他-3-17:0（买过龙控器留种子） | 误标（玩法建议当机制） | 待核 |
| 10 | 技能特例-15-1:0（书刀与字必须交替） | 明确条件特例（E2 假阳性；措辞祈使但内容是机制限制） | 不改正文，记 OQ |
| 11 | 技能特例-21-11:0（PRTS 仍是参考指标） | 元话语 | 待核 |
| 12 | 伤害结算-0-10:1/5（抗性结算 vs 生命流失） | 明确机制（误报） | 不改 |

校准得到的判据（写入补证提示词）：
- rule 自身 `scope` 是**最可靠**的确定性信号；`atom scope` 只作辅证，因为「实例观测被正确升格为一般表述」
  与「实例被硬说成通则」在文本上无法用关键词分开。
- ASR 草稿来源是合法证据（校准 #6 的来源就是 `asr_drafts/`），**不自动降权**。
- 「帧/针」在 ASR 里混用是常态，补证不得替换成另一个字；单位不明一律标未闭合。
- 祈使句 ≠ 建议：只有「对局策略/操作建议」才算元话语（#9、#11），机制限制（#10）不算。

## 4. 执行步骤（最终状态）

| # | 步骤 | 产物 | 状态 |
|---|---|---|---|
| 1 | 复核第二轮产物、`gate.py`、`diagnostics.json`、生产 mtime | 只读 | 完成 |
| 2 | 写本计划 | `docs/plans/2026-09-20-kb-targeted-semantic-repair.md` | 完成（收尾时据实回填） |
| 3 | 建工作目录 + 输入指纹（sha256） | `inputs_sha256.json` | 完成 |
| 4 | 算 E1/I/E2 × default 交集（卡级/规则级分开、去重、标误报） | `scope_intersection.json`、`scope_units.jsonl` | 完成 |
| 5 | 本地可追溯性三分（原子存在性/scope/ctx 解析） | `e1_triage.jsonl`、`triage_summary.json` | 完成 |
| 6 | 小样本校准 12 条（代理判定五分类） | `calibration_sample.md` | 完成 |
| 7 | LLM 定向复核/补证（只跑并集 117 卡 + 3 E2 卡，逐条缓存原子落盘） | `cache_semantic/`、`semantic_repaired.jsonl`、`semantic_repair_log.jsonl` | 完成（125 ok / 20 × HTTP 429） |
| 8 | gate v2：通则段/实例段拆分 + 命题级覆盖 + 残余标注 + 共享来源保护 | `gated_default_v2.jsonl`、`gated_archive_v2.jsonl`、`gated_old_kept_v2.jsonl`、`coverage_residual.json` | 完成（**build3 两处再修，见 7.2/7.3**） |
| 9 | 校验器 v2（新增：v2 可复现、`cache_items/` 未变、生产 mtime 未变） | `gate_validation_v2.json` | 完成（**C1–C12**，硬违规 0） |
| 10 | 冻结新题 ≥12 + 原 7 + 20 题失败样本 | `heldout_q_v2.jsonl`、`heldout_v2_frozen.json` | 完成（30 题，sha `690e78f0…`） |
| 11 | 对照评测 旧 gated vs 新 gated v2（同检索/prompt/预算） | `answers_v2_old.jsonl`、`answers_v2_new.jsonl`、`trial_v2_usage.json` | 完成（build1/build2） |
| 12 | 代理逐题判分 + 引用核验 + 回归检查 | `heldout_v2_review.json/.md` | 完成 |
| 13 | 报告 + 状态 | `REPORT.md`、`STATUS.md` | 完成（收尾版含 build3 与噪声带披露） |
| 14 | 跑既有 `validate_full.py` / `validate_gates.py` / `kb/kb_eval.py`（只读） | 结果写入报告 | 完成（全绿） |
| 15 | **（收尾）** 上下文预算审计 + X07 根因定位 | `x07_diagnosis.json` | 完成 |
| 16 | **（收尾）** registry `downweight`/`keep_unknown` 分支回归 + 校验器 C12 | `gate_v2.py`、`gate_validation_v2.json` | 完成 |
| 17 | **（收尾）** supersede 判据保守化 + 13 条边界自检 | `gate_v2.py`、`coverage_boundary_check.json` | 完成 |
| 18 | **（收尾）** 同源配额三模式评估 + 消融 | `quota_check.json`、`answers_v4_*`、`answers_v5_*` | 完成 |
| 19 | **（收尾）** 报告措辞更正（非人工真值 / 相似度≠语义蕴涵）+ 修复前后可浏览示例 | `REPORT.md` 第 0、3、4.1、5.1、9.5、15 节 | 完成 |

## 5. 命令与验收（实际执行的）

```bash
export GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash GROK_BASE=https://aitreez.com/v1  # 仅 shell env, 不落盘
cd kb_pilot_synth/semantic_repair_round1
PYTHONIOENCODING=utf-8 python compute_scope.py            # -> scope_intersection.json  (幂等)
PYTHONIOENCODING=utf-8 python triage_e1.py                # -> e1_triage.jsonl / triage_summary.json
PYTHONIOENCODING=utf-8 python repair_semantic.py --apply  # -> cache_semantic/ + semantic_repaired.jsonl
PYTHONIOENCODING=utf-8 python audit_overlay.py            # -> audit_overlay_llm_miss.jsonl (计划外)
PYTHONIOENCODING=utf-8 python gate_v2.py --apply          # -> gated_*_v2.jsonl + coverage_residual.json
PYTHONIOENCODING=utf-8 python validate_gates_v2.py        # -> gate_validation_v2.json (硬违规 0, C1–C12)
PYTHONIOENCODING=utf-8 python trial_rag_v2.py             # -> answers_v2_*.jsonl
PYTHONIOENCODING=utf-8 python make_review_v2.py           # -> heldout_v2_review.json (代理判分)
# 收尾段
PYTHONIOENCODING=utf-8 python x07_diagnose.py             # -> x07_diagnosis.json
PYTHONIOENCODING=utf-8 python check_coverage_boundary.py   # -> 13/13 PASS
PYTHONIOENCODING=utf-8 python quota_check.py               # -> quota_check.json
QUOTA_MODE=layer_only V3_SUFFIX=v4 python trial_rag_v3.py  # -> answers_v4_*
QUOTA_MODE=off V3_SUFFIX=v5 V3_SEED=v4,v3,v2 python trial_rag_v3.py  # -> answers_v5_*
PYTHONIOENCODING=utf-8 python attribute_noquota.py         # -> attribution_noquota.json
PYTHONIOENCODING=utf-8 python ../full_candidate_round1/validate_full.py
PYTHONIOENCODING=utf-8 python ../full_candidate_round1/validate_gates.py
PYTHONIOENCODING=utf-8 python ../kb/kb_eval.py             # 生产只读
```

验收硬指标（**全部达成**）：
- `validate_gates_v2.py` 硬违规 0（分层 / pending-reject 归档 / 覆盖或残余理由 / 引用有效性 /
  通则段不含 instance/example 规则 / 修复产物可复现 / `cache_items` 与生产文件未被改动 / **registry 落位对齐**）。
- 新题 + 原题合并后逐题有代理判定；**修复侧未出现新增严重错误**（无引用编造、未把未核当已知、未把实例当通则）。
- 报告所有计数与产物文件行数一致；`reviewer_type=agent`。
- **未达成、也不能主张的**：新旧面总体提升——±0.033 噪声带 ≥ 全部差值（见第 7.4 节）。

## 6. 明确不做（最终遵守情况）

- ✅ 不重跑 2418 条合成、不动 `cache_items/`；不写生产 `kb/`；不 git commit；
- ✅ 不用「帧/取整/0.5」等关键词做全局过滤（校准 #6 证明 ASR 来源合法）；
- ✅ 不把 LLM 分类当审核真值；不把 OQ 缺口扣分；不宣称开源就绪；
- ✅ **（收尾补充）也不把我的判定当人工审核真值**——它是代理证据审核标签；
- ✅ 不为任何单题调检索（配额按簇分组，未硬编码 X07）；
- ✅ 不通过提高 `k` 或上下文预算来「修」X07（审计证明预算从不生效，属无据调参）。

---

## 7. 执行中发现的增补（计划外，逐项标注性质）

本计划的 §1–§6 是**执行前**写的。执行过程中发现了 5 处计划里没有的内容；下面区分「计划内」与「执行中发现」并给出证据文件。

### 7.1 审核覆盖层（16 条元话语）—— 计划外，收尾前已补入

**性质**：计划里只想到「LLM 定向复核能把问题降级」，没想到 **LLM 漏检无法自动回收**（它只做单调收紧）。
**发现方式**：抽检复查时，我逐条读修复后的正文，找到 16 条元话语 / 6 张卡仍坐在通则段。
**处置**：`audit_overlay.py`（锚句唯一命中回填真实 idx，失败即报错退出）→ `audit_overlay_llm_miss.jsonl`；`gate_v2.py` 打 3 处补丁合并 overlay；`stats.audit_overlay_applied 16`；校验器新增 **C11** 逐条复核落位。
**效果**：`帧时序与计时器-11-13` 整卡 7 条被清空 → 入 archive。
**副作用与更正**：`spotcheck_worksheet.md` 的 `llm=` 列按显示顺序索引，出现假警报；`label_application_check.py` 按规则文本回溯后证明 **276/276 标签全部正确落位**。

### 7.2 X07 回归的根因与修复 —— 计划外

**性质**：计划 §1 只列了 E1/I/E2 三类风险与 F05/F06，**没有预见会有可复现回归**，更没有预见根因在 gate 的 `registry` 分支。
**症状**：build2 新面对 X07（「眩晕结束时阻挡帧会不会像索敌帧那样立刻触发」）答「不能一概而论…没有直接结论」，同输入 3/3 复现（`variance_check.json`），非采样噪声。
**先排错路**：`x07_diagnose.py` 审计 30 题的 k 与上下文预算 → **两面都是 6 个 hit、`n_at_budget=0`、`n_hits_cut_by_budget=0`**，3000 字预算从不生效 ⇒ **「提高预算」无据，「提高 k」也不是对症**。
**真实根因**：`gate_v2.py` 丢失了 v1 的 registry `downweight` / `keep_unknown` 分支。第二轮的 21 条 registry 决定（`drop 13 / downweight 7 / keep_unknown 1`）里恰好有一条针对 X07 的挤占源 `vod_entry:帧时序与计时器-40-13`（领主实例）——v1 把它降为 `boost 0.15 / weight 0.3`（eff 2.41），v2 让它回落生产值 `boost 1.6 / weight 1.0`（eff **85.08**）→ 抢进 top6 第 4 位。**v2 原地复现了第二轮已修掉的挤占。**
**修复**：恢复三分支；校验器新增 **C12_registry_parity**（`downweight` 必须 `boost≈0.15 & weight≈0.3`；`keep_unknown` 必须带 `registry_action` 前缀；共核 8 条）。
**归因**：`attribute_noquota.py` 证明**关掉同源配额**后 X07 两次采样仍明确作答 ⇒ **registry 对齐本身就修好了 X07，配额不是必要条件。**
**披露（保留的刻意差异）**：`retrieval_weight=0.6`（第二轮 D 类）被带进 default，而 v1 硬编码 1.0 → `fc1:索敌-16-0` eff 由 78.33 降到 46.41。**不减权以求对齐**，如实记录。

### 7.3 覆盖判据保守化 —— 半计划内（计划说了命题级，没说「相似度 ≠ 蕴涵」）

**计划原文**：§1.2「supersedes 覆盖改成命题级：仅因被 cited 不得声称完整覆盖」——方向对了，但**执行时的第一版把判据落成「字符二元组覆盖率 ≥0.7 即算完整覆盖」**，这是错的：
- **措辞**：0.7 是相似度，**不是语义蕴涵**，不能称「充分覆盖」；
- **判据**：「同样的字、意义可能相反」——「需要命中」vs「不需要命中」相似度极高，用它作 supersede 授权会**丢内容**。

**处置**：新增 `gate_v2.supersede_verdict(prop, txt)`：只有**精确子串**且**否定/数值/条件兼容**才授权删除；近似一律 `ok=False, mode="approx"`，只登记到 `coverage_candidates_approx.json`。`COV_THR=0.7` 只用于找候选。
**自检**：`check_coverage_boundary.py` 13 条对抗样例 **ALL PASS**，含结构不变式「`ok=True` ⇒ 命题必是正文精确子串」。
**代价（刻意）**：`old_atom_removed_fully_covered` 5467 → **3061**，`n_residual_fc1` 342 → **1058**、`n_residual_atoms` 592 → **2997**。**宁可多留，不为缩库误删。**
**同时收紧的校验**：C4 从「相似度 ≥COV_THR」改为用**同一个** `supersede_verdict` 复算。

### 7.4 同源配额评估 —— 计划外（计划只允许「若无提升，给最小范围改进」）

**性质**：计划写着「若无提升，如实写『无提升』并给最小范围改进，不重跑全库」。收尾时做的是**最小范围的检索改进实验**，未重跑全库。
**做法**：在 `trial_rag_v3.py` 里加 `QUOTA_MODE`：

| 模式 | 折叠范围 |
|---|---|
| `all` | 任何共享 cluster 的文档互为同源（含 `er1:` / `B1xx` / `canonical` / `vod_atom`） |
| `layer_only` | **只折叠同一簇的分层表示**（`fc1:` / `vod_entry:` / `vod_cluster:`） |
| `off` | 不折叠 |

**关键证据 1（弃用 `all`）**：`quota_check.py` 证明 `all` 会把 gold 的**独立证据卡**当作同簇重复挤掉（F04 的 `B074-imbalance-speed-separate`、F06 的 `B036-path-not-wallhack`，锚点 2/4）；`layer_only` 与 `off` 均为 4/4。
**关键证据 2（配额不损失信息）**：把「gold 文档进 top6」放宽成「**与 gold 同簇的任一文档**进 top6」后，三模式**完全相同**（旧 26/30、新 26/30）。
**关键证据 3（噪声带）**：`layer_only` 在 v1 旧语料上与 `off` 的 30 题 top6 **逐题完全相同** ⇒ `build2` 旧面（0.90）与 `v4` 旧面（0.933）是**同一检索配置**，差值 **+0.033 是重采样 + 复核口径噪声**。由此**±0.033 的噪声带 ≥ 三代全部新旧差值** ⇒ **不主张总体提升**。
**真实 LLM 对照（只调 ctx 改变的题）**：v3（`all`）42 次调用 0.958；**v4（`layer_only`）40 次 0.958**；v5（`off` 消融）20 次 0.942。
**结论**：**采用 `layer_only`**（无 `all` 的挤占缺陷、信息可得性与 `off` 等价、优于 `off` 且无不可定位引用）。
**边界**：配额只落在评测脚本，**未回灌生产 `kb_search.py`**；未为任何单题硬编码。

### 7.5 一处度量缺陷的更正 —— 计划外

`trial_rag.retrieval_metrics()` 的 `hit_gold_cluster` **恒为 0**：它拿 `fc1:伤害结算-12-18` 这类 gold id 直接和 `伤害结算-12-18` 这类 cluster id 比，忘了剥前缀。**上一版报告里「gold 进 top6：旧 26 → 新 19 / 11」因此是严格 id 匹配的产物，不能读成信息丢失**；改用 `quota_check.family_hit` 后为 26/30，两侧相同。

### 7.6 仍未做（明确列出）

- 未在**生产检索**（`kb_search.py`）上验证配额；
- 未对覆盖判据保守化后的**内容层**做抽检（只做了 13 条判据边界自检），多留的约 2400 条旧原子是否仍有冗余未核；
- 未做统计显著的多采样评测（全部 n=1，噪声带 ±0.033）；
- `N09` 欠断定、`N07`/`N08` 对 ctx 敏感、`N15` 取不到时间、`N10` 冻结 `expect` 疑有误 —— 均未处理，见 `REPORT.md` 第 12 节。
