# -*- coding: utf-8 -*-
"""Close the loop on the 612 evidence verdicts.

The parent rejected the previous state for three reasons, all addressed here:

1. `evidence_verdicts.jsonl` was written as a template `supported` for every entry and
   never actually reached the shipped JSON (`kb_curation_evidence_apply.py` had not been
   run). Facts inside `reason` were sometimes wrong: `驯鹿` is an ASR corruption of `寻路`,
   yet entries shipped `subject="驯鹿"`.
2. Verdicts must not be rubber-stamped `supported`. Where the derived text carries a
   known-wrong term, the DERIVED claim/subject/condition must be repaired (quotes stay
   byte-identical). Where the source cannot settle the claim, the verdict is `pending`.
3. The verdict must land in the build output as an `evidence_review` block with an honest
   confidence ceiling: text-source-supported, NOT verified game truth.

This script rewrites the verdict file in place from a table of per-entry decisions, so the
result is auditable: every change is stated explicitly and can be diffed.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial' / 'curation'
VERDICTS = OUT / 'evidence_verdicts.jsonl'
QQ_OVERLAY = OUT / 'qq_claim_overlay.json'
QQ_HELD_OUT = OUT / 'qq_claim_held_out.json'
STAGING = OUT / 'curated_staging.json'
CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'

# ---------------------------------------------------------------------------
# A. derived-text repairs: entry_id -> list of (field, before, after, justification)
#    Quotes are never touched. Only the DERIVED text is corrected.
# ---------------------------------------------------------------------------
REPAIRS = {
    'fc1:寻路-37-2#r0': [
        ('claim', '眩晕、阻挡、束缚完全不改变驯鹿的状态', '眩晕、阻挡、束缚完全不改变单位的寻路状态',
         '源 [01:58:41] 逐字作「他们是完全不改变驯鹿的状态的」，「驯鹿」为 ASR 对「寻路」的讹写（同文件 [02:23:48] 同一句内并列「避障力 驯鹿力和分离力」随后又作「寻路力」，[45:15] 同段并列「地面寻路的刹车距离」「飞行驯鹿的刹车距离」），故派生文本订正为「寻路」。'),
        ('subject', '驯鹿', '单位的寻路状态',
         '原文「驯鹿」是 ASR 讹写，实际指单位的寻路状态；subject 必须能回答「什么处于眩晕」，故由名词「寻路」改为「单位的寻路状态」。'),
        ('condition', '驯鹿处于眩晕、阻挡或束缚时', '单位处于眩晕、阻挡或束缚时',
         '原条件把状态主语写成「驯鹿」（误读为单位），实际主语是被控的单位。源 [01:58:35]「我们说一下眩晕阻挡束缚这一类」的主语是单位，不是寻路。'),
    ],
    'fc1:寻路-37-2#r1': [
        ('claim', '眩晕、阻挡、束缚的时间可以从中间直接删掉，两边可以拼起来',
         '眩晕、阻挡、束缚占用的时间可以从寻路过程中直接删掉，寻路过程在停顿前后连续、两边可以直接拼起来',
         '源 [01:58:41] 的宾语「这些时间」指的是角色被控的那段时间，「两边可以拼起来」的主语是寻路过程本身：紧接的 [01:58:55]「之前我说的上一帧的速度 这个概念也是寻路的 上一帧不包括停顿」与 [01:59:17]「眩晕是不会更新寻路的速度的」都在讲寻路过程的连续性。原派生文本省略了动作对象，单独读会被误解为「任意两段时间可拼接」，故补出对象与「寻路过程连续」这一源中明确含义。'),
        ('subject', '驯鹿', '单位的寻路过程',
         '同 r0，「驯鹿」为「寻路」讹写；本条的宾语与主语都是寻路过程，故 subject 明确为「单位的寻路过程」。'),
        ('condition', '驯鹿处于眩晕、阻挡或束缚时', '单位处于眩晕、阻挡或束缚时',
         '条件的主语是被控单位，不是寻路本身；「寻路处于眩晕」是角色错位。'),
    ],
    'fc1:寻路-37-2#r2': [
        ('claim', '束缚不是退出驯鹿的状态，而是在寻路中直接跳过驯鹿的位移过程',
         '束缚不是退出寻路状态，而是在寻路中直接跳过单位的位移过程',
         '源 [02:12:19] 逐字作「束缚他不是退出了驯鹿的状态 但是他是在寻路中直接跳过了驯鹿的位移 这个过程」：句内同时出现订正后的「寻路」与讹写的「驯鹿」，可自证两者同指；且「驯鹿的位移」实际指单位的位移。'),
        ('subject', '驯鹿', '单位的寻路状态与束缚的关系',
         '订正讹写并补出本条真正的主语（寻路状态与束缚的关系），原「驯鹿」不可作为主语。'),
        ('condition', '驯鹿处于束缚时', '单位处于束缚时',
         '主语角色错位订正，同 r0/r1。'),
    ],
    'fc1:帧时序与计时器-45-12#r0': [
        ('claim', '在蛤蟆中间没有影响过驯鹿的前提下，破箱帧可由蛤蟆的出生帧加上抛两个硬币的时间直接算出。',
         '在蛤蟆中途没有影响过寻路的前提下，破箱帧可由蛤蟆的出生帧加上抛两个硬币的时间直接算出。',
         '源 [13:32] 逐字为「比如说这个蛤蟆有没有中间影响过驯鹿」，「驯鹿」为「寻路」讹写（同视频 [29:44]「他的驯鹿还是在正常的」与 [35:09]「我记得寻路这个东西」互证）。claim 的主干（破箱帧推算）由引文逐字支持，仅订正该讹写词。'),
        ('subject', '蛤蟆的出生帧与抛两个硬币的时间之和对破箱帧的推算', '蛤蟆的出生帧与抛两个硬币的时间之和用于推算破箱帧',
         'subject 应是一个名词性论题而非「之和对……的推算」这种悬空结构，改写为可独立读的通顺论题；机制含义不变。'),
        ('condition', '蛤蟆中间没有影响过驯鹿;已知蛤蟆的出生帧;已知抛两个硬币的时间',
         '蛤蟆中途没有影响过寻路;已知蛤蟆的出生帧;已知抛两个硬币的时间',
         '同 claim，订正「驯鹿」为「寻路」。'),
    ],
    'fc1:寻路-3-3#r3': [
        ('claim', '寻路过程中会判定离坑、障碍物、不可通行地块有多近，并计算B张力向量。',
         '寻路过程中会判定离坑、障碍物、不可通行地块有多近，并计算避障力向量。',
         '引文逐字作「计算一个B张力向量」，而「B张力」是 ASR 对「避障力」的讹写：同文件 [02:23:48]「避障力 驯鹿力和分离力」给出正式术语，[02:30:47]「他的避障判定区」、[02:36:40]「这个B张力向量的话 然后在这一步要乘以这个系数」与 [02:53:49]「避障判定力 避障判定的中心」同为该向量的描述。引文保持原字，派生 claim 用订正术语。'),
    ],
    'fc1:索敌-19-12#r0': [
        ('claim', '严格可确定的攻击事件流程为：出生到索敌、索敌到事件真、事件真到命中、事件帧到动画结束、动画结束到下次索敌、索敌到下次索敌。',
         '严格可确定的攻击事件流程为：出生到索敌、索敌到事件帧、事件帧到命中、事件帧到动画结束、动画结束到下次索敌、索敌到下次索敌。',
         '引文本身在同句内先作「索敌到事件真事件真到命中」后作「然后事件帧到动画结束」，可自证「事件真」=「事件帧」；原派生文本前两处未订正、第三处已订正，同一条内术语不一致，故统一为「事件帧」。'),
    ],
    'fc1:索敌-19-12#r1': [
        ('claim', '事件真到命中对应弹道发射。', '事件帧到命中对应弹道发射。',
         '引文逐字作「事件真到命中啊 这个是弹道发射」；同源 [02:30] 同段作「事件帧到动画结束」，证「事件真」为「事件帧」讹写。引文保持原字。'),
    ],
    'fc1:帧时序与计时器-27-3#r1': [
        ('claim', '同为「空费针开的部署」的半针轴出现两种表现，是因为部署的人不知道空飞针有两帧。',
         '同为「空飞针开的部署」的半针轴出现两种表现，是因为部署的人不知道空飞针有两帧。',
         '同一 claim 内先作「空费针」后作「空飞针」，源 [56:24]「说都是空费针开的」与 [56:39]「他们不知道空飞针有两针」证实二者同指、正确写法为「空飞针」；原文本同条内术语不一致，故统一。'),
        ('subject', '半针轴（空费针开的部署）', '半针轴（空飞针开的部署）', '同 claim，订正讹写。'),
        ('condition', '空费针开的部署', '空飞针开的部署', '同 claim，订正讹写。'),
    ],
    'fc1:其他-3-19#r0': [
        ('claim', '陷阱师会严格定义怪的隔判。', '陷阱师会严格定义怪的格判。',
         '源为 ASR 草稿层，同一段落内三种写法并存：[47:12]「线阱师的隔判是严格的」、[47:57]「陷警师认为他是到高台了……这就是怪的格判」，证实「隔判」为「格判」讹写、「线阱师/陷警师」为「陷阱师」讹写。引文保持原字。'),
    ],
}

# ---------------------------------------------------------------------------
# A2. QQ entries: the upstream rule text is a window TITLE, not a mechanism sentence,
#     and every one of the 11 shipped with subject/condition/scope unfilled. These are
#     re-derived from the literal window spans only, and each field states no more than
#     the spans carry. A window whose spans cannot settle the claim goes to QQ_PENDING
#     below instead of being generalised.
#     (claim_from, claim, subject, condition, scope, note)
# ---------------------------------------------------------------------------
QQ_REPAIRS = {
    'window:w000006#r0': (
        '夜半眠兽撤退与开技能出睡帧时序',
        '夜半眠兽的睡眠状态在撤退或再部署时立即解除，而开技能后第 16 帧才施加睡眠。',
        '夜半的眠兽',
        '眠兽撤退、再部署，或夜半开启技能时',
        'instance',
        '逐条 span 为问答两段：问句「夜半眠兽撤退和再部署后几帧会取消睡眠啊」，答句逐字「撤退直接没，重生也是立刻，开技能后16帧出睡」。'
        '「没」指睡眠消失、「重生」指再部署后重新登场，两句共同给出撤退/重建立即解除、开技能后 16 帧施加睡眠这一条帧时序，是可直接使用的机制规则。'
        '范围仍限定为夜半的眠兽这一实例，窗口未主张其为所有召唤物或所有睡眠来源的通则，故 scope=instance、不升为 universal。'
    ),
    'window:w000012#r0': (
        '阻挡与索敌同帧导致群攻能力被插入结算',
        '部分群攻能力的锁人分为「决定锁人」与「决定锁谁」两步，中间可被插入结算；'
        '阻挡与索敌发生在同一帧时，该插入即会发生。',
        '部分群攻能力（锁定目标的选取过程）',
        '阻挡与索敌发生在同一帧时',
        '未标注',
        'span 逐字给出三句：「阻挡和索敌同帧」「部分群攻能力会被插结算」「我记得有些群攻能力，会先决定锁人／再决定锁谁／中间能插入进去」。'
        '复核时发现初稿把「分为两步、中间可插入」写成了群攻能力的普遍结构，而 span 的限定词是「部分」与「有些」，「我记得」更表明这是回忆性陈述——'
        '已把限定词回填到 claim 与 subject，不再收窄为全部群攻能力。'
        '范围留「未标注」：span 未界定该规律适用于哪些单位或哪种攻击流程，泛化会是超出 span 的推断。'
    ),
    'window:w000027#r0': (
        '弹道组件结构定义与Prefab拆包路径',
        '弹道一般分为三个部分：Projectile 定义弹道是什么、Movement 定义弹道怎么移动、'
        '以及可能存在的 HitBehavior、碰撞判定、targetVaildator 等定义弹道怎么命中；'
        '要找弹道数据，建议从单位的 prefab 取得弹道 id，再用该 id 搜索弹道并查看数据（要看的字段在 Movement 里）；'
        '弹道文件位于安装目录 battle/prefabs 下。',
        '弹道（Projectile）数据文件与其组件',
        '在单位 prefab 中取得弹道 id 后检索该弹道数据时',
        'instance',
        'span 逐字给出三段式职责（「弹道一般分为三个部分：Projectile定义／Movement定义／以及可能存在的HitBehavior、碰撞判定、targetVaildator等东西」'
        '对应「定义弹道是个什么东西／定义弹道怎么跑／定义弹道怎么打中人」），并给出检索路径与两条具体目录。'
        '复核时发现初稿把 span 的「弹道一般分为三个部分」升格成了确定的「由三个部分组成」、并去掉了「最好是从…」的建议口吻，'
        '已回填「一般」与「建议」；「你要的东西在Movement里面」也不再被省略。'
        '属拆包结构说明与操作路径，不是对游戏行为的主张，故 scope 记为 instance 而非 universal。'
        '注意 span 中的「targetVaildator」是原始拼写（非 valid），claim 沿用原写法以免与拆包数据里的实际字段名脱节。'
    ),
    'window:w000033#r0': (
        '凯尔希抓人目标判定逻辑与同帧/同创建时间优先级',
        '凯尔希抓人选取创建时间最久的单位；创建时间相同时按默认顺序、即先部署者优先，因此同帧部署时先部署的单位先被抓取。',
        '凯尔希的抓取技能目标选取',
        '多个候选单位可被凯尔希抓取时',
        'instance',
        'span 逐字给出「凯尔希抓人是"创建时间最久"」「同帧部署先打先部署的」「创建时间相同的情况下还是默认顺序，先部署先选」「同仇恨就是先部署」。'
        '四句互相印证，可直接支撑「以创建时间排序、相同则先部署优先」这一选取规则；「这不是bug」是讨论者的定性，未写入 claim。'
        '范围限定为该技能的实例，窗口未主张其为所有选取类技能的通用排序，故 scope=instance。'
    ),
    'window:w000037#r0': (
        '仇恨0.1精度比较与医疗索敌',
        '仇恨值以 0.1 为精度比较：比较时将双方仇恨临时乘以 10 转为整数，再比较这两个整数。',
        '仇恨值的比较过程',
        '比较两个单位的仇恨值时',
        'instance',
        'span 逐字给出「仇恨里面的"0.1"精度，本质上是在两边比较时，双方临时*10，转为整数，然后再比较」，同句在窗口内重复出现一次。'
        '复核时发现初稿把本条与同一窗口内相邻的医疗索敌发言用「；」合并成一条 claim，'
        '并把 subject/condition 也用「；」并起来，读起来像同一条规则的两面，实际二者互不相关。'
        '本窗口只保留仇恨精度比较这一条（话题自足）；医疗索敌部分因同窗口内无独立规则载体、'
        '且「医疗一般都是生命比例最低」含「一般」这一限定，不足以单独成条，未一并收入本 claim，'
        '原始 span 仍在 citations 中完整保留可供查阅。'
    ),
    'window:w000040#r0': (
        '麻痹免疫判定布尔写反与_isUnset配置',
        '在麻痹免疫相关判定中，免疫「关着」的单位反而才通得过判定；该判定把「没有麻痹免疫」写成了「并非没有麻痹免疫」，'
        '配置项名为 _isUnset（意为「没有这么个东西」）。',
        '麻痹免疫的判定条件与 _isUnset 配置项',
        '在拆包数据中检查麻痹免疫相关判定时',
        'instance',
        'span 逐字给出「关了="有免疫"才能过判定」「本来该判定"没有麻痹免疫"的这行，写成了"并非没有麻痹免疫"」'
        '「仔细看看会发现这个配置叫"_isUnset"，即"没有这么个东西"」「因为没有是对的」。'
        '复核时发现初稿把「_isUnset 为 true 才表示没有麻痹免疫」写进了 claim，但 span 只给出配置的命名含义，'
        '并没有说 true 与「没有」的对应关系——「true 是没有、false 是有」只出现在评论句'
        '「程序员估计到死都没想明白为什么true是没有，false是有」里，属他人评论而非机制陈述。claim 已收回到 span 的字面表述。'
        'scope=instance：本条描述的是具体某个判定与具体配置项，不是通则。'
    ),
    'window:w000042#r0': (
        '恐惧地块选取与恐惧源为自己时的寻路回落',
        '恐惧地块不看来源格，直接取绑定干员（生成该单位的干员）视野范围内的地块；'
        '恐惧源是自己的情况下没有恐惧地块，寻路时回落到自己的地块上，表现为在自己地块内乱走。',
        '恐惧状态下的目标地块选取与寻路',
        '某单位被施加恐惧状态时；恐惧源是该单位自身时',
        'instance',
        'span 逐字给出「首先是不看来源格，直接拿绑定的干员（就是生成他的干员）的视野范围的地块作为恐惧地块」'
        '「恐惧源是自己的情况下，没有任何恐惧地块 寻路时回落到自己地块上」「表现就是在自己地块里瞎走」。'
        '同一窗口还给出排除项——生息羊「被打时会随机选择一个地块然后跑过去挂机」「这个就不是恐惧」，'
        '该排除项在 claim 中不出现，但正因窗口自身区分了恐惧与随机选地，此条才限定为恐惧机制本身。'
        'scope=instance：讨论的是恐惧这一具体状态的实现，未主张其为所有位移型状态的通则。'
    ),
    'window:w000044#r0': (
        '嘲讽机制数值与仇恨异常表现',
        '嘲讽提供固定的 +1000 仇恨加值。',
        '嘲讽状态提供的仇恨加值',
        '单位处于嘲讽状态时',
        'instance',
        'span 逐字给出「嘲讽就是+1000仇恨」，另有「嘲讽一直正常生效」与「被干员超过了那是干员的事」两句作旁证（后句说明该加值可被干员的仇恨超过，不改变 +1000 这一固定加值本身）。'
        '数值「+1000」是窗口内直接给出的字面陈述，不是需推导或估算的量，故不按「数值未经核实」处理；'
        '但它属于群聊中的机制讨论共识，不是本项目独立复算或实测的结果，这一点在 evidence_review.review_basis 与 confidence 中已如实标注。'
        'scope=instance：窗口讨论的是当时嘲讽在仇恨异常环境下的表现，未主张该数值适用于所有版本或所有单位，且同窗口的'
        '「城防炮出问题了，刁民车嘲讽出问题了，阿你怎么能这么正常呢」「异常在于阿在现在仇恨异常的数量级下十分正常」「只能解包看了」'
        '是当时的现场观测，均未写入 claim。'
    ),
}

# ---------------------------------------------------------------------------
# A3. QQ entries whose spans do NOT settle the claim: these must not ship with a
#     mechanism sentence that the window cannot carry.
# ---------------------------------------------------------------------------
QQ_PENDING = {
    'window:w000031#r0': (
        'source_cannot_settle_claim',
        '窗口 span 含未闭合疑问与相互冲突的表述，无法从 span 直接确定机制主张，故不给 claim 定稿：'
        '(1) 疑问句「死亡不会清除buff，退出浮空状态机吗」是提问，答案并未在 span 内以完整句给出，'
        '紧接的「浮空的飞行又不是buff带来的」「buff和状态机都没了」两句与提问是否同指、谁接谁的发言，'
        '在脱敏后的片段里无从区分；(2)「起飞单位还是地面单位，不对空不要紧」与首句「浮空敌人为飞行单位，而起飞只防地面单位的索敌」'
        '是两条并列且需要上下文才能调和的说法；(3)「能炸到就是上面这个原理，不能炸到就说明死亡的时候已经解除飞行了」'
        '是对现象的二分解释，本身不构成一个机制陈述。把这些拼接成「死亡时点是否已解除飞行决定能否被炸到」属于替来源补结论，'
        '按「来源不确定 → pending」处理，不猜补。'
    ),
    'window:w000036#r0': (
        'source_cannot_settle_claim',
        '窗口 span 的假设句与实测句混在一起，无法据此定稿机制主张：'
        '(1)「现在就是每次部署给全局仇恨计数硬性+1来规避同仇恨值」是实测陈述，但同一窗口的'
        '「但是理论上你还是可以靠部署100个干员来出现同仇恨」是假设，二者并存说明「同仇恨不可达」不成立；'
        '(2)「越晚的仇恨应该越高」含「应该」，是推测而非断言；「4号：仇恨降序」「——那同帧依旧是先部署」是被截断的讨论片段，'
        '缺少主语与参照对象；(3) 群攻伤害顺序仅由「你猜猜群攻干员的伤害顺序是什么？」「诶，对，从先到后」一问一答承载，'
        '「从先到后」的具体含义（按部署顺序还是按仇恨顺序）未在 span 内说清。以上任一条都不足以单独支撑机制句，且互相约束，'
        '按「来源不确定 → pending」处理。'
    ),
    'window:w000041#r0': (
        'source_cannot_settle_claim',
        '窗口把一条可复用的伤害通式与一个未闭合的实测记录混在一起，故只保留前者时仍不足以给本条定稿：'
        '(1) 可用的部分仅「明日方舟所有伤害都是 攻击力 * 攻击力倍率 + 附加攻击力」这一句通式（同窗口「只是在逻之前没有任何人用过这个附加攻击力区」为其注解）；'
        '(2) 本条 claim 的另一半是钩爪位移伤害的帧数记录「每2帧判定一次，距离5帧更新一次，所以实际上是每4/6帧一次伤害，但挂上罗哥buff后就是每2帧一次伤害了」，'
        '该数值属单次实测，且同窗口紧邻的「能对0伤害+x的吗我靠」表明讨论仍在进行中，数值是否已被讨论者与提问者确认在 span 内看不出；'
        '(3)「天赋并不增伤，其实是个"隐藏乘区"」是对乘区归属的解释性表述，未给出可核对的判定条件。'
        '把通式与实测数值合成一条 claim 会同时抬高两者的确定性，按「来源不确定 → pending」处理，不拆分、不选取其一。'
    ),
}

# ---------------------------------------------------------------------------
# B. verdicts downgraded from `supported` to `pending`.
# ---------------------------------------------------------------------------
PENDING = {
    'fc1:帧时序与计时器-35-0#r16': (
        'source_cannot_settle_claim',
        '本条不是自包含的机制规则，且来源无法独立确定其含义：(1) 引文中的「池塘/鱼/鱼字」出自主播当时在打的某一具体关卡与解谜过程，'
        '源中反复出现「运气问题」「第一天那种现象」「前两条鱼必须都得是零猜鱼」等仅在该局语境成立的表述，条目未记录关卡与模式；'
        '(2) 同文件后半段明确是主播自建模拟程序的调试（[50:48]「反正就是AI写的这个程序有很多的bug」、'
        '[01:37:07]「注意啊 我最开始的代码中 这里做了一个简化」），本条引文所指的「入水帧/检测周期」与程序实现纠缠，'
        '无法区分是游戏行为还是模拟器行为；(3) 「每条鱼各自的入水帧不同，因此各自可以出去的时间不同」这一句在源中是对该局观察的解释，'
        '而非对全体单位的普适陈述。按「来源不确定 → pending」处理，不再声称 supported。'
    ),
    'fc1:寻路-39-7#r8': (
        'source_cannot_settle_claim',
        '源文本在此处自相矛盾，无法确定 claim 主张的到底是哪种几何：(1) claim 与引文都写「往格子中线的路径点走」，'
        '「中线」是一条线、不是中心点；(2) 但同一章紧邻的两行明确说的是「中心」——'
        '源 BV1TomVBBEK1_p1_34675165371.txt [03:50:00]「寻路坐标一定出生在一个格子的中心」、'
        '[03:50:17]「寻路坐标也会认为每个格子的路径点都在中心 也会认为终点在中心」；'
        '(3) 本条引文所在的 [03:50:40] 是同一段里的第三次表述，却是唯一出现「中线」的一次。'
        '「格子中线」与「格子中心」在机制上不是措辞差异而是几何差异（线 vs 点）：若路径点真在中线，'
        '实体坐标的偏移参照就不是中心点，结论会不同。本轮无法从文本判定主播当时口误还是另有含义，'
        '也不替来源在两者间取舍，故按「来源不确定 → pending」隔离，不再声称 supported。'
    ),
}

# ---------------------------------------------------------------------------
# C. honest review metadata applied to every row (replaces the template wording).
# ---------------------------------------------------------------------------
REVIEW_BASIS = (
    '本轮为 agent 依据 packet 内嵌的 SOURCE WINDOW 与已解析引文逐条比对后作出的文本层判定；'
    '未做人工核听、未回看原片视频。置信上限为「有文本出处支持该派生表述」，'
    '不等于游戏内真值已验证（非 game-truth verified）。'
)
LIMITATION = (
    '局限：判定依据是转录文本（官方 AI 字幕层或云端 ASR 草稿层），不是原片音画；'
    'ASR 讹写会同时污染引文与派生文本，本轮只订正了能由同源上下文自证的确定讹写，'
    '其余存疑处未改动并在 derived_correction_applied 中记明。'
    '「all reviewed」不代表「all correct」。'
)


def parse_correction(c):
    """Classify a derived_correction string into applied/not_needed/pending."""
    if not c or not c.strip():
        return 'not_needed'
    if re.search(r'无术语讹写|无讹写|无需纠正|不是讹写|非讹写|无需订正|口述重复|口述叠字|口述顿词|口述连写|口述冗余|口误残句|口语', c):
        return 'not_needed'
    if '疑为' in c or '存疑' in c or '不确定' in c:
        return 'pending'
    return 'applied'


MARKER = ' 【派生文本订正】'


def strip_markers(reason, eid):
    """Return the pristine base reason, removing text this script adds (idempotence)."""
    r = reason
    for _code, why in PENDING.values():
        if r == why:
            return r
    i = r.find(MARKER)
    if i != -1:
        r = r[:i]
    return r.rstrip()


rows = [json.loads(l) for l in VERDICTS.read_text(encoding='utf-8').splitlines() if l.strip()]
# The QQ verdicts are authored in section E below; on a re-run they are already in the file
# and must not be re-processed by the VOD rewrite loop (that loop only knows the 612). They
# are dropped here and regenerated from the table, so the table stays the single source.
rows = [r for r in rows if not r['entry_id'].startswith('window:')]
byid = {r['entry_id']: r for r in rows}
assert len(byid) == 612, len(byid)


new_rows = []
stats = {'applied': 0, 'not_needed': 0, 'pending': 0}
for r in rows:
    r = dict(r)
    eid = r['entry_id']

    # Strip anything a previous run of this script added, so the rewrite is idempotent.
    base_reason = strip_markers(r.get('reason', ''), eid)

    # ---- corrections disposition ----
    disp = parse_correction(r.get('derived_correction'))
    r['derived_correction_disposition'] = disp
    stats[disp] += 1

    # ---- derived-text repairs ----
    rep = REPAIRS.get(eid)
    if rep:
        r['repaired_fields'] = [{'field': f, 'from': b, 'to': a, 'justification': j} for f, b, a, j in rep]
        r['derived_correction_disposition'] = 'applied'
        r['status'] = 'supported'
        r['reason'] = (
            base_reason
            + MARKER + '；'.join('%s：「%s」→「%s」' % (f, b, a) for f, b, a, _ in rep)
            + '。引文保持原始逐字文本不变。'
        )
    # ---- downgrades ----
    if eid in PENDING:
        code, why = PENDING[eid]
        r['status'] = 'pending'
        r['pending_code'] = code
        r['reason'] = why
        r['repaired_fields'] = []
        r['confidence'] = 'text-source-inconclusive'

    # ---- honest basis on every row ----
    r['review_basis'] = REVIEW_BASIS
    r['limitation'] = LIMITATION
    if eid not in PENDING:
        r['confidence'] = 'text-source-supported'
    new_rows.append(r)

# (verdict file is written after section E, so the QQ verdicts land in the same file)

# ---------------------------------------------------------------------------
# D. Emit the QQ claim overlay, and check the two tables against what actually ships.
#    The overlay is generated from the tables above rather than hand-edited so that the
#    derivation stays diffable and rebuildable; the checks fail loudly if an id drifts.
# ---------------------------------------------------------------------------
qq_rows = []
for eid in sorted(QQ_REPAIRS):
    item = QQ_REPAIRS[eid]
    if len(item) != 6:
        raise SystemExit('QQ_REPAIRS[%s] must be (claim_from, claim, subject, condition, scope, note)' % eid)
    claim_from, claim, subject, condition, scope, note = item
    if scope not in ('universal', 'instance', '未标注'):
        raise SystemExit('QQ_REPAIRS[%s]: unexpected scope %r' % (eid, scope))
    if claim == claim_from:
        raise SystemExit('QQ_REPAIRS[%s]: claim unchanged from the upstream title' % eid)
    if subject == '未标注' or condition == '未标注':
        raise SystemExit('QQ_REPAIRS[%s]: subject/condition must be stated, not 未标注' % eid)
    qq_rows.append({'entry_id': eid, 'claim_from': claim_from, 'claim': claim, 'subject': subject,
                    'condition': condition, 'scope': scope, 'note': note})
# The upstream window titles for the held-out entries, stated literally so the hold-out
# record can point at exactly what was NOT allowed to ship as a mechanism sentence.
_TITLE_FALLBACK = {
    'window:w000031#r0': '浮空状态与飞行判定及死亡时点机制',
    'window:w000036#r0': '群攻伤害结算顺序与仇恨同帧/同仇恨判定逻辑',
    'window:w000041#r0': '附加攻击力乘区与钩爪位移伤害判定机制',
}

QQ_OVERLAY.write_text(json.dumps(
    {'note': '由 kb_curation_evidence_close.py 依据 curation/qq_worklist.json 的窗口 span 生成；'
             'kb_curation_build.py 在构建时应用，令 QQ 条目不再以窗口标题充当机制句，'
             '并补出其 subject/condition/scope。引文（citations[].quotes[].text）一律保持原始逐字文本。'
             '本文件逐条给出 from/to 与取舍理由，可 diff、可重跑。'
             'records 只含 span 能直接支撑的窗口；excluded 列出 span 无法确定主张、'
             '故隔离待人工判读的窗口。',
     'entry_count': len(qq_rows),
     'excluded_count': len(QQ_PENDING),
     'records': qq_rows},
    ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

# ---------------------------------------------------------------------------
# E. Evidence verdicts for the QQ entries that cleared review.
#
#    These entries were missing from evidence_review_worklist.jsonl (that worklist only
#    selected review.status == auto_screened, and the QQ track ships as agent_verified),
#    so this stage had no verdict for them and wrote an "inherited" block instead. The
#    verdicts below are the actual span-by-span adjudication, appended so the QQ track is
#    judged by the same stage and the same schema as the VOD track.
# ---------------------------------------------------------------------------
QQ_VERDICT_REASON = {
    'window:w000006#r0':
        '逐条比对窗口 span：问句「夜半眠兽撤退和再部署后几帧会取消睡眠啊」，答句逐字「撤退直接没，重生也是立刻，开技能后16帧出睡」。'
        'claim 的两项（撤退/再部署立即解除、开技能后第 16 帧施加睡眠）与答句一一对应，数字 16 为 span 直接给出，非推导。'
        '范围限定为夜半的眠兽这一实例，span 未主张其为所有召唤物或所有睡眠来源的通则。',
    'window:w000012#r0':
        '逐条比对窗口 span：「阻挡和索敌同帧」「部分群攻能力会被插结算」「我记得有些群攻能力，会先决定锁人／再决定锁谁／中间能插入进去」。'
        'claim 已把「部分」「有些」的限定写回正文与 subject，未把该结构说成全部群攻能力的普遍性质。'
        '「我记得」表明来源本身是回忆性陈述，这一点已写入 limitation；condition「阻挡与索敌同帧」由 span 首句直接给出。',
    'window:w000027#r0':
        '逐条比对窗口 span：三段式职责与两条具体目录均为逐字。claim 保留了 span 的「一般」与建议口吻（「最好是从…」），'
        '未把带限定的说法升格为确定结构；「targetVaildator」沿用 span 原始拼写。'
        '本条属拆包结构说明与操作路径，不是对游戏行为的主张，故 scope=instance。',
    'window:w000033#r0':
        '逐条比对窗口 span：「凯尔希抓人是"创建时间最久"」「同帧部署先打先部署的」「创建时间相同的情况下还是默认顺序，先部署先选」'
        '「同仇恨就是先部署」。四句互相印证，claim 的「以创建时间排序、相同则先部署者优先」与之一一对应，未超出。'
        '「这不是bug」是讨论者定性，未写入 claim。',
    'window:w000037#r0':
        '逐条比对窗口 span：「仇恨里面的"0.1"精度，本质上是在两边比较时，双方临时*10，转为整数，然后再比较」（同句在窗口重复一次）。'
        'claim 仅保留该机制，数字 10 与 0.1 均为 span 字面给出。'
        '复核中已把初稿合并进来、与本条互不相关的医疗索敌发言移出 claim（「医疗一般都是生命比例最低」含「一般」，'
        '且同窗口无独立规则载体），避免用「；」把两条机制并成一条。',
    'window:w000040#r0':
        '逐条比对窗口 span：「关了="有免疫"才能过判定」「本来该判定"没有麻痹免疫"的这行，写成了"并非没有麻痹免疫"」'
        '「仔细看看会发现这个配置叫"_isUnset"，即"没有这么个东西"」。claim 已收回到这些字面表述。'
        '复核中移出了初稿「_isUnset 为 true 才表示没有麻痹免疫」——span 只说配置的命名含义，'
        '并未给出 true 与「没有」的对应；「true 是没有、false 是有」仅见于评论句「程序员估计到死都没想明白为什么true是没有，false是有」，'
        '属他人评论，不作为机制依据。',
    'window:w000042#r0':
        '逐条比对窗口 span：「不看来源格，直接拿绑定的干员（就是生成他的干员）的视野范围的地块作为恐惧地块」'
        '「恐惧源是自己的情况下，没有任何恐惧地块 寻路时回落到自己地块上」「表现就是在自己地块里瞎走」。'
        'claim 三句均有对应，「视野范围」为 span 逐字。同窗口的生息羊「被打时会随机选择一个地块然后跑过去挂机」'
        '被 span 自身明确排除（「这个就不是恐惧」），未混入 claim。',
    'window:w000044#r0':
        '逐条比对窗口 span：「嘲讽就是+1000仇恨」，另有「嘲讽一直正常生效」「被干员超过了那是干员的事」为旁证。'
        'claim 仅复述该固定加值，数字 1000 为 span 字面给出，非估算。'
        '同窗口的现场异常观测（「城防炮出问题了，刁民车嘲讽出问题了，阿你怎么能这么正常呢」「只能解包看了」）未被写入 claim。'
        '注意依据是群聊中的机制陈述，不是本项目独立复算或实测的结果。',
}

qq_verdicts = []
for eid, reason in sorted(QQ_VERDICT_REASON.items()):
    qq_verdicts.append({
        'entry_id': eid,
        'status': 'supported',
        'reason': reason,
        'reviewer_type': 'agent',
        'review_basis': 'agent 依据 qq_worklist.json 的窗口 span 与已脱敏引文逐条比对；'
                        '未做人工核听、未回看原片，也未在游戏内复现。',
        'limitation': '局限：判定依据是群聊文本片段本身；片段经脱敏、丢失发言者与上下文顺序，'
                      '无法区分提问、假设与结论，也不含录播的推导过程。'
                      '官方 AI 字幕/群聊文字出现某字不等于主播或群友确实如此表述。'
                      '「all reviewed」不代表「all correct」。',
        'confidence': 'text-source-supported',
        'derived_correction': 'QQ 窗口标题改为按 span 重写的机制句',
        'derived_correction_disposition': 'applied',
        'supports': 'qq_window_span',
    })

VERDICTS.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in new_rows + qq_verdicts),
                    encoding='utf-8')

QQ_HELD_OUT.write_text(json.dumps(
    {'note': '窗口 span 无法确定机制主张、因而不得以机制句形式发布的 QQ 条目。'
             'kb_curation_build.py 仍会构建这些条目（以便审阅），由 '
             'kb_curation_evidence_apply.py 依据本文件把它们移入 curated_staging.json，'
             '并保留其待判读文本与保留理由。',
     'entry_count': len(QQ_PENDING),
     'hold_out_reason': 'QQ_NOT_SELF_CONTAINED',
     'records': [{'entry_id': eid, 'claim_from': QQ_REPAIRS.get(eid, (None,))[0]
                  or _TITLE_FALLBACK.get(eid),
                  'code': QQ_PENDING[eid][0], 'reason': QQ_PENDING[eid][1]}
                 for eid in sorted(QQ_PENDING)]},
    ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

try:
    shipped = json.loads(CURATED.read_text(encoding='utf-8'))
    shipped_qq = {e['id'] for e in shipped['entries']
                  if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])}
except FileNotFoundError:
    shipped_qq = set()
# The shipped file is expected to be at a post-partition state on a re-run, so entries
# already moved to staging are legitimately absent here. Account for them.
try:
    staged = json.loads(STAGING.read_text(encoding='utf-8'))
    staged_qq = {e['id'] for e in staged['entries']
                 if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])}
except FileNotFoundError:
    staged_qq = set()
covered = set(QQ_REPAIRS) | set(QQ_PENDING)
seen = shipped_qq | staged_qq
if seen:
    unhandled = sorted(shipped_qq - covered)
    if unhandled:
        raise SystemExit('shipped QQ entries with no re-derived claim and not pending: %s' % unhandled)
    missing = sorted(covered - seen)
    if missing:
        raise SystemExit('QQ tables name entries that ship nowhere: %s' % missing)

# The phase-2 QQ expansion appends its own entries, which are not in the hand-written tables
# above (building the tables by hand is exactly what that pipeline replaces). Accept them only
# when the loader re-verifies them against the approved manifest; anything else that ships with
# a QQ span and no table entry is still an error.
try:
    import kb_curation_qq_expansion_loader as _EXL
    _mf = json.loads(_EXL.MANIFEST.read_text(encoding='utf-8'))
except Exception:
    _EXL, _mf = None, None
if _EXL and _mf and _EXL.manifest_is_approved(_mf):
    _audit = _EXL.AUDIT
    for item in _mf['entries']:
        eid = _EXL.entry_id(item['window_id'], item['local_id'])
        if eid not in seen:
            continue
        errs = _EXL.verify_entry(item, audit=json.loads(_audit.read_text(encoding='utf-8')))
        if errs:
            raise SystemExit('qq_expansion entry %s failed loader re-verification: %s' % (eid, errs))
        covered.add(eid)
        print('qq_expansion entry accepted by loader re-verification:', eid)
elif any(i.startswith('qq_expansion:') for i in seen):
    raise SystemExit('shipped qq_expansion entries but the manifest is not approved: %s'
                     % sorted(i for i in seen if i.startswith('qq_expansion:')))

from collections import Counter
print('verdicts rewritten:', len(new_rows))
print('status:', dict(Counter(r['status'] for r in new_rows)))
print('derived_correction_disposition:', stats)
print('entries with repaired derived fields:', sum(1 for r in new_rows if r.get('repaired_fields')))
print('pending entries:', [r['entry_id'] for r in new_rows if r['status'] == 'pending'])
print('qq claim overlay:', len(qq_rows), 'entries |', sorted(qq_rows[i]['entry_id'] for i in range(len(qq_rows))))
print('qq entries held out as pending:', sorted(QQ_PENDING))
