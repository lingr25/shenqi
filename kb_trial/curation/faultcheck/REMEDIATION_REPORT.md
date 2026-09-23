# 对抗性挑刺（faultcheck）落地报告

日期：2026-09-22　范围：`kb_trial/curation/`（甄选草稿层，非发布）
执行：`kb_trial/curation/faultcheck/_faultcheck_apply.py`（任务一/二/三）+ `_b3_converge_build.py`、
`_b4_converge_build.py`、`_phase2_apply_faultcheck.py`（批次产出器落地）+ `kb_curation_build.py`
/ `kb_curation_validate.py`（重建与校验）

二级审读共 16 份 `triage_*.json` 聚合为 338 条 fix 建议与 58 条 remove 结论。本报告记录它们的落地
结果、未能落地的 33 条及理由、连带影响，以及需要父裁定的余项。

---

## 1. 数字总表

| 项 | 值 |
|---|---|
| 精选层条目数 | 1520 → **1462**（−58） |
| remove 落地 | 58 / 58（b3 7、b4 12、vod 39、phase2 0） |
| fix 落地 | 305 / 338（b3 55、b4 121、vod 122、phase2 7） |
| fix 跳过 | 33（逐条记于 `_remediation_plan.json` 的 `fix_skipped`） |
| fix×remove 冲突 | 0 |
| 隐私昵称替换 | 35 处 / 22 个文件（主跑 16 处/12 文件 + 补扫 19 处/10 文件） |
| b3 批 keep | 319 → **312** |
| b4 批 keep | 508 → **496** |
| phase2 批 keep | 30 → 30 |
| 引文（evidence 文本 / evidence_sha256） | 未因 fix 改动；仅 2 条 QQ 引文随材料脱敏而变（见 §3） |
| 冻结试验产物（`kb_trial/{docs,archive,evidence,manifest}.jsonl`） | 未改动（validate 复核） |

发布文件里的 `merged_result_entry_count` 现由产出器**现算**，三处同为 **1462**：
`approved_manifest_b3.json`（原 319）、`approved_manifest_b4.json`（原硬编码 1518）、
`approved_manifest.json`（原 693）。算法：发布文件里非本批条目数 − 其中本轮被撤下的条目数 + 本批 keep。

---

## 2. 任务一 · 隐私昵称统一

两个群聊昵称残留统一替换为「某人」，替换后同步重算受影响材料的 `source_sha256` 与 manifest 的
evidence 文本 / `evidence_sha256`（否则 loader 拒收）。

主跑改写 12 个文件（16 处），全部落在 `curation/qq_expansion/`：

- 工单：`workorders/qq_wo_008`(2)、`qq_wo_041`(1)、`workorders_b3/qq_wo_b3_099`(2)、`qq_wo_b3_100`(2)、`workorders_b4/qq_wo_b4_048`(1)
- 回执：`final_reviews/qq_wo_008`(1)、`reviews/qq_wo_008`(1)、`reviews_b3/qq_wo_b3_099`(2)、`qq_wo_b3_100`(1)、`reviews_b4/qq_wo_b4_048`(1)
- manifest：`approved_manifest_b3.json`(1)、`approved_manifest_b4.json`(1)

同步项：5 份回执的 `source_sha256` 重算（`final_reviews/008|041`、`reviews_b3/099|100`、`reviews_b4/048`），
2 份 manifest 的 evidence 文本与 `evidence_sha256` 重算。`reviews/`（阶段二 round-1 回执目录）只做文本
替换、不重算 sha——loader 读的是 `final_reviews`，该目录的 sha 不参与校验。

补扫（`--privacy-only`）另改 10 个文件（19 处）：本轮挑刺自己的分析件与落地表
（`faultcheck/{chunk_17,chunk_22,faultcheck_b3,findings_17,findings_22,flags_09,flags_11,triage_09}`）、
b4 上下文摘录 `qq_expansion/_b4ctx/c04.txt`、以及被它再生成的 `qq_expansion/audit_decisions_b3.json`。

