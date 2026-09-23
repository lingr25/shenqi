# 甄选高质量规则层交付说明（`curated_high_quality.json`）

本文件是 `kb_trial/curated_high_quality.json` 的交付说明：它是什么、怎么用、数字从哪来、
以及使用时必须知道的上限。

**状态**：本地甄选草稿层（`schema_version: curated-1.0`，`status: draft_curated`）。
**未部署、未发布、未提交**；本文件不构成发布许可判断，是否对外发布由项目负责人决定。

**一句话**：1462 条机制规则（含 846 条 QQ 群聊轨），每条都带可定位引文（字幕文件+秒 / 已脱敏 QQ 窗口片段），
**可直接接 RAG 检索使用**；但每条的置信上限是**「有文本出处支持这句表述」**，
**不是「游戏内真值已验证」**——本层没有做过原片音画核听。

> **校准落地（calibration_decisions_01，2026-09-23）。** `faultcheck/calibration_decisions_01.json` 的 20 条裁定已写入构建输入并重建：19 条按裁定收窄派生文本和/或补了逐字引文，`qq_expansion:w000141:c01` 未改。条数仍 **1462**。既有引文文本未改，只追加。新 sha256 `2c6b9a7cda6d3d3186838ac118b42dac15f69bd167317b71db6a36b8d7d38c3a`。
>
> **对抗性挑刺（faultcheck）落地（2026-09-22）。** 16 份二审挑刺材料（`curation/faultcheck/triage_*.json`）
> 汇成 338 条 fix 建议与 58 条 remove 结论，已按父指令落地：**撤下 58 条、按建议改写 305 条**
> （只改 `claim`/`subject`/`condition` 三类派生文本，**引文一个字未动**），33 条附理由跳过。
> 条数 1520 → **1462**（b3 keep 319 → 312、b4 keep 508 → 496、阶段二 30 不变；录播轨撤 39、QQ 轨撤 19）。
> 同时把两个群聊昵称残留统一为「某人」（含回执 `source_sha256` 与 manifest evidence 文本/哈希同步）。
> 逐条落地与跳过理由见 `curation/faultcheck/REMEDIATION_REPORT.md` 与 `_remediation_plan.json`；
> 三条产出器的 `merged_result_entry_count` 已改为现算（原 b4 硬编码 1518、阶段二 693），现值 **1462**。
> 连带：`fc1:索敌-22-14#r1` 因去重分组变化浮出为独立候选、经证据审核进 staging（staging 5 → 6）；
> 2 条 QQ 引文（`w000493:c01`、`w000494:c01`）的文本随材料脱敏同步变化，非本次改写所致。
> 新 sha256 `9e5a44652bc80941b014c96dd051b56029bd8566a119d9cf93632cd12912f35d`。
>
> **b3 已发布条目引文的占位缺陷已修复。** 承上一条：材料层改成「按值脱敏」后，
> curated 里仍有 4 条已发布条目的文本带旧占位（占位落在该条自身引文内，使引文不再是逐字原文）。
> 经父裁定批准，4 份工单里被误抹的 6 条消息已按源复原（`curation/qq_expansion/_b3_apply_quote_fidelity_fix.py`）：
> `w000677:c02`、`w000208:c02`（另补入 seq59 作为其 claim 数值的逐字出处）、`w000211:c01`、
> `w001321:c01`。复原值经核对均非导出中的身份号，故**无条目移出**，条数仍 1520（b3 keep 仍 319）；
> 与修复前快照逐条比对为**改动 4 条、添加 0、删除 0、其余 1516 条内容不变、顺序不变**，
> curated 内占位残留 **0**。新 sha256 `42c0efbdba78092ffd38f4faac3cb68ae0643297d48cf69397ffcb2580ee21bd`。
>
> **b3 遗留 pending 的隐私修复重审 2 条已并入。** 材料层把「按形态抹除 6–12 位数字」
> 改为「按值脱敏」（只抹导出里真实的 QQ/UID/群号）后，b3 批 `w000511` 的两条关键消息在冻结工单里
> 仍带旧占位；本轮按修复后的渲染逻辑把这两条复原（`curation/qq_expansion/_b3_apply_privacy_fix.py`，
> 见同目录 README_B3.md），并对 b3 全部 10 条 pending 逐条重读原文重判：
> `w000511` 的 `c01`/`c02` 回 keep，其余 8 条维持 pending，b3 批 keep 317 → **319**。
> 已在库的 1518 条逐条比对为 **0 改动**（添加 2、删除 0）。
>
> **阶段四 b4 批 508 条已并入。** 在阶段三 b3 批后的 1010 条之上，经 QQ 精选扩展阶段四 b4
> （441 窗 / 572 条候选 claim）的全量收敛审读与父对 28 条存疑的逐项裁决，新增 508 条 QQ 群聊轨机制规则
> （逐条裁定见 `curation/qq_expansion/audit_decisions_b4.json`，来源
> `curation/qq_expansion/approved_manifest_b4.json`，现状态 `approved_merged`）。
> 原 1010 条逐字节未变，只追加。
>
> **阶段三 b3 批 319 条已并入。** 在阶段二试批后的 693 条之上，经 QQ 精选扩展阶段三 b3
> （260 窗 / 386 条候选 claim）的全量收敛审读与父裁决，新增 317 条 QQ 群聊轨机制规则
> （逐条裁定见 `curation/qq_expansion/audit_decisions_b3.json`，来源
> `curation/qq_expansion/approved_manifest_b3.json`，现状态 `approved_merged`）；
> 另经上一条的隐私修复重审追加 2 条，b3 批合计 319 条。
> 原 693 条逐字节未变，只追加。
>
> **阶段二试批 30 条已并入。** 在原有 663 条之上，经 QQ 精选扩展阶段二的 80 窗试批复审，
> 新增 30 条 QQ 群聊轨机制规则（逐条裁定见 `curation/qq_expansion/audit_decisions.json`，
> 来源 `curation/qq_expansion/approved_manifest.json`，现状态 `approved_merged`）。
> 原 663 条逐字节未变，只追加。

---

## 1. 实际交付内容（按最终 JSON 实测）

