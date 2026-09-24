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
├── kb/                     # [统一层/draft] 直播轨+QQ轨横向合并的统一知识库: docs.jsonl(统一文档层,gitignore)、entity_index.json(统一实体索引)、cross_links/cross_conflicts(跨轨对齐)、检索评测报告；历史层冲突策略为 vod_wins，仅供参考，甄选子层已改为不做自动裁决；可直接作 RAG 语料
├── kb_trial/               # [本地试验/draft] 当前唯一试验入口产物，docs/archive/evidence/overlay/manifest；总览 OVERVIEW.md，历史 kb_pilot_synth/ 保留作只读来源，禁止当权威或直接发布
├── kb_build_trial.py       # [本地试验] 幂等构建，不调用 API、不覆盖 kb/；按精确来源应用用户审核，保留原始引文；内含 trial_user_aliases 人工别名表（用户裁定的 ASR 讹写→正确词，按 scope 限定条目生效，如 血屋→血霭遮月、鼠传送→黍传送）
├── kb_trial_search.py      # [本地试验] 稳定 CLI，默认 mechanism；experiment/pending/all/archive 须显式选择，--self-test 验证
├── kb_trial_verify.py      # [本地试验] 本地重建、引用/边界与新旧检索对照；结果 kb_trial/validation.json
├── kb_trial/curated_high_quality.json # [甄选子层/draft] 单个 JSON 对象的甄选高质量规则层(schema curated-1.0)，当前1473条(官方字幕576/云ASR28/混合17/QQ852=既有QQ8+阶段二试批30+阶段三b3批312+阶段四b4批502；b3批含材料修复后重审追加的2条，另有4条已发布条目的引文占位经父裁定批准按源复原、见 curation/qq_expansion/audit_decisions_b3.json 的 quote_fidelity_repair，已发布层占位残留0；2026-09-22 对抗性挑刺落地：撤58条(改前1520)、按二审建议改写305条claim/subject/condition，引文未动，见 curation/faultcheck/REMEDIATION_REPORT.md；2026-09-23 校准复核落地：175条 needs_human_confirmation 分9批校准(补引~74/回退~77/恢复6条QQ误撤+5条录播误拒/维持撤下8/用户裁定4条)，净+11条，见 curation/faultcheck/calibration_decisions_01..09.json)，可直接作RAG语料；非权威、未部署未发布；审核状态 user_verified/agent_verified(本版无 auto_screened，未过审者隔离不入集)；仅用户明确"优秀"的整卡可继承 user_verified，"修改后可用"须降为 agent_verified；证据形态含 VOD原子/VOD内联/QQ span 三轨
├── kb_trial/curation/      # [甄选子层/draft] 甄选过程证据: candidates/decisions/agent_verifications/qq_worklist/evidence_verdicts(620)/curated_staging(隔离5条)/qq_claim_overlay/curated_validation/qq_expansion(阶段二试批: approved_manifest 30条已并入 + audit_decisions 147条裁定 + trial_candidate + REVIEW_REPORT_80/user_sample_round2；阶段三b3批: approved_manifest_b3 319条已并入 + audit_decisions_b3 386条裁定 + review_impact_manifest_b3 + README_B3/user_sample_round3；阶段四b4批: approved_manifest_b4 502条已并入 + audit_decisions_b4 572条裁定(keep502/reject40/pending30) + README_B4/user_sample_round4)，全程本地 0 外部 API
├── kb_curation_qq_expansion*.py # [甄选子层] QQ 精选扩展专用: 候选生成/loader 增量并入(支持 --batch phase2|b3|b4)/逐条裁定生成/b3 读源影响清单，仅经 kb_curation_build.py 追加进 curated_high_quality.json
├── kb_curation_qq_expansion_loader.py # [甄选子层] 唯一可把 approved_manifest(_b3/_b4).json 变成 curated 条目的加载器；BATCHES 登记批次的工单/回执/裁定/清单路径，只追加绝不改写既有条目，逐条复验 source_sha256/裁定 verdict=keep/引文逐字
├── kb_curation_qq_expansion_diff_b3.py # [甄选子层] b3 批(260窗)读源影响清单: 工单消息层修复对 b3 工单的影响，并逐 seq 复核交付文本 == 重算文本
├── kb_trial/CURATED_OVERVIEW.md # [甄选子层/draft] 交付说明: 实测数量与来源分布、证据形态、审核上限(text-source-supported，非核听非实测)、已隔离条目、使用方法与已知局限
├── kb_curation_*.py        # [甄选子层] 预筛/证据查证/闸门判定/代理逐条读源/构建/校验，只写 kb_trial/curation 与 curated_high_quality.json，不改 kb_trial 四件套与 kb/
├── kb_curated_search.py    # [甄选子层] 仅检索 curated_high_quality.json 的独立 CLI，不回退到更宽层；--self-test 验证
├── kb_build_docs.py        # [统一层] 阶段A: 两轨 pack 成统一 schema 文档 (纯本地)
├── kb_build_entities.py    # [统一层] 阶段B: PRTS+QQ别名统一实体索引与回填 (纯本地)
├── kb_link_tracks.py       # [统一层] 阶段C: 跨轨确定性弱对齐 (纯本地)
├── kb_llm_align.py         # [统一层] 阶段C+: LLM 跨轨仲裁 same_issue/agree/conflict, vod_wins (带断点缓存)
├── kb_atomize_qq.py        # [统一层] 阶段D+: QQ 窗卡原子化 (带断点缓存)
├── kb_pack_qq_atoms.py     # [统一层] 阶段D+: qq_atom 并入 docs.jsonl
├── kb_eval.py              # [统一层] 阶段D: 统一检索评测 22 题 (纯本地 BM25)
├── kb_search.py            # [统一层] RAG 检索入口: BM25 × boost × weight, 冲突 vod_wins
├── audios/                 # [本地私有/独立层] 缺失官方字幕分P的原画质纯音频(.m4a)，被.gitignore严格忽略
├── vad_results/            # [实验性/独立层] FSMN-VAD 人声端点检测时间戳与 vad_report.md 人声活跃度大盘
├── asr_drafts/             # [实验性/独立层] SenseVoiceSmall 本地粗识别转写草稿，完全独立于 transcripts_txt/
├── cloud_clips/            # [实验性/独立层] 云端ASR切片产物：manifest.json 裁剪清单 + 按VAD/草稿过滤后的音频切片（文件名含原音频绝对时间轴），被.gitignore忽略
├── plan_cloud_clips.py     # [实验性/独立层] 云端切片清单生成器：VAD段×草稿文本打分过滤→合并→pad→硬切
├── cut_cloud_clips.py      # [实验性/独立层] 按 manifest 用 ffmpeg 流拷贝切片
├── knowledge_pilot/        # [实验性/独立层] 机制知识卡抽取试点：章节大纲、draft父卡、原子命题(*.atoms.jsonl)、噪声卡(*.noise.jsonl)，被.gitignore忽略，人工审核前不得升入权威层或公开发布
├── chapter_extract_claims.py # [实验性/独立层] 方案2章节优先知识卡抽取管线
├── atomize_claims.py       # [实验性/独立层] 父卡→原子命题拆分、证据重绑、类型分权（不合成「正确卡」）
├── cluster_atoms.py        # [实验性/独立层] 原子卡→议题档案(agreed/conflict/open), LLM不裁对错
├── merge_clusters.py       # [实验性/独立层] 跨批次议题归并(union-find确定合并+canonical门槛重跑)
├── enrich_atoms.py         # [实验性/独立层] 原子卡增强: claim_id/录制日期/PRTS实体挂接(纯本地)
├── rag_eval.py             # [实验性/独立层] RAG检索评测(纯本地BM25), 当前基线10/10
├── KNOWLEDGE_PIPELINE.md   # [实验性/独立层] 知识库生产管线文档, 新视频入库按此操作
├── pilot_extract_claims.py # [实验性/独立层] 方案1固定窗口知识卡抽取试点脚本（对照组）
├── audit_timeline.py       # [实验性/独立层] VAD采样时间轴 vs 原媒体时间轴审计，产出 cloud_clips/timeline_audit.json
├── xp_rank.py              # [娱乐向/本地私有] 群友 XP 榜单挖掘：干员提及/示爱/官宣单推统计，产物 xp_report.md/xp_data.json 只写入 qq_info/（gitignore 保护，仅昵称不含 QQ 号）
├── xp_page.py              # [娱乐向/本地私有] 把 xp_data.json 渲染成自包含 HTML 看板 xp_report.html（无外部依赖，仅昵称）
├── LICENSE                 # 代码许可：MIT
├── LICENSE-CONTENT         # 内容许可（知识库/逐字稿/词表/报告）：CC BY-NC-SA 4.0
├── README.md               # 开源说明：产物、双协议分区、隐私边界、管线速览
├── local_ids.py            # 本地身份注入：从 qq_info/identities.json（gitignore）读真实QQ号，脚本不得硬编码号码
├── scripts/privacy_gate.py # [发布闸门] 全库隐私扫描：密钥/手机号/真实QQ+UID/花名，发布前必须通过；白名单 scripts/privacy_allowlist.txt 仅收人工核实的非身份误报
├── glossary.json           # [黑话清单/RAG直用] 正词→别名+英文+ASR讹写变体消歧清单，由 build_glossary.py 从实体索引+glossary+消歧规则确定性合成，禁止手改产物
├── build_glossary.py       # 黑话清单重跑入口(纯本地,无API)
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
   - **冲突不做自动裁决**：群聊交流与主播录播推导不一致时，两方并列保留、呈现分歧，由人工判断。历史统一层（`kb/`）曾采用 vod_wins，那只是旧层策略，不是本仓库通则；甄选层明确 *no automatic precedence*。