**脚本本体不留明文**：`_faultcheck_apply.py` 的替换表改为 base64 常量（`_decode_terms()`），
故 `grep` 明文昵称在 `kb_trial/` 下为 0（`__pycache__` 里一份旧的编译产物已删）。

**「自忍」保留并上报**：本批两处（`workorders_b4/qq_wo_b4_433` seq3「h8-4自忍」、seq75「之前看自忍」）
指自限玩法/观赏对象，不指人，且不在任何已发布条目内，故不替换。`reviews_b4/qq_wo_b4_433.json` 与
`_b4ctx/c26.txt` 同理保留。

**两点须知的边界**：

1. `qq_info/`（22.7 万条原始群聊，`.gitignore` 忽略、非流水线材料）仍含真实昵称——它是脱敏的来源，
   本次未动，也不应动。
2. `kb_trial/archive.jsonl`、`kb_trial/evidence.jsonl`（以及 `kb/` 旧层）里能 grep 到「小＋拉丁字母 A」
   这样的字样，但那是 ASR 把「小于」错写成「小<A>」的产物（同段原文另见「小鱼」「小于6」；`kb/` 的
   `quality_audit*.jsonl` 已把它标为 `asr_suspect`），**不是昵称**。这两个文件是冻结试验产物，
   `kb_curation_validate.py` 要求字节不变，故未动、也不应动。

---

## 3. 任务二 · remove 58 条

按二审 `_triage_agg.json` 的 remove 清单从产出器侧真正撤下：

| 轨 | 条数 | 落地方式 |
|---|---|---|
| QQ b3 | 7 | 写进 `faultcheck_b3.json` 的 `removes`；产出器把 verdict 覆盖为 `reject` + `reason_code=faultcheck_remove`，条目不再进 manifest |
| QQ b4 | 12 | 同上（`faultcheck_b4.json`） |
| 录播 vod | 39 | `decisions.jsonl` 对应行改成 `decision=reject`，并记 `reject_reason=faultcheck_remove: …`、`audit_kind/audit_verdict/audit_reason` |
| QQ phase2 | 0 | 本批无 remove |

校验：58 个 id 在重建后的 `curated_high_quality.json` 中命中数为 **0**，且原有 1520 条里恰好消失这 58 个 id、无新增、无误删。

b3 的 7 条被撤项原本都是 keep，故 b3 的 keep 319 → 312、reject 59 → 66、pending 仍为 8（386 条候选对账一致）。

---

## 4. 任务三 · fix 305 / 338

只改 `claim` / `subject` / `condition` 三类派生文本，引文一个字不动。

| 批次 | fix 数 | 落地方式 |
|---|---|---|
| QQ b3 | 55 | b3 产出器按 `faultcheck_b3.json` 的 `fixes` 覆盖后重建 manifest |
| QQ b4 | 121 | b4 产出器同上（叠加在父裁决 `_b4_dec.jsonl` 的 override 之上） |
| 录播 vod | 122 | `decisions.jsonl` 的 `suffix_claim/suffix_subject/suffix_condition`，并记 `derived_text_repairs_faultcheck` |
| QQ phase2 | 7 | `_phase2_apply_faultcheck.py` 直接字段级覆盖 `approved_manifest.json`（不重跑产出器，否则 status 会从 `approved_merged` 打回 `proposed`、loader 拒收整批） |

逐条落地记录：`_remediation_plan.json` 的 `applied`（305 条，含 `fault_type`/`source`/`suggestion`/覆盖字段）。
每条修复同时追加进对应条目的 `review_limitations`，并在 `audit_decisions_*.json` 的
`decisions[].claim_repaired_by_faultcheck` 留痕。

**校验**：305 条的每一个落地字段与 curated 条目逐字比对，0 处不一致。

---

## 5. 跳过的 33 条及理由

