# 本地实验性 ASR 语音转写报告（完全独立语料层）

> **架构独立说明**：本模块为独立的实验性本地 ASR 转写流水线，基于 `FSMN-VAD` 端点检测与阿里 `SenseVoiceSmall` 语音大模型。所有输出均存储于独立的 `asr_drafts/` 目录中，与 B 站官方 AI 字幕库（`subtitles/`、`cleaned_subtitles/`、`transcripts_txt/`）严格物理隔离，杜绝混淆。

- **分析音频总数**：39 个缺失官方字幕分P（总计 **61.62 小时**）
- **VAD 有效人声总时长**：**25.97 小时**（整体人声活跃度 **42.1%**，自动过滤了 35.66 小时的纯挂机/音乐）
- **本地 ASR 转写完成分P**：**32** 个核心分P
- **本地 ASR 转写总字数**：**524,649** 字
- **本地 ASR 时间戳语音句**：**16,439** 条
- **本地草稿存储目录**：[`asr_drafts/`](file:///c:/Users/cheny/Downloads/shenqi/asr_drafts/)（已被 `.gitignore` 保护，不入库）

## 1. 独立运行工具

- **单文件转写/切片**：[`local_asr_pipeline.py`](file:///c:/Users/cheny/Downloads/shenqi/local_asr_pipeline.py)
  ```powershell
  python local_asr_pipeline.py -f audios/BV1aTeV6yENP_p5_41898410286.m4a
  ```
- **全量 VAD 端点扫描**：[`batch_vad_analysis.py`](file:///c:/Users/cheny/Downloads/shenqi/batch_vad_analysis.py)
- **全量批量 ASR 转写**：[`batch_asr_transcribe.py`](file:///c:/Users/cheny/Downloads/shenqi/batch_asr_transcribe.py)

## 2. 39 个音频分P本地 ASR 转写状态明细表

| 序号 | 优先级 | BV号 | 视频标题 | 分P | 音频时长 | 有效说话时长 | 人声占比 | ASR转写状态 | 转写字数/句数 | 草稿文件名 |
| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | 🔥 核心 | [`BV1JX8WzFEUU`](https://www.bilibili.com/video/BV1JX8WzFEUU) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P2 | 00:13 | 00:11 | 87.5% | ✅ 已转写 | 1,370字 (20句) | `BV1JX8WzFEUU_p2_31284528171_asr.txt` |
| 2 | 🔥 核心 | [`BV1KBgX6WEVm`](https://www.bilibili.com/video/BV1KBgX6WEVm) | 【神祇读神奇】今天例题课-2026072 | P1 | 03:40 | 02:50 | 77.5% | ✅ 已转写 | 51,408字 (888句) | `BV1KBgX6WEVm_p1_40322532606_asr.txt` |
| 3 | 🔥 核心 | [`BV1j4KC6KEse`](https://www.bilibili.com/video/BV1j4KC6KEse) | 【神奇】上课│20260718直播 | P1 | 04:00 | 02:48 | 70.2% | ✅ 已转写 | 55,127字 (1092句) | `BV1j4KC6KEse_p1_40109737103_asr.txt` |
| 4 | 🔥 核心 | [`BV14gby6LEni`](https://www.bilibili.com/video/BV14gby6LEni) | 【神祇读神奇】今天讲各种计时器│2026 | P1 | 01:59 | 01:23 | 69.4% | ✅ 已转写 | 26,439字 (450句) | `BV14gby6LEni_p1_40940472044_asr.txt` |
| 5 | 🔥 核心 | [`BV14gby6LEni`](https://www.bilibili.com/video/BV14gby6LEni) | 【神祇读神奇】今天讲各种计时器│2026 | P2 | 02:00 | 01:22 | 68.9% | ✅ 已转写 | 25,237字 (463句) | `BV14gby6LEni_p2_40943751084_asr.txt` |
| 6 | 🔥 核心 | [`BV199KH6TEra`](https://www.bilibili.com/video/BV199KH6TEra) | 【神奇】上课│20260719直播 | P1 | 01:59 | 01:15 | 62.8% | ✅ 已转写 | 24,493字 (641句) | `BV199KH6TEra_p1_40136673556_asr.txt` |
| 7 | 🔥 核心 | [`BV1sPsPzeEBc`](https://www.bilibili.com/video/BV1sPsPzeEBc) | 【神奇】看看明日方舟之神的上帝公式│20 | P1 | 02:28 | 01:31 | 61.6% | ✅ 已转写 | 32,330字 (901句) | `BV1sPsPzeEBc_p1_33218494500_asr.txt` |
| 8 | 🔥 核心 | [`BV1UnNSzSEvF`](https://www.bilibili.com/video/BV1UnNSzSEvF) | 【棋棋】神奇猫猫崽哪里│20250622 | P2 | 01:53 | 00:59 | 52.5% | ✅ 已转写 | 23,277字 (784句) | `BV1UnNSzSEvF_p2_30628448907_asr.txt` |
| 9 | 🔥 核心 | [`BV1JX8WzFEUU`](https://www.bilibili.com/video/BV1JX8WzFEUU) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P1 | 01:43 | 00:54 | 52.4% | ✅ 已转写 | 13,774字 (362句) | `BV1JX8WzFEUU_p1_31284463292_asr.txt` |
| 10 | 🔥 核心 | [`BV1CZ8t6wEyr`](https://www.bilibili.com/video/BV1CZ8t6wEyr) | 【神祇读神奇】今天讲避障力│202608 | P2 | 02:00 | 01:02 | 51.7% | ✅ 已转写 | 22,247字 (555句) | `BV1CZ8t6wEyr_p2_41195670049_asr.txt` |
| 11 | 🔥 核心 | [`BV1JX8WzFEUU`](https://www.bilibili.com/video/BV1JX8WzFEUU) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P3 | 01:14 | 00:38 | 51.4% | ✅ 已转写 | 8,947字 (203句) | `BV1JX8WzFEUU_p3_31284528562_asr.txt` |
| 12 | 🔥 核心 | [`BV16xhV6DEF4`](https://www.bilibili.com/video/BV16xhV6DEF4) | 【神祇读神奇】三船入坑│20260825 | P1 | 02:00 | 00:59 | 49.9% | ✅ 已转写 | 22,059字 (631句) | `BV16xhV6DEF4_p1_41261337528_asr.txt` |
| 13 | 🔥 核心 | [`BV14b4k6qEXt`](https://www.bilibili.com/video/BV14b4k6qEXt) | 【神祇读神奇】看看女神异闻录│20260 | P2 | 01:53 | 00:54 | 47.9% | ✅ 已转写 | 20,414字 (585句) | `BV14b4k6qEXt_p2_41436122513_asr.txt` |
| 14 | 🔥 核心 | [`BV1UnNSzSEvF`](https://www.bilibili.com/video/BV1UnNSzSEvF) | 【棋棋】神奇猫猫崽哪里│20250622 | P3 | 01:24 | 00:38 | 46.1% | ✅ 已转写 | 15,656字 (549句) | `BV1UnNSzSEvF_p3_30628513718_asr.txt` |
| 15 | 🔥 核心 | [`BV17WquBEEdX`](https://www.bilibili.com/video/BV17WquBEEdX) | 【神奇】看看缇缇│20260106直播 | P1 | 04:00 | 01:49 | 45.5% | ✅ 已转写 | 39,304字 (1581句) | `BV17WquBEEdX_p1_35235627214_asr.txt` |
| 16 | 🔥 核心 | [`BV1N58nzbE8x`](https://www.bilibili.com/video/BV1N58nzbE8x) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P1 | 02:00 | 00:52 | 43.8% | ✅ 已转写 | 19,176字 (624句) | `BV1N58nzbE8x_p1_31342462101_asr.txt` |
| 17 | 🔥 核心 | [`BV1XGiiB2EDS`](https://www.bilibili.com/video/BV1XGiiB2EDS) | 【神奇】孤星的球球搞清楚了，歇会玩玩小游 | P1 | 02:08 | 00:52 | 40.6% | ✅ 已转写 | 16,217字 (1260句) | `BV1XGiiB2EDS_p1_35160982284_asr.txt` |
| 18 | 🔥 核心 | [`BV1W38zzVEDX`](https://www.bilibili.com/video/BV1W38zzVEDX) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P2 | 00:40 | 00:13 | 32.9% | ✅ 已转写 | 4,801字 (206句) | `BV1W38zzVEDX_p2_31365268153_asr.txt` |
| 19 | 🔥 核心 | [`BV16xhV6DEF4`](https://www.bilibili.com/video/BV16xhV6DEF4) | 【神祇读神奇】三船入坑│20260825 | P2 | 01:33 | 00:29 | 31.7% | ✅ 已转写 | 12,347字 (520句) | `BV16xhV6DEF4_p2_41263435601_asr.txt` |
| 20 | 🔥 核心 | [`BV1N58nzbE8x`](https://www.bilibili.com/video/BV1N58nzbE8x) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P2 | 01:20 | 00:25 | 31.5% | ✅ 已转写 | 9,789字 (408句) | `BV1N58nzbE8x_p2_31342595942_asr.txt` |
| 21 | 🔥 核心 | [`BV1aTeV6yENP`](https://www.bilibili.com/video/BV1aTeV6yENP) | 【神祇读神奇】研究一下紧急远北猎场，7点 | P5 | 01:37 | 00:29 | 30.6% | ✅ 已转写 | 12,727字 (598句) | `BV1aTeV6yENP_p5_41898410286_asr.txt` |
| 22 | 🔥 核心 | [`BV1UnNSzSEvF`](https://www.bilibili.com/video/BV1UnNSzSEvF) | 【棋棋】神奇猫猫崽哪里│20250622 | P1 | 00:07 | 00:02 | 30.4% | ✅ 已转写 | 815字 (37句) | `BV1UnNSzSEvF_p1_30628448661_asr.txt` |
| 23 | 🔥 核心 | [`BV1N58nzbE8x`](https://www.bilibili.com/video/BV1N58nzbE8x) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P4 | 00:20 | 00:05 | 29.0% | ✅ 已转写 | 2,365字 (120句) | `BV1N58nzbE8x_p4_31342791973_asr.txt` |
| 24 | 🔥 核心 | [`BV1W38zzVEDX`](https://www.bilibili.com/video/BV1W38zzVEDX) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P1 | 02:00 | 00:33 | 27.8% | ✅ 已转写 | 13,070字 (552句) | `BV1W38zzVEDX_p1_31365074901_asr.txt` |
| 25 | 🔥 核心 | [`BV1CZ8t6wEyr`](https://www.bilibili.com/video/BV1CZ8t6wEyr) | 【神祇读神奇】今天讲避障力│202608 | P3 | 01:50 | 00:28 | 25.7% | ✅ 已转写 | 12,454字 (564句) | `BV1CZ8t6wEyr_p3_41230140885_asr.txt` |
| 26 | 🔥 核心 | [`BV1N58nzbE8x`](https://www.bilibili.com/video/BV1N58nzbE8x) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P5 | 01:59 | 00:30 | 25.2% | ✅ 已转写 | 12,004字 (509句) | `BV1N58nzbE8x_p5_31342855009_asr.txt` |
| 27 | 🔥 核心 | [`BV1fM8gzQEbo`](https://www.bilibili.com/video/BV1fM8gzQEbo) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P1 | 01:19 | 00:19 | 24.7% | ✅ 已转写 | 7,726字 (382句) | `BV1fM8gzQEbo_p1_31319392314_asr.txt` |
| 28 | 🔥 核心 | [`BV1W38zzVEDX`](https://www.bilibili.com/video/BV1W38zzVEDX) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P3 | 00:39 | 00:09 | 23.2% | ✅ 已转写 | 3,348字 (153句) | `BV1W38zzVEDX_p3_31365271408_asr.txt` |
| 29 | 🔥 核心 | [`BV1N58nzbE8x`](https://www.bilibili.com/video/BV1N58nzbE8x) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P6 | 01:03 | 00:14 | 22.7% | ✅ 已转写 | 5,971字 (282句) | `BV1N58nzbE8x_p6_31342987227_asr.txt` |
| 30 | 🔥 核心 | [`BV1N58nzbE8x`](https://www.bilibili.com/video/BV1N58nzbE8x) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P3 | 01:07 | 00:11 | 16.4% | ✅ 已转写 | 4,193字 (192句) | `BV1N58nzbE8x_p3_31342726612_asr.txt` |
| 31 | 🟡 中等 | [`BV1iq6GYqEHy`](https://www.bilibili.com/video/BV1iq6GYqEHy) | 【神奇】玩玩方舟明日矿工│2024122 | P3 | 00:00 | 00:00 | 13.7% | ⏸️ 低活跃跳过 | - | - |
| 32 | 🟡 中等 | [`BV1iq6GYqEHy`](https://www.bilibili.com/video/BV1iq6GYqEHy) | 【神奇】玩玩方舟明日矿工│2024122 | P4 | 01:01 | 00:07 | 12.4% | ⏸️ 低活跃跳过 | - | - |
| 33 | 🔥 核心 | [`BV1W38zzVEDX`](https://www.bilibili.com/video/BV1W38zzVEDX) | 【神奇】凹一下电弧全员界园入坑奖励图│2 | P4 | 01:42 | 00:11 | 10.8% | ✅ 已转写 | 5,526字 (324句) | `BV1W38zzVEDX_p4_31386832074_asr.txt` |
| 34 | 🟡 中等 | [`BV1CArkYKEqs`](https://www.bilibili.com/video/BV1CArkYKEqs) | 【神奇】大家都在打新肉鸽，我接着玩钩│2 | P1 | 01:14 | 00:06 | 8.7% | ⏸️ 低活跃跳过 | - | - |
| 35 | 🟡 中等 | [`BV18YrgYxE2U`](https://www.bilibili.com/video/BV18YrgYxE2U) | 【神奇】试试数据化玩矿工│2025010 | P1 | 01:22 | 00:04 | 5.3% | ⏸️ 低活跃跳过 | - | - |
| 36 | 🟡 中等 | [`BV1iq6GYqEHy`](https://www.bilibili.com/video/BV1iq6GYqEHy) | 【神奇】玩玩方舟明日矿工│2024122 | P1 | 02:42 | 00:08 | 5.3% | ⏸️ 低活跃跳过 | - | - |
| 37 | ❄️ 挂机 | [`BV1iq6GYqEHy`](https://www.bilibili.com/video/BV1iq6GYqEHy) | 【神奇】玩玩方舟明日矿工│2024122 | P2 | 00:36 | 00:01 | 4.0% | ⏸️ 低活跃跳过 | - | - |
| 38 | ❄️ 挂机 | [`BV1bbWUzcE6v`](https://www.bilibili.com/video/BV1bbWUzcE6v) | 【神奇】打打20攻速为崖│2025102 | P2 | 00:05 | 00:00 | 1.1% | ⏸️ 低活跃跳过 | - | - |
| 39 | ❄️ 挂机 | [`BV1bbWUzcE6v`](https://www.bilibili.com/video/BV1bbWUzcE6v) | 【神奇】打打20攻速为崖│2025102 | P1 | 00:30 | 00:00 | 0.2% | ✅ 已转写 | 38字 (3句) | `BV1bbWUzcE6v_p1_33254084555_asr_draft.txt` |