2. **消歧与黑话词库建设**：
   - 充分挖掘群聊中的高频同音错字与底层机制黑话（如帧数判定、索敌分支、力道位移结算等），持续沉淀并扩充 `entity_corrector.py` 的消歧规则。
3. **隐私脱敏与安全纪律**：
   - **严防隐私入库**：`qq_info/` 含有群友真实 QQ 号与交流记录，体积大且涉及隐私，已被 `.gitignore` 严格忽略，**严禁提交至公开 Git 远端仓库**。
   - **对外引用强制脱敏**：Agent 在基于群聊语料提炼公开机制笔记、知识库词条或答疑报告时，必须隐去非主播本人的 QQ 号与敏感个人信息，杜绝隐私泄漏。
   - **降噪过滤**：检索与引用时严格过滤纯表情刷屏、日常闲聊与无关打闹，聚焦机制逻辑、参数计算与实测验证。

---

## 6.1 甄选层（`kb_trial/curated_high_quality.json`）使用纪律

甄选层是当前可直接接 RAG 的规则层，使用时必须遵守以下口径，**不得复述为权威或已验证**：

1. **置信上限是 `text-source-supported`**：全部判定基于**转写文本**（官方 AI 字幕或云端 ASR）与 QQ 窗口片段逐条比对，**未核听原片音画、未做游戏内实测**。
2. **官方字幕出现某字，不等于主播确实这么说**：字幕本身有 ASR 讹写（例：「寻路」→「驯鹿」、「伤判」→「商判」）。引文一律保留原始逐字文本不动；只在同源上下文可自证时订正派生 `claim`/`subject`/`condition`，并记录于 `derived_text_repairs`。
3. **审核状态如实区分**：`user_verified` 仅限用户明确说「优秀」的整卡；「修改后可用」须降为 `agent_verified`。本版 `auto_screened` 为 0，未过审条目**隔离**在 `curation/curated_staging.json`，不静默丢弃也不入库。
4. **`inherited_verified` 不等于核听**：它表示本条本轮未被重读，判定继承自上一轮的用户反馈与代理文本审核。
5. **`--layer qq` 等过滤是硬过滤**，不回退到更宽的 `kb_trial` 层；QQ 引文已脱敏，不含群号、QQ 号与昵称。发布前必须跑 `scripts/privacy_gate.py`（密钥/手机号/真实 QQ+UID/花名残留全库扫描，0 命中才允许推送公开远端）；`kb_curation_qq_expansion_loader.py` 内的 `PUBLISH_REDACTIONS` 表保存发布期身份词映射，新增泄漏词只加映射并重跑 loader 链路，不直接手改产物。
6. **数字与 sha256 以实测为准**：改动甄选链路后必须重跑 `kb_curation_evidence_close.py` → `kb_curation_build.py` → `kb_curation_validate.py` → `kb_curated_search.py --self-test`，并同步更新 `CURATED_OVERVIEW.md` 与本节条数。**禁止**用旧版数字或旧层回归成绩背书本层。