| 类 | 条数 | 理由 |
|---|---|---|
| B-1 建议落在本层改不到的引文层 | 11 | 只改 `citations[].chapter`（赛雷亚→塞雷娅、三针→三帧）、`citation.transcript_file`/`t_line_label`/来源层标注。这些字段由冻结的 `kb_trial/docs.jsonl`、`kb_trial/evidence.jsonl` 生成，`kb_curation_build.py` 只是搬运；本层改不到，且改冻结产物会被 validate 拒 |
| B-2 建议补引 citations | 3 | `w000654:c01`(+seq17)、`w000668:c01`(+seq9)、`w000768:c01`(+seq3)。本轮约束是引文一个字不动，增补引文会改变已发布引文集，留待父决定 |
| C 建议只改审核叙述/登记表 | 15 | 建议改的是 `review`/`evidence_review` 的 reason、或只在 `derived_text_repairs` 登记 ASR 讹写（如「同真→同帧」「同针→同帧」「这一阵→这一帧」）、或 claim 已用订正后写法，claim 层本无改动。本轮只改 claim 层文本 |
| D 与既有订正冲突 | 1 | `fc1:帧时序与计时器-27-3#r1`：`evidence_verdicts.jsonl` 已把「空费针」订为「空飞针」，triage 建议改「空费帧」，而源字幕同窗两种写法并存（BV1aTeV6yENP_p4 [56:24]「空费针」/[56:39]「空飞针」）。三方不一致，留待父裁定 |
| E 不宜入 claim 正文 | 2 | `w001789:c01/c02`：建议在 claim 里补注 wiki 草稿出处与同窗争议，属编辑过程元信息，不入机制命题正文 |
| F 父裁定跳过 | 1 | `qq_expansion:w000597:c01`：父裁定初筛为误报（窗内证据逐字含该表述），不改 |

「部分落地」2 条：`fc1:索敌-13-8#r0`（claim 已改，建议附带要求 `scope` 由 universal 降为 instance）、
`fc1:索敌-15-6#r1`（claim 已改，建议附带要求补 `recorded_ym=2026-02` 与补全 `derived_correction`）。
`scope` 取自冻结的 `decisions.jsonl` 的 `suffix_scope`、`recorded_ym` 取自同文件的 `recorded_ym`、
`derived_correction` 由 `evidence_verdicts.jsonl` 生成，本层均改不到，故只落了 claim 部分。

---

## 6. 连带影响（须知道，但都不是缺陷）

1. **去重分组变化**：`dedupe_claims()` 按 `normalise(claim)` 合并。`fc1:索敌-22-12#r3` 的 claim 被改写后，
   它与原先被合并掉的 `fc1:索敌-22-14#r1` 不再同文，后者浮出为独立候选；该候选随后被证据审核判为
   `pending`，进入 `curated_staging.json`（staging 5 → 6）。净效果是**多一条候选被显式评估**，
   发布集条目数不受影响。`fc1:索敌-22-12#r3` 因此失去了它的 `also_from` 溯源一行（原来记的是这条副本）。
2. **2 条 QQ 引文文本变化**：`qq_expansion:w000493:c01`、`w000494:c01` 的引文里含被替换的昵称，
   随**任务一**的材料脱敏同步变为「某人」。这是隐私统一的结果，不是 faultcheck 的 fix 所致
   （fix 从不触碰引文）。其余 1460 条的 `citations[].quotes[].text` 与改动前逐字一致。
3. **`curated_stats.json` 的 `entries` 与发布条数不同口径**：构建脚本在证据审核**之前**统计，
   故本版 `entries=1468`，而证据审核后发布 1462（差额即进入 staging 的条目）。这是既有行为，
   不代表有 6 条丢失。查发布条数请用 `curated_high_quality.json` 的 `entry_count`。
4. **`docs.jsonl` 生成物未动**：`kb_trial/{docs,archive,evidence,manifest}.jsonl` 是冻结试验产物，
   本轮 0 改动（validate 的 `trial_artifacts_unchanged`）。

---

## 7. 验证（全部实测）

```
python kb_curation_build.py        # entry_count 1462；curated_stats.json 报 1468（审核前口径，见 §6.3）
python kb_curation_validate.py     # status=passed, failures=[], idempotent=true,
                                   # trial_artifacts_unchanged=true, entries=1462
python kb_curated_search.py --self-test   # status=passed，entry_count=1462
python kb_trial_search.py --self-test     # status=passed
```

另做的定点核对：

