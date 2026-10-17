# -*- coding: utf-8 -*-
"""阶段三 b3（260 窗 / 386 条 claim）全量收敛审读的产出器（纯本地，无 API）。

输入：reviews_b3/qq_wo_b3_001..260.json + workorders_b3/qq_wo_b3_001..260.json
输出：audit_decisions_b3.json（逐条裁定） + approved_manifest_b3.json（keep 条目）

DECISIONS 只列「非 keep」的条目（keep 为缺省），因此表最短、最易复核。
键 = (workorder_id, local_id)，值 = (verdict, reason_code, criterion_note)。
"""
import hashlib
import json
import os
import re
import sys

PLACEHOLDER = re.compile(r"已隐去|已隐藏|\[账号")

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEWS = os.path.join(HERE, "reviews_b3")
WORKORDERS = os.path.join(HERE, "workorders_b3")
OUT_DECISIONS = os.path.join(HERE, "audit_decisions_b3.json")
OUT_MANIFEST = os.path.join(HERE, "approved_manifest_b3.json")
# 对抗性挑刺（faultcheck）落地表：removes=撤下、fixes=按二审建议改写派生文本。
# 由 kb_trial/curation/faultcheck/_faultcheck_apply.py 生成，键为 curated 条目 id。
FAULTCHECK = os.path.join(HERE, "..", "faultcheck", "faultcheck_b3.json")

# ---------------------------------------------------------------- 判据（照抄阶段二）
CRITERIA = {
    "keep": "四项全过：自包含、无未解决争议、明确对象、有效信息",
    "reject": "四项中任一项不过",
    "pending": "证据句存在但判定量被抹掉或口径未收束——「尚未证明」不等于「不可证」，记为材料缺陷而非并入已证集",
}

# 阶段二 11 键原样保留；本轮按父指令新增 privacy_redacted_number
REJECT_REASONS = {
    "not_self_contained": "claim 把主体/对象留在窗外，原文无法独立支撑",
    "subject_unidentified": "主体在窗内未点名（只说「该干员」「龙」「这个效果」等回指）",
    "source_scope_unresolved": "适用范围在窗内未限定或被说成通用，属外推",
    "scene_specific": "单次操作/单局观察/单实例断言，缺可复用条件",
    "measurement_unresolved": "帧号、数值等测量口径（起算点、基准、单位）未给出，无法复核",
    "unresolved_dispute": "窗内仍有反对、追问或口径未收束",
    "performance_talk": "性能或实现评价、可行性建议，不是机制结论",
    "memory_uncertain": "发言者自称不确定/凭回忆，窗内未获确认",
    "conflicting_attribution": "同一现象在窗内有两种互相冲突的归属说法",
    "privacy_redacted": "关键数值被脱敏规则误抹，判定量无法复核",
    "privacy_redacted_number": "关键数值被脱敏规则抹成「[账号已隐去]」占位，原算式/判定量无法复核（本批新增，父指令项）",
    "not_mechanism": "观感、印象或玩笑话，不构成机制命题",
    "faultcheck_remove": "对抗性挑刺（faultcheck）二审 verdict=remove：重复、无独立信息量、主体不可锚定或命题未被原文支撑，复核后从本批撤下",
}

# ---------------------------------------------------------------- claim 改写表（父裁决「改写后 keep」）
# 键 = (workorder_id, local_id)；值 = 对该条 claim/subject/limitations 的覆盖。
# 用途：父复核认定 claim 的结论成立，但写法引入原文没有的词（此处是技能名），
# 故改写 claim 使其只保留原文可支持的部分，并在 limitations 注明被删去的推定。
CLAIM_OVERRIDES = {
    ("qq_wo_b3_089", "c02"): {
        "claim": "银灰的「射射射」技能（原文如此称呼，未给出技能名）在攻击动作结束后会把反隐效果挂到自己身上。",
        "subject": "银灰（「射射射」技能）",
        "condition": "该技能（原文称「射射射」）的攻击动作结束时",
        "limitations_append": [
            "父复核裁定：原 claim 与 condition 写作「真银斩」，而原文 seq75 只有「银灰那个射射射结束会把反隐给自己挂上」，"
            "「真银斩」三字在本窗未出现、系回执推定，故 claim 与 condition 均已改写为原文称呼；"
            "技能名未在原文出现，指认该技能时需回看原片或另有出处。",
        ],
    },
}

# ---------------------------------------------------------------- keep 条的裁定说明
# 缺省 keep 不带说明；本表只记需要写明裁定理由的 keep（材料修复后重审回 keep 的两条）。
# 用途：进 audit_decisions_b3.json 的 criterion_note，并经 manifest 的 audit_note 落到
# 已发布条目的 claim_derivation.audit_note。
KEEP_NOTES = {
    ("qq_wo_b3_182", "c01"):
        "材料修复后重审回 keep。首轮因 seq1 的数值区间被旧隐私规则抹成占位而移 pending"
        "（privacy_redacted_number）；材料层改为按值脱敏后，本窗 seq1 的区间已按原文逐字恢复"
        "（0.232322–0.232326），seq2 的精度自述与 seq6-7 的规律句同在窗内、逐字可回指。"
        "主体（梓兰）点名，窗内无反对、无未答追问，四项判据齐备；判定量的近似性与单位按"
        "limitations 如实标注。口径与本批既有的单方近似自测一致（(126,c01)「大概是 0.8 格/s」、"
        "(133,c01)「约 0.8/30 格」均为 keep）。",
    ("qq_wo_b3_182", "c02"):
        "材料修复后重审回 keep。首轮因 seq3 的算式被占位而移 pending；材料修复后该算式已按原文"
        "逐字恢复（10*0.0333333*3=0.999999），与 seq4 的结论句同窗可复核，四项判据齐备。"
        "原文「每格会有10^-6误差」与算式给出的 3 格累计差 1e-6 之间的口径差，按 limitations "
        "如实标注，不在 claim 内代它统一，也不据此换算单格误差。",
    # ---- 引文保真修复（父裁定 2026-09-22）：占位落在本条引文内，复原后逐条重记 ----
    ("qq_wo_b3_054", "c02"):
        "引文保真修复。父裁定批准修复已发布条目引文里的占位缺陷：seq33 的算式由旧规则抹出的占位按源复原为"
        "「30/1.08=27.77777778」（已核：复原值不是导出中的身份号）。算式逐字值与原话下一条自行写作的"
        "「27.77帧」之别已入 limitations，claim 仍照录原文的近似写法。裁定沿用父首轮裁决（claim 本体不依赖"
        "被抹算式，seq34 与 seq55/57 未被抹除），维持 keep。",
    ("qq_wo_b3_083", "c02"):
        "引文保真修复。父裁定批准修复已发布条目引文里的占位缺陷：本窗 seq26/59/69 三处小数按源复原"
        "（0.9666666666、0.0333333、0.000001；已核均非导出中的身份号）。其中 seq59「鹰角是float(0.0333333)」"
        "补入本条引文——claim 里写出的该数值此前因占位没有逐字出处。limitations 相应改写：另两处数值"
        "已可读但本条不引用，误差量级只在 seq26 的差值算式里且依赖自述估算，不据此写定量级（原「未给出"
        "误差量级」一条据此更正）。裁定沿用父首轮裁决，维持 keep。",
    ("qq_wo_b3_084", "c01"):
        "引文保真修复。父裁定批准修复已发布条目引文里的占位缺陷：seq56 的每帧扣减量由旧规则抹出的占位"
        "按源复原为「每帧仍然-0.0333333」（已核：复原值不是导出中的身份号），review.reason 与 limitations "
        "中的同一句同步复原，原「数值已被抹除、本条不引用」一条改为照录该值的如实标注。裁定沿用父首轮"
        "裁决（claim 本体不含数字，seq55/57 未被抹除），维持 keep。",
    ("qq_wo_b3_213", "c01"):
        "引文保真修复。父裁定批准修复已发布条目引文里的占位缺陷：seq8 由旧规则抹出的占位按源复原为"
        "「只有float(0.0333333)」（已核：复原值不是导出中的身份号）。review.reason 里对 seq8 的转写同步"
        "复原；limitations 由「具体数位已脱敏截断」改为记明该句逐字内容，claim 仍不写出该数值"
        "（claim 的引文仍只取 seq4-7 的正面表述）。",
}

