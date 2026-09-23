# 阶段四（b4）：剩余全部未审 QQ 窗口的工单

**状态：** 材料生成已完成；**审读、父裁决与并入均已完成**——见下方「后续进展」。本文件描述的是
材料生成阶段（当时 `curated_high_quality.json` 仍为 1010 条），**不是最终状态**。

> **后续进展（材料生成之后发生的事）**
> 441 窗经全量收敛审读（`reviews_b4/` 572 条 claim，其中 313 窗有候选）与父对 28 条存疑的逐项裁决后，
> **keep 508 条**已并入 `kb_trial/curated_high_quality.json`：该文件由 1010 条 → **1518 条**
> （QQ 轨 355 → **863**），新 sha256 `85f71e91334fc4e8c665f4d94126f24617fee1e15565ac6caf72ba9b83113cd0`，
> 原 1010 条逐字节未变（添加 508 / 删除 0 / 既有条目改动 0）。
>
> **注**：此后 b3 遗留 pending 的隐私修复重审又追加 2 条，现为 **1520 条**（sha256
> `d91affb3fdd89944ccff239fa8a46bcc69651845eaf3574080f9b22cd8412f4f`）。本文件其余数字是
> b4 合并当时的记录，未随之改写。
>
> **对抗性挑刺后的现值（2026-09-22，最新）。** 16 份二审挑刺材料判定本批 **12 条 remove、121 条 fix**：
> 12 条已从 b4 批撤下（keep 508 → **496**、reject 34 → 46、pending 30 不变），121 条按建议改写
> `claim`/`subject`/`condition`（引文一个字未动）。`curated_high_quality.json` 相应由 1520 条 →
> **1462 条**（sha256 `9e5a44652bc80941b014c96dd051b56029bd8566a119d9cf93632cd12912f35d`）。
> 被撤条目与逐条理由见 `audit_decisions_b4.json` 的 `faultcheck` 段；本 manifest 的
> `merged_result_entry_count` 已从硬编码 1518 改为现算，现值 1462。细则见
> `kb_trial/curation/faultcheck/REMEDIATION_REPORT.md`。
> 裁定见 `audit_decisions_b4.json`（572 条逐条裁定 + `parent_ruling` 段），批准产物见
> `approved_manifest_b4.json`（`status: approved_merged`），人工台账见 `_b4_dec.jsonl`，
> 产出器 `_b4_converge_build.py`、独立自检 `_b4_verify_outputs.py`，
> 人工抽审样本见 `user_sample_round4.md`。
> 父裁决要点：降级 5 条 keep → pending、维持 keep 3 条、批准 7 处改写（8 条）、其余维持原判；
> 非 keep 的 64 条（reject 34 + pending 30）留在 `audit_decisions_b4.json` 不删除。

本批是 QQ 轨扩批的**收尾批**：把阶段二（b2 80 窗）、阶段三（b3 260 窗）与已入甄选库（8 窗）
之外的**全部**未审窗口一次做完，候选池就此清空，不再需要 b5。

- 生成脚本：`kb_curation_qq_expansion_materials.py --stage4`
- **生成阶段未做任何审核判定**：本批只产出读源材料，`verdict` / `claim` 一律留给审核方。
- 生成阶段未改动 `kb_trial/curated_high_quality.json`（当时实测仍 **1010 条**，sha256 前 16 位
  `59d31a41414805f2`）、`reviews/`、`reviews_b3/`、`final_reviews/`、`approved_manifest*`、
  `audit_decisions*`，也未触碰 `kb/` 与字幕层，未调用任何外部 API。

## 1. 实测统计

| 项 | 数值 |
| --- | --- |
| 库存窗口总数 | 789 |
| 已审（阶段二 b2） | 80 |
| 已审（阶段三 b3） | 260 |
| 已在甄选库（shipped） | 8 |
| **候选池（本批）** | **441** |
| **本批窗口数** | **441** |
| **剩余数** | **0** |
| **raw 缺失数** | **0** |

