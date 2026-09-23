# 证据优先机制卡 Implementation Plan

> 步骤 1–4 均已在独立目录执行（1–2：`evidence_round1/`；3–4：`cross_eval_round1/`）。不 git 提交、不改生产 `kb/docs.jsonl` / `kb/synthesized.jsonl`。

**Goal:** 用完整讲段（非固定 40 秒）把高价值议题收成可追溯证据包，再拆成机制 / 实验 / 推导；主语条件单位不明不得当机制，也不得把 accepted.jsonl 当真值。

**Architecture:** 代理逐条对照 `transcripts_txt/`（权威）或仅在无官方稿时用 `asr_drafts/`（草稿层，须标明）。`reviewer_type=agent`，不是人类审核。产出独立目录 `kb_pilot_synth/evidence_round1/`。机制与实验双向挂 id，推导仅在讲段明确支持时写入。文本无法闭合则记 `needs_av` 并停止补全。

**Tech Stack:** 本地 Python 3；无 LLM（本任务不调用 API）。结构校验脚本，不新增测试框架。

**状态（2026-09-20，真实已做）：**

- 步骤 1–2 完成：`evidence_round1/`。`validate_evidence_round1.py` → ok。
- 步骤 3–4 完成：`cross_eval_round1/`（5 议题横向无自动 vod_wins；20 题冻结后 40 次答题）。
- **污染隔离 + 复测闸门完成：** `retest_round2/`。26 completions，total_tokens **30723**。`validate_retest.py` → ok。闸门通过。quarantine 只是 pilot 证据不足 overlay，不是全库真值。
- **首批讲段完成：** `batch100_round2/`。人为过滤得到 94 讲段（候选 368，不是全库 94）。代理逐条证据审核 94/94。`validate_batch100.py` → ok（n_err 0）。机制 39 / 实验 14 / 拒 34 / pending 7。**本轮不生产打包。** 审核墙钟未测，不猜。
- **全量候选完成：** `kb_pilot_synth/full_candidate_round1/`。2418/2418 有结果（13 条 429/SSL 补跑成功）。events 2526（ok 2418 + error 108，其中 429×97）。主进程 token 6,103,436；补跑 30,469。随机100 自动严重 9%（复核后确认漏网主要是 39-6 的 0.5帧/加一，已不覆盖旧卡）。试验 RAG 20 题新侧 19.25/20（Q16 瞬移=传送 0.5）。**不声称全库准确率。不生产打包进 kb/docs.jsonl。**

---

## 12 议题选型（6 可补证 / 3 实验风险 / 3 拒收负例）

| # | cluster_id | 桶 | 焦点 |
|---|---|---|---|
| 1 | 帧时序与计时器-24-0 | 可补证 | 动画/冷却 |
| 2 | 索敌-0-1 | 可补证 | 弹道检测 |
| 3 | 索敌-1-0 | 可补证 | 阻挡帧起点 vs 索敌/避障 |
| 4 | 帧时序与计时器-46-2 | 可补证 | 动画 0.1 倍下限 |
| 5 | 位移-1-5 | 可补证 | 四种移动 |
| 6 | 帧时序与计时器-43-1 | 可补证 | 动画下限取整 |
| 7 | 索敌-22-7 | 局部实验风险 | 城防炮演示；含两套索敌冷却讲段 |
| 8 | 帧时序与计时器-3-10 | 局部实验风险 | 桃金娘空费帧；不猜主语、不把 99/29 当闭合通则 |
| 9 | 寻路-7-8 | 局部实验风险 | 一帧可达；酒神猫是特例实验 |
| 10 | 其他-6-1 | 拒收负例 | 零到五十九无单位 |
| 11 | 寻路-36-6 | 拒收负例 | 例题变量不闭合 |
| 12 | 技能特例-16-7 | 拒收负例 | 3N+2 未定义且声明还有更完整流程 |

含桃金娘与城防炮，禁止把翼德/异德补成规则主语。

---

### Task 1: 高价值议题补完整字幕证据

**Files:**
- Create: `kb_pilot_synth/evidence_round1/evidence_packets.jsonl`
- Create: `kb_pilot_synth/evidence_round1/manifest.json`
- Create: `kb_pilot_synth/evidence_round1/build_evidence_round1.py`

**Step 1:** 按议题从证据时刻向两侧扩到换题边界（不固定 40s）。官方稿优先，否则 ASR 并标 `layer=asr_draft`。

**Step 2:** 每包保留原文行、`file`、`t`。文本不能闭合的写入 `needs_av`，停止脑补。

**Step 3:** 校验每条引用能在文件该时刻附近找到。

---

### Task 2: 拆规则 / 实验 / 推导

**Files:**
- Create: `kb_pilot_synth/evidence_round1/mechanisms.jsonl`
- Create: `kb_pilot_synth/evidence_round1/experiments.jsonl`
- Create: `kb_pilot_synth/evidence_round1/rejected.jsonl`
- Create: `kb_pilot_synth/evidence_round1/review.md`
- Create: `kb_pilot_synth/evidence_round1/validate_evidence_round1.py`

**Step 1:** 机制：主语+条件+单位可陈述，且有原文。实验：绑定部署/关卡/当场演示。推导：仅讲者明确推出的链。

**Step 2:** 机制↔实验双向 id；禁止孤立链接。不明主语/单位进 rejected 或 `needs_av`。

**Step 3:** 跑校验：引用真实、分类分离、无孤链。不把结果写成游戏真值。

---

### Task 3: 5 议题 QQ 横向（已做）

产物：`kb_pilot_synth/cross_eval_round1/cross_merge.jsonl`、`cross_review.md`。不自动 vod_wins。X1/X2 无同题匹配，如实。

---

### Task 4: 20 题端到端回答评测（已做）

题集先冻结 hash 再答题。旧/新同检索器同预算。代理逐条证据审核见 `eval_report.md`（`reviewer_type=agent`）。n=20 不外推。

---

## 红线

- 不改生产 kb 文档层；`accepted.jsonl` 只作线索。
- 权威字幕 vs ASR 分层；ASR 不得写入 `transcripts_txt/`。
- 不 git 提交。
