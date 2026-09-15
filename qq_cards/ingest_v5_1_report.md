# v5.1 批次合并入库报告

日期：2026-09-16

## 乱码 / 覆盖

- reclass 合并 146（批次覆盖 0）；乱码 无；非法类别 无
- novelty 合并 257（批次覆盖 60）；乱码 无；非法枚举 无
- conflict evidence 空：无；jsonl conflict：['w000416', 'w000554']
- 强制 41-60 覆盖窗：20（w000271–w000374）

## reclass 十类

- 干员机制：64
- 关卡与出怪：22
- 数值与读图：21
- 位移：9
- 索敌：8
- 伤害结算：6
- 拆包数据：6
- 帧时序：5
- 其他：4
- 寻路：1

- 写入 cards：146；仍为「其他」draft：4

## novelty 复核（257 行）

- 行内分布：{'group_only': 239, 'also_in_vod': 16, 'conflict': 2}
- 写入 also_in_vod：16；conflict：2；仍 group_only：239
- 全库 novelty：{'group_only': 379, 'unknown': 335, 'also_in_vod': 72, 'conflict': 3}（复核前约 group_only 397 / also_in_vod 56 / conflict 1）

## conflict 卡

- w000416 novelty=conflict resolution=vod_wins takeaway_ok=True note=True
- w000554 novelty=conflict resolution=vod_wins takeaway_ok=True note=True

- rag_docs：869；glossary 挂载 44/50；隐私 0