# ---------------------------------------------------------------- 材料层修复与遗留 pending 的重审（本轮新增）
# 背景：旧隐私规则按形态把 6–12 位连续数字整体抹成「[账号已隐去]」，连带抹掉了机制常数的小数
# 尾部。材料层随后改为按值脱敏（只替换导出里真实的 QQ/UID/群号，其余数字一概保留），b4 批工单
# 即按新口径生成（20:20）；但 b3 批工单是 18:25 的冻结产物，未随该修复重建，故 w000511 的两条
# 关键消息仍带占位。本轮把这两条按修复后的渲染逻辑复原（_b3_apply_privacy_fix.py），并对 b3 全部
# 10 条 pending 逐条重读原文重判。
MATERIAL_REPAIR = {
    "applied_at": "2026-09-21",
    "script": "kb_trial/curation/qq_expansion/_b3_apply_privacy_fix.py",
    "cause": "b3 工单是 18:25 的冻结产物，早于材料层「按值脱敏」修复（b4 批工单 20:20 已按新口径"
             "生成），故 w000511 的两条关键消息仍以旧形态规则的占位交付。",
    "repaired": [{
        "workorder": "qq_wo_b3_182", "window": "w000511", "seqs": [1, 3],
        "before": ["…梓兰偏移的大致结论是0.[账号已隐去]-0.[账号已隐去]之间",
                   "弹道飞行本身就是10*0.[账号已隐去]*3=0.[账号已隐去]"],
        "after": ["…梓兰偏移的大致结论是0.232322-0.232326之间",
                  "弹道飞行本身就是10*0.0333333*3=0.999999"],
    }],
    "how": "新文本不是手写：由同窗源按 kb_curation_qq_expansion_diff.render_new（材料层修复后的"
           "渲染逻辑）现算，与写入工单的文本逐 seq 严格相等方可通过；改写只改变被误抹的数字，"
           "@ 指向与昵称的脱敏形态与冻结版逐字相同（把占位与数字统一成 # 后逐字相同）。",
    "scope": "首轮只修被重审的 w000511 一份工单。此后父裁定「已发布条目引文里的占位缺陷必须修复」，"
             "本轮再修 4 份（见 quote_fidelity_repair）。两轮合计修 5 份；材料修复后仍与修复口径"
             "不一致的工单剩 17 份（对照见 kb_curation_qq_expansion_diff_b3.py 的 delivered_text_check："
             "本轮输出 delivered_mismatches=32），其占位均落在未被任何已发布条目引用的上下文里，"
             "故不动（重建它们不会改善任何已发布条目）。",
}

# ---------------------------------------------------------------- 引文保真修复（父裁定 2026-09-22）
# 背景：w000511 先行修复后，curated_high_quality.json 中仍有 4 条已发布条目的文本带占位——占位落在
# 该条 claim 自身的 evidence 里（并因此渗进 review.reason / review_limitations），引文不再是逐字原文。
# 父裁定：批准修复，前提是复原出的数字串不得是导出里真实存在的 QQ/UID/群号；若背后是真实账号则不得
# 复原，该条改判 pending 移出精选库。本轮 6 条消息的复原值经核对均与身份号集合无交集（非账号），
# 故全部复原，无条目移出。
QUOTE_FIDELITY_REPAIR = {
    "applied_at": "2026-09-22",
    "script": "kb_trial/curation/qq_expansion/_b3_apply_quote_fidelity_fix.py",
    "cause": "b3 工单为 18:25 冻结产物，早于材料层「按值脱敏」修复。旧形态规则把 6–12 位连续数字"
             "整体抹成占位，连带抹掉了同句机制数值的小数尾部，使已发布条目的引文不再是逐字原文。",
    "account_precondition": "逐条核对：复原出的数字串与材料层身份号集合（导出里真实 QQ/UID/群号）"
                            "无交集，且复原后工单内占位归零；因此不存在「占位背后是真实账号」的情形，"
                            "无需按父裁定的兜底条款把任何条目改判 pending。",
    "repaired": [
        {"workorder": "qq_wo_b3_054", "window": "w000677", "affected_entry": "w000677:c02",
         "seqs": [33], "before": ["30/1.08=27.[账号已隐去]"], "after": ["30/1.08=27.77777778"]},
        {"workorder": "qq_wo_b3_083", "window": "w000208", "affected_entry": "w000208:c02",
         "seqs": [26, 59, 69],
         "before": ["0.9667-0.[账号已隐去]=3.33334e-05", "鹰角是float(0.[账号已隐去])",
                    "最小距离判定是根号0.[账号已隐去]"],
         "after": ["0.9667-0.9666666666=3.33334e-05", "鹰角是float(0.0333333)",
                   "最小距离判定是根号0.000001"]},
        {"workorder": "qq_wo_b3_084", "window": "w000211", "affected_entry": "w000211:c01",
         "seqs": [56], "before": ["每帧仍然-0.[账号已隐去]"], "after": ["每帧仍然-0.0333333"]},
        {"workorder": "qq_wo_b3_213", "window": "w001321", "affected_entry": "w001321:c01",
         "seqs": [8], "before": ["只有float(0.[账号已隐去])"], "after": ["只有float(0.0333333)"]},
    ],
    "entry_level_changes": {
        "w000677:c02": "引文 seq33 复原为 30/1.08=27.77777778；limitations 记明算式逐字值与原话自行写作的"
                       "「27.77帧」（seq34）之别，claim 仍照录原文自己的近似写法。",
        "w000208:c02": "新增引文 seq59「鹰角是float(0.0333333)」——claim 里写出的该数值此前因占位没有逐字"
                       "出处；limitations 改写为：另两处数值（seq26/seq69）已可读但本条不引用，误差量级只在 "
                       "seq26 的差值算式里且依赖自述估算，不据此写定量级。",
        "w000211:c01": "引文 seq56 复原为「每帧仍然-0.0333333」；review.reason 与 limitations 中的同一句"
                       "同步复原，原「数值已被抹除、本条不引用」一条改写为照录该值的如实标注。",
        "w001321:c01": "review.reason 里对 seq8 的转写复原为「只有float(0.0333333)」；limitations 由"
                       "「数值已脱敏截断」改为记明该句逐字内容，claim 仍不写出该数值。",
    },
    "excluded_narrative_sync": "同窗 excluded[] 里因「数值被抹除、无法判读」而写的叙述已同步为材料事实"
                               "（qq_wo_b3_083 的两条：最小距离判定、0.9667 差值算式；qq_wo_b3_213 的半径"
                               "一组；qq_wo_b3_084 的 review_note），**未改动任何 verdict**——其中"
                               "qq_wo_b3_083 的「最小距离判定为根号 0.000001」一项，原 reject 依据"
                               "（数值被抹除、原文含量失）因修复而失效，是否改判属 excluded 裁量，"
                               "留待父决定。",
    "how": "新文本不是手写：由同窗源按 kb_curation_qq_expansion_diff.render_new 现算，与写入工单的文本"
           "逐 seq 严格相等方可通过；改写只改变被误抹的数字（占位与数字统一为 # 后逐字相同），"
           "@ 指向与昵称的脱敏形态与冻结版逐字相同；工单原为 CRLF，按字节替换、行尾不变。",
    "scope": "本轮只修这 4 份工单（6 条消息）。其余 17 份仍与修复口径不一致的工单，其占位不在任何"
             "已发布条目的引文内，故不动。",
}

