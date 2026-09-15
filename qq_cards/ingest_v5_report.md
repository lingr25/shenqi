# v5 子代理入库报告

日期：2026-09-16

## 校验

- 「其他」draft：146；reclass 行 96 唯一 96 重复 0
- 未覆盖：50；多余：0；非法类别：无
- group_only∩authoritative：257；novelty 行 177 唯一 177 重复 0
- novelty 未覆盖：80；多余：0；非法枚举：无
- jsonl 内 conflict：['w000554']；evidence 空：无
- 产物缺口：reclass 缺 50，novelty 缺 80（含任务点名的 w000416，已按评审结论手动入库）

## reclass 分布（已入库）

- 干员机制：44
- 关卡与出怪：15
- 数值与读图：10
- 位移：8
- 拆包数据：5
- 索敌：5
- 伤害结算：4
- 帧时序：4
- 寻路：1

- 实际写入 cards.jsonl：96；仍为「其他」的 draft：50

## novelty

- also_in_vod 升级：6
- conflict 写入：2（jsonl 有 w000554；w000416 手动 vod_wins）
- 仍 group_only：170

## glossary

- 阻挡：mechanic_def 补完，needs_more_evidence=false，confidence=medium
- 过伤：保持 unknown，补 short_def/evidence，confidence=low
- 入控：保持 unknown，补 short_def/evidence，confidence=low
- 免控：保持 unknown，补 short_def/evidence，confidence=low
- 力道：无子代理产物，维持原样
- visitNodeCenter：无子代理产物，维持原样
- TypeTree：无子代理产物，维持原样

## rag_docs

- 条数：869；glossary 挂载 44/50
- 隐私 hits：0

