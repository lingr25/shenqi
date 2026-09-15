# AGENTS.md - 神祇读神奇 机制讲堂录播归档库规范

本文件是本代码仓库（`shenqi`）的最高行动指南与规约。所有参与本项目的 AI Agent 以及开发者，在读取、处理、清洗、生成或维护本仓库中的任何文本、脚本与字幕文件时，必须严格遵守以下准则。

---

## 1. 项目定位与背景

- **归档对象**：B 站录播员 `Lapis___`（UID: `592610`）录制的明日方舟硬核机制主播 `神祇读神奇`（UID: `374873950`，直播间 `31229274`）的全部录播视频。
- **一手讨论语料补充**：主播官方核心机制讨论群 `桃大将军粉丝群`（群号：`1097395794`）的 22.7 万条历史交流记录，作为视频录播的即时探讨、答疑互动、实机测试与机制考据补充知识库。
- **项目目标**：低商业成本、高精准度、成体系地归档全部录播的官方 AI 字幕与群聊一手讨论，进行方舟底层机制专有名词消歧与清洗，生成带精确时间戳的逐字稿，并沉淀为权威的方舟机制知识库。

---

## 2. 目录结构规范

```text
shenqi/
├── .gitignore              # 忽略音视频大文件、本地缓存与实验性ASR草稿
├── AGENTS.md               # [本文件] 项目规范与 Agent 行动指南
├── entity_corrector.py      # 机制专有名词与高频同音消歧纠错模块
├── all_search_videos.json  # 空间搜索全量录播视频元数据（当前61部）
├── all_videos_census.md    # 全量视频时长清单与分类报告
├── subtitle_inventory.json # 视频分P与字幕抓取状态清单
├── subtitles_report.md     # [权威层] 官方 AI 字幕覆盖率与缺失音频归档报告（严禁混入本地ASR数据）
├── subtitles/              # [权威层] B 站官方 AI 字幕原始 JSON，保留毫秒级时间戳，严禁破坏
├── cleaned_subtitles/      # [权威层] 经过专有名词与实体消歧校准后的结构化 JSON
├── transcripts_txt/        # [权威层] 带 [时:分:秒] 时间戳、自然断句合并的逐字稿纯文本（严禁混入本地ASR草稿）
├── qq_info/                # [补充语料/本地私有] 桃大将军粉丝群(1097395794)全量聊天记录(22.7万条)，用于机制考据与黑话挖掘
├── qq_cards/               # [补充语料/公开层] LLM 提炼的机制知识卡片，draft 状态，冲突以录播为准
├── audios/                 # [本地私有/独立层] 缺失官方字幕分P的原画质纯音频(.m4a)，被.gitignore严格忽略
├── vad_results/            # [实验性/独立层] FSMN-VAD 人声端点检测时间戳与 vad_report.md 人声活跃度大盘
├── asr_drafts/             # [实验性/独立层] SenseVoiceSmall 本地粗识别转写草稿，完全独立于 transcripts_txt/
├── cloud_clips/            # [实验性/独立层] 云端ASR切片产物：manifest.json 裁剪清单 + 按VAD/草稿过滤后的音频切片（文件名含原音频绝对时间轴），被.gitignore忽略
├── plan_cloud_clips.py     # [实验性/独立层] 云端切片清单生成器：VAD段×草稿文本打分过滤→合并→pad→硬切
├── cut_cloud_clips.py      # [实验性/独立层] 按 manifest 用 ffmpeg 流拷贝切片
├── knowledge_pilot/        # [实验性/独立层] 机制知识卡抽取试点：章节大纲、draft父卡、原子命题(*.atoms.jsonl)、噪声卡(*.noise.jsonl)，被.gitignore忽略，人工审核前不得升入权威层或公开发布
├── chapter_extract_claims.py # [实验性/独立层] 方案2章节优先知识卡抽取管线
├── atomize_claims.py       # [实验性/独立层] 父卡→原子命题拆分、证据重绑、类型分权（不合成「正确卡」）
├── pilot_extract_claims.py # [实验性/独立层] 方案1固定窗口知识卡抽取试点脚本（对照组）
├── audit_timeline.py       # [实验性/独立层] VAD采样时间轴 vs 原媒体时间轴审计，产出 cloud_clips/timeline_audit.json
└── local_asr_report.md     # [实验性/独立层] 本地实验性 ASR 进展、活跃度与草稿索引报告
```