REAUDIT = {
    "audited_at": "2026-09-21",
    "trigger": "材料层「按值脱敏」修复落地后，对 b3 全部 10 条 pending 回读修复后的工单原文"
               "（原序、含 speaker_id 与 time）按同一套四项判据重判。",
    "reviewed": 10,
    "changed_to_keep": 2,
    "changed_to_reject": 0,
    "still_pending": 8,
    "items": [
        {"workorder": "qq_wo_b3_092", "local_id": "c01", "window": "w000340",
         "first_round_reason": "unresolved_dispute", "verdict_after": "pending",
         "basis": "本窗无占位，材料修复与之无关。原文「看起来像是转身丢失事件帧」的假说语气在窗内"
                  "未获第二方确认、未实测复核，父已裁决维持 pending。"},
        {"workorder": "qq_wo_b3_099", "local_id": "c01", "window": "w000492",
         "first_round_reason": "unresolved_dispute", "verdict_after": "pending",
         "basis": "本窗占位仅出现在 seq16（日报块）且未被任何 claim 引用。否定式命题的正面对照"
                  "（135/155）在窗内未闭合，维持 pending。"},
        {"workorder": "qq_wo_b3_140", "local_id": "c01", "window": "w001766",
         "first_round_reason": "measurement_unresolved", "verdict_after": "pending",
         "basis": "本窗无占位。claim 的「大范围」无具体值，且「九格」与「周围8格」在窗内并列为"
                  "同一范围的两种叫法、未统一，测量口径未闭合，与材料修复无因果。"},
        {"workorder": "qq_wo_b3_182", "local_id": "c01", "window": "w000511",
         "first_round_reason": "privacy_redacted_number", "verdict_after": "keep",
         "basis": "材料修复后 seq1 的数值区间按原文逐字恢复，判定量可在同窗 raw_messages 内复核；"
                  "主体点名、无未闭合争议、有效信息齐备，故回 keep。近似性与单位入 limitations。"},
        {"workorder": "qq_wo_b3_182", "local_id": "c02", "window": "w000511",
         "first_round_reason": "privacy_redacted_number", "verdict_after": "keep",
         "basis": "材料修复后 seq3 的算式按原文逐字恢复（10*0.0333333*3=0.999999），与 seq4 的"
                  "结论句同窗可复核，故回 keep；「每格」与 3 格累计的口径差入 limitations。"},
        {"workorder": "qq_wo_b3_189", "local_id": "c03", "window": "w000595",
         "first_round_reason": "subject_unidentified", "verdict_after": "pending",
         "basis": "本窗无占位。「触发2天赋」未点名干员，帧值（51/52）来自单方盯帧，主体仍未点名，"
                  "维持 pending。"},
        {"workorder": "qq_wo_b3_228", "local_id": "c03", "window": "w001677",
         "first_round_reason": "subject_unidentified", "verdict_after": "pending",
         "basis": "本窗无占位。机制句（seq24-26「溅射不对空/余震对空」）内未点名干员，名号需由"
                  "seq7「迷迭香三技能对空」推定。本轮不动：若要收，属「改写后 keep」类的父裁项"
                  "（比照 (089,c02) 先例），与材料修复无因果。"},
        {"workorder": "qq_wo_b3_241", "local_id": "c01", "window": "w001961",
         "first_round_reason": "unresolved_dispute", "verdict_after": "pending",
         "basis": "本窗无占位。「重力取决于寻路状态」主语未在原文出现，互斥判断以「应该也是」"
                  "语气给出，窗内另有「应该不能吧」未收束，维持 pending。"},
        {"workorder": "qq_wo_b3_243", "local_id": "c01", "window": "w001991",
         "first_round_reason": "subject_unidentified", "verdict_after": "pending",
         "basis": "本窗无占位。「激光」未说明是哪一关/哪一单位的机制，且窗末 seq8「也或许可以把」"
                  "反转了原口径，维持 pending。"},
        {"workorder": "qq_wo_b3_249", "local_id": "c01", "window": "w000076",
         "first_round_reason": "subject_unidentified", "verdict_after": "pending",
         "basis": "本窗无占位。该单位只以「她」指代，「14章的」不足以唯一定位，主体仍未点名，"
                  "维持 pending。"},
    ],
}

