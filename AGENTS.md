# AGENTS.md - 神祇读神奇 机制讲堂录播归档库规范

本文件是本代码仓库（`shenqi`）的最高行动指南与规约。所有参与本项目的 AI Agent 以及开发者，在读取、处理、清洗、生成或维护本仓库中的任何文本、脚本与字幕文件时，必须严格遵守以下准则。

---

## 1. 项目定位与背景

- **归档对象**：B 站录播员 `Lapis___`（UID: `592610`）录制的明日方舟硬核机制主播 `神祇读神奇`（UID: `374873950`，直播间 `31229274`）的全部录播视频。
- **项目目标**：低商业成本、高精准度、成体系地归档全部录播的官方 AI 字幕，进行方舟底层机制专有名词消歧与清洗，生成带精确时间戳的逐字稿，并沉淀为权威的方舟机制知识库。

---

## 2. 目录结构规范

```text
shenqi/
├── .gitignore              # 忽略音视频大文件及缓存
├── AGENTS.md               # [本文件] 项目规范与 Agent 行动指南
├── entity_corrector.py      # 机制专有名词与高频同音消歧纠错模块
├── all_search_videos.json  # 空间搜索全量录播视频元数据（当前60部）
├── all_videos_census.md    # 全量视频时长清单与分类报告
├── subtitle_inventory.json # 视频分P与字幕抓取状态清单
├── subtitles_report.md     # 官方 AI 字幕覆盖率与缺失分P报告
├── subtitles/              # [原始数据] B 站官方 AI 字幕原始 JSON，保留毫秒级时间戳，严禁破坏
├── cleaned_subtitles/      # [清洗数据] 经过专有名词与实体消歧校准后的结构化 JSON
└── transcripts_txt/        # [阅读/LLM] 带 [时:分:秒] 时间戳、自然断句合并的逐字稿纯文本
```

---

## 3. 专有名词与实体消歧

明日方舟底层代码逻辑黑话较多，通用 ASR 模型错词率极高，应当注意。


---

## 4. 文本清洗与断句规范

1. **时间戳精度**：TXT 逐字稿行首必须保留 `[HH:MM:SS]` 或 `[MM:SS]` 格式时间戳，便于用户直接拉回 B 站进度条核对原视频。
2. **自然断句合并**：原始字幕以 1~2 秒切片，必须在停顿小于 1.0 秒且长度适中时自然合并，剔除纯无意义结巴，保留原汁原味的推导过程。
3. **噪音段标记**：若前 10~30 分钟为纯热身闲聊、调设备或肉鸽打怪，在生成结构化笔记时应做清晰切分，避免污染理论正文。

---

## 5. Git 工作流与版本管理准则

本仓库已建立 Git 版本控制（`master` 分支），任何修改必须遵循以下纪律：

1. **修改后必须提交**：
   - 凡是对清洗规则（`entity_corrector.py`）、逐字稿（`transcripts_txt/`）、清洗后 JSON（`cleaned_subtitles/`）或文档进行了批量增删改，必须在验证无误后立即执行 `git add` 并 `git commit`。
2. **规范提交信息（Conventional Commits）**：
   - 规则更新：`feat(corrector): add xxx entity rules`
   - 文案清洗：`chore(transcripts): re-clean xxx with new rules`
   - 爬取归档：`feat(crawl): archive subtitles for BVxxxx`
   - 文档维护：`docs: update census and inventory reports`
3. **严防巨型二进制入库**：
   - 绝对禁止将任何 `*.mp3`, `*.m4a`, `*.wav`, `*.flac`, `*.mp4`, `*.mkv` 等音视频文件提交到 Git 中。如需提取音频转写，临时音频应保存在临时目录或严格被 `.gitignore` 过滤。
4. **可回滚保证**：在执行大规模正则或破坏性修改前，必须确保 `git status` 为干净状态，以便随时使用 `git diff` 审查变更或 `git checkout` 安全回退。
