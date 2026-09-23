"""Whitelist, rendering and gates for kb_trial/curated_high_quality.json.

This module is the single source of truth for what may ship in the curated layer.

Design constraints the rest of the pipeline depends on:

* Nothing is admitted because of its ``doc_type``, ``confidence``, ``kind``, track or a
  "high" label. A rule ships only if (a) it passes every deterministic gate, and either
  (b) an agent verified that exact (doc_id, rule_idx) against its raw quote, or
  (c) the user explicitly approved the card it belongs to.
* ``user_verified`` / ``agent_verified`` / ``auto_screened`` are three distinct evidence
  states and are never conflated. ``auto_screened`` means deterministic gates ran and
  passed - it does not mean a human or an agent read that rule.
* A rule's shipped string is taken from the frozen decision tables below, not re-derived
  at build time, so what ships is exactly what was reviewed.
* Only user *approval* is positive evidence. "Not yet reviewed" is not a negative
  verdict and not a positive one. Feedback the user called unusable is a rejection.
* An ASR-only card is not disqualified for being ASR. It ships only if an agent checked
  that exact claim against the raw ASR quote; the source layer is always disclosed.
"""
import re

SCHEMA_VERSION = 'curated-1.0'

# --- reviewer boundary ------------------------------------------------------------
# Rules must not ship. Reasons come from kb_pilot_synth/user_review_round1/feedback.jsonl
# and the review reasoning recorded alongside it.
REJECT = {
    ('fc1:技能特例-11-1', 0): 'user_review_round1 #1 用户明确"无意义"；已 archive，非机制规则',
    ('fc1:技能特例-11-1', 1): 'user_review_round1 #1 用户明确"无意义"；已 archive，非机制规则',
    ('fc1:技能特例-11-1', 2): 'user_review_round1 #1 用户明确"无意义"；已 archive，非机制规则',
    ('fc1:技能特例-6-4', 0): 'user_review_round1 #4 用户明确"无意义"；单关部署次数，非机制规则',
    ('fc1:技能特例-6-4', 1): 'user_review_round1 #4 用户明确"无意义"；单关部署次数，非机制规则',
    ('fc1:伤害结算-15-1', 0): 'user_review_round1 #6 用户明确"无意义"；单关关卡血量加成，非机制规则',
    ('fc1:其他-8-8', 0): 'user_review_round1 #3 用户"看不懂"；主语未点名，待核，不得当已知',
    ('fc1:其他-8-8', 1): 'user_review_round1 #3 用户"看不懂"；主语未点名，待核，不得当已知',
    ('fc1:其他-8-8#pending', 0): 'user_review_round1 #3 未闭合；门控 llm_mark_unclosed',
    ('fc1:其他-9-11', 0): '单关/单次实验观测，已隔离到 experiment 轨，不进入可复用规则层',
    ('fc1:其他-9-11', 1): '单关/单次实验观测，已隔离到 experiment 轨，不进入可复用规则层',
}

# Rules the user explicitly approved with the word "优秀" (whole card inherits to its
# unchanged, explicit rule sentences). feedback.jsonl sample_number 5 / 8 / 10 only.
# Rules whose card the user approved but which the agent then judged unverifiable stay
# out (listed under AGENT_PENDING instead).
# 'claim' is the frozen shipped string; the build asserts the source claim matches the
# first character sequence of it so upstream drift cannot pass silently.
USER_VERIFIED = {
    ('fc1:索敌-20-14', 0): 'user_review_round1 #5 明确"优秀"',
    ('fc1:索敌-20-14', 1): 'user_review_round1 #5 明确"优秀"',
    ('fc1:索敌-20-14', 3): 'user_review_round1 #5 明确"优秀"',
    ('fc1:索敌-20-14', 4): 'user_review_round1 #5 明确"优秀"',
    ('fc1:索敌-20-14', 5): 'user_review_round1 #5 明确"优秀"',
    ('fc1:索敌-20-14', 6): 'user_review_round1 #5 明确"优秀"',
    ('fc1:索敌-16-10', 0): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 1): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 2): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 3): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 4): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 5): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 6): 'user_review_round1 #8 明确"优秀"',
    ('fc1:索敌-16-10', 7): 'user_review_round1 #8 明确"优秀"',
    ('fc1:帧时序与计时器-37-5', 0): 'user_review_round1 #10 明确"优秀"',
    ('fc1:帧时序与计时器-37-5', 1): 'user_review_round1 #10 明确"优秀"',
    ('fc1:帧时序与计时器-37-5', 4): 'user_review_round1 #10 明确"优秀"',
    ('fc1:帧时序与计时器-37-5', 5): 'user_review_round1 #10 明确"优秀"',
    ('fc1:帧时序与计时器-37-5', 6): 'user_review_round1 #10 明确"优秀"',
    ('fc1:帧时序与计时器-37-5', 7): 'user_review_round1 #10 明确"优秀"',
}