| 文件 | 内容 |
| --- | --- |
| `kb_trial/curated_high_quality.json` | **主产物**。单个 JSON 对象，`entries` 数组即 1462 条规则 |
| `kb_trial/curation/qq_claim_overlay.json` | 8 条 QQ 条目 claim 的重写记录（原值→新值+理由，逐条可 diff） |
| `kb_trial/curation/qq_claim_held_out.json` | 3 条 QQ 窗口的隔离记录（span 无法确定主张，不进交付集） |
| `kb_trial/curation/curated_staging.json` | **6 条**被隔离条目（**3 条 QQ + 3 条 VOD**），含保留理由 |
| `kb_trial/curation/evidence_verdicts.jsonl` | **620 条**逐条读源判定（612 条 VOD + 8 条 QQ） |
| `kb_trial/curation/curated_validation.json` | 独立校验报告（`status: passed`，含 sha256 与幂等结论） |
| `kb_trial/curation/semantic_review.json` | 全量 814 条的语义内审（claim 层，含被剔条目） |
| `kb_trial/curation/faultcheck/REMEDIATION_REPORT.md` | 本轮对抗性挑刺的落地报告（remove/fix/跳过逐项、连带影响、留待裁定项） |
| `kb_trial/curation/qq_expansion/approved_manifest_b4.json` | 阶段四 b4 批 **496 条**批准产物（`approved_merged`，含 `parent_ruling`） |
| `kb_trial/curation/qq_expansion/audit_decisions_b4.json` | 阶段四 b4 批 572 条候选的逐条裁定（含父裁决段与 `faultcheck` 段） |
| `kb_trial/curation/qq_expansion/approved_manifest_b3.json` | 阶段三 b3 批 **312 条**批准产物（`approved_merged`；含材料修复后重审追加的 2 条、已扣本轮撤下的 7 条） |
| `kb_trial/curation/qq_expansion/audit_decisions_b3.json` | 阶段三 b3 批 386 条候选的逐条裁定（含 `faultcheck` 段） |
| `kb_trial/curation/qq_expansion/review_impact_manifest_b3.json` | b3 批 260 工单的读源影响清单（含交付文本逐 seq 复核） |

**最终 sha256**：`9e5a44652bc80941b014c96dd051b56029bd8566a119d9cf93632cd12912f35d`

### 数字（全部由最终 JSON 直接统计得出）

| 维度 | 值 |
| --- | --- |
| entries | **1462** |
| `review.status` | `agent_verified` 1445、`user_verified` 17 |
| `evidence_review.status` | `supported` 1419、`inherited_verified` 43 |
| **来源轨** | `vod_official` 571、`vod_cloud` 28、`mixed_or_unknown` 17、`qq` 8、**`qq_chat` 838（阶段二 30 + 阶段三 b3 312 + 阶段四 b4 496）** |
| 来源层 | 官方AI字幕 571、云端ASR重转写 28、官方AI字幕+云端ASR 17、**QQ群聊 846** |
| scope | `universal` 646、`general_mechanism` 638、`entity_mechanism` 219、`未标注` 10、`instance` 7 |
| 类别 | 寻路 284、索敌 183、位移 172、帧时序 134、伤害结算 120、帧时序与计时器 87、状态效果 52、干员机制 40、拆包数据 37、其他 34、技能特例 12、数值与读图 14、关卡与出怪 11、技力 8，其余为 1–8 条的细分标签 |
| 来源卡数 | 732 |
| 派生文本订正 | 9 条（见 §4） |
| **隔离（不进交付集）** | **5 条：QQ 3 + VOD 2** |

### 隔离明细（`curated_staging.json`，按轨）

| id | 轨 | 隔离理由 |
| --- | --- | --- |
| `window:w000031#r0` | qq | span 含未闭合疑问「死亡不会清除buff，退出浮空状态机吗」，答案未在片段内闭合 |
| `window:w000036#r0` | qq | 实测句与「理论上…100个干员」假设句并存，「越晚的仇恨应该越高」含「应该」 |
| `window:w000041#r0` | qq | 可复用的只有伤害通式；钩爪位移每 2/4/6 帧的数值是单次实测且讨论未闭合 |
| `fc1:寻路-39-7#r8` | vod | 源自相矛盾：「格子中线」与同章 [03:50:00]/[03:50:17] 的「格子中心」是几何差异（线 vs 点），文本无法判定孰是 |
| `fc1:帧时序与计时器-35-0#r16` | vod | 引文与主播自建模拟程序调试纠缠，无法区分游戏行为与模拟器行为 |
| `fc1:索敌-22-14#r1` | vod | 2026-09-22 挑刺改写 `fc1:索敌-22-12#r3` 的 claim 后，本条不再是它的同文副本、浮出为独立候选；经证据审核判为 `pending`（源无法确定该 claim），进 staging。条目未丢失，见 `curation/faultcheck/REMEDIATION_REPORT.md` §6.1 |

**QQ 轨 11 条的完整去向**：8 条通过并交付（见 §4 表），3 条隔离待人工判读。
（另经阶段二试批新增 30 条 QQ 群聊轨条目，来源与裁定见 `curation/qq_expansion/`。）

---

## 2. 证据审核的上限（这一段是使用前提，请先读）

本层做的审核是**逐条读源比对**：代理打开每条引文所指的转写文本 / QQ 窗口片段，
判断**该文本是否支持这句 claim**。它**不是**下面任何一件事：

- **不是原片核听**：没有回看视频音画，判定依据是官方 AI 字幕或云端 ASR 转写文本。
- **不是游戏内实测**：没有在游戏里复现或复算任何数值。
- **不是独立第三方复核**：`reviewer_type` 字段的值就是 `agent`。
- **不是全量无遗漏**：语义内审工单曾漏掉 2 条已入选条目（后补审），
  同类遗漏不能排除。

因此产物里的 `confidence` 一律不高于 `text-source-supported`（文本层有出处支持），
`evidence_review.review_basis` 与 `limitation` 逐条写明这一点。
**「all reviewed」不等于「all correct」。**

一个必须分开看的细节：**官方 AI 字幕里出现某个字，不等于主播当时确实是这么说的。**
字幕本身有错字（例如把「寻路」转成「驯鹿」、「伤判」转成「商判」）。
凡引文一律保持**原始逐字文本**、不做任何改写；能由同源上下文自证的确定讹写，
只订正派生出的 `claim` / `subject` / `condition`，并在 `derived_text_repairs` 里记录 before/after。

