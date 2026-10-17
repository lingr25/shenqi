# 合成词条隔离 pilot 计划

## 红线

- 不写 `kb/docs.jsonl`、`kb/synthesized.jsonl`
- 不删除 `kb/.synth_cache.json`
- 不全量跑
- 不 git 提交
- 产物只落 `kb_pilot_synth/`，缓存 `kb_pilot_synth/.synth_cache_{v1,v2,v3}.json`
- `--no-qq` 仅 `--pilot` 默认开启；生产默认仍附 QQ 线索（禁止用 QQ 补主语）

## 样本（18）

调参 12（`ids_train.txt`）：用户点名 7 + 随机正负例 5

| ID | 角色 | 关注点 |
|---|---|---|
| 帧时序与计时器-3-10 | 用户 | 中文帧数、桃金娘局部观测 vs 光环通则 |
| 技能特例-16-7 | 用户 | QQ 窗口把主语污染成「祥子」 |
| 帧时序与计时器-20-2 | 用户 | 材料薄，「隔几帧」不可发明数值 |
| 其他-6-1 | 用户 | open；「车来了」无信息；五秒起点未决 |
| 索敌-22-7 | 用户 | 零帧部署/一帧撤退实验 → instance |
| 索敌-0-1 | 用户 | 弹道结论清楚；QQ 问题不得进 rules |
| 帧时序与计时器-46-2 | 用户 | 单条 0.1 倍，有数字≠high |
| 寻路-36-6 | 正例大簇 | 旧合成混入加速度 8、30/8-1（材料没有） |
| 帧时序与计时器-65-4 | 正例 | 「六针」ASR；旧合成 high 过满 |
| 帧时序与计时器-24-0 | 负例 | 单句「四舍五入」；旧合成编造公式 |
| 位移-3-5 | 截断压力 | 15 成员；hypothesis 不得进 rules |
| 索敌-20-10 | 混杂 | 多主语（敌人/梓兰/祥子）勿揉成一条通则 |

留出 6（`ids_heldout.txt`）：寻路-7-8、帧时序与计时器-43-1、寻路-14-14、技能特例-3-6、帧时序与计时器-14-5、状态效果-3-7

## 安全传入免费 key（不要写入仓库/命令历史文件）

环境里当前 **没有** `GROK_API_KEY`。不要把 key 写进 `.env`、脚本或 review 文件。

Git Bash 一次性注入（本进程可见，不落盘）：

```bash
export GROK_API_KEY='…'          # 由父代理/用户粘贴，勿 echo
export GROK_MODEL=deepseek-v4.1-flash
# 可选: export GROK_BASE=https://aitreez.com/v1
python kb_synthesize.py --self-test
python kb_synthesize.py --pilot --prompt-version v1 \
  --ids-file kb_pilot_synth/ids_train.txt --workers 2
```

PowerShell：`$env:GROK_API_KEY='…'; $env:GROK_MODEL='deepseek-v4.1-flash'`

## 轮次

1. v1 调参集 → 人工对照 `source_dump.md` 原话
2. 按真实失败改 prompt 为 v2，重跑必要样本
3. 冻结 v2，跑留出集
4. v3：5 条 + `--sub-ctx`；冻结后新留出 `ids_heldout_v3.txt`
5. **最终交付不是自动 JSON**，而是人工闸门 `accepted.jsonl` / `rejected.jsonl` / `review_final.md`。自动合成不可直接扩量。