# ---------------------------------------------------------------- 非 keep 覆盖表
DECISIONS = {
    # ===== 隐私占位数字（父指令 (a)：直接移 pending，标 privacy_redacted_number）=====
    # 本表为「只列非 keep」的缺省表，故以下各条不列在此即为 keep：
    #   ("qq_wo_b3_054","c02")、("qq_wo_b3_084","c01") —— claim 本体不依赖被抹算式，
    #   且支持该 claim 的 seq34/seq55+57 未被抹除；父裁决：回 keep。两条引文里的占位已在
    #   引文保真修复中按源复原（父裁定 2026-09-22，见 QUOTE_FIDELITY_REPAIR / KEEP_NOTES）。
    #   ("qq_wo_b3_083","c02")、("qq_wo_b3_213","c01") —— 同样因引文含占位而进入本轮保真修复，
    #   复原后仍为 keep（前者新收 seq59 作为 claim 数值的逐字出处）。
    #   ("qq_wo_b3_089","c02") —— 父裁决：改写后 keep，见 CLAIM_OVERRIDES。
    #   ("qq_wo_b3_182","c01")、("qq_wo_b3_182","c02") —— 首轮同因 privacy_redacted_number 移
    #   pending（父指令项 (a)），父复核后仍 pending（父裁决 2026-09-21 记「父裁决后仍为
    #   privacy_redacted_number 的只剩 w000511 的 c01/c02」）。本轮材料层修复重审：w000511 的
    #   seq1/seq3 已按修复后的渲染逻辑逐字复原（见 _b3_apply_privacy_fix.py），判定量可复核，
    #   故两条按同一套四项判据回 keep，重审理由见 KEEP_NOTES。

    # ===== 未闭合争议（窗内问答未收束）=====
    ("qq_wo_b3_001", "c01"): ("reject", "unresolved_dispute",
        "窗内以「也有点道理」「好像又对了」这类来回收尾，未给出可复用判据，争议未闭合。"),
    ("qq_wo_b3_006", "c03"): ("reject", "unresolved_dispute",
        "同一窗内对「基础 buff 覆盖」的边界仍有追问未见收束；claim 把「10点、3秒、+3」三个数并列写死，而原文该处是举例列举，非定义式。"),
    ("qq_wo_b3_010", "c02"): ("reject", "measurement_unresolved",
        "claim 依赖「2.75 帧」这一等效值，原文未给出该值的起算点与基准，无法复核。"),
    ("qq_wo_b3_012", "c03"): ("reject", "unresolved_dispute",
        "「事件帧丢失」的判定链路在窗内仍有追问未答，且原文用「估计」类措辞，未收束。"),
    ("qq_wo_b3_012", "c04"): ("reject", "performance_talk",
        "「靠猜很不可靠、不能靠猜」是对方法可靠性的评价，非机制命题。"),
    ("qq_wo_b3_013", "c02"): ("reject", "measurement_unresolved",
        "「开技能时的可选性判定」「不是同帧」在原窗未给出判定口径（在哪个环节、依据什么），无法复核。"),
    ("qq_wo_b3_018", "c04"): ("reject", "unresolved_dispute",
        "「无法排除」的表述本身即未闭合，窗内无收束。"),
    ("qq_wo_b3_019", "c01"): ("reject", "measurement_unresolved",
        "「6 帧（对应 0.2 秒）」的换算基准原文未给，且该窗讨论的是「表现」而非机制口径。"),
    ("qq_wo_b3_024", "c02"): ("reject", "memory_uncertain",
        "原文以「我记得」引出并自带不确定限定，窗内未获确认。"),
    ("qq_wo_b3_034", "c01"): ("reject", "unresolved_dispute",
        "窗内对该说法有正面质疑且未收束，claim 只取一半口径。"),
    ("qq_wo_b3_037", "c01"): ("reject", "unresolved_dispute",
        "窗内对「该字段是否为飞行判定的唯一来源」仍有追问未答。"),
    ("qq_wo_b3_041", "c01"): ("reject", "unresolved_dispute",
        "limits 自述「本窗未给出 changableMotionMode 的取值枚举」，且窗内另一人对同一对象给出不同归属，两说并存未裁决；另 limitations 存在重复行（「未核听原片、未做游戏内实测」两次），属回执质量问题，一并记录。"),
    ("qq_wo_b3_050", "c01"): ("reject", "not_self_contained",
        "claim 依赖窗外/未出示的图与表，脱离上下文不可复述。"),
    ("qq_wo_b3_062", "c01"): ("reject", "unresolved_dispute",
        "父复核项备选。原文 seq60 是「寻路和传送可以一起，阻挡偏移不行」的并列句，claim 只取肯定半句；同窗对被取半句的否定项（阻挡偏移能否与失衡移动一起）在 seq64/66/67 各执一词、以 seq68「切」收尾，争议未闭合，且「一起」的确切含义（是否可以同时施加）原文未定义。"),
    ("qq_wo_b3_063", "c01"): ("reject", "performance_talk",
        "对实现优劣的评价，非机制命题。"),
    ("qq_wo_b3_070", "c01"): ("reject", "scene_specific",
        "单次对局内的观察，缺可复用条件。"),
    # ("qq_wo_b3_089","c02") 父裁决为「改写后 keep」，故从本表移出；改写见 CLAIM_OVERRIDES。
    ("qq_wo_b3_092", "c01"): ("pending", "unresolved_dispute",
        "父复核项。原文自述措辞为「看起来像是」，属假说语气；本回执已在 limitations 如实标注「属假说而非已验证结论」，但该假说在窗内未获第二方确认、未实测复核。按「未闭合争议不收」，移 pending 而非 keep。"),
    ("qq_wo_b3_099", "c01"): ("pending", "unresolved_dispute",
        "父复核项备选。claim 是否定式命题（「不应呈严格稳定的两档帧数」），且同窗被引的 135/155 数值另标 pending、转述者自述「没研究没有发言权」；否定命题所依据的正面对照未闭合。"),
    ("qq_wo_b3_103", "c02"): ("reject", "source_scope_unresolved",
        "「某个扣减一半的藏品」在原文未点名，「之前／之后生效」的判定基准未给，适用范围外推。"),
    ("qq_wo_b3_107", "c01"): ("reject", "source_scope_unresolved",
        "「运行就没有值」「从代码反解不如实测」是对方法论的外推式断言，未给出适用边界。"),
    ("qq_wo_b3_110", "c02"): ("reject", "unresolved_dispute",
        "「先后顺序不固定、由创建顺序决定」在窗内未给出可复核的判据与实例。"),
    ("qq_wo_b3_118", "c02"): ("reject", "memory_uncertain",
        "claim 自带「很可能」这一推测限定，窗内未获确认。"),
    ("qq_wo_b3_123", "c01"): ("reject", "not_self_contained",
        "claim 只有「会不同」这一比较式结论，未写出不同之处；脱离原文不可复述。"),
    ("qq_wo_b3_137", "c01"): ("reject", "performance_talk",
        "「口述对齐位置有理解歧义、一般不会出问题」是对传达方式与容错的评价，非机制命题。"),
    ("qq_wo_b3_137", "c02"): ("reject", "source_scope_unresolved",
        "「一般而论」的分辨能力比较是程度判断，未给出量化的判定口径。"),
    ("qq_wo_b3_140", "c01"): ("pending", "measurement_unresolved",
        "「大范围」的具体范围值原文未给；「九格」与「周围8格」原文对同一范围有两种叫法未统一，判定量不可复核。"),
    ("qq_wo_b3_140", "c02"): ("reject", "scene_specific",
        "claim 描述的是单次逐帧观察（「最后一次判定范围内只有熊哥」），缺可复用条件。"),
    ("qq_wo_b3_146", "c01"): ("reject", "subject_unidentified",
        "被描述的单位在窗内始终以「他」出现，没有名字或可回指对象，主体不可确指。"),
    ("qq_wo_b3_154", "c01"): ("reject", "subject_unidentified",
        "原文只写「火陈龙」这一简称，未给出单位全名；claim 未能唯一确指该单位。"),
    ("qq_wo_b3_161", "c01"): ("reject", "performance_talk",
        "「应尽可能不用有前摇、弹道的干员」是操作建议，不是机制结论。"),
    ("qq_wo_b3_163", "c01"): ("reject", "source_scope_unresolved",
        "「其余都可以」是排他式表述，原文未穷举可落点类型（下水、天上只在反问中出现未确认），适用面外推。"),
    ("qq_wo_b3_169", "c01"): ("reject", "not_self_contained",
        "原文举例「0.8 移速的单位在 8 坐标出生往里走」而 claim 未带该条件，「这里」无指代对象，脱离原文不可复述。"),
    ("qq_wo_b3_178", "c01"): ("reject", "source_scope_unresolved",
        "claim 把「前摇=索敌抬手到出伤帧、后摇=出伤到待机动画帧」写成前后摇的定义，而原文该句是对具体提问给出的口径；「前摇是播放值」与端点定义在窗内未合成单一框架，适用边界未收束。"),
    ("qq_wo_b3_187", "c01"): ("reject", "subject_unidentified",
        "「该干员」在原文全程以代词出现，本窗未给出姓名或代号，主体靠窗卡确定，窗内不可自证。"),
    ("qq_wo_b3_187", "c02"): ("reject", "subject_unidentified",
        "同上，主体在窗内未点名。"),
    ("qq_wo_b3_187", "c03"): ("reject", "subject_unidentified",
        "同上，主体在窗内未点名。"),
    ("qq_wo_b3_189", "c03"): ("pending", "subject_unidentified",
        "原文以「触发2天赋」指代某干员的第二天赋，本窗未出现该干员姓名；同时 limits 自述「该帧值来自一个人盯帧，窗内无第二方复核」。"),
    ("qq_wo_b3_190", "c01"): ("reject", "subject_unidentified",
        "claim 只写「同帧触发时」，被提问的机制名（原文写作「第」、窗卡作「罗门」）未在 claim 内点名，主体不可确指。"),
    ("qq_wo_b3_201", "c02"): ("reject", "not_self_contained",
        "claim 以「多出来的时间」起头，该量由 c01 的「至少 6 秒 1 帧」定义而 claim 未带；且原文以「可以是」列出四项，非穷举，claim 写作「具体包含」属外推。"),
    ("qq_wo_b3_206", "c01"): ("reject", "unresolved_dispute",
        "claim 自述「但具体调用什么参数尚不确定」，并引原文「这不确定」「他用什么不清楚」，自身即未闭合。"),
    ("qq_wo_b3_207", "c02"): ("reject", "source_scope_unresolved",
        "该组合数是还原计算器的手动枚举，claim 的「6 种情况」原文属举例（以「就有」引出）未穷举，不适合作通用规则。"),
    ("qq_wo_b3_208", "c02"): ("reject", "unresolved_dispute",
        "claim 自述同窗 seq7/8「但是可能有点问题／还在改」，该判定仍在调整、在窗内未收束。"),
    ("qq_wo_b3_209", "c01"): ("reject", "measurement_unresolved",
        "「3s1z」是原文写法（z 未定义），「技力回复和费用回复有问题」未给出具体偏差量，判定量无法复核。"),
    ("qq_wo_b3_210", "c01"): ("reject", "subject_unidentified",
        "该「传送类机制」的具体名称与所属技能在本窗未点名，claim 只能写「该（传送类）机制」。"),
    ("qq_wo_b3_211", "c01"): ("reject", "subject_unidentified",
        "claim 全部以「那个」「橙子」「到处飞的那个」等指示语写成，对应到具体游戏实体的名称在本窗不可确指。"),
    ("qq_wo_b3_215", "c01"): ("reject", "not_self_contained",
        "claim 只有「索敌与出伤是两个独立环节」一句，未给出分立判据；原文该句承载于「你的条件得改」的对话依赖之上，脱离原文不可复述。"),
    ("qq_wo_b3_216", "c01"): ("reject", "performance_talk",
        "「组合关系」的陈述服务于「也是一个很合理的永控吧」这一玩法强度评价，非机制命题。"),
    ("qq_wo_b3_217", "c01"): ("reject", "not_self_contained",
        "claim 保留「不受（该）时间的影响」中的指示语「这个时间」而不代填，脱离原文无指代对象。"),
    ("qq_wo_b3_217", "c02"): ("reject", "not_self_contained",
        "claim 保留「喊人（警报）」「这个事件被放在最后」两处窗外/未定义指代，脱离原文不可复述。"),
    ("qq_wo_b3_220", "c01"): ("reject", "not_self_contained",
        "「人造高台」在原文未定义，且 claim 只有一句定性，未给出与正常高台的构造差异，不可独立复述。"),
    ("qq_wo_b3_222", "c01"): ("reject", "not_self_contained",
        "「该浮空碰撞」在窗内没有更明确的所指（回执自述「原文未说明浮空碰撞指哪个单位/场景的碰撞体」）。"),
    ("qq_wo_b3_222", "c02"): ("reject", "not_self_contained",
        "「单纯的距离问题」未给出具体距离量或阈值，且窗内同时提出「相切判定？」的追问，claim 的指代不可独立成立。"),
    ("qq_wo_b3_228", "c02"): ("reject", "scene_specific",
        "claim 描述的是对某一具体实例（大象被山海车传送）的路径分支推演，缺可复用条件。"),
    ("qq_wo_b3_228", "c03"): ("pending", "subject_unidentified",
        "原文机制句内未直接点名干员名（须由 seq7「迷迭香三技能对空」推定），claim 以匿名指代写成。"),
    ("qq_wo_b3_236", "c01"): ("reject", "not_self_contained",
        "「该技能」未在机制句中出现（仅由窗内上下文指明），且 claim 含原文自述「没有什么用」的无关判定。"),
    ("qq_wo_b3_236", "c02"): ("reject", "not_self_contained",
        "主体（哪一位 Boss、哪一技能）在 claim 内未点名；「1.5」的单位与含义原文未写明。"),
    ("qq_wo_b3_241", "c01"): ("pending", "unresolved_dispute",
        "claim 含两个并列命题（失衡/寻路互斥；重力取决于寻路状态），原文用「应该也是互斥的」这一非断言语气，且「重力取决于寻路状态」主语未在原文出现。"),
    ("qq_wo_b3_243", "c01"): ("pending", "subject_unidentified",
        "「激光」是哪一关/哪一单位的机制原文未说明，且同窗末句「也或许可以把」反转了口径，未闭合。"),
    ("qq_wo_b3_245", "c01"): ("reject", "memory_uncertain",
        "原文以「吧」结尾属估断，同窗 seq24「最好还是测一测」表明未实测。"),
    ("qq_wo_b3_249", "c01"): ("pending", "subject_unidentified",
        "该单位原文未点名（只以「她」指代），「14章的」不足以唯一定位到具体关卡与单位。"),
    ("qq_wo_b3_250", "c01"): ("reject", "subject_unidentified",
        "claim 自述「技能三未点名是哪位干员的技能三」「seq1 的『他』原文未知是谁」，主体不可确指。"),
    ("qq_wo_b3_253", "c01"): ("reject", "performance_talk",
        "「测精细偏移可以用寻路三点画圆」是测量手段建议，非机制结论。"),
    ("qq_wo_b3_257", "c01"): ("reject", "measurement_unresolved",
        "「造伤前的附属事件改不掉倍率」这一推论由提问方在 seq17/19 提出并以「快照」收束，属对实现机制的推测，原文未给出可复核的判定口径。"),
    ("qq_wo_b3_258", "c01"): ("reject", "not_self_contained",
        "「动伤buff」的伤害来源在原文未点名（原文以「因为伤害的基础值是移动距离啊」承接前文），claim 的指代不可独立成立。"),
    ("qq_wo_b3_259", "c01"): ("reject", "measurement_unresolved",
        "「9.9 秒」「时间上限 10」的起算点原文未说明，且「第 34 发」与 seq3「33.3333」是否同一发未明确。"),
    ("qq_wo_b3_259", "c02"): ("reject", "not_self_contained",
        "claim 全文只有「取整是算法」四字，「取整」取在哪一步、针对什么对象均未给出，不可独立复述。"),
    ("qq_wo_b3_260", "c01"): ("reject", "not_self_contained",
        "「防御升序的仇恨精度 0.001」在原文是问答中的一句确认，claim 未给出该精度作用的量（什么值被截断到 0.001），判定口径不可复核。"),
    ("qq_wo_b3_260", "c02"): ("reject", "measurement_unresolved",
        "claim 自述「各算式中 9、16、33、32、300、150 等常数的来源未在本窗给出，原文未定义」，判定量不可复核。"),
    ("qq_wo_b3_260", "c03"): ("reject", "measurement_unresolved",
        "「第一发 3+／6-」的反推依赖 c02 那组来源不明的常数，且其上游「多的帧数只能是3-6之间」本身未闭合。"),
}