候选池 441 全量入批，未按优先级截断，因此**没有产出 `remaining_b5.json`**——没有剩余窗口。
一次全做在本机实测可行（441 单约 6.7 MB、全流程约 40 秒），拆批只会平白引入一个中间态。

### 分组分布（桶）

| 桶 | 数量 | 含义 |
| --- | --- | --- |
| `no_process` | 367 | 有上游候选行、但从未逐条读源 |
| `no_candidates` | 74 | raw-only：无 worklist 候选行，判定只能靠 `raw_messages` |

历史桶在池中如实记 0（不是被重定义，而是确实已清空）：

| 桶 | 数量 | 说明 |
| --- | --- | --- |
| `final_keep` | 0 | 30 窗全部已在阶段二批内 |
| `rescue` | 0 | 3 个救援样本已在阶段二批内复核（`w000041` 归入 `final_keep`） |
| `keep_before_qq_fix` | 0 | 历史上 supported/keep 的 11 窗：8 窗已入 curated、3 窗在 b2 |
| `qq_pending` | 0 | pending 是阶段二的窗口级判定，已在批内消化 |
| `retry` | 0 | 尚无需要重读的窗口 |

排除计数（用于核对池子为什么是 441）：`final_keep` 30 + `rescue` 2 + `reviewed_b2` 48
+ `reviewed_b3` 260 + `no_process` 367 + `no_candidates` 74 = **781**，加 8 窗 shipped
= **789**，与库存总数吻合。

### 上游分类分布（`classification.group`）

`B_number_formula_code` 197 · `C_mixed_or_guess` 123 · `D_other_random` 113 ·
`A_complete_mechanism` 8

### 议题分类分布（`window.category`）

索敌 81 · 伤害结算 79 · 帧时序 70 · 位移 53 · 干员机制 50 · 寻路 38 · 拆包数据 35 ·
关卡与出怪 16 · 数值与读图 15 · 其他 4

### 体量

441 份工单，合计 6,707,565 字节（平均 15.6 KB/单），`total_raw_messages` = **13,362**。

## 2. 排序规则

先 `no_process` 后 `no_candidates`（有候选行的窗至少有个抽取结论可对照，raw-only 窗没有）；
组内按 `(has_host_authority 降序, window_score 降序, window_id 升序)`。全程确定性，不用随机，
可随时增量续跑。

## 3. 产物

| 路径 | 内容 |
| --- | --- |
| `workorders_b4/qq_wo_b4_001.json` … `_441.json` | 441 份工单，逐字段与 b3 同构 |
| `workorders_b4/index.json` | 批索引：工单号、窗口 id、桶、raw 定位状态、sha256 |
| `mapping_b4.json` | 工单号 ↔ 窗口 id 映射，含桶归属、优先级键与 sha256 |
| `inventory_scale_up_b4.json` / `.jsonl` | 789 窗全量清点：所属桶、是否在池内、未入选原因 |
| `scale_up_stats_b4.json` | 本批统计（计数、桶分布、raw 覆盖、分类分布） |

工单编号前缀 `qq_wo_b4_`，`phase` 为 `phase4_scale_up`，`scale_up.batch` 为 `b4`。
除新增 `raw_only_note`（仅 74 个 raw-only 窗有）外，**top-level 键与 b3 完全一致**；
`raw_messages` 的键与 b3 逐字相同。

## 4. 自检结果

`python kb_curation_qq_expansion_materials.py --check-stage4` → exit 0：

```
STAGE4 CHECK OK (batch=b4): windows=789 batch_windows=441
  buckets={...no_process:367, no_candidates:74...} raw_missing=0 remaining=0
  privacy_qq_hits=0 privacy_group_hits=0
```

- **raw 全量可定位**：441/441，`mapping_status` 全为 `ok`；`seq` 连续；缺失 0。
- **隐私扫描 0 命中**：437 个真实 QQ、439 个真实 UID、群号，在全部 441 份工单中出现次数均为 **0**。
- **幂等**：连跑两次，442 个产物（441 工单 + 4 个清单文件）sha256 逐字节一致。
- **独立复验**（不 import 生成器）：逐条比对 13,362 条消息与源 CSV `发送时间`，确认是
  **只删不增**的变换——13,359 条完全一致，余 3 条是日报机器人正文（`参与者:` 名单与
  `[QQ]` 引用被正确脱敏），机制数值原样保留。