---

## 3. 三种 `review.status` 的真实含义

| 状态 | 条数 | 含义 |
| --- | --- | --- |
| `agent_verified` | 1445 | 代理逐条读源（文本层）后确认该句有出处支持。**不等于已证实** |
| `user_verified` | 17 | 用户明确说过「优秀」的整卡，继承到其未被改写的规则句 |
| `auto_screened` | 0 | 本版交付集内为空；未过审的条目全部隔离在 `curated_staging.json` |

`inherited_verified` 是 `evidence_review.status` 的取值，表示**本条本轮未被重读**：
其判定继承自上一轮，来源是**用户反馈与代理文本审核**，**不是核听**。
该类条目共 43 条，逐条带 `limitation` 说明其旧判定未经复核。
（阶段二 30 条、阶段三 b3 312 条与阶段四 b4 496 条 QQ 扩展条目共 838 条均为本轮逐条读源，属 `supported`，不在此列。）

---

## 4. 本轮改了什么（可复现的变更摘要）

1. **QQ 条目的 claim 不再是窗口标题**。上游把窗口标题（如「嘲讽机制数值与仇恨异常表现」）
   直接当成了机制句，且 `subject`/`condition`/`scope` 全为「未标注」。
   本轮从窗口 span 重新推导出**能被 span 直接支撑**的机制句：

   | id | 原（窗口标题） | 现（机制句） | 判定 |
   | --- | --- | --- | --- |
   | `w000044#r0` | 嘲讽机制数值与仇恨异常表现 | 嘲讽提供固定的 +1000 仇恨加值。 | 通过 |
   | `w000033#r0` | 凯尔希抓人目标判定逻辑与同帧/同创建时间优先级 | 凯尔希抓人选取创建时间最久的单位；创建时间相同时按默认顺序、即先部署者优先，因此同帧部署时先部署的单位先被抓取。 | 通过 |
   | `w000042#r0` | 恐惧地块选取与恐惧源为自己时的寻路回落 | 恐惧地块不看来源格，直接取绑定干员（生成该单位的干员）视野范围内的地块；恐惧源是自己的情况下没有恐惧地块，寻路时回落到自己的地块上，表现为在自己地块内乱走。 | 通过 |
   | `w000006#r0` | 夜半眠兽撤退与开技能出睡帧时序 | 夜半眠兽的睡眠状态在撤退或再部署时立即解除，而开技能后第 16 帧才施加睡眠。 | 通过 |
   | `w000012#r0` | 阻挡与索敌同帧导致群攻能力被插入结算 | 部分群攻能力的锁人分为「决定锁人」与「决定锁谁」两步，中间可被插入结算；阻挡与索敌发生在同一帧时，该插入即会发生。 | 通过（修正初稿超范围写法） |
   | `w000027#r0` | 弹道组件结构定义与Prefab拆包路径 | 弹道一般分为三个部分：Projectile…／Movement…／以及可能存在的 HitBehavior…；要找弹道数据，建议从单位的 prefab 取得弹道 id，再用该 id 搜索弹道并查看数据（要看的字段在 Movement 里）。 | 通过（修正初稿超范围写法） |
   | `w000037#r0` | 仇恨0.1精度比较与医疗索敌 | 仇恨值以 0.1 为精度比较：比较时将双方仇恨临时乘以 10 转为整数，再比较这两个整数。 | 通过（修正初稿超范围写法） |
   | `w000040#r0` | 麻痹免疫判定布尔写反与_isUnset配置 | 在麻痹免疫相关判定中，免疫「关着」的单位反而才通得过判定；该判定把「没有麻痹免疫」写成了「并非没有麻痹免疫」，配置项名为 _isUnset（意为「没有这么个东西」）。 | 通过（修正初稿超范围写法） |

   逐条 from/to 与取舍理由见 `curation/qq_claim_overlay.json`；
   每条的读源判定与局限见产物内 `evidence_review`。
   **引文一律未改**，仍是群聊原文片段。

2. **3 条 QQ 窗口隔离，不泛化**。`w000031`（span 含未闭合疑问「死亡不会清除buff…吗」，
   答案未在片段内闭合）、`w000036`（实测句与「理论上…100个干员」假设句并存，
   「越晚的仇恨应该越高」含「应该」）、`w000041`（可复用的只有伤害通式，
   钩爪位移每 2/4/6 帧的数值是单次实测且讨论未闭合）。
   这三条**没有**被写成机制句，已移入 `curated_staging.json`，隔离理由逐条记录。

3. **`inherited_verified` 的理由改成实话**。原文写「该条在上轮即已逐条核听」——不实。
   现为「本条未进入本轮证据审读工单；其 review.status=… 来自上一轮由用户反馈与代理文本审核
   作出的判定，本轮未重读、未核听」。

4. **QQ 条目 disclaimer 不再声称录播自动优先**。原文写「权威真值以主播录播推导为准」，
   与本层 `conflict_policy`（明确 *no automatic precedence*）自相矛盾。
   现改为只说明文本来源，并指向 `conflict_policy`：分歧并列呈现、留待人工判断。

5. **`derived_correction_disposition=pending` 由 3 条降为 2 条**（见 §7）。

6. **修复了 QQ 轨整轨被漏审的链路缺陷**（本轮最关键的一处）。上一版把 11 条 QQ 全部
   排除在交付集外，根因不是内容不合格，而是**两个环节的选取器都用了 `review.status`**：

   - `kb_curation_evidence_review.py` 生成工单时只选 `auto_screened`。
     QQ 轨在 `kb_curation_decide.py` 里是以 `agent_verified` 出闸的，
     因此**从未进入证据审读工单**（`evidence_verdicts.jsonl` 里 612 条全是 VOD）。
   - `kb_curation_evidence_apply.py` 随即走「无 verdict」分支，给 QQ 打上
     `inherited_verified`，理由还写成「上轮即已逐条核听」——**该核听并不存在**。

   修法：工单选取器改为「本阶段尚无 verdict 的条目」（与 `review.status` 解耦），
   QQ 轨与 VOD 轨走同一套 schema、同一套判定。11 条的 span 已逐条比对：
   **8 条通过并交付，3 条隔离**。

