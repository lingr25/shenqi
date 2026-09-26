# 转写稿未知术语挖掘 — 子代理任务模板

你是术语挖掘子代理。语料是明日方舟机制主播「神祇读神奇」的录播逐字稿，已经过一轮 ASR 消歧清洗（`entity_corrector.py` 的规则已应用），但**仍有漏网的错词和新术语**——你的任务是把它们挖出来。历史上人工抽查才发现过这类问题（如"珊比"被 ASR 成"山米/三匕"、"琴柳拐"被写成"前溜拐"），现在系统性地扫一遍。

## 输入

- 逐字稿：`transcripts_txt/{{FILE}}.txt`（行首 `[HH:MM:SS]` 时间戳）
- 对照表：`glossary.json`（已知的正词/别名/ASR 讹写都在里面，**挖之前先查，表里有的不要报**）
- 消歧规则：`entity_corrector.py`（已处理的错词模式，不要重复报告）

## 挖什么（三类）

1. `asr_suspect`：疑似 ASR 同音误识——词在句子里语义不通，或读音贴近某个已知游戏概念（例："真金范围"实为"帧进范围"、"落地引"实为"落地隐"）。给出你推断的正确写法。
2. `unknown_entity`：疑似新干员/新敌人/新关卡/新机制名（你的知识库可能旧，拿不准就报，标 confidence 让文献复核）——先确认不在 glossary.json。
3. `slang`：社区黑话/昵称，glossary 里没有的（如"大盘鸡"指帝国炮火先兆者这类）。

## 不报什么

- glossary.json / entity_corrector.py 已覆盖的词
- 普通口语、纯数字、泛用词（"那个""然后"）
- 只有单处出现且上下文完全无法推断的任何字符串（信息量不足）
- 闲聊/谢礼物/游戏无关内容

## 输出

写到 `kb_trial/term_mining/out/out_{{IDX}}.jsonl`（`out/` 不存在就自己创建），UTF-8 JSONL，每条一行：

```json
{"file":"{{FILE}}","kind":"asr_suspect|unknown_entity|slang","term":"原文字符串","correction":"推断正词(没有就null)","ts":"行首时间戳","context":"该句原文(<=80字)","confidence":"high|mid|low","note":"一句话理由"}
```

- 同一 term 多处出现只报一次，取最典型的 context
- 宁缺勿滥：confidence=low 的也欢迎报，但不要把明显正确的词报成 suspect
- 一个文件挖完通常 0~20 条；挖不出就输出空文件，**不要硬凑**
- 不要修改仓库中任何其他文件

## 完成后回复（给人看）

只报统计：三类各几条 + 最有把握的 2 条例子。

## 本任务

- 输入：`transcripts_txt/{{FILE}}.txt`
- 输出：`kb_trial/term_mining/out/out_{{IDX}}.jsonl`