- **时间序倒序如实报告**：`w001545`、`w000112` 各 1 处（源导出按消息 id 排序所致的形态，
  原样保留、不重排不丢弃），与 b3 的处理一致。

### 隐私与机制数值的边界（本批修正）

本批发现并修正了一个**沿用自 b2/b3 的脱敏缺陷**：旧规则把所有 6–12 位连续数字一律抹为
`[账号已隐去]`，但明日方舟的机制数值恰恰长这样，于是被误杀：

| 源文 | 旧输出（错） |
| --- | --- |
| `一帧+0.0333333` | `一帧+0.[账号已隐去]` |
| `1级嘲讽提供300000000基础仇恨` | `提供[账号已隐去]基础仇恨` |
| `现在是10000000*嘲讽` | `现在是[账号已隐去]*嘲讽` |
| `7*24*3600*1000=604800000个种子` | `=[账号已隐去]个种子` |
| `2/3.162277=0.6324556641` | 两个数字都被抹 |

改为**按值脱敏**：只抹导出里真实存在的身份值（每个发送人 QQ、每个发送人 UID、群号），
其余数字一律保留。实测 437 个 QQ + 439 个 UID 在正文中出现 1,648 + 13 次，
而**没有任何非账号数字串与真实账号互为子串**（`262145`、`4294967296` 等
均非任何人的账号，已逐一核对），因此这次改动**不损失任何隐私覆盖**。

修正后 b4 的 `0.0333333` preserved 计数由 **0 → 7**（b3 由 0 → 10，b3 文件已同源重生成，
`--check-stage3` 仍通过且 sha256 与索引一致）。同时新增一条自检：任何
`.[账号已隐去]`（小数点后紧跟脱敏标记 = 分数被吃掉）立即判 FAILED，杜绝同类问题再次静默通过。

## 5. 已知局限

- **置信上限是 `text-source-supported`**：本批只提供材料，判定仍基于**转写文本**，
  未核听原片音画、未做游戏内实测。审核方读源时须自己把握这一上限。
- **官方字幕/导出本身有讹写**，例：「寻路」→「驯鹿」、「伤判」→「商判」。引文必须逐字保留，
  不要顺手订正。
- **`raw_messages` 是本窗的完整消息块，不等于整个群聊线程**：块的范围由 `windows.jsonl`
  的 `source_msg_ids` 成员表决定（取首末引用之间的连续消息），成员表未覆盖的邻近对答不在其中。
- **`source_spans_excerpts` 常是截断片段**（例：原文 `@群友 我记得有些…` 被截成 `我记得有些…`），
  只看片段会把提问误读成断言——这正是每份工单都附 `raw_messages` 的原因。
- **`windows.jsonl` 的 `start_ts`/`end_ts` 与实际消息相差 +3600 秒**，仅作参考，不是取数依据；
  取数依据是窗口自己的 `source_msg_ids`。工单里已写明这一点。
- **74 个 raw-only 窗**的 `atoms_from_this_window` 与 `old_decisions` 为空数组，这是
  「上游没为它产出候选」，不是「材料缺失」；`raw_messages` 仍完整可定位。
- 群号在脚本中从导出文件名解析（`QQ_CHAT_EXPORT.stem.split('_')[0]`），未硬编码。
  产物与本文档均不回显昵称、QQ 号与群号。
- **`w000317`（b3）之外的源序倒序窗口**在 b4 为 `w001545` / `w000112`，属源数据形态。

## 6. 复现

```bash
python kb_curation_qq_expansion_materials.py --stage4        # 生成 b4
python kb_curation_qq_expansion_materials.py --check-stage4  # 自检（幂等 + 隐私 + raw）
python kb_curation_qq_expansion_materials.py --check-stage3  # 回归：b3 不受影响
python kb_curation_qq_expansion_materials.py --check         # 回归：阶段二试批不受影响
```
