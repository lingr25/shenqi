# 机制知识库生产管线 (直播垂直方向)

本文档描述从录播转写到机制知识卡档案的完整管线。新视频到货后按 §3 操作即可。
所有产出落在**草稿层** `knowledge_pilot/`（已被 .gitignore 保护），**严禁**直接写入
`transcripts_txt/` / `cleaned_subtitles/` 等权威层；人工审核前所有卡均为 `claim_status=draft`。

## 1. 管线总览

```
转写文本 ──► ① 章节切分+章内抽卡 ──► ② 原子化 ──► ③ 议题聚类 ──► ④ 跨批归并 ──► ⑤ 实体增强 ──► ⑥ 检索评测
              chapter_extract_         atomize_      cluster_       merge_           enrich_        rag_eval.py
              claims.py                claims.py     atoms.py       clusters.py      atoms.py
              (grok-4.6)               (grok-4.6)    (grok-4.6)     (grok-4.6)       (纯本地)       (纯本地)
```

LLM 一律走 **grok-4.6**（`https://aitreez.com/v1`，环境变量 `GROK_API_KEY`，
可用 `GROK_BASE` / `GROK_MODEL` 覆盖）。**不要用百炼 qwen3.8-max 跑抽取**（贵）；百炼只用于云端 ASR。

## 2. 各环节契约

### ① 章节切分 + 章内抽卡 `chapter_extract_claims.py`
```bash
python chapter_extract_claims.py --stem <STEM> --source official   # 或 cloud
python chapter_extract_claims.py --stem <STEM> --source official --chapters-only  # 只切章节
```
- 输入：官方逐字稿 `transcripts_txt/{stem}.txt`（`[MM:SS]`/`[HH:MM:SS]` 均可，头部元信息行自动跳过）；
  或云端 ASR `cloud_clips/asr_cloud/{stem}.jsonl`。
- Pass1 整场一次性切章（标题/起止秒/kind: warmup|lecture|combat|qa|other，程序校验边界单调、全覆盖）；
  Pass2 章内按 600s 窗（60s 重叠）抽父卡，卡带逐字 quote 证据，程序做 quote 回原文校验。
- 产出：`{stem}.chapters.json`、`{stem}.chapter_claims.jsonl`。
- **断点**：chapters.json 与 chapter_claims.jsonl 均已存在则跳过/续跑。
- 时间轴标记：official 默认 `timeline_ok`；cloud 查 `cloud_clips/timeline_audit.json`，
  `timeline_unverified` 的场会带进卡里，**进 canonical 前必须先修时间轴**。

### ② 原子化 `atomize_claims.py`
```bash
python atomize_claims.py --stem <STEM> [--limit N]
```
- 父卡 → 原子命题；规则先滤噪声（学习方法/元评论），LLM 再判 drop；
  按课型路由 lesson_kind（algorithm/derivation/special_case/observation_default），
  推导链保留 `parent_idx` + `derivation_step`。
- 产出：`{stem}.atoms.jsonl`、`{stem}.noise.jsonl`。
- **注意：覆盖写**，重跑会删除该 stem 旧 atoms（③④ 的全局结果需跟着重跑）。

### ③ 议题聚类 `cluster_atoms.py`
```bash
python cluster_atoms.py [--bucket 索敌] [--only-stem <STEM>]
```
- 全量读所有 `*.atoms.jsonl` → 受控分桶（索敌/寻路/帧时序与计时器/位移/伤害结算/状态效果/技能特例）
  → 桶内 50 张/批聚类。只出档案：agreed / conflict / open，LLM 不裁对错。
- 合并红线：条件不同不合并；特例不并 general；hypothesis/question 不升级为结论；
  observation 不与 conclusion 自动等同；推导链整链同议题。
- canonical 草案硬门槛：agreed + 同 applies_to + 同 conditions + ≥2 独立时间窗 + 无未关闭假设，
  且永远标 draft。
- 产出：`clusters.jsonl` + `clusters_report.md`。**断点缓存** `.cluster_cache.json`，失败重跑自动续。

### ④ 跨批归并 `merge_clusters.py`
```bash
python merge_clusters.py
```
- 修③的批次边界裂痕：同桶议题摘要再送一轮 LLM 判重，union-find 确定性合并，
  状态按 conflict > open > agreed 取最高，重跑 canonical 门槛。
- 产出：`clusters_merged.jsonl` + `clusters_merged_report.md`。断点缓存 `.merge_cache.json`。

### ⑤ 实体增强 `enrich_atoms.py`
```bash
python enrich_atoms.py        # 纯本地, 无 LLM
```
- 每卡加：`claim_id`（sha1 稳定）、`recorded_at`（视频发布日期）、`game_version`（暂为 null，
  待版本日历）、`entity_links`（PRTS 词表精确匹配：operator/enemy/device/status/mechanic/slang/shenqi_slang）。
