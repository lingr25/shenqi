# VOD 增量甄选扩展管线 (VOD Expansion Pipeline)

本目录（`kb_trial/curation/vod_expansion/`）提供从新录播转写与原子抽取卡片到 `kb_trial/curated_high_quality.json` 甄选高质量库的自足式增量并入流水线，建模自 `qq_expansion` 与 `qq_semantic_review` 的工单-回执-裁定-清单架构。

---

## 1. 架构与目录约定

```text
kb_trial/curation/vod_expansion/
├── README.md                      # [本文件] 架构与操作规约
├── PROMPT.md                      # 代理审读提示词契约（四大闸门）
├── workorders_{batch}/            # [工单层] 冻结候选命题与逐字稿上下文窗口（含 source_sha256）
│   └── vod_wo_{batch}_{idx:03d}.json
├── tasks_{batch}/                 # [任务层] 供审核代理阅读的 Markdown 任务卡
│   └── task_{idx:03d}.md
├── reviews_{batch}/               # [回执层] 代理逐条审读回执（keep / reject / pending）
│   └── vod_wo_{batch}_{idx:03d}.json
├── audit_decisions_{batch}.json   # [裁定层] 全批次审读裁定汇总统合
└── approved_manifest_{batch}.json # [清单层] 终审批准清单（approved / approved_merged）
```

---

## 2. 核心四大审读闸门 (The 4 Gates)

任何候选原子卡必须经受逐条读源审查，唯有同时满足以下 4 点方可裁定为 `keep`：
1. **自包含命题 (Self-contained Claim)**：命题必须是清晰独立、逻辑完整、可脱离上下文自解释的机制陈述，严禁依赖代词（「这个」「它」）或当局特定局况。
2. **逐字引文对齐 (Exact Verbatim Quote Match)**：所有 evidence 引文必须字符级 100% 存在于 `transcripts_txt/{stem}.txt`（或缺字幕分P的云端 ASR `cloud_clips/asr_cloud/{stem}.jsonl`），禁止臆造或跨段无缝拼接。
3. **显式三元约束 (Explicit Subject / Condition / Scope)**：
   - `subject`：明确执行或承受机制的主体（干员、敌人、判定系统等）。
   - `condition`：触发前提或环境限定（如「同帧部署」「处于停驻状态」；如为全域生效则标明 universal）。
   - `scope`：明确区分 `universal`（全域通则）、`instance`（特定关卡/单次实况）、`entity_mechanism`（特定干员/敌人特例）。
4. **排除未定论假说与反问 (No Unresolved Hypotheses / Questions)**：排除 `hypothesis`（主播口头猜测）、`question`（提问反诘）以及未包含参数/条件的泛化日常感叹。

---

## 3. 标准操作流水线

### 步骤 1: 导出候选工单与任务
```bash
python kb_curation_vod_expansion.py export --stem <STEM> --batch <BATCH_ID>
```
- 输入：`knowledge_pilot/{stem}.atoms.enriched.jsonl`（或 `{stem}.atoms.jsonl`）与 `transcripts_txt/{stem}.txt`。
- 输出：`workorders_{batch}/` 与 `tasks_{batch}/`。

### 步骤 2: 代理逐条审读 (Agent Review)
- 代理根据 `PROMPT.md` 与 `tasks_{batch}/`，回读工单内的原始逐字稿上下文，输出结构化回执至 `reviews_{batch}/vod_wo_{batch}_{idx:03d}.json`。

### 步骤 3: 汇聚与校验
```bash
python kb_curation_vod_expansion.py converge --batch <BATCH_ID>
```
- 逐条校验 `source_sha256` 字节匹配，校验每条 quote 逐字存在于逐字稿，产出 `audit_decisions_{batch}.json` 与 `approved_manifest_{batch}.json`（状态默认为 `proposed_pending_parent_approval`）。

### 步骤 4: 父审核与合并并入
- 人工或父代理抽查验收后将清单状态标为 `approved`。
- 运行 `python kb_curation_build.py`，`kb_curation_vod_loader.py` 自动发现并挂载增量条目（`id: vod_expansion:{batch}:{stem}:{local_id}`），审核状态赋予 `agent_verified`，上限诚实标明 `text-source-supported`。
