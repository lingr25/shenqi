# 横向合并总报告：直播轨 + QQ群轨 → 统一知识库 kb/

日期：2026-09-19

## 规模

| 层 | 数量 |
|---|---:|
| vod_atom（直播原子命题，63 场） | 14,361 |
| vod_cluster（议题簇 agreed/conflict/open） | 2,989（1,368 / 98 / 1,523） |
| qq_window（群聊窗卡） | 773 |
| qq_canonical（群聊词条） | 52 |
| glossary（黑话术语） | 50 |
| qq_atom（QQ 窗卡原子化，773 窗拆分） | 6,087 |
| **docs.jsonl 合计** | **24,312** |

## 实体层（阶段B）

- 统一实体索引 6,655 mention：PRTS typed 主表 + QQ 1487 别名合并反查。
- 同名多义 351 个（如「酒神」mechanic vs 干员俗称），保留全部候选不强制消歧。
- 文本回扫为 2,683 条无链接文档补挂实体。
- 1,324 个 QQ 俗称候选（`entity_suggestions.json`）待人工确认后入 `entity_corrector.py`。

## 跨轨对齐（阶段C/C+）

- 确定性弱对齐：18,857 候选对（实体 Jaccard + 分桶映射 + glossary 命中 + bigram）。
- LLM 仲裁（deepseek-v4.1-flash，2,885 对）：same_issue 353 对，其中 agree 292 / conflict 26 / independent 35。
- **26 对跨轨冲突全部 conflict_resolution=vod_wins**（`cross_conflicts.jsonl`），典型例：寻路与传送独立性、睡眠与阻挡关系、1级嘲讽等效仇恨值。
- 双向 `counterpart_ids`：174 个直播议题 ↔ 105 个 QQ 文档。

## 检索评测（阶段D）

- `kb/kb_eval_report.md`：22 题（直播 10 + QQ 5 + glossary 4 + conflict vod_wins 3），**命中 22/22**；并入 qq_atom 后 top3 轨道分布 vod 34 / qq 32，双轨均衡。
- 检索入口：`python kb_search.py "问题"`（BM25 × boost × weight，纯本地，自动排除 status=noise）。

## 质量审计（2026-09-19，LLM 三档）

对全部 vod_cluster + qq_window 做 keep/demote/drop 审计（`kb_quality_audit.py`，缓存 `.quality_cache.json`）：

| 档 | vod_cluster | qq_window |
|---|---:|---:|
| keep/mechanism | 787 | 685 |
| keep/question | 1,342 | 67 |
| demote/trivia（boost×0.3） | 437 | 13 |
| drop/noise（移出检索） | 109 | 0 |

- 结论：QQ 轨 98% keep；vod 轨 80% keep 但其中真机制仅 29%，碎碎念/开放问题靠降权压制。
- 另有人工审核反馈落库 3 条 + 本地规则（纯观察无参数无条件）砍 400 簇：合计 **502 簇 / 983 原子置 noise**。
- ASR 错词产出：真金范围→帧进范围、三针→三帧 等已入 `entity_corrector.py` 并回填 docs（155 条修正）。
- 效率教训已沉淀到 `KNOWLEDGE_PIPELINE.md` §6（章节 kind 过滤、抽取闸门、单成员不建簇）。

## QQ 原子化质量抽样

- 6087 原子：conclusion 4769 / observation 449 / hypothesis 385 / question 256 / derivation 228。
- 发言人权重：authoritative 2763 / expert 2507 / lead 588 / member 229。
- 例：`w000006:qa0`「夜半的眠兽撤退时睡眠状态直接消失。」（authoritative conclusion）。
- 0 窗失败。deepseek 余额中断后切 grok 再切回 deepseek 断点续跑，prompt 约束 JSON 对象。

## 遗留问题

1. 全部内容仍为 draft；24 条 proposed_canonical 未升正式词条。
2. `game_version` 全 null，跨年机制变更无法自动分行。
3. 直播 28 场缺 chapter_claims 父卡（不影响 atom 层）。
4. 12 场 timeline_unverified 云端场次未入库。
5. 1,324 个 QQ 俗称候选待人工确认后入 entity_corrector.py。