- 58 个 remove id ∩ 发布条目 = **0**；1520 − 58 = 1462 逐 id 对账一致（消失的 58 个 id 与被撤清单完全相等，无新增、无误删）。
- 305 条 fix 的落地字段与发布条目**逐字一致**，0 处不符。
- `grep -rl <明文昵称> kb_trial/` = **0** 个文件。
- 改动前后发布条目按 id 比对：消失 58、新增 0；变化字段只有
  `claim`(300)、`subject`(32)、`condition`(10)，以及由它们派生的
  `evidence_review`/`claim_derivation`、1 处 `derived_text_repairs`、2 处 `citations`（见 §6.2）。
- 重建后 b3 manifest `entry_count=312`、b4 `entry_count=496`，两者与 phase2 的
  `merged_result_entry_count` 均为 1462、且等于发布条数。

---

## 8. 留待父裁定

1. **`fc1:帧时序与计时器-27-3#r1`**：「空费针 / 空飞针 / 空费帧」三方不一致（见 §5 D）。现状是保留既有
   ASR 订正「空飞针」，triage 建议未落地。
2. **3 条补引建议**（`w000654:c01` / `w000668:c01` / `w000768:c01`）：补引会改变已发布引文集，
   本轮按「引文一个字不动」跳过。若父认可，需要单独一轮引文增补（并重算 `evidence_sha256`）。
3. **11 条引文层拼写/指向建议**：要落地必须改冻结的 `docs.jsonl` 或 `evidence.jsonl`，
   会破坏 `validate` 的字节不变约定，需父先决定是否解冻。
4. **匿名哈希进入 claim 正文**：`qq_expansion:w000563:c01` 的新 claim 首次把发言者的匿名哈希
   `0f17ac97` 写进正文（该哈希已是 manifest evidence 的既有字段，非新泄漏）。若不宜出现在 claim 里，
   需改写该条。
5. **claim 内引用内部条目编号**：`w000761:c05`（「与 c01 的关系」）、`w001521:c01`（「见同窗 c02」）、
   `w001151:c04`（「见本条未列入引文的 seq12」）。这些引用在发布层无处可查（`c01`/`seq12` 是挑刺
   内部的条目编号），若要求 claim 自包含须再改写这三条。
6. **「自忍」保留**：见 §2，本批两处均指玩法/观赏对象，未替换。若父认定其中某处指人，可再定点处理。

---

## 9. 复现路径

```bash
# 1) 任务一/二/三。**本轮只需在这一步做一次**；此后材料已收敛，重复跑任务二/三会
#    在已改写的文本上再叠加（_faultcheck_apply.py 的 fix 写的是目标值，重复跑本身不改结果，
#    但它会重写 decisions.jsonl 与 manifests，故非必要不重跑）。
python kb_trial/curation/faultcheck/_faultcheck_apply.py
#   仅补扫昵称（不重跑任务二/三），可安全重复执行，幂等：
python kb_trial/curation/faultcheck/_faultcheck_apply.py --privacy-only
# 2) 批次产出器按 faultcheck 落地表重建 manifest 与 audit（幂等）
python kb_trial/curation/qq_expansion/_b3_converge_build.py
python kb_trial/curation/qq_expansion/_b4_converge_build.py
python kb_trial/curation/qq_expansion/_phase2_apply_faultcheck.py
# 3) 重建发布层并校验（幂等；实测连跑两次 sha256 不变）
python kb_curation_build.py
python kb_curation_validate.py
```

**日常重跑只需要第 2+3 步**（已实测连跑两次结果逐字节相同）。第 1 步只在本轮或
日后挑刺表、昵称表发生变化时才需要，且改完后必须接着跑第 2、3 步。

`_faultcheck_apply.py` 的 privacy_pass 覆盖目录含 `faultcheck/` 本身与 `_b4ctx/`，按 UTF-8/GBK
先试后写、原编码逐字节回写（`_triage_agg.json` 是 GBK）。批次产出器的 `load_faultcheck()` 以
`(window_id, local_id)` 为键——同一窗口可能一次撤多条（b3 的 w000509 一次撤 5 条），以窗口为键会丢。