7. **复核中发现并修正了初稿 4 处超出 span 的写法**（自查，非外部指正）：

   | id | 初稿问题 | 修正 |
   | --- | --- | --- |
   | `w000012#r0` | 把「分为两步、中间可插入」写成群攻能力的普遍结构，丢掉 span 的「部分」「有些」「我记得」限定 | 限定词回填 claim 与 subject |
   | `w000027#r0` | 把「弹道**一般**分为三个部分」升格为「由三个部分组成」，并抹掉「最好是从…」的建议口吻 | 回填「一般」「建议」，补回被省略的「你要的东西在Movement里面」 |
   | `w000037#r0` | 用「；」把互不相关的仇恨精度与医疗索敌两条机制并成一条 claim | 只保留仇恨精度比较；医疗索敌因含「一般」且同窗口无独立载体，移出 claim |
   | `w000040#r0` | 写了「_isUnset 为 true 才表示没有麻痹免疫」，而 span 只给配置命名含义；该对应关系仅见于他人的评论句 | 收回到 span 字面表述 |

8. **`fc1:寻路-39-7#r8` 按你的判断隔离**。该条不是措辞差异：claim 与引文写「格子**中线**」
   （一条线），而同一章 `[03:50:00]`「寻路坐标一定出生在一个格子的**中心**」、
   `[03:50:17]`「路径点都在**中心**」（一个点）。几何含义不同、结论会随之不同，
   文本无法判定主播是口误还是另有所指，已移入隔离集，不替来源取舍。

---

## 5. 怎么用

```python
import json
d = json.load(open('kb_trial/curated_high_quality.json', encoding='utf-8'))
d['schema_version']   # 'curated-1.0'
d['entry_count']      # 1462
for e in d['entries']:
    e['claim']                                    # 规则句
    e['subject'], e['condition'], e['scope']      # 主语 / 触发条件 / 适用范围
    e['citations'][0]['quotes'][0]['text']        # 引文原文（逐字，未改）
    e['citations'][0].get('transcript_file')      # VOD 轨：定位用的转写文件
    e['citations'][0].get('t_start')              # 秒；QQ 轨为 None，只有窗口片段
    e['review']['status'], e['review']['reason']  # 证据审核
    e['evidence_review']                          # 本轮读源判定 + 置信上限 + 局限
    e['semantic_review']                          # claim 层语义内审
```

过滤提示：

- 只要官方字幕支撑的条目：`e['source_layer'] == '官方AI字幕'` → 571 条。
- 只要 QQ 群聊轨：`e['track'] == 'qq'` → 8 条（用 `--layer qq`）。
- 复核引文时必须先看它落在哪一层：官方字幕轨读 `transcripts_txt/`，
  30+17 条落在 `asr_drafts/`（对应分P没有官方字幕，正文来自云端 ASR 重转写，
  权威性更低，详见 §6）。
- QQ 轨 11 条（阶段二之前的老 QQ 条目）的去向：**8 条在交付集**，
  3 条在 `curated_staging.json`（见 §1 隔离明细）。
  阶段二 30 条、阶段三 b3 312 条与阶段四 b4 496 条的裁定记录另见 `curation/qq_expansion/`。
- b4 批条目：`e['origin']['card_section'] == 'QQ扩展(阶段四b4批)'` → 496 条；
  其 `evidence_review.source_path` 指向 `workorders_b4/`、`audit_decision` 指向
  `audit_decisions_b4.json`，与 b3 条目可区分；父对 28 条存疑的裁决见 manifest 的 `parent_ruling`。
- b3 批条目：`e['origin']['card_section'] == 'QQ扩展(阶段三b3批)'` → 312 条；
  其 `evidence_review.source_path` 指向 `workorders_b3/`，与阶段二条目可区分。

命令行检索：

```
python kb_curated_search.py --self-test                    # passed
python kb_curated_search.py "索敌帧 远程抬手" --k 5
python kb_curated_search.py "事件帧 目标丢失" --review agent_verified
python kb_curated_search.py "伤判 闪避 格挡" --layer official
python kb_curated_search.py --id "fc1:帧时序与计时器-37-5#r0"
python kb_curated_search.py --stats
```

`--review` / `--layer` / `--category` 是硬过滤，**不会**回退到更宽的 `kb_trial` 层。

---

## 6. 已知局限

1. **未核听原片、未实测游戏**：全部判定基于转写文本。置信上限 `text-source-supported`。
2. **官方 AI 字幕不是权威真值**：字幕本身有转写错字；引文照原样保留，派生文本只在可自证时订正。
3. **30 + 17 条的证据落在 `asr_drafts/`**（云端 ASR 重转写，对应 4 个分P 无官方字幕），
   权威性低于官方字幕轨。需纯官方字幕时按 `source_layer == '官方AI字幕'` 过滤（608 条）。
4. **1473 条 `supported` 是逐条读源判定**；另 45 条 `inherited_verified` 的旧判定本轮未复核，
   旧判定本身也未核听（b3 与阶段二试批共 349 条 QQ 条目均为本轮逐条读源，不属 inherited 部分）。
5. **2 条 `derived_correction_disposition=pending`**（另有 292 条 applied、324 条 not_needed）
   属「源措辞存疑但**不影响**实际主张」，逐个判定见 §7。
6. **9 条派生文本订正**只改了 `claim`/`subject`/`condition`，引文未动；
   同类 ASR 讹写若未被同源上下文自证，本轮**未**改动（不做猜测性订正）。
7. **少量引文不是逐字**：`normalised` 11 条、`paraphrase` 14 条，已分级记录，
   未按逐字引文对待。
8. **语义内审覆盖面本身有漏**（曾漏 2 条），1462 条**不保证无一遗漏**。
   本轮另发现并修复了 QQ 轨整轨漏审的链路缺陷（§4 第 6 条）——**选取器缺陷可以整轨静默漏审**，这一点必须记住。
9. **单代理判定**，非独立第三方复核。
10. **QQ 轨仍是待补的重头**：阶段二试批 30 条、阶段三 b3 批 312 条与阶段四 b4 批 496 条已并入（见 §7），
    但 `qq_worklist.json` 中仍有大量 QQ 候选等待同样方式逐条读源。
    b3 批实测产出率约 1.22 条/窗（260 窗 → 317 条，材料修复后重审再 +2 → 319，2026-09-22 挑刺再撤 7 → 312）、
    b4 批约 1.15 条/窗（441 窗 → 508 条，父裁决后降 5 条，挑刺再撤 12 → 496），均高于阶段二试批的 0.375 条/窗。