- 产出：`{stem}.atoms.enriched.jsonl` + `enrich_report.md`。覆盖写，新卡到货直接重跑。

### ⑥ 检索评测 `rag_eval.py`
```bash
python rag_eval.py            # 纯本地 bigram+BM25
```
- 10 个机制提问打榜，重点验证 conflict 议题两面召回。产出 `rag_eval_report.md`。
- 当前基线：**10/10 命中**。扩覆盖后应重跑盯退化。

## 3. 新视频入库步骤

**A. 有官方 AI 字幕的分 P**（首选路径）：
1. 确认 `transcripts_txt/{stem}.txt` 已生成（没有则先走原有的字幕抓取+`clean_transcripts.py` 流程）。
2. `python chapter_extract_claims.py --stem {stem} --source official`（记录 `extract_model` 与 `extract_prompt_sha256`）
3. `python atomize_claims.py --stem {stem}`（记录 `atomize_model` 与 `atomize_prompt_sha256`）
4. 运行实体挂接：`python enrich_atoms.py`（纯本地，注入 `claim_id`、`recorded_at`、PRTS 实体词表链接）
5. 全局议题归并（历史草稿层分析）：`python cluster_atoms.py` → `python merge_clusters.py` → `python rag_eval.py`
6. **增量甄选扩展（权威草稿层入库，推荐路径）**：
   - 导出审读工单：`python kb_curation_vod_expansion.py export --stem {stem} --batch {batch_id}`
   - 代理按四大硬性闸门审读生成回执：`reviews_{batch}/vod_wo_{batch}_{idx:03d}.json`
   - 汇聚裁定与清单：`python kb_curation_vod_expansion.py converge --batch {batch_id} [--approve]`
   - 并入甄选高质量库：`python kb_curation_build.py`（经 `kb_curation_vod_loader.py` 追加）
   - 质量门禁与检索自测：`python kb_curation_validate.py` && `python kb_curated_search.py --self-test`
   - 发布/编译 RAG 生产语料：`python rag_pack/build_rag_pack.py`

**B. 只有音频、无官方字幕的分 P**：
1. `asr/plan_cloud_clips.py` / `asr/cut_cloud_clips.py` 切片 → `asr/transcribe_cloud.py` 走百炼
   `qwen3-asr-flash`（密钥从环境变量 `BAILIAN_API_KEY` 读取，勿写进脚本）→ `asr/audit_timeline.py` 校验时间轴。
   （以上脚本 2026-10 起位于 `asr/`，从仓库根目录运行。）
2. `timeline_ok` 后同 A 的 2-6 步，`--source cloud`。
3. `timeline_unverified` 先修时间轴再入库；源 AAC 损坏的切片（见 `dropped_unrecoverable.json`）不重试。

## 4. 规模适用性核查结论（2026-09 试点后）

已在 3 场试点（计时器云端/寻路官方/索敌官方）外，对全量语料做了核查：

- **官方逐字稿 45 个分 P 全部可直接跑**：时间戳格式 100% 兼容（3 个文件的"异常行"只是文件头元信息，
  load_items 自动跳过）；最大 1382 行，Pass1 单次送 grok 无压力；已用未参与试点的
  `BV1qReG6XE6W_p4` 冒烟通过（3 章、边界校验无问题）。
- **云端 30 个分 P 与官方零重叠**，其中 18 个 `timeline_ok` 可直接跑，12 个 `timeline_unverified`
  会先产出但带标记，不进 canonical。
- 扩到全量 ≈ 试点 3 场的 15-25 倍 LLM 调用量；①②③④ 全部有断点缓存，可分批跑。
- 非机制内容（整场的电影/小游戏）靠 ① 的章节 kind + ② 的噪声规则处理，不需要人工整文件剔除。

## 5. 已知限制（扩覆盖前要有预期）

- `applies_to` 约 64% 为 general，特例收紧需后续一轮 LLM 批处理。
- 参数 `value_norm` 约 48% 未归一（"十的负五次方"未转 1e-5）。
- `visual_required` 卡依赖画面，纯文本无法自证，需抽帧配对或降级。
- `game_version` 全 null，需接版本更新日历。
- 敌人俗称（大盾/刁民船/穿刺花等）不在 PRTS 词表，entity_links 的 enemy 覆盖率低，
  需持续扩充 `prts_entities.json` 的 shenqi_slangs。
- ③④ 的议题划分对同主题跨场次只做档案分行，跨场次的"同一机制不同场次结论"合并
  目前靠人工读 report。

## 6. 效率闸门（2026-09-19 全量跑完后的教训）

全量首轮跑完后人工抽审发现：产出里约 70% 是水（47% 开放问题 + 17% 当局碎碎念 + 5% 噪音），
即大部分 LLM 调用烧在了最终会被丢弃的内容上。新视频入库时按以下闸门前移原则执行，
越便宜的过滤越靠前：