# ---------------------------------------------------------------- 逐条裁定
def load_all():
    claims, excluded = [], []
    for i in range(1, 261):
        wid = "qq_wo_b3_%03d" % i
        with open(os.path.join(REVIEWS, wid + ".json"), encoding="utf-8") as fh:
            rv = json.load(fh)
        with open(os.path.join(WORKORDERS, wid + ".json"), encoding="utf-8") as fh:
            wo = json.load(fh)
        for c in rv.get("claims", []):
            claims.append((wid, rv, wo, c))
        for e in rv.get("excluded", []):
            excluded.append((wid, rv, e))
    return claims, excluded


def merged_result_entry_count(batch_entry_count, label):
    """本轮追加进 curated_high_quality.json 之后的发布条目总数（现算，不写死）。

    取发布文件里「非本批」的条目数（本批条目以 manifest 路径标识），扣掉其中本轮被
    faultcheck 移除的、再加本批当前的 keep 数：两边时点同值（并批前后 others 不变）。
    """
    path = os.path.abspath(os.path.join(HERE, "..", "..", "curated_high_quality.json"))
    try:
        data = json.load(open(path, encoding="utf-8"))
    except OSError:
        return batch_entry_count
    removed = faultcheck_remove_ids()
    others = sum(1 for e in data["entries"]
                 if ((e.get("origin") or {}).get("trial_manifest_outputs") != label
                     and e["id"] not in removed))
    return others + batch_entry_count


