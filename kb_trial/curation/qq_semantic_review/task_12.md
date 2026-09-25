# QQ 扩展条目语义复审 — 审核子代理任务模板

你是审核子代理。任务：对明日方舟机制知识库中一批 **QQ 群聊来源**条目做**对抗性语义复审**。这批条目此前只做过格式/证据校验，从未做过语义级审核，是知识库当前最大的质量缺口。

## 输入

读取批次文件：`kb_trial/curation/qq_semantic_review/batch_12.jsonl`（12 见本任务末尾），每行一条 JSON：

- `id` / `category`：条目 ID 与议题分类
- `claim` / `subject` / `condition`：策展阶段合成的知识卡文本（规则表述、适用对象、触发条件）
- `quotes`：QQ 群聊原文引文，**已脱敏**：`@某人`=被@的群友、`speaker_id` 是匿名哈希、这些是正常脱敏标记，不是问题

## 参照（按需查，不要全文加载进上下文）

- `glossary.json`：干员/敌人/黑话/ASR 讹写 → 正词对照表。判断"未知词"之前**先查这里**
- `entity_corrector.py`：本语料的消歧规则（可了解哪些词是已知错词）
- 注意：你的内置知识库可能偏旧，遇到不认识的新干员/新机制名词，**先查 glossary.json；查不到也不许凭印象判错**，在 issues 里标 `unknown_term:<词>` 交给人工

## 判定标准

每行输入输出一条判定，`verdict` 三选一：

- `keep`：claim 准确、引文支撑、归类恰当
- `demote`：内容真实但价值定级过高——典型如把主播/群友主观观点写成机制规则、把开放假设写成定论、把单次单关卡观察写成通用规则 → `info_value` 填降级后的类别
- `reject`：不成立——引文不支持 claim、错词/误解导致语义不成立、纯闲聊/玩梗/无信息量

`info_value` 三选一：

- `mechanism`：可复用的机制规则/数值/判定逻辑
- `question`：有研究价值的开放问题/假设/未闭合的实测现象
- `trivia`：即时性内容、单关卡限定、主观评价、无通用价值

## 输出

写到 `kb_trial/curation/qq_semantic_review/out/out_12.jsonl`（`out/` 不存在就自己创建）。UTF-8 JSONL，每条输入**恰好一行**，保持输入顺序：

```json
{"id":"...","verdict":"keep|demote|reject","info_value":"mechanism|question|trivia","issues":["..."],"reason":"一句话","fix":null}
```

- `reject`/`demote` 必须填 `reason`；有更准确的表述时 `fix` 填建议改写文本，否则 `null`
- `issues` 自描述标签数组，没有就 `[]`；常用：`unknown_term:<词>`、`asr_suspect:<原词>-><应为>`、`claim_not_supported`、`opinion_as_fact`、`missing_subject`、`scope_too_broad`、`single_map_only`
- **不要修改仓库中任何其他文件**，不要往输出文件里写解释性文字

## 完成后回复（给人看的，不写进文件）

只报统计：keep/demote/reject 各几条 + 最多 3 条最典型的 reject/demote 例子（id + 一句话理由）。

## 本批次

- 输入：`kb_trial/curation/qq_semantic_review/batch_12.jsonl`
- 输出：`kb_trial/curation/qq_semantic_review/out/out_12.jsonl`