1. **章节级过滤（零成本）**：`{stem}.chapters.json` 里 kind 为 `warmup`/`combat`/`other`
   的章节不进入 Pass2 抽卡（首轮全量约 30% 时长属此类，含打肉鸽碎碎念）。
   仅 `lecture`/`qa` 章进抽取。
2. **抽取 prompt 闸门**：成卡必须满足其一 —— 含参数（帧数/数值）｜含条件+跨局规则｜
   明确提出未解决的机制问题。明确禁止：当局实况描述（"这次红的索敌成功了"）、
   感性评价（"重装很硬"）、问题与答案同源的循环卡。
3. **便宜规则先跑，LLM 只审可疑档**：如「纯 observation 且无 parameters 且无 conditions」
   本地规则直接 noise（首轮以此砍掉 400 簇 / 738 原子，占簇数 13%）。
4. **单成员不建簇**：`cluster_atoms.py` 对单成员 open 簇不再自动成簇，从源头掐断
   「命题→改写问句→原话当答案」的循环卡。

存量数据的补救见 `kb_quality_audit.py`（LLM 三档审计 keep/demote/drop，
结果落 `kb/quality_audit.jsonl` 并回写 `kb/docs.jsonl`）。

## 7. 录播增量并入甄选高质量库与 RAG 语料包管线 (VOD to Curated & RAG Pack)

### 7.1 管线定位与背景
历史全量归纳（`kb_pilot_synth/` 与 `kb/docs.jsonl`）属于旧层实验性全量综合，存在批量重跑成本高、难以局部追溯的问题。
为实现**单视频/小批次增量接入、透明审查、可追溯版本与幂等并入**，本库建立了基于工单-回执-裁定-清单的 VOD 增量甄选扩展管线（`kb_trial/curation/vod_expansion/`），对齐 QQ 扩展（`qq_expansion`）的标准契约。

### 7.2 完整流转路径图
```
新录播分P ──► transcripts_txt/{stem}.txt (官方逐字稿或 cloud ASR)
              │
              ├──► ① chapter_extract_claims.py (带 extract_model & prompt_sha256)
              │    产出: {stem}.chapters.json & {stem}.chapter_claims.jsonl
              │
              ├──► ② atomize_claims.py (带 atomize_model & prompt_sha256)
              │    产出: {stem}.atoms.jsonl
              │
              ├──► ③ enrich_atoms.py (纯本地)
              │    产出: {stem}.atoms.enriched.jsonl (含 PRTS 实体链、recorded_at、claim_id)
              │
              ├──► ④ kb_curation_vod_expansion.py export --stem {stem} --batch {batch}
              │    产出: workorders_{batch}/vod_wo_*.json & tasks_{batch}/task_*.md
              │
              ├──► ⑤ 代理审读 (Agent Review 遵循 PROMPT.md 四大闸门)
              │    产出: reviews_{batch}/vod_wo_*.json (keep / reject / pending)
              │
              ├──► ⑥ kb_curation_vod_expansion.py converge --batch {batch}
              │    校验: source_sha256 吻合 + 引文逐字匹配 transcripts_txt
              │    产出: audit_decisions_{batch}.json & approved_manifest_{batch}.json
              │
              ├──► ⑦ 父代理/人工批准清单 (status: approved)
              │
              ├──► ⑧ kb_curation_build.py (经 kb_curation_vod_loader.py 挂载)
              │    产出: kb_trial/curated_high_quality.json (追加 vod_expansion:* 条目)
              │    门禁: kb_curation_validate.py 保证 0 泄漏、100% 幂等、引文可追溯
              │
              └──► ⑨ rag_pack/build_rag_pack.py (纯本地编译)
                   产出: rag_pack/corpus.jsonl, corpus.json, system_prompt.txt (供外部生产 RAG 直接使用)
```

### 7.3 出处追溯与模型指纹 (Provenance Tracking)
在整条管线中，每一处由模型生成或提取的节点均记录完整版本元数据：
1. **章节抽取与初筛**：`extract_model` 与 `extract_prompt_sha256`（前 12 位 sha256 散列）。
2. **原子化命题**：`atomize_model` 与 `atomize_prompt_sha256`。
3. **审读回执与终审清单**：记录 `reviewer_model`、`source_sha256`（锁定工单当时字节）以及引文的 `evidence_sha256`。
4. **甄选层条目**：条目 ID 为 `vod_expansion:{batch}:{stem}:{local_id}`，审核状态为 `agent_verified`，置信上限诚实标注为 `text-source-supported`，绝不谎称原片音画核听或游戏实测。

### 7.4 质量守恒与防退化准则
- **只追加、不改写**：`kb_curation_vod_loader.py` 严格遵循 append-only，若无已批准（`approved` / `approved_merged`）的 VOD manifest，构建产物 `curated_high_quality.json` 保持 100% 字节一致。
- **发布闸门检测**：合并后必须顺序通过 `kb_curation_validate.py` 与 `kb_curated_search.py --self-test`。

