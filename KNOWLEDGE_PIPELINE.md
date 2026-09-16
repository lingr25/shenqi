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
2. `python chapter_extract_claims.py --stem {stem} --source official`
3. `python atomize_claims.py --stem {stem}`
4. 全部新分 P 跑完后：`python cluster_atoms.py` → `python merge_clusters.py` → `python enrich_atoms.py` → `python rag_eval.py`
5. 人工审查 `clusters_merged_report.md` 的 conflict/open 区，再考虑升 canonical。

**B. 只有音频、无官方字幕的分 P**：
1. `plan_cloud_clips.py` / `cut_cloud_clips.py` 切片 → `transcribe_cloud.py` 走百炼
   `qwen3-asr-flash`（密钥在脚本内，注意勿外泄）→ `audit_timeline.py` 校验时间轴。
2. `timeline_ok` 后同 A 的 2-4 步，`--source cloud`。
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