11. **隔离条目未删除**：6 条（QQ 3 + VOD 3）全部留在 `curated_staging.json`，不静默丢弃、也不发布。
    另有 b3 批自身被裁定为非 keep 的 74 条（reject 66 + pending 8）与 b4 批的 76 条（reject 46 + pending 30），
    全部留在 `audit_decisions_b3.json` / `audit_decisions_b4.json` 的 `decisions` 里，连同理由码与父裁决记录、
    以及本轮 `faultcheck` 段的逐条挑刺落地记录，可逐条复核，同样不删除。
12. **隐私**：QQ 证据只保留消息文本与窗口标识，不含群号、QQ 号或昵称。
    2026-09-22 起两个群聊昵称残留统一为「某人」，涉及材料连同回执 `source_sha256`、manifest evidence 文本与哈希一并同步
    （细则见 `curation/faultcheck/REMEDIATION_REPORT.md` §2）。
13. **本层不是 `kb_trial` 的替代**，也不替代 `kb/` 统一层；旧层回归通过不能当作本层成绩。
14. **未部署、未提交**：未执行 `git commit` / `git push`，未写入生产 `kb/`。

---

## 7. `derived_correction_disposition = pending` 的 2 条：逐个判定

判据：`derived_correction` 文本中含「疑为 / 存疑 / 不确定」即记为 pending。逐条结论如下。

| id | 存疑点 | 判定 |
| --- | --- | --- |
| `fc1:状态效果-15-14#r3` | 源句「反之」疑为「反制」的讹字 | **不影响**。claim 用的是上下文一致的「反制」，与源意图一致；存疑只在引文原字 |
| `fc1:索敌-26-2#r3` | 「干源」「无视见真」「通知他出生」三处疑为讹写 | **不影响机制**。claim 未依赖这三处；`reason` 已记明两条引文属同句在分段切点处的重复定位、**不构成第二处独立依据** |

两条**均未隔离**：存疑点只落在引文原字层面，不影响 `claim` 所陈述的机制。

> **原第 3 条 `fc1:寻路-39-7#r8` 已改判隔离。** 上一版把它归为「只是术语差异、不影响主张」，
> 这个判断是错的：`格子中线` 与 `格子中心` 是**线 vs 点**的几何差异，claim 主张的是
> 「路径点在中心」这一几何事实，若真为中线则结论不同。同章 `[03:50:00]`、`[03:50:17]`
> 两处均作「中心」，仅引文所在 `[03:50:40]` 作「中线」，文本无法判定孰是，故隔离，
> 不替来源取舍。该条因此从 `pending` 类重归类为 `source_cannot_settle_claim` 隔离项。

---

## 8. 功能改变时请同步本文件

以下任一改动都会让本文件的数字失效，改完请重跑并更新本文件的实测值与 sha256：

- 改 `kb_curation_evidence_close.py` 的 `REPAIRS` / `QQ_REPAIRS` / `QQ_PENDING` / `PENDING`
  或 `QQ_VERDICT_REASON`；
- 改 `kb_curation_evidence_apply.py` 的发布/隔离逻辑；
- 改 `kb_curation_build.py` 的字段契约或过滤条件；
- 改 `kb_curation_evidence_review.py` 的工单选取器（**注意：它必须按「尚无 verdict」选取，
  不能按 `review.status` 选，否则会重演 QQ 轨整轨漏审**）；
- 增删 `kb_trial/curation/` 下的工单与审核文件。

复现命令（顺序固定）：

```
python kb_curation_evidence_review.py --all   # 工单覆盖全部条目（含 QQ 轨）
python kb_curation_evidence_close.py          # 重写 verdict + QQ verdict + 生成 overlay（幂等）
python kb_curation_build.py                   # 构建 + 自动跑 evidence_apply + quote_times
python kb_curation_validate.py                # 独立校验，必须 passed 且 idempotent
python kb_curated_search.py --self-test
python kb_trial_verify.py                     # 旧层未被影响
```

---

## 9. 校验记录（本版实测）

### 2026-09-22 对抗性挑刺（faultcheck）落地后

```
python kb_curation_build.py
  entries: 1468   (构建中间态；证据审核后发布 1462，隔离 6)
  output_sha256: 0d8d6a667df76229c252047de83fd90060f43871591de6e9eff1ccd5d6c411a0

python kb_curation_validate.py
  status: passed   failures: []
  entries: 1462   idempotent: true   trial_artifacts_unchanged: true
  curated_sha256: 9e5a44652bc80941b014c96dd051b56029bd8566a119d9cf93632cd12912f35d
  quote_traceability_counts: {normalised: 11, paraphrase: 14}

python kb_curated_search.py --self-test
  status: passed   entry_count: 1462
  review.status: agent_verified 1445 / user_verified 17
  source_layer: 官方AI字幕 571 / 云端ASR重转写 28 / 官方AI字幕+云端ASR 17 / QQ群聊 846

python kb_trial_search.py --self-test
  status: passed

批次产出器
  _b3_converge_build.py  → claims=386 keep=312 reject=66 pending=8 entries=312
  _b4_converge_build.py  → workorders=441 windows_with_claims=313 claims=572 keep=496 reject=46 pending=30 entries=496
  _phase2_apply_faultcheck.py → fix_applied 7, entry_count 30, merged_result_entry_count 1462

定点核对
  58 个 remove id ∩ 发布条目 = 0；1520 − 58 = 1462 逐 id 对账（消失 58、新增 0）
  305 条 fix 的落地字段与发布条目逐字一致，0 处不符
  grep -rl <明文昵称> kb_trial/ = 0 个文件
  改动前后逐字段比对：仅 claim(300)/subject(32)/condition(10) 及其派生字段变化，
  另有 2 条 QQ 引文随材料脱敏变化（w000493:c01、w000494:c01）
```

细则（含 33 条跳过理由、连带影响、留待父裁定项）见 `curation/faultcheck/REMEDIATION_REPORT.md`。

### 早前几轮（保留原样，数字为各轮时点值）

