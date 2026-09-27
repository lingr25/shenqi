# 术语挖掘 Round 1 — 用户裁定与落地记录（2026-09-27）

## 裁定范围

- **high 级 asr_suspect 325 条：全部采用**（用户："high推断的都可以用"）。
- 新实体/黑话逐条裁定见下表；未点名项留在 `CANDIDATES_REVIEW_R2.md`（672 条）待裁。

## 落地方式

| 产物 | 内容 |
|---|---|
| `entity_corrector.py` | 新增 **191 条全局规则**（同族合并，如 8 种避障力讹写并 1 条）+ **88 条文件级定向规则**（22 个 BV 前缀）；另对 2 条既有规则做同族修补（技力前缀加"加"、"统称神奇"允许空格） |
| `build_glossary.py` | 新增第 4 源 `kb_trial/term_mining/user_entities.jsonl`（用户裁定实体），产物 glossary.json 1887 → **2010** 条 |
| `apply_r1.py` | 规则落地脚本（幂等），含全部规则数据与拼写归一说明 |

**文件级/锚定原则**：常用词与单字讹写（目录、建设、发生、买、费、车、研、请、轻、趟、挺、碎、折、传→船 等）一律加 BV 前缀 scope 或上下文锚定（如 `(?<=帧)挺`、`(?<=这一帧)除上`、`传→船` 排除 黍传/余传/传送），防止污染正常中文。`大跌→大爹` 仅限 BV1dVcbzFEdd（他片"大跌"实为"大姨"）；`火神→火陈` 仅限 BV1UVeV66E7p（与干员火神冲突）。

## 用户逐条裁定（实体/黑话）

| 词 | 裁定 | 落地 |
|---|---|---|
| 三帧一判 | 部分机制（如阻挡）每三帧判定一次 | glossary mechanic |
| 上右下左 | 明日方舟魔改的 SPFA 寻路机制 | glossary mechanic |
| 停住 | 实为"停驻"（停驻状态机） | corrector 全局 停住→停驻 |
| 分离力 | 先记下（定义待核；逐字稿语境：使敌人相互远离的力） | glossary mechanic |
| 坎诺特 | 诡异商人坎诺特，肉鸽机制 | glossary mechanic |
| 孤星 / 将进酒 | 活动关卡 | glossary term（孤星含讹写"胡星"） |
| 寻路坐标 | 就是寻路坐标 | glossary mechanic |
| 机械之灾 | ISW-NO 关卡 | glossary term |
| 紧急建制 | 关卡 | glossary term |
| 赤霄 | 陈的武器 | glossary term |
| 划火柴 | 暂停部署 | glossary slang |
| 山雀 | 一个人 | glossary shenqi_slang |
| 整费 | 费用条为 0 时 | glossary slang |
| 斗蛐蛐 | 明日方舟的一个活动（争锋频道） | glossary slang |
| 无藏 | 不拿任何藏品打集成战略 | glossary slang（含讹写"武藏"） |
| 狼头 | 荒芜拉普兰德的浮游炮 | glossary slang |
| 花佬 | 花见花开，擅长解包 | glossary shenqi_slang |
| 黑梭 | 黑蓑影卫攻略组 | glossary shenqi_slang |
| 赛博塑料 | 帧级别自动复刻预录轴的程序 | glossary slang |
| 免疫渔船 | → 免疫余传（余=干员，对齐既有"免疫黍传"） | corrector 全局 |
| 同遇共存 | → 同域共存（关卡） | corrector 全局 + glossary term |
| 国光 | → 弧光行动 | corrector 全局（canonical 化） |
| 大跌 | → 大爹（爱国者） | corrector 文件级 + glossary slang |
| 永动致残 | → 涌动之餐（否决 agent 猜测"永冻之餐"） | corrector 全局 |
| 猫车 | 本身正确：一星干员泰拉大陆调查团 | glossary slang；**否决** corrector 候选"猫车→猫撤" |
| 书刀 | 本身正确 | glossary term |
| 中立生灵 | ASR 乱码，不收 | **否决**，不入任何表 |
| 封护 | 本身正确：缇缇的技能 | glossary term；**否决** corrector 候选"封护→风护" |

**拼写归一**（落地前核对 glossary 现有正词）：钩锁师→**钩索师**（PRTS 分支名）；隐德莱希→**隐德来希**；歌蒂(歌蕾蒂娅)→**歌蒂**。

## 验证

- 自检 35 用例全过（含护栏：传送/黍传/旺盛/蜥蜴/重组回去/资格/小柯基/埃拉托色尼/统一德国/挺进/发生了 均不被误改）。
- 全语料干跑：191 全局 + 88 文件级规则 0 失效；最高频为 停住→停驻(156)、避障力族(89)、远北猎场族(32)、驯鹿→寻路(31)。
- 重清洗影响面（**未执行**，仅干跑统计）：926/23521 行（3.9%）会变化。

## 待办（需用户放行）

1. 用新规则重清洗 45 份 `transcripts_txt/`（预期 926 行变化）。
2. R2 清单 672 条逐批裁定（high 2 条：移速因子、避障中间量；mid 409；low 261）。