def faultcheck_remove_ids():
    """本轮 faultcheck 的移除 id（qq 三批读 faultcheck_*.json，录播轨读 decisions.jsonl 的 reject 标记）。"""
    ids = set()
    for name in ("faultcheck_phase2.json", "faultcheck_b3.json", "faultcheck_b4.json"):
        path = os.path.join(HERE, "..", "faultcheck", name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                ids |= set((json.load(fh).get("removes") or {}))
    dec = os.path.join(HERE, "..", "decisions.jsonl")
    if os.path.exists(dec):
        with open(dec, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("audit_kind") == "faultcheck_remove":
                    ids.add("%s#r%s" % (row["doc_id"], row["rule_idx"]))
    return ids


def load_faultcheck():
    """读 faultcheck 落地表，键换成 (window_id, local_id)（条目 id 为 qq_expansion:<window>:<local>）。

    一个窗口可能有多条（w000509 一次撤 5 条），故键必须带 local_id。
    """
    removes, fixes, meta = {}, {}, {}
    if not os.path.exists(FAULTCHECK):
        return removes, fixes, meta
    with open(FAULTCHECK, encoding="utf-8") as fh:
        d = json.load(fh)
    meta = {k: d.get(k) for k in ("applied_at", "counts", "policy", "source", "script")}
    for eid, spec in (d.get("removes") or {}).items():
        _, win, lid = eid.split(":", 2)
        removes[(win, lid)] = dict(spec, local_id=lid)
    for eid, spec in (d.get("fixes") or {}).items():
        _, win, lid = eid.split(":", 2)
        fixes[(win, lid)] = dict(spec, local_id=lid)
    return removes, fixes, meta


def build():
    claims, excluded = load_all()
    raw_by_wo = {}
    for i in range(1, 261):
        wid = "qq_wo_b3_%03d" % i
        with open(os.path.join(WORKORDERS, wid + ".json"), encoding="utf-8") as fh:
            raw_by_wo[wid] = json.load(fh)
    as_of = {w: raw_by_wo[w]["window"]["as_of"] for w in raw_by_wo}
    review_model = {}
    for c in claims:
        review_model.setdefault(c[0], c[1].get("reviewer_model"))

    # ---- 隐私占位普查：工单 raw_messages 中被抹成占位的消息，以及它们是否落在某条 claim 的 evidence 内
    ev_by_wo = {}
    for wid, rv, wo, c in claims:
        ev_by_wo.setdefault(wid, set()).update(e["seq"] for e in c["evidence"])
    privacy_census = []
    for wid in sorted(raw_by_wo):
        hit = [m["seq"] for m in raw_by_wo[wid]["raw_messages"]["messages"]
               if PLACEHOLDER.search(m["text"])]
        if not hit:
            continue
        insc = sorted(set(hit) & ev_by_wo.get(wid, set()))
        privacy_census.append({
            "workorder": wid,
            "window": raw_by_wo[wid]["window"]["window_id"],
            "placeholder_seqs": hit,
            "in_claim_evidence_seqs": insc,
            "action": "claim 移 pending（privacy_redacted_number）" if insc else "占位仅出现在未裁定的上下文里，不进入收敛",
        })

    decisions, entries = [], []
    counts = {"keep": 0, "reject": 0, "pending": 0}

    # ---- 对抗性挑刺（faultcheck）落地：先把条目 id 换成 (workorder_id, local_id)
    fc_rm_raw, fc_fix_raw, fc_meta = load_faultcheck()
    wo_to_win = {wid: raw_by_wo[wid]["window"]["window_id"] for wid in raw_by_wo}
    win_to_wo = {win: wid for wid, win in wo_to_win.items()}
    fc_remove, fc_fix = {}, {}
    for (win, lid), spec in fc_rm_raw.items():
        fc_remove[(win_to_wo[win], lid)] = spec
    for (win, lid), spec in fc_fix_raw.items():
        fc_fix[(win_to_wo[win], lid)] = spec
    fc_removed = []

    for wid, rv, wo, c in claims:
        key = (wid, c["local_id"])
        verdict, reason_code, note = DECISIONS.get(key, ("keep", None, None))
        ov = CLAIM_OVERRIDES.get(key)
        fc = fc_fix.get(key)
        fcr = fc_remove.get(key)
        if fcr is not None:
            # 二审 verdict=remove：从本批撤下（不再进 manifest），裁定留在 audit
            verdict, reason_code = "reject", "faultcheck_remove"
            note = "对抗性挑刺二审 remove（%s）：%s" % (fcr.get("fault_type", ""), fcr.get("reason", ""))
            fc_removed.append({"window": rv["window_id"], "workorder": wid,
                               "local_id": c["local_id"], "fault_type": fcr.get("fault_type", ""),
                               "reason": fcr.get("reason", ""), "source": fcr.get("source", "")})
        claim_text = ((fc or {}).get("claim") or (ov or {}).get("claim") or c["claim"])
        subject_text = ((fc or {}).get("subject") or (ov or {}).get("subject") or c["subject"])
        condition_text = ((fc or {}).get("condition") or (ov or {}).get("condition") or c["condition"])
        corrected = ov is not None or fc is not None
        counts[verdict] += 1
        d = {
            "workorder": wid,
            "window": rv["window_id"],
            "local_id": c["local_id"],
            "kind": "claim",
            "verdict": verdict,
        }
        if verdict == "keep":
            d["claim"] = claim_text
            d["scope"] = c["scope"]
            if ov is not None:
                d["criterion_note"] = (
                    "%s；父复核裁决：改写后 keep——原 claim 写作「真银斩」，原文 seq75 未出现该三字，"
                    "已改写为原文称呼「射射射」。%s" % (c["reason"], note or ""))
            elif fc is not None:
                d["criterion_note"] = (
                    "%s；对抗性挑刺修复（%s）：%s" % (c["reason"], fc.get("fault_type", ""),
                                                 fc.get("note") or fc.get("suggestion", "")))
            else:
                d["criterion_note"] = KEEP_NOTES.get(key)
        else:
            d["reason_code"] = reason_code
            d["reason"] = REJECT_REASONS[reason_code]
            d["claim"] = claim_text
            d["scope"] = c["scope"]
            d["criterion_note"] = note
        if corrected:
            d["claim_corrected_by_audit"] = True
            d["claim_original"] = c["claim"]
        if fc is not None:
            d["claim_repaired_by_faultcheck"] = {
                "fault_type": fc.get("fault_type", ""), "suggestion": fc.get("suggestion", ""),
                "note": fc.get("note", ""), "source": fc.get("source", ""),
            }
        decisions.append(d)

        if verdict != "keep":
            continue

        msgs = {m["seq"]: m for m in wo["raw_messages"]["messages"]}
        ev = []
        for item in c["evidence"]:
            m = msgs.get(item["seq"])
            if m is None:
                raise SystemExit("seq %s 不在 %s 的 raw_messages" % (item["seq"], wid))
            if m["text"] != item["text"]:
                raise SystemExit("evidence 文本与 raw_messages 不一致：%s seq%s" % (wid, item["seq"]))
            ev.append({
                "seq": item["seq"],
                "speaker_id": m.get("speaker_id"),
                "time": m.get("time"),
                "text": item["text"],
            })
        # 与 kb_curation_qq_expansion_loader.verify_entry 的公式一致（阶段二 manifest 同式）：
        # 对 evidence 各条 {seq,speaker_id,time,text} 的 json.dumps(..., ensure_ascii=False,
        # sort_keys=True)（默认分隔符）取 sha256。注意与阶段二不同式会在此被 loader 拒绝。
        payload = json.dumps(
            [{"seq": e["seq"], "speaker_id": e["speaker_id"],
              "time": e["time"], "text": e["text"]} for e in ev],
            ensure_ascii=False, sort_keys=True,
        )
        lims = list(c.get("limitations", []))
        if ov is not None:
            lims = lims + list(ov.get("limitations_append", []))
        if fc is not None:
            lims = lims + ["对抗性挑刺（faultcheck）修复（%s）：%s"
                           % (fc.get("fault_type", ""), fc.get("note") or fc.get("suggestion", ""))]
        entries.append({
            "workorder_id": wid,
            "window_id": rv["window_id"],
            "local_id": c["local_id"],
            "claim": claim_text,
            "subject": subject_text,
            "condition": condition_text,
            "scope": c["scope"],
            "category": c["category"],
            "as_of": as_of[wid],
            "evidence": ev,
            "evidence_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "reviewer_model": rv.get("reviewer_model"),
            "review_reason": c["reason"],
            "review_limitations": lims,
            "audit_note": d["criterion_note"],
            "claim_corrected_by_audit": corrected,
            "claim_original": c["claim"] if corrected else None,
        })

    kept_wo = []
    for e in entries:
        if e["workorder_id"] not in kept_wo:
            kept_wo.append(e["workorder_id"])

    audit = {
        "note": "阶段三 b3 批（260 窗 / 386 条 claim）的逐条收敛审读裁定。本批候选为 reviews_b3 的 claims[]，逐条回读同窗 workorders_b3 的 raw_messages 核实 evidence 的 seq 与原文逐字一致，再按阶段二同一套四项判据裁定 keep/reject/pending。本批 excluded[]（806 条）不进入收敛，亦不据此反向支持任何 claim。evidence 逐字校验为 0 处不一致（386 条 claim 的全部 evidence 均与 raw_messages 逐字相同）。父已对首轮 5+1 条存疑作出裁决，本文件已按裁决收敛：qq_wo_b3_054/c02、qq_wo_b3_084/c01 回 keep，qq_wo_b3_089/c02 改写后 keep（claim 去掉原文未出现的「真银斩」），qq_wo_b3_092/c01、qq_wo_b3_099/c01 维持 pending，qq_wo_b3_062/c01 维持 reject。**本轮（材料层修复后重审）**：w000511 的两条关键消息按修复后的口径复原（见 material_repair），b3 全部 10 条 pending 逐条重读原文重判（见 privacy_fix_reaudit），其中 w000511 的 c01/c02 回 keep，其余 8 条维持 pending；本批 keep 由 317 变为 319。**本轮（引文保真修复，父裁定 2026-09-22）**：curated_high_quality.json 中另有 4 条已发布条目的引文/派生文本带占位（w000677:c02、w000208:c02、w000211:c01、w001321:c01），已按源复原被误抹的 6 条消息（见 quote_fidelity_repair）；复原值经核对均非导出中的身份号，故无条目移出精选库，本批 keep 仍为 319。本文件不动 curated_high_quality.json，追加由 kb_curation_qq_expansion_loader b3 路径执行。**本轮（对抗性挑刺 faultcheck）**：二审对已发布条目逐条挑刺，本批 7 条 verdict=remove 已撤下（不再进 manifest）、55 条 verdict=fix 已按建议改写 claim/subject/condition（引文一字未动），本批 keep 由 319 变为 %d（见 faultcheck 块）。" % len(entries),
        "inputs": {
            "workorders": "kb_trial/curation/qq_expansion/workorders_b3/qq_wo_b3_001..260.json",
            "final_reviews": "kb_trial/curation/qq_expansion/reviews_b3/qq_wo_b3_001..260.json",
            "final_reviews_count": 260,
        },
        "audit_method": "以 reviews_b3 的 claims[] 为候选（共 386 条，全部 100% 有裁定），逐窗回读同窗 raw_messages（全文、原序、含 speaker_id 与 time），逐字校验 evidence；对 claim 中引用的数值、代码标识符、专名再回原文核对。privacy_redacted_number 为本批新增 reason：工单里被隐私脚本抹成「0.[账号已隐去]」一类占位的窗口，凡该占位出现在被判 claim 自身的 evidence 文本内，一律移 pending 并标此 reason（父指令项 a）。claim 中凡以引号或「原文记作」形式引用原文的，逐条回原文确认确有该词，未命中的按主体/口径未闭合降级（父指令项 b）。父裁决后仍为 privacy_redacted_number 的只剩 w000511 的 c01/c02。**本轮材料层修复后重审**：旧形态规则（6–12 位数字整体抹除）已改为按值脱敏（只抹导出里真实的 QQ/UID/群号），w000511 的 seq1/seq3 即按修复后的渲染逻辑逐字复原（见 material_repair）；随后对 b3 全部 10 条 pending 逐条回读修复后的工单原文重判，只有 w000511 的 c01/c02 因判定量恢复而回 keep，其余 8 条的 pending 原因（假说语气、否定式命题未闭合、测量口径未给、主体未点名等）与材料修复无因果，一律维持（见 privacy_fix_reaudit）。**本轮引文保真修复**：父裁定「已发布条目引文里的占位缺陷必须修复」，据此把 4 份工单里落在已发布条目引文内的 6 条消息按同一行源复原（见 quote_fidelity_repair），并逐条核对复原值不是导出中的身份号；同窗 excluded[] 叙述里因占位而写的句子同步为材料事实，未改任何 verdict。**本轮对抗性挑刺（faultcheck）**：二审对已发布条目逐条挑刺，只改 claim/subject/condition 三类派生文本，引文（evidence 文本与 evidence_sha256）一字未动；verdict=remove 的条目从本批撤下（reason_code=faultcheck_remove），verdict=fix 的条目按建议改写并把 faultcheck 说明追加进 review_limitations，逐条留在 decisions[].claim_repaired_by_faultcheck。",
        "criteria": CRITERIA,
        "reject_reasons": REJECT_REASONS,
        "header_blindness_note": "b3 批的工单与回执均为 write-back 冻结产物；例外是被旧隐私规则误抹的消息，已在材料层修复后按同一行源重算复原（_b3_apply_privacy_fix.py 修 w000511 的 seq1/seq3；_b3_apply_quote_fidelity_fix.py 修 054/083/084/213 的 6 条；改写只涉数字，脱敏形态与冻结版一致）。本文件的裁定与证据一律取自 raw_messages，凡不能逐字回指的候选一律不入库。回执由 ds/deepseek-v4.1-flash 生成，本收敛审读不据发言者身份加权，只据原文是否闭合。",
        "parent_ruling": {
            "decided_at": "2026-09-21",
            "note": "父对首轮 5+1 条存疑的裁决，逐项落地记录；本批 status 即由此从 pending_parent_review 转为 approved_merged。",
            "items": [
                {"workorder": "qq_wo_b3_084", "local_id": "c01", "first_round": "pending",
                 "ruling": "keep", "basis": "claim 本体不含数字；支持该 claim 的 seq55/seq57 未被抹成占位。"},
                {"workorder": "qq_wo_b3_054", "local_id": "c02", "first_round": "pending",
                 "ruling": "keep", "basis": "seq34「27.77帧」逐字恢复；claim 的结论不依赖被抹的除法算式。"},
                {"workorder": "qq_wo_b3_089", "local_id": "c02", "first_round": "pending",
                 "ruling": "keep_after_rewrite",
                 "basis": "claim 结论成立，但原文 seq75 未出现「真银斩」，故去掉该推定词、改写为原文称呼「射射射」，并在 limitations 注明技能名未在原文出现。"},
                {"workorder": "qq_wo_b3_092", "local_id": "c01", "first_round": "pending",
                 "ruling": "pending", "basis": "假说语气未获第二方确认，维持 pending。"},
                {"workorder": "qq_wo_b3_099", "local_id": "c01", "first_round": "pending",
                 "ruling": "pending", "basis": "否定式命题的正面对照未闭合，维持 pending。"},
                {"workorder": "qq_wo_b3_062", "local_id": "c01", "first_round": "reject",
                 "ruling": "reject", "basis": "只取肯定半句、否定半句窗内各执一词未收束，维持 reject。"},
            ],
            "post_repair_reaudit": "父遗留项。材料层「按值脱敏」修复后，b3 的 10 条 pending 已逐条"
                                   "重读修复后的工单原文重判（见 privacy_fix_reaudit）：改判 keep 2 条"
                                   "（w000511 的 c01/c02），其余 8 条维持 pending；本批 keep 由 317 变"
                                   "为 319，manifest 的 merged_entries / merged_result_entry_count "
                                   "随之一并更新。",
        },
        "decisions": decisions,
        "material_repair": MATERIAL_REPAIR,
        "privacy_fix_reaudit": REAUDIT,
        "kept_summary": {
            "count": len(entries),
            "workorders": kept_wo,
            "note": "keep 为缺省（DECISIONS 表只列非 keep 项）；本批不移除任何证据句，只做收/不收的裁定。",
        },
        "excluded_summary": {
            "excluded_reviewed": len(excluded),
            "note": "父指令本轮只收敛 386 条 claim，excluded[]（806 条）不逐条复裁，保持 reviews_b3 原样；本文件不把任何 excluded 项升为 keep，也不以之为依据反向支持 claims[]。",
        },
        "privacy_redacted_number_census": {
            "note": "父指令项 (a) 的落地记录。占位形态为「0.[账号已隐去]」一类（旧隐私脚本把 6–12 位连续数字整体替换；材料层修复后改为按值脱敏，机制数值保留）。这里列出全部含占位的工单，以及占位是否落在被判 claim 自身的 evidence 文本内——只有后者才触发 privacy_redacted_number。本表按**当前**工单材料现算：w000511 的 seq1/seq3 与 054/083/084/213 的 6 条被误抹的消息均已在材料修复与引文保真修复中复原，故已不在表内；表内工单的占位一律只落在未被引用的上下文里，`claim_evidence_hit_workorders` 现为空。",
            "claim_evidence_hit_workorders": sorted({r["workorder"] for r in privacy_census if r["in_claim_evidence_seqs"]}),
            "claim_evidence_hit_windows": sorted({r["window"] for r in privacy_census if r["in_claim_evidence_seqs"]}),
            "context_only_workorders": sorted({r["workorder"] for r in privacy_census if not r["in_claim_evidence_seqs"]}),
            "workorder_count_with_placeholder": len(privacy_census),
            "claim_evidence_hit_count": sum(1 for r in privacy_census if r["in_claim_evidence_seqs"]),
            "repaired_workorders": ([r["workorder"] for r in MATERIAL_REPAIR["repaired"]]
                                    + [r["workorder"] for r in QUOTE_FIDELITY_REPAIR["repaired"]]),
            "stale_workorders_left": 17,
            "stale_note": "材料修复后仍与修复口径不一致的工单 17 份（kb_curation_qq_expansion_diff_b3.py "
                          "本轮输出 delivered_mismatches=32）。两轮修复（w000511；054/083/084/213）已把落在"
                          "已发布条目引文内的占位全部复原；这 17 份的占位都只在未被引用的上下文里，"
                          "重建它们不会改善任何已发布条目，故不动（见 material_repair.scope 与 "
                          "quote_fidelity_repair.scope）。",
            "windows": privacy_census,
        },
        "quote_fidelity_repair": QUOTE_FIDELITY_REPAIR,
        "faultcheck": {
            "applied_at": fc_meta.get("applied_at") or "2026-09-22",
            "script": "kb_trial/curation/faultcheck/_faultcheck_apply.py",
            "source": "kb_trial/curation/faultcheck/faultcheck_b3.json"
                      "（由 kb_trial/curation/faultcheck/_faultcheck_apply.py 汇总批 16 份 triage_*.json 的二审结论）",
            "note": "对抗性挑刺（faultcheck）本轮落地：二审逐条对已发布条目挑刺，verdict=remove 的撤下、"
                    "verdict=fix 的按建议改写 claim/subject/condition（引文一个字不动）。"
                    "removes 全量列于本块，fixes 逐条记在 decisions[].claim_repaired_by_faultcheck，"
                    "并作为 limitations 追加到对应条目。本批 keep 由 319 变为 %d。"
                    % len(entries),
            "remove_count": len(fc_removed),
            "removes": sorted(fc_removed, key=lambda r: r["workorder"]),
            "fix_count": len(fc_fix),
            "fixes": sorted(
                [{"window": wo_to_win[wo], "workorder": wo, "local_id": lid,
                  "fault_type": spec.get("fault_type", ""),
                  "fields": sorted(k for k in ("claim", "subject", "condition") if k in spec)}
                 for (wo, lid), spec in fc_fix.items()],
                key=lambda r: (r["workorder"], r["local_id"])),
        },
        "counts": counts,
    }
    with open(OUT_DECISIONS, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    manifest = {
        "note": "阶段三 b3 批（260 窗）全量收敛审读后的批准产物，只含本代理逐条回读 raw_messages 后认可的命题；每条 evidence 与冻结工单 raw_messages 逐字校验（evidence_sha256 可复核，算法=对 evidence 各条 {seq,speaker_id,time,text} 的 JSON（ensure_ascii=False、sort_keys=True、默认分隔符）取 sha256，与阶段二 approved_manifest.json 同式）。父已批准本批并已追加进 kb_trial/curated_high_quality.json，故 status 为终端态 approved_merged。本轮（材料层修复后重审）追加 w000511 的 c01/c02 两条（首轮因 privacy_redacted_number 移 pending，材料修复后判定量恢复、按四项判据回 keep），本批 keep 由 317 变为 319。此后（父裁定 2026-09-22）又对 4 条已发布条目的引文做了保真修复：054/083/084/213 中被旧隐私规则误抹的 6 条消息按源复原，w000208:c02 另补入 seq59 作为其 claim 数值的逐字出处；条数不变（319），见 audit_decisions_b3.json 的 quote_fidelity_repair。**本轮对抗性挑刺（faultcheck，2026-09-22）**：二审逐条挑刺后本批撤下 7 条（reason_code=faultcheck_remove）、按建议改写 55 条派生文本（引文一字未动），本批 keep 由 319 变为 %d；见 audit_decisions_b3.json 的 faultcheck 块。" % len(entries),
        "schema": "qq-expansion-approved-1.0",
        "phase": "phase3_b3_full_convergence",
        "criteria": CRITERIA,
        "windows_reviewed": 260,
        "source": {
            "workorders": "kb_trial/curation/qq_expansion/workorders_b3/",
            "final_reviews": "kb_trial/curation/qq_expansion/reviews_b3/",
            "audit_decisions": "kb_trial/curation/qq_expansion/audit_decisions_b3.json",
        },
        "status": "approved_merged",
        "entry_count": len(entries),
        "hard_exclusions_enforced": [
            "%s %s/%s %s" % (d["window"], d["workorder"], d["local_id"], d["reason_code"])
            for d in decisions if d["verdict"] != "keep"
        ],
        "hard_exclusions_note": "与阶段四 b4 批同式：列出本批全部非 keep 裁定（reject + pending）。"
                                "首轮列出的两条 privacy_redacted_number（w000511 的 c01/c02）已在材料层"
                                "修复后重审回 keep，故不再出现在此列（见 audit_decisions_b3.json 的 "
                                "material_repair / privacy_fix_reaudit）。",
        "entries": entries,
        "approved_by": "parent ruling 2026-09-21: 5+1 条存疑逐项裁决（084/c01→keep、054/c02→keep、"
                       "089/c02→改写后 keep、092/c01→pending、099/c01→pending、062/c01→reject），"
                       "其余批次整体认可；keep=317。本轮追加：材料层修复后重审 b3 全部 10 条 pending，"
                       "w000511 的 c01/c02 回 keep，keep=319。父裁定 2026-09-22：批准修复已发布条目引文里"
                       "的占位缺陷（054/083/084/213 共 6 条消息按源复原，w000208:c02 补入 seq59），"
                       "复原值均非身份号，故无条目改判 pending 移出，keep 仍为 319。"
                       "父裁定 2026-09-22：批准对抗性挑刺（faultcheck）二审结论，本批 7 条 verdict=remove "
                       "撤下、55 条 verdict=fix 改写派生文本（引文与 evidence_sha256 未动），keep=%d。" % len(entries),
        "merged_at": "2026-09-21",
        "merged_into": "kb_trial/curated_high_quality.json",
        "merged_entries": len(entries),
        "merged_result_entry_count": merged_result_entry_count(len(entries), "kb_trial/curation/qq_expansion/" + os.path.basename(OUT_MANIFEST)),
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print("claims=%d keep=%d reject=%d pending=%d entries=%d" % (
        len(claims), counts["keep"], counts["reject"], counts["pending"], len(entries)))


if __name__ == "__main__":
    build()