```
python kb_curation_evidence_review.py --all
  worklist entries: 668   （含 11 条 QQ；修复前该工单只选 auto_screened，QQ 全部缺席）

python kb_curation_evidence_close.py
  verdicts rewritten: 612   (+ 8QQ 写入 verdict 文件，合计 620)
  status: {supported: 610, pending: 2}
  derived_correction_disposition: {applied: 285, not_needed: 324, pending: 3}
  entries with repaired derived fields: 9
  qq claim overlay: 8 entries
  qq entries held out as pending: [w000031#r0, w000036#r0, w000041#r0]

python kb_curation_build.py  (连跑两次)
  entries: 1525   (构建中间态 1525 → 证据审核后发布 1520，隔离 5)
  output_sha256: de1f7cbb64f2de35da279ca45810f639bbfb55bf710cfdbdd3f1a3c725372bb6  (构建阶段)
  落盘产物 sha256: 42c0efbdba78092ffd38f4faac3cb68ae0643297d48cf69397ffcb2580ee21bd
  run1 == run2 → 逐字节相同

python kb_curation_validate.py
  status: passed   failures: []
  entries: 1520   idempotent: true   trial_artifacts_unchanged: true
  curated_sha256: 42c0efbdba78092ffd38f4faac3cb68ae0643297d48cf69397ffcb2580ee21bd
  quote_traceability_counts: {normalised: 12, paraphrase: 16}

python kb_curation_validate.py -- 引文保真修复（父裁定 2026-09-22）后的实测
  占位残留：curated_high_quality.json 内「[账号已隐去]」出现 0 次（修复前 4 条条目共 7 处）
  条目级改动：与修复前快照逐条比对 → 改动 4 条、添加 0、删除 0、其余 1516 条内容不变、顺序不变
  改动条目：w000677:c02（引文 30/1.08=27.77777778）、w000208:c02（新增引文 seq59 float(0.0333333)）、
            w000211:c01（引文 每帧仍然-0.0333333）、w001321:c01（reason/limitations 恢复 seq8 原值）

python kb_curated_search.py --self-test
  status: passed（4 个定向查询均 rank 1）
  entry_count: 1520   by_source_layer: 官方AI字幕 608 / 云端ASR重转写 30 / 官方AI字幕+云端ASR 17 / QQ群聊 865

python kb_curated_search.py "阻挡偏移 6帧" / "飞贼 加速度" / "白面鸮 银灰 反隐"
  三条新查询均命中 b3 新增条目（分别命中 w000208/w000154 等、w000939:c01–c03、w000956:c01 + w000317:c02）

python kb_curated_search.py "0.232322" / "弹道飞行 每格 误差"
  b3 privacy_fix 重审新收的 w000511:c01 / w000511:c02 分别 rank 1

python kb_curated_search.py "30/1.08=27.77777778" / "只有float(0.0333333)" /
                          "费用回复速度改变 改变cd大小" / "没有float(1/30) 帧时间 小数点"
  本轮引文保真修复的 4 条（w000677:c02 / w000208:c02 / w000211:c01 / w001321:c01）各命中 rank 1
```

### 阶段四 b4 批 508 条 → 挑刺后 496 条（QQ 精选扩展）

在阶段三 b3 批后的 1010 条之上，经阶段四 b4（441 窗 / 572 条候选 claim）全量收敛审读与父对
28 条存疑的逐项裁决，新增 **508 条**。原 1010 条逐字节未变（添加 508、删除 0、**已逐条比对确认为 0 改动**）。

覆盖：441 窗中 **313 窗有候选（71.0%）**、128 窗零候选（不产生 claim 级裁定）；
候选窗平均 1.83 条/窗，产出 289 窗有 keep。裁定：keep 513 → 父裁决后 **508**、reject 34、pending 25 → 父裁决后 **30**。

```
python kb_trial/curation/qq_expansion/_b4_converge_build.py
  workorders=441 windows_with_claims=313 claims=572 keep=508(with_note=47) reject=34 pending=30 entries=508
  → audit_decisions_b4.json（572 条逐条裁定 + needs_parent_review 28 条 + parent_ruling 段）
  → approved_manifest_b4.json（status=approved_merged，merged_entries=508，merged_result_entry_count=1518）

python kb_trial/curation/qq_expansion/_b4_verify_outputs.py
  errors=0（台账覆盖、audit 与台账逐字段一致、508 条 evidence 逐字与 sha256 独立复算、id 唯一、计数一致）

python kb_curation_build.py
  entries: 1010 → 1523（构建中间态）→ 发布 1518
  qq_expansion_manifest_b4.appended: 508
  逐条比对：添加 508 / 删除 0 / 既有条目内容改动 0
  （以上为该轮合并时点的实测值；此后 b3 材料修复重审再 +2，现为 1520，见 §9 顶部与下节）

python kb_curation_validate.py
  status: passed   failures: []   entries: 1518
  idempotent: true   trial_artifacts_unchanged: true
  curated_sha256: 85f71e91334fc4e8c665f4d94126f24617fee1e15565ac6caf72ba9b83113cd0
  qq_number_quote_sourced: [qq_expansion:w001525:c01]（见下「隐私闸门」）

python kb_curated_search.py --self-test      status: passed（4 个定向查询均 rank 1）
python kb_curated_search.py "抵抗 时间流逝"   rank 1 = w001617:c02（b4），前 5 名全为 b4
python kb_curated_search.py "碰撞半径"        前 5 名含 w001507:c01（b4、rank 2）
python kb_curated_search.py "部署状态机 打断" rank 1 = w001576:c02，前 3 名含 2 条 b4
python kb_trial_verify.py                    status: passed（旧层未受影响）
```

**父裁决（已逐项落地，记录见 `audit_decisions_b4.json` / manifest 的 `parent_ruling`）**：
降级 5 条 keep → pending（`022/c02`、`322/c03`、`322/c04` 主体未锚定；`395/c02` 源自述「我只是这么一说」；
`206/c02` 疑问句「0.51吗」被写成断言）；维持 keep 3 条（`019/c01`、`307/c02` 补「未实战验证」limitations、
`383/c02` 保留 500/1000 数差留注）；批准 7 处改写（8 条：`154/c01`、`156/c01`、`222/c02`、`325/c01`、
`325/c02`、`347/c01`、`358/c01`、`434/c01`）；其余 20 条 pending/reject 维持原判不救回；
`037` 隐私存疑项经父核实（匿名 speaker_id 的 hex 子串，非 QQ 号，且不被任何 keep 证据引用）无需处理。

