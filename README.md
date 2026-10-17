# shenqi — 神祇读神奇 机制讲堂归档与明日方舟进阶知识库

对 B 站硬核机制主播 **神祇读神奇**（UID `374873950`，直播间 `31229274`，录播员
Lapis\_\_\_，UID `592610`）的全部机制讲堂录播做系统归档：抓取官方 AI 字幕 →
专有名词消歧清洗 → 带精确时间戳的逐字稿 → LLM 提炼 + 人工/对抗审核 →
可直接接 RAG 的甄选机制知识库。

**非官方粉丝归档项目**，与鹰角网络、哔哩哔哩及主播本人无关。

## 核心产物

| 文件/目录 | 说明 |
|---|---|
| `curated_high_quality.json` | **甄选知识库（<!-- stat:card_count -->1388<!-- /stat --> 条）**，每条含 `claim`/`subject`/`condition`/`category`/引文证据（逐字稿文件 + 秒数 / 已脱敏 QQ 窗口）/审核结论，可直接灌入向量库做 RAG。根目录这份与 `kb_trial/curated_high_quality.json` 逐字节相同（CI 校验） |
| `transcripts_txt/` | 带 `[HH:MM:SS]` 时间戳的逐字稿（官方 AI 字幕消歧清洗版） |
| `cleaned_subtitles/` | 消歧后的结构化字幕 JSON（保留毫秒时间戳） |
| `glossary.json` | **黑话/实体消歧清单（<!-- stat:glossary_count -->2100<!-- /stat --> 条）**：正词 → 社区别名 + 英文别名 + ASR 讹写变体，<!-- stat:glossary_mechanic_def -->50<!-- /stat --> 条核心机制词带机制定义；由 `build_glossary.py` 从实体索引+词表+消歧规则确定性合成，RAG 同义词扩展直用 |
| `entity_corrector.py` | 方舟机制黑话 × ASR 同音错字消歧规则库（帧/索敌/格判/干员别名…），本项目最稀缺资产 |
| `qq_cards/` | 群聊提炼的知识卡片（draft 层，冲突以录播为准） |
| `kb_trial/` | 知识库构建的中间层：甄选清单、审核决策、总览报告 |
| `AGENTS.md` / `KNOWLEDGE_PIPELINE.md` | 仓库规约与知识管线操作手册（可复现整套流程） |

### `curated_high_quality.json` 条目结构（摘要）

```jsonc
{
  "id": "fc1:索敌-20-14#r0",           // 稳定ID，见下方「ID 格式」
  "claim": "……规则文本……",
  "subject": "城防炮",                 // 适用对象
  "condition": "零帧部署、一帧撤退",     // 触发条件
  "category": "索敌",
  "source_layer": "官方AI字幕",         // 官方AI字幕 / 云端ASR重转写 / 混合 / QQ群聊
  "track": "vod_official",             // vod_official / vod_cloud / mixed_or_unknown / qq / qq_chat
  "citations": [{
    "transcript_file": "transcripts_txt/<BV>_p<N>_<cid>.txt",   // 录播条目；QQ 条目改为 "window_id": "w000078"
    "quotes": [{ "text": "原文逐字引文", "t_start": 9368, "t_end": null }]  // t_start 为视频内秒数
  }],
  "review": { "status": "agent_verified|user_verified", "confidence": "text-source-supported" },
  "semantic_review": { "verdict": "keep|demote", "info_value": "mechanism|reusable_rule|question" }
}
```

**ID 格式**（实测存在的几类前缀，均为历史构建批次留下的稳定 ID）：

| 前缀示例 | 含义 |
|---|---|
| `fc1:<类别>-<章>-<序>#r<规则序>` | 录播卡（官方字幕 / 云端 ASR / 混合），来自用户审核轮修订后的卡片（`origin.upstream_record` 指向 `kb_pilot_synth/user_review_round1/`） |
| `B010-event-order-exceptions#r0` | 录播卡，来自 batch100 第二轮合成（`kb_pilot_synth/batch100_round2/`） |
| `window:w000031#r0` | 早期 QQ 窗口卡（`track=qq`） |
| `qq_expansion:w000078:c01` | QQ 精选扩展批次（`track=qq_chat`，阶段二 / b3 / b4） |