# Rules that cleared every structural gate but that the fixed-seed audit (seed 20260920)
# read against the source and found unsupported by their own citation. Recorded as
# exclusions rather than silently left in, because the defect is in the evidence, not in
# the sentence: a reader checking the cited clip cannot confirm the claim.
AUDIT_NOT_SUPPORTED = {
    ('fc1:帧时序与计时器-10-1', 7):
        '定审读源发现引文不足以支持整句：clip p61:a8「这个轴实际上非常的死」只涵盖句尾，'
        '前半句“中路至少两个必须始终打断”及“40 秒左右”属上游从别处并入，引文未闭合；'
        '同卡的 10-1#r7 与 69-6#r5 属同类截断问题',
    ('fc1:帧时序与计时器-69-6', 5):
        '定审读源发现引文不匹配：引文为「三个小车对三个小车」「部署费用再部署」，未含声称的'
        '“40 秒左右”时点，主张超出引文支持范围',
}
# re-approve afterwards. The feedback is applied, but applying feedback is not the same
# as the user accepting the result, so these may NOT ship as user_verified. They ship
# only if an agent reads the original quote and confirms the corrected sentence, which
# is what makes them agent_verified.
FEEDBACK_APPLIED = {
    ('fc1:伤害结算-13-0', 0): 'user_review_round1 #7 "删改后可用"(action=trim)；修正已应用但用户未复审，'
                              '故按代理核实收录，不得标为 user_verified',
    ('fc1:伤害结算-13-0', 1): 'user_review_round1 #7 "删改后可用"(action=trim)；修正已应用但用户未复审，'
                              '故按代理核实收录，不得标为 user_verified',
    ('fc1:伤害结算-13-0', 2): 'user_review_round1 #7 "删改后可用"(action=trim)；修正已应用但用户未复审，'
                              '故按代理核实收录，不得标为 user_verified',
    ('fc1:伤害结算-13-0', 3): 'user_review_round1 #7 "删改后可用"(action=trim)；修正已应用但用户未复审，'
                              '故按代理核实收录，不得标为 user_verified',
    ('fc1:伤害结算-13-0', 4): 'user_review_round1 #7 "删改后可用"(action=trim)；修正已应用但用户未复审，'
                              '故按代理核实收录，不得标为 user_verified',
    ('fc1:位移-4-5', 0): 'user_review_round1 #12 "修改后可用"(action=correct，维尼斯→维云斯)；修正已应用但'
                         '用户未复审，故按代理核实收录，不得标为 user_verified',
}

# Rules whose card the user approved, but which the agent could not verify from the raw
# quote. Kept in the decisions file as pending, never shipped.
AGENT_PENDING = {
    ('fc1:位移-4-5', 1): '门控 ctx_only_evidence；无原子引文，无法核听',
}

# Rules that pass every structural gate but whose citation cannot be traced back to the
# raw transcript: the upstream atom layer packed non-adjacent windows, or reused an atom
# hash under a different BVID so the quote sits in the wrong file. A rule whose only
# evidence cannot be located is not shippable, so these are dropped from the curated
# layer and recorded here instead of being silently relaxed through the validator.
UNTRACEABLE_CITATION = {
    ('fc1:伤害结算-13-2', 1):
        'BVID 引文「大部分伤判的默认数值都是零，默认优先级都是零。」在 asr_drafts/'
        'BV1j4KC6KEse_p1_40109737103_asr.txt 中不可定位（上游原子层合并了非相邻窗口）',
    ('fc1:寻路-8-5', 1):
        '原子哈希 f2b814e5 被 BV16xhV6DEF4_p1_41261337528 与 BV14y8269EbS_p2_41167359561 '
        '复用，该 BVID 下无法定位引文；跨文件错引，不可作为可定位证据',
    ('fc1:索敌-26-2', 8):
        '引文「以整个攻击间隔为前摇…」在 asr_drafts/BV1KBgX6WEVm_p1_40322532606_asr.txt '
        '中不可逐字定位；上游原子层改写了措辞且未保留原始行，证据不可核',
    ('fc1:寻路-8-5', 6):
        '引文「闪现终究也是非寻路」的整句在该 BVID 的 asr_drafts 中不可定位'
        '（「非寻路」0 次出现）；原子哈希 1d249d06 跨 BVID 复用，属跨文件错引',
    ('fc1:帧时序与计时器-17-6', 0):
        '引文「同帧的话，敌人先移动，然后的话珊比再传送」在 asr_drafts/'
        'BV16xhV6DEF4_p2_41263435601_asr.txt 中不可定位（「同帧的话」0 次出现）；'
        '同一原子哈希 ebcb9449 的措辞只存在于其它 BVID，属跨文件错引',
}

# Agent-verified rules: the agent read the raw quote and window for this exact rule and
# confirmed the claim is a standalone, source-supported mechanism statement. Populated
# by kb_curation_verify.py output; see curation/agent_verifications.json for the
# per-rule evidence trail. Listed here as an explicit literal so the shipped set is
# reviewable in source without running anything.
AGENT_VERIFIED_REASONS = {}


def normalise(claim):
    """Normalise a shipped claim for matching against frozen source claims."""
    c = re.sub(r'证据:[^\n)]*', '', claim)
    c = re.sub(r'\s*\[(?:非通则|门控|实例)[^\]]*\]', '', c)
    return re.sub(r'[\s、，。；：()（）,.;:]', '', c).strip()


def is_rejected(doc_id, rule_idx):
    key = (doc_id, rule_idx)
    return (key in REJECT or key in AGENT_PENDING or key in UNTRACEABLE_CITATION
            or key in AUDIT_NOT_SUPPORTED)
