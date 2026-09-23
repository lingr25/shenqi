# 阶段二 80 窗试批：审核报告（交父抽查）

日期：2026-09-21 ｜ 范围：`kb_trial/curation/qq_expansion/`，80 份 `final_reviews`

---

## 一、结论摘要

| 项 | 数 |
|---|---|
| 审读窗口 | 80 |
| `final_reviews` 候选命题（`claims[]`） | 137 |
| 逐条裁定 | **147 条裁定，覆盖 137 条候选 + 10 个父点名排除项，0 遗漏** |
| keep | **30**（跨 30 个窗口） |
| reject | 114 |
| pending | 3 |
| `excluded[]` 复核 | 319 条全部归入 pending/reject，无一条升为 keep |

**30 条中 `general_mechanism` 23 条、`entity_mechanism` 7 条。**

统计口径：`keep:reject ≈ 1:3.8`。**未为凑数保留任何一条**——137 条里被拒的 105 条大多栽在
「主体未点名」与「测量口径未给出」两项，这正是 QQ 群聊片段的固有缺陷。

---

## 二、父点名项逐条处置（全部核实，无例外）

### 已按父要求排除（硬隔离，已写入生成器的 `HARD_EXCLUDE`，keep 即报错）

| 工单 | 窗口 | 父点名理由 | 裁定 | reason_code |
|---|---|---|---|---|
| wo003 | w000105 | 2.95 范围 / boss 9 格下侧 / LS-4 虫子偏移 | reject×3 | `unresolved_dispute` / `subject_unidentified` / `scene_specific` |
| wo010 c02 | w000679 | EW / 迷彩指称不明 | reject | `subject_unidentified` |
| wo014 | w001078 | 召唤干员未点名 | reject | `subject_unidentified` |
| wo017 | w001232 | 弹道先后争议 + 样本偏差 | reject | `unresolved_dispute` |
| wo020 | w001294 | 弹道期再部署争议未收束 | reject | `unresolved_dispute` |
| wo041 c01/c02 | w000031 | 浮空起飞混淆 | reject×2 | `conflicting_attribution` / `not_self_contained` |
| wo045 | w000111 | 阻挡数值不明 | reject | `source_scope_unresolved` |
| wo049 | w000177 | 性能实现议论 | reject | `performance_talk` |
| wo051 c01–c03 | w000202 | 自称回忆不确定 | reject×3 | `memory_uncertain` |
| wo052 | w000209 | 阈值量未知 | reject | `measurement_unresolved` |
| wo055 c03 | w000271 | 单场景动画上限通则 | reject | `scene_specific` |
| wo063 | w000363 | 「龙」归属不明 | reject | `subject_unidentified` |
| wo068 c02 | w000611 | 梓兰2 缺攻速条件 | reject | `measurement_unresolved` |
| wo075 | w001465 | 粗算精度单场景 | reject | `performance_talk` |
| wo078 c01/c02 | w001680 | 隐私误遮数值 | **pending×2** | `privacy_redacted` |

### 保留（父点名中允许入的）

- **wo003 c01（w000105）保留**：受击碰撞箱 vs 坐标的分工。原文 seq 12→16 是发言者主动给出的
  通用分界（眼睛看到的是受击碰撞箱，坐标决定弹道去向），句内主语齐备，不依赖任何未点名 boss。
  同窗三个生成规则数值已全部排除。
- **wo010 c01（w000679）保留**：一帧＝一回合。claim 落点收在回合制本身，
  **未把尾句的「迷彩」写进命题**（迷彩在窗内未定义）。
- **wo024 c01（w000041）保留但已按父要求校正**：原文 seq 21 逐字为
  「明日方舟所有伤害都是\n攻击力 * 攻击力倍率 + 附加攻击力」。已用 `CLAIM_REPLACEMENTS`
  把落点限定为**「攻击力计算项」**，明确不泛写为完整伤害公式。
- **wo071 c01（w001044）保留**：父指定正例。已独立回读 src1/2/3 确认——
  seq 1 完全点名提问，seq 2「每0.1s挂0.3s睡眠」、seq 3「格判」为答句，
  seq 12/28 两次复述印证；两个数值均逐字出自 `raw_messages`。

---

## 三、需要父注意的一处「推翻」

**wo003 c01 是本批唯一被推翻的上一轮判定。** 上一轮 `reviews/` 对该窗结论是「一律 pending」。
本次逐条回读后判定：**前半段（seq 5–8 的生成规则、seq 10 的 boss 坐标）确实 pending**
（seq 21 有人当场声明「我写的是实际数据啊」，生成顺序不可靠）；
**但后半段 seq 12–16 是发言者主动给出的通用分界，可以逐字引用，故保留。**