---

## 3. 双轨语料分层规范（官方AI字幕 vs 本地实验性ASR）

为确保知识库的严谨性与权威性，本仓库严格实施**“权威官方 AI 字幕”**与**“本地实验性 ASR 草稿”**的双轨物理隔离机制：

1. **权威官方 AI 字幕层（生产层）**：
   - 包括 `subtitles/`、`cleaned_subtitles/`、`transcripts_txt/`、`subtitle_inventory.json` 和 `subtitles_report.md`。
   - **绝对红线**：严禁将任何本地模型（SenseVoice、Whisper等）推断的非官方文本、字数统计或状态标签混合写入上述四个目录或官方报告中。
2. **本地实验性 ASR 层（草稿层）**：
   - 包括 `audios/`、`vad_results/`、`asr_drafts/`、`cloud_clips/` 和 `local_asr_report.md`。
   - 专门用于在官方字幕缺失时，利用极轻量 VAD 与 SenseVoice 进行语音端点定位、粗识别与检索辅助。其生成的文件统一存放在 `asr_drafts/`，并已被 `.gitignore` 保护，不参与生产层逐字稿发布。云端 ASR 重转写前的音频切片统一存放在 `cloud_clips/`（由 `plan_cloud_clips.py` 生成清单、`cut_cloud_clips.py` 执行切片），同样被 `.gitignore` 保护；云端重转写结果在人工验证前也必须留在草稿层，严禁直接写入权威层。

---

## 4. 专有名词与实体消歧

明日方舟底层代码逻辑黑话较多，通用 ASR 模型错词率极高，应当注意。


---

## 5. 文本清洗与断句规范

1. **时间戳精度**：TXT 逐字稿行首必须保留 `[HH:MM:SS]` 或 `[MM:SS]` 格式时间戳，便于用户直接拉回 B 站进度条核对原视频。
2. **自然断句合并**：原始字幕以 1~2 秒切片，必须在停顿小于 1.0 秒且长度适中时自然合并，剔除纯无意义结巴，保留原汁原味的推导过程。
3. **噪音段标记**：若前 10~30 分钟为纯热身闲聊、调设备或肉鸽打怪，在生成结构化笔记时应做清晰切分，避免污染理论正文。

---

## 6. 群聊补充语料库规范（`qq_info/`）

群聊记录 `qq_info/` 汇集了粉丝群内 22.7 万条关于方舟底层机制的深度实操讨论，是录播归档的重要知识补充。Agent 在检索与使用该语料时必须遵循以下规范：

1. **定位与佐证价值**：
   - 作为录播视频的背景与衍生材料，用于印证视频推导、解释模糊专有名词、补充实机测试数据与拆包细节。
   - 权威真值判定：当群聊交流与主播录播视频推导结论不一致时，以主播录播讲解与推导为最高优先级（权威真值），群聊作为讨论线索。
2. **消歧与黑话词库建设**：
   - 充分挖掘群聊中的高频同音错字与底层机制黑话（如帧数判定、索敌分支、力道位移结算等），持续沉淀并扩充 `entity_corrector.py` 的消歧规则。
3. **隐私脱敏与安全纪律**：
   - **严防隐私入库**：`qq_info/` 含有群友真实 QQ 号与交流记录，体积大且涉及隐私，已被 `.gitignore` 严格忽略，**严禁提交至公开 Git 远端仓库**。
   - **对外引用强制脱敏**：Agent 在基于群聊语料提炼公开机制笔记、知识库词条或答疑报告时，必须隐去非主播本人的 QQ 号与敏感个人信息，杜绝隐私泄漏。
   - **降噪过滤**：检索与引用时严格过滤纯表情刷屏、日常闲聊与无关打闹，聚焦机制逻辑、参数计算与实测验证。

---

## 7. Git 工作流与版本管理准则

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