**隐私闸门的一处收紧后放宽（可复核）**：`kb_curation_validate.py` 的「6–12 位连续数字」检查原按
`claim/subject/condition/context` 直接判失败，b4 的 `w001525:c01`（嘲讽权重系数 10000000，逐字见于其引文）
因此被误判。现改为：**只有该数字串在条目自身引文内也逐字存在时才能豁免**，且豁免在报告
`qq_number_quote_sourced` 里按 entry id 记录、不回显数字；无引文支撑的数字串仍判失败。
本条不影响既有条目（b3 及更早条目无此情形）。

**相关文件**：`curation/qq_expansion/audit_decisions_b4.json`（572 条逐条裁定 + 父裁决段 + 本轮 `faultcheck` 段）、
`curation/qq_expansion/approved_manifest_b4.json`（**2026-09-22 挑刺后 496 条**，`status: approved_merged`）、
`curation/qq_expansion/_b4_dec.jsonl`（111 行人工裁定台账）、
`curation/qq_expansion/user_sample_round4.md`（用户抽审样本 20 条）、
`curation/qq_expansion/README_B4.md`（b4 批说明）。

> **2026-09-22 对抗性挑刺后现值：496 条**（keep 508 → 496、reject 34 → 46、pending 30 不变，572 条候选对账一致）。
> 被撤的 12 条逐条理由见 `audit_decisions_b4.json` 的 `faultcheck.removes`；另有 121 条按二审建议改写派生文本
> （引文未动）。manifest 的 `merged_result_entry_count` 由硬编码 1518 改为现算，现值 1462。

### 阶段三 b3 批 319 条 → 挑刺后 312 条（QQ 精选扩展）

在阶段二试批后的 693 条之上，经阶段三 b3（260 窗 / 386 条候选 claim）全量收敛审读与父裁决
新增 **317 条**；此后又经材料层隐私修复后的重审再收 **2 条**（`w000511:c01`/`c02`，见本节末
「材料层修复后的重审」），**现为 319 条**。原 693 条逐字节未变（已逐条比对确认为 0 改动）。

> **2026-09-22 对抗性挑刺后现值：312 条**（keep 319 → 312、reject 59 → 66、pending 8 不变，386 条候选对账一致）。
> 被撤的 7 条为 w000374:c01、w000509:c03/c04/c05/c06/c07、w001040:c01，逐条理由见
> `audit_decisions_b3.json` 的 `faultcheck.removes`；另有 55 条按二审建议改写派生文本（引文未动）。
> manifest 的 `merged_result_entry_count` 已改现算，现值 1462。下表命令输出为**该轮时点**的实测值，保留原样。

```
python kb_trial/curation/qq_expansion/_b3_converge_build.py
  claims=386 keep=319 reject=59 pending=8 entries=319(with_note=2)
  → audit_decisions_b3.json（386 条逐条裁定 + parent_ruling 段 + material_repair / privacy_fix_reaudit 段）
  → approved_manifest_b3.json（status=approved_merged，merged_entries=319，merged_result_entry_count=1520）

python kb_curation_build.py
  b3 首次合并（历史值）：entries: 693 → 1010，qq_expansion_manifest_b3.appended: 317
  本轮 privacy_fix 重审后重跑（基线为 b4 之后的 1518 条）：
    entries: 1518 → 1520
    逐条比对：添加 2 / 删除 0 / 既有 1518 条内容改动 0
    落盘产物 sha256: 42c0efbdba78092ffd38f4faac3cb68ae0643297d48cf69397ffcb2580ee21bd（引文保真修复后；重审并批时为 d91affb3…）

python kb_curation_validate.py
  status: passed   failures: []   entries: 1520
  idempotent: true   trial_artifacts_unchanged: true
  curated_sha256: 42c0efbdba78092ffd38f4faac3cb68ae0643297d48cf69397ffcb2580ee21bd

python kb_curation_qq_expansion_diff_b3.py
  260 工单中 258 条 needs_reread；delivered_mismatches: 32（涉 17 份工单）
  （这 17 份仍停留在「材料层修复前」生成的版本：交付文本里的身份占位把同句的机制数值一并
   抹成了占位；它们的占位都只落在未被任何已发布条目引用的上下文里，故不影响已发布内容）
```

**本轮顺带修掉的一处链路缺陷**：`kb_curation_evidence_apply.py` 原先只认阶段二的
`approved_manifest.json` / `audit_decisions.json`（路径硬编码），b3 的条目（当时 317 条）因此会落到该脚本的
`inherited_verified` 兜底分支：`evidence_review` 被改写成「本条未进入本轮证据审读工单」、
`review_limitations` 被丢弃（但 `review` 块仍写 `agent_verified`，即**状态与说明自相矛盾**）。
现已改为按 loader 的 `BATCHES` 登记逐个批次处理，b3 条目获得自己的
`evidence_review.status=supported`、`source_path` 指向 `workorders_b3/`、`audit_decision` 指向
`audit_decisions_b3.json`，limitations 也随 manifest 一起落盘；`evidence_review_summary` 新增
`qq_expansion_reverified_by_batch`（阶段二 30 / b3 319 / b4 508）以便事后核验。

**父裁决的 6 条存疑（已按裁决落地）**：`qq_wo_b3_084/c01` 回 keep、`qq_wo_b3_054/c02` 回 keep、
`qq_wo_b3_089/c02` 改写后 keep（去掉原文未出现的「真银斩」，claim 与 condition 均改为原文称呼
「射射射」并在 `review_limitations` 注明；原值保留在 `claim_derivation.from` /
`claim_original`）、`qq_wo_b3_092/c01` 与 `qq_wo_b3_099/c01` 维持 pending、`qq_wo_b3_062/c01` 维持 reject。