理由已完整写入 `audit_decisions.json` 的 `criterion_note`。若父不认可该拆分，只需删
`audit_decisions.json` 中 `qq_wo_003` 的 keep 记录并重跑生成器即可，其余 29 条不受影响。

---

## 四、交付物清单

| 文件 | 说明 |
|---|---|
| `kb_trial/curation/qq_expansion/audit_decisions.json` | **147 条逐条裁定**，含 `criteria`／`reject_reasons`（11 类 reason_code）／`decisions[]`。供父抽查任意一条候选。 |
| `kb_trial/curation/qq_expansion/approved_manifest.json` | 30 条批准提案，`status: proposed_pending_parent_approval`。每条 evidence 与冻结工单逐字校验，`evidence_sha256` 可复核。 |
| `kb_trial/curation/qq_expansion/trial_candidate.json` | **693 条**的合并候选（663 现有 + 30 新增），仅供父预览。 |
| `kb_curation_audit_decisions.py` | 裁定表生成器（含「候选必须 100% 有裁定」的硬断言）。 |
| `kb_curation_qq_expansion.py` | 审核闸门 + manifest 生成器。 |
| `kb_curation_qq_expansion_loader.py` | **新增**增量 loader，唯一能把 manifest 变成 entry 的地方。 |

改动挂载点：`kb_curation_build.py`（`dedupe_claims` 之后追加）、
`kb_curation_evidence_apply.py`（新增源识别与真实 supported 审核）、
`kb_curation_evidence_close.py`（覆盖自检接受经 loader 验证的新 IDs）。

---

## 五、验证结果（全部实跑）

| 验证 | 结果 |
|---|---|
| 137 条候选是否 100% 有裁定 | **0 遗漏**（生成器硬断言） |
| 30 条 evidence 逐字 / `evidence_sha256` 复现 | **0 失败** |
| 硬排除项 ∩ keep | **空** |
| 既有 663 条逐 entry 未变 | **0 条改动、0 条丢失**（ID 集合与逐 entry JSON 全等） |
| `kb_curation_validate.py` | `status: passed`,`failures: []`,`idempotent: true` |
| 整合幂等（连跑 2 次 build） | sha256 完全一致 |
| `kb_curated_search.py --self-test` | `status: passed`，定向查询全部 rank 1 |
| approved 路径端到端 | 临时置 `approved` → 663→693 条，30 条全部 released 为 `supported`，无一条误入 staging |
| 新增条目检索 | 5 组新查询（缇缇／蓝毒／酒神／阻挡偏移／断罪者）**全部命中新增条目 rank 1** |

正式 `kb_trial/curated_high_quality.json` **保持 663 条**，sha256
`1da4243f5dc9381ad696b8015f77bb61cb66b5a6cf6ecfc8eafd6d313bb847b4`，
`qq_expansion_manifest.appended = 0`。

---

## 六、诚实边界与遗留

1. **审核上限恒为 `text-source-supported`**：基于脱敏文本，未核听原片、未做游戏内实测。
2. **3 条 pending 是材料缺陷，不是判定失败**：
   - wo034 c01 / wo012 c01：数值被隐私规则误遮（形如 `0.0333333` 的小数被整体替换）。
   - wo078 c01/c02：父点名项，数值被误遮。
   按父指示**未改冻结工单、未重跑材料**，只在审核侧记录。
3. **13 份工单的 `claims[]` 为空**（`pending` / `pending_source_cannot_settle`），
   已在 `audit_decisions.json` 中以 `(none)` 记录，不是遗漏。
4. **`final_reviews` 的 claim 文本带「本审归纳（非原文引文）」字样**，是生成流程的模板残留；
   凡这类字样进入 evidence 或 claim 的一律不予采信，判定一律回到 `raw_messages`。
5. **`reviews/` 目录（83 项，旧哈希已失效）未作为依据**，仅 `final_reviews/` 有效。
6. **未提交 Git**（按纪律）。新增/修改的 6 个脚本目前为 untracked。

---

## 七、请父决策

1. **是否批准这 30 条**：批准 = 把 `approved_manifest.json` 的 `status` 改为 `approved`，
   再重跑 `kb_curation_build.py`，loader 即自动并入（663→693）；**未批准时 loader 完全惰性，正式文件不受影响**。
2. **wo003 c01 的推翻判定**是否认可（见 §三）。
3. **是否继续扩至 150–250 窗**。当前每 80 窗产出 30 条（≈0.375 条/窗），
   按此比率 250 窗约再增 60–70 条。建议先对 30 条做一次人工抽听再放量。