**已知短板**：QQ 轨目前 852 条入选（既有 8 条 + 阶段二试批 30 条 + 阶段三 b3 批 312 条 + 阶段四 b4 批 502 条，四批均已 `approved_merged` 并入；b3 的 312 含材料修复后重审追加的 2 条、并已扣掉 2026-09-22 对抗性挑刺撤下的 7 条；b4 的 502 = 508 keep − 6 挑刺撤下，含 2026-09-23 校准恢复的 6 条误撤），仍有大量候选待逐条读源，本层不代表完整知识库。
b3 批实测产出率约 1.23 条/窗（260 窗 → keep 319，含材料修复后重审追加的 2 条），被裁定为非 keep 的 67 条（reject 59 + pending 8）全部留在
`curation/qq_expansion/audit_decisions_b3.json` 的 `decisions` 里，连同理由码可逐条复核，不删除。
b4 批实测产出率约 1.14 条/窗（441 窗 → keep 502 = 508 − 12 挑刺撤下 + 6 校准恢复），非 keep 的 70 条（reject 40 + pending 30）同样留在
`curation/qq_expansion/audit_decisions_b4.json` 的 `decisions` 里，逐条带理由码与父裁决记录（`parent_ruling`），不删除。
隐私闸门（`kb_curation_validate.py` 的 6–12 位数字检查）对「同一串数字在条目自身引文内逐字存在」的条目按来源数值豁免，
只在报告 `qq_number_quote_sourced` 里记 entry id、不回显数字；无引文支撑的数字串仍判失败。

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