**定位原片**：录播条目给出的是 `transcript_file` + `quotes[].t_start`（视频内秒数）。文件名形如
`<BV号>_p<分P>_<cid>.txt`，可自行拼成 `https://www.bilibili.com/video/<BV号>?p=<分P>&t=<秒>` 回 B 站核对；
条目本身**不含**现成的 B 站链接。部分引文（约 70 处）指向未入库的本地 ASR 草稿（`asr_drafts/`、`cloud_clips/`），
外部无法打开；引文保留生成时的原始逐字文本，少数与之后重新清洗过的逐字稿措辞略有出入。
两者都由 `python tools/validate_release.py` 以 WARN 列出。

### 当前实测统计

<!-- stats:start -->
> 本区块由 `python tools/stats.py --write` 生成，请勿手改；CI 以 `--check` 校验。
> 区块外正文中带日期的数字是当时时点的记录，以本区块为准。

| 维度 | 实测值 |
| --- | --- |
| 甄选知识卡条数（`entries`） | **1388**（`entry_count` 字段 1388） |
| 来源层 `source_layer` | QQ群聊 797、官方AI字幕 546、云端ASR重转写(无官方字幕分P) 28、官方AI字幕+云端ASR重转写 17 |
| 来源轨 `track` | qq_chat 789、vod_official 546、vod_cloud 28、mixed_or_unknown 17、qq 8 |
| QQ 轨按批次（`origin.card_section`） | QQ扩展(阶段四b4批) 458、QQ扩展(阶段三b3批) 302、QQ扩展(阶段二试批) 29、早期QQ窗口卡(window:*) 8 |
| `review.status` | agent_verified 1371、user_verified 17 |
| `evidence_review.status` | supported 1348、inherited_verified 40 |
| `scope` | universal 590、general_mechanism 590、entity_mechanism 199、instance 8、未标注 1 |
| 类别 `category` | 204 种（其中 129 种仅 1 条）；前 10：寻路 262、索敌 173、位移 161、帧时序 124、伤害结算 108、帧时序与计时器 77、状态效果 43、干员机制 39、拆包数据 29、其他 28 |
| 含 `derived_text_repairs` 的条目 | 75 |
| 隔离（`curation/curated_staging.json`） | 6 |
| 黑话词表 `glossary.json` | 2100 条（`short_def` 76、`mechanic_def` 50） |
| 逐字稿 / 清洗字幕 / 原始字幕 | 45 / 45 / 45 个分P文件 |
| `curated_high_quality.json` sha256（LF） | `6e321a5e7922f3710c4ab14dbee24467debdb21c094fcb034a5dbc87da412908` |
| 同上（CRLF 工作区口径） | `2a95320b7bd0c8aa10bf2b421b570ba7fdf1af094e1da07c120225e471b83ec9` |
<!-- stats:end -->

## 许可（双协议）

- **代码**（全部 `*.py`）：[MIT](LICENSE)
- **内容**（知识库、逐字稿、清洗字幕、词表规则、报告）：[CC BY-NC-SA 4.0](LICENSE-CONTENT)
  — 署名 + 非商业 + 相同方式共享。内容上游是主播讲解/B站字幕/群聊讨论，
  本许可仅覆盖本项目的整理汇编成果。

## 管线速览

```
B站官方AI字幕 ──entity_corrector.py──► cleaned_subtitles/ ──► transcripts_txt/
                                        │
群聊记录(本地) ──脱敏/窗口化──► qq_cards ──┤
                                        ▼
                    章节切分→原子命题→议题簇→LLM合成→多轮审核
                    (kb_build_trial.py → kb_curation_*.py)
                                        ▼
                          curated_high_quality.json
```

检索试用与自检（新克隆即可运行，纯标准库）：

```bash
python kb_curated_search.py "索敌帧 远程抬手"   # BM25 检索甄选层
python kb_curated_search.py --self-test         # 甄选层自检
python tools/validate_release.py                # 结构 + 引文校验（只用已提交文件）
python tools/stats.py --check                   # 文档中的数字是否与产物一致
```

脚本目录：根目录为字幕清洗 / 知识库 / 甄选链路脚本；`asr/` 为本地与云端 ASR 脚本；`qq/` 为群聊管线脚本
（输入在本地私有的 `qq_info/`）；`tools/` 为发布校验工具。所有脚本都从仓库根目录运行。

## 致谢与声明

- 主播 **神祇读神奇** 的机制讲解是全部内容的源头；**录播员 Lapis\_\_\_** 的长期录制。
- 逐字稿基于 B 站官方 AI 字幕清洗，修正错字不改动语义；冲突判定以录播原话为准。
- 若内容存在错误或侵权，欢迎开 issue 指正/联系撤下。