**材料层修复后的重审（本轮）**：材料层改为「按值脱敏」后重审 b3 的 10 条 pending，
重审 **10** 条、改判 **2** 条（`qq_wo_b3_182/c01`、`/c02` 转 keep，即 `w000511:c01`/`c02`），
其余 8 条（`092/c01`、`099/c01`、`140/c01`、`189/c03`、`228/c03`、`241/c01`、`243/c01`、`249/c01`）
维持 pending，其理由（假说语气／否定式命题未闭合／测量口径未给／主体未点名）**与材料修复无因果**。
判定依据可复核：修复后同窗的判定量在材料里逐字可读，与 b3 已有的单方近似自测 keep
（`126/c01`「大概是 0.8 格/s」、`133/c01`「约 0.8/30 格」）口径一致；`c02` 的「每格 vs 3 格累计」
口径差已写入 `review_limitations`。
为使 keep 的引文能逐字带出数值，本轮对 `workorders_b3/qq_wo_b3_182.json` 做了**最小材料修复**
（seq 1/seq 3 两条消息按同窗源以修复后渲染逻辑复原，只改数字，`@某人` 脱敏形态不变；
脚本 `curation/qq_expansion/_b3_apply_privacy_fix.py`，幂等），并同步 `reviews_b3/` 的 evidence
文本、reason、过时的 limitation 与 `source_sha256`。
判定台账侧：`audit_decisions_b3.json` 记录 `counts = keep 319 / reject 59 / pending 8`，
并新增 `material_repair`、`privacy_fix_reaudit` 与 `parent_ruling.post_repair_reaudit` 段。

**引文保真修复（父裁定 2026-09-22）**：上一条只修了 w000511，curated 里仍有 4 条已发布条目的
文本带占位——占位落在该条自身引文内（并渗进 `review.reason` / `review_limitations`），引文不再是
逐字原文。父批准后按同一套逻辑修复：

| 条目 | 窗口 / 工单 | 复原 | 条目侧改动 |
|---|---|---|---|
| `w000677:c02` | w000677 / `qq_wo_b3_054` | seq33 `30/1.08=27.[…]` → `30/1.08=27.77777778` | 引文 + limitations（记明与原话自行写作的「27.77帧」之别） |
| `w000208:c02` | w000208 / `qq_wo_b3_083` | seq26 `0.9667-0.9666666666=3.33334e-05`、seq59 `鹰角是float(0.0333333)`、seq69 `最小距离判定是根号0.000001` | **新增引文 seq59**（claim 里写出的该数值此前没有逐字出处）+ limitations 三条改写 |
| `w000211:c01` | w000211 / `qq_wo_b3_084` | seq56 `每帧仍然-0.0333333` | 引文 + `review.reason` + limitations |
| `w001321:c01` | w001321 / `qq_wo_b3_213` | seq8 `只有float(0.0333333)` | `review.reason` + limitations（claim 仍不写出该数值） |

**账号前提校验**：逐条核对复原出的数字串与材料层身份号集合（导出里真实 QQ/UID/群号，855 项）
无交集，复原后工单内占位归零——**不存在「占位背后是真实账号」的情形，故无条目改判 pending
移出精选库**，条数仍为 1520（b3 keep 仍 319）。同窗 `excluded[]` 叙述里因占位而写的句子已同步为
材料事实，**未改任何 verdict**：其中 `qq_wo_b3_083` 的 excluded 项「最小距离判定为根号 0.000001」
原 reject 依据（数值被抹除、原文含量失）因修复而失效，是否改判属 excluded 裁量，**留待父决定**。
修复脚本：`curation/qq_expansion/_b3_apply_quote_fidelity_fix.py`（幂等，工单按字节替换、保留 CRLF；
回执改写逐句精确匹配，重复运行输出为空改动）。台账侧 `audit_decisions_b3.json` 新增
`quote_fidelity_repair` 段（逐工单 before/after + 账号前提校验结论 + 条目级改动说明），
四条条目的 `claim_derivation.audit_note` 也各记一笔。至此**已发布层占位残留为 0**；
仍带占位的 24 份工单（`delivered_mismatches: 32`，涉 17 份）其占位只在未被引用的上下文里。

**相关文件**：`curation/qq_expansion/audit_decisions_b3.json`（386 条逐条裁定 + 重审段 + 保真修复段）、
`curation/qq_expansion/approved_manifest_b3.json`（319 条，`status: approved_merged`）、
`curation/qq_expansion/review_impact_manifest_b3.json`（b3 读源影响清单）、
`curation/qq_expansion/user_sample_round3.md`（用户抽审样本 15 条）、
`curation/qq_expansion/README_B3.md`（b3 批说明）。

### 阶段二试批 30 条（QQ 精选扩展）

在原有 663 条之上，经 QQ 精选扩展阶段二的 80 窗试批复审新增 30 条。原 663 条逐字节未变。

```
python kb_curation_audit_decisions.py            # 逐条裁定 137 条候选（keep 30 / reject 114 / pending 3）
python kb_curation_qq_expansion.py --preview     # 审核闸门 → approved_manifest.json（30 条，evidence_sha256 可复核）
                                                 # 父抽查批准后置 status=approved
python kb_curation_build.py                      # 由 kb_curation_qq_expansion_loader.py 增量并入
  entries: 698 → 693（发布 693）
  qq_expansion_appended: 30
  output_sha256: 0d23d5ca904d3a4c098a432298412323981c5225a5e5961c341e7e03aace287b
  manifest 落盘后置 status=approved_merged（终态，重跑仍会加载）

python kb_curation_validate.py
  status: passed   failures: []   entries: 693
  idempotent: true   trial_artifacts_unchanged: true
  curated_sha256: 0d23d5ca904d3a4c098a432298412323981c5225a5e5961c341e7e03aace287b
```

**相关文件**：`curation/qq_expansion/audit_decisions.json`（147 条逐条裁定）、
`curation/qq_expansion/approved_manifest.json`（30 条批准提案，`status: approved_merged`）、
`curation/qq_expansion/user_sample_round2.md`（用户抽审样本 10 条）、
`curation/qq_expansion/REVIEW_REPORT_80.md`（父审报告）。

**审核口径**：与既有 QQ 轨相同——引文逐字取自冻结工单 `raw_messages`（已脱敏，不含群号/QQ 号/昵称），
`evidence_review.confidence` 上限仍为 `text-source-supported`。

### QQ 轨逐条去向（11 条）

| 去向 | 条数 | ids |
| --- | --- | --- |
| 交付集 | 8 | `w000006#r0` `w000012#r0` `w000027#r0` `w000033#r0` `w000037#r0` `w000040#r0` `w000042#r0` `w000044#r0` |
| 隔离 | 3 | `w000031#r0` `w000036#r0` `w000041#r0` |
