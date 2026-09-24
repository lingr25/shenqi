# shenqi — 神祇读神奇 机制讲堂归档与明日方舟进阶知识库

对 B 站硬核机制主播 **神祇读神奇**（UID `374873950`，直播间 `31229274`，录播员
Lapis\_\_\_，UID `592610`）的全部机制讲堂录播做系统归档：抓取官方 AI 字幕 →
专有名词消歧清洗 → 带精确时间戳的逐字稿 → LLM 提炼 + 人工/对抗审核 →
可直接接 RAG 的甄选机制知识库。

**非官方粉丝归档项目**，与鹰角网络、哔哩哔哩及主播本人无关。

## 核心产物

| 文件/目录 | 说明 |
|---|---|
| `curated_high_quality.json` | **甄选知识库（~1390 条）**，每条含 `claim`/`subject`/`condition`/`category`/引文证据/B站时间戳链接/审核结论，可直接灌入向量库做 RAG |
| `transcripts_txt/` | 带 `[HH:MM:SS]` 时间戳的逐字稿（官方 AI 字幕消歧清洗版） |
| `cleaned_subtitles/` | 消歧后的结构化字幕 JSON（保留毫秒时间戳） |
| `glossary.json` | **黑话/实体消歧清单（~1887 条）**：正词 → 社区别名 + 英文别名 + ASR 讹写变体，50 条核心机制词带定义；由 `build_glossary.py` 从实体索引+词表+消歧规则确定性合成，RAG 同义词扩展直用 |
| `entity_corrector.py` | 方舟机制黑话 × ASR 同音错字消歧规则库（帧/索敌/格判/干员别名…），本项目最稀缺资产 |
| `qq_cards/` | 群聊提炼的知识卡片（draft 层，冲突以录播为准） |
| `kb_trial/` | 知识库构建的中间层：甄选清单、审核决策、总览报告 |
| `AGENTS.md` / `KNOWLEDGE_PIPELINE.md` | 仓库规约与知识管线操作手册（可复现整套流程） |

### `curated_high_quality.json` 条目结构（摘要）

```jsonc
{
  "id": "vod_entry:索敌-22-7",        // 稳定ID（vod_*=录播, qq_*=群聊）
  "claim": "……规则文本……",
  "subject": "城防炮",                 // 适用对象
  "condition": "零帧部署、一帧撤退",     // 触发条件
  "category": "索敌",
  "citations": [{ "transcript_file": "…", "quotes": [/* 原文引文 */] }],
  "review": { "status": "…", "confidence": "…" },
  "semantic_review": { "verdict": "keep|…", "info_value": "mechanism|question|trivia" }
}
```

录播条目带 `https://bilibili.com/video/<BV>?t=<秒>` 精确定位链接，可秒回源视频核对。

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

检索试用：`python kb_curated_search.py "<关键词>"`（自带 self-test）。

## 致谢与声明

- 主播 **神祇读神奇** 的机制讲解是全部内容的源头；**录播员 Lapis\_\_\_** 的长期录制。
- 逐字稿基于 B 站官方 AI 字幕清洗，修正错字不改动语义；冲突判定以录播原话为准。
- 若内容存在错误或侵权，欢迎开 issue 指正/联系撤下。
