# -*- coding: utf-8 -*-
"""对抗性挑刺（faultcheck）修复落地：隐私统一 + remove 58 + fix 338。

输入（只读）：
  kb_trial/curation/faultcheck/_triage_agg.json   二审聚合的 remove/fix id 清单
  kb_trial/curation/faultcheck/triage_*.json      二审逐条 verdict 与 suggestion
  kb_trial/curation/faultcheck/_fix_plan.json     _faultcheck_extract.py 的机械抽取结果

输出：
  kb_trial/curation/faultcheck/faultcheck_b3.json / faultcheck_b4.json / faultcheck_phase2.json
        → 供三个批次的产出器消费的确定性改写/移除表（本人手核+机械抽取合成）
  kb_trial/curation/decisions.jsonl                vod 轨（fc1/window/B###）claim 改写与 reject 落地
  kb_trial/curation/faultcheck/_remediation_plan.json  逐条动作台账（含跳过理由）
  隐私替换：workorders_*/reviews_*/approved_manifest_*/audit_decisions_* 内昵称 → 某人

本脚本幂等：重复运行不产生新变化（已改过的字段按新值即已应用处理），也不改任何引文文本。
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
QQEXP = os.path.join(ROOT, "kb_trial", "curation", "qq_expansion")
CURATED = os.path.join(ROOT, "kb_trial", "curated_high_quality.json")
DECISIONS = os.path.join(ROOT, "kb_trial", "curation", "decisions.jsonl")
PLAN_IN = os.path.join(HERE, "_fix_plan.json")
OVERLAY = os.path.join(ROOT, "kb_trial", "curation", "qq_claim_overlay.json")
EVIDENCE_VERDICTS = os.path.join(ROOT, "kb_trial", "curation", "evidence_verdicts.jsonl")

# ----------------------------------------------------------------- 隐私
# 两个群聊昵称残留（见下方 _decode_terms，明文不落盘）统一替换为「某人」。
# 自忍 只在对人时替换；本批两处（qq_wo_b4_433 seq3「h8-4自忍」、seq75「之前看自忍」）
# 均指「自忍」这一自限玩法/观赏对象，且都不在任何已发布条目内，故保留并上报父判断。
def _decode_terms():
    import base64
    return {base64.b64decode(k).decode("utf-8"): v
            for k, v in (("5bCPQQ==", "某人"), ("THljb3Jpcy4=", "某人"))}


PRIVACY_TERMS = _decode_terms()
PRIVACY_SELF_TERM = "自忍"
PRIVACY_DIRS = [os.path.join(QQEXP, d) for d in
                ("workorders", "workorders_b3", "workorders_b4",
                 "reviews", "final_reviews", "reviews_b3", "reviews_b4")]
# 本轮挑刺自己的分析件（chunk/findings/flags/triage/_fix_* 与落地表）与 b4 的上下文摘录
# 也属流水线材料：昵称一律抹平，脚本本体只留 base64，故 grep 明文昵称为 0。
PRIVACY_EXTRA_DIRS = (HERE, os.path.join(QQEXP, "_b4ctx"))
PRIVACY_EXTRA_EXTS = (".json", ".txt", ".md")
PRIVACY_FILES = [os.path.join(QQEXP, f) for f in
                 ("approved_manifest.json", "approved_manifest_b3.json", "approved_manifest_b4.json",
                  "audit_decisions.json", "audit_decisions_b3.json", "audit_decisions_b4.json")]
# 批次 →（工单目录，回执目录（loader 实际读的那个在前），manifest 文件名）。
# 材料被改写后回执的 source_sha256 与 manifest 的 evidence 文本/哈希必须同步，否则 loader 拒收。
BATCH_RESYNC = (
    ("phase2", "workorders", ("final_reviews",), "approved_manifest.json"),
    ("b3", "workorders_b3", ("reviews_b3",), "approved_manifest_b3.json"),
    ("b4", "workorders_b4", ("reviews_b4",), "approved_manifest_b4.json"),
)

# ----------------------------------------------------------------- 单条人工裁定
# 抽取器无法可靠处理的条目；键 = entry id，值为显式字段覆盖或跳过理由。
MANUAL = {
    # 「claim 与 subject 改为「避障力」：「…」」：抽取器取到了第一个「」
    "fc1:寻路-37-9#r1": {
        "claim": "避障力的第一种来源：单位处于不可通行地块时由该地块触发。",
        "subject": "避障力"},
    "fc1:寻路-37-9#r3": {
        "claim": "避障力的第二种来源：单位处于可通行地块时，会触发周围不可通行地块与障碍物提供的避障力。",
        "subject": "避障力"},
    # 合计 99.9% 是建议方自算、窗内只有 33.3，故删去该数字
    "qq_expansion:w000499:c02": {
        "claim": "三连击每段 33.3%（三段各自系数）这个值是 YJ 自己敲的（不是包里写的）。",
        "note": "建议里的「合计 99.9%」为建议方自算、窗内无此数，落库时删去。"},
    # 物欲抗结者 → 物欲拮抗者（PRTS 正名；原写法不在实体表，属讹写）
    "qq_expansion:w001408:c02": {
        "claim": "部分单位（如物欲拮抗者）在不同模式下采用不同配置，只有在特定模式下才「没办法被阻挡」"
                 "（物欲是一阶段模式可以阻挡、二阶段模式不能阻挡）。",
        "subject": "同一单位不同模式下的阻挡配置差异（物欲拮抗者）"},
    # 罗小黑 → 妮符（源用名）
    "qq_expansion:w000382:c01": {
        "claim": "妮符（原文用名）的出伤与同帧回血之间存在结算顺序，同帧普通回血不起作用；"
                 "必须是复活甲这类插在应用中（结算流程中）的回血机制才会介入。",
        "subject": "妮符出伤与同帧怪回血的结算顺序"},
    "qq_expansion:w000064:c01": {
        "claim": "在 120 帧下，费用条上细节「怎么也看不到」，原因是鹰角费用条逻辑本身的限制。",
        "note": "取建议的第二个方案（删去引文未覆盖的半句）；未增补引文。"},
    "qq_expansion:w000759:c01": {
        "claim": "踢球产生的推力默认需要来源，否则没法判定0.25半径和45°角力度-2这些参数；"
                 "球按干员与球相对位置决定的是伤害部分（原文未展开『不是推力』）。",
        "note": "取建议的第二个方案（不加引文，按原文未展开收窄半句）。"},
    "qq_expansion:w001466:c02": {
        "claim": "某帧的间距若落在 0.005 到 0.01 之间，这帧可以到达该位置，下帧移动前会直接顶在碰撞箱上停止失衡。",
        "subject": "相离碰撞区间内的位移落点"},
    "qq_expansion:w001931:c01": {
        "claim": "平行组（原文口径：平行组是减攻速加攻速）不会多出 1 帧。"},
    "qq_expansion:w001553:c01": {
        "claim": "灵知不清冷却（不重置冷却）时，开完技能后会随机残留 0-1 点“技力”（会留绿条）。",
        "subject": "灵知（不清冷却时）技能结束的技力残留"},
    "qq_expansion:w000047:c01": {
        "condition": "该单位开技能或移动产出召唤物时；原文未给出对照对象"},
    "qq_expansion:w001487:c02": {
        "condition": "该伤害走预计算时（原窗「使用缓存攻击力的伤害」一说被当场反驳，未采用）"},
    "fc1:位移-31-1#r1": {"condition": "未标注（失衡力的通用定义）"},
    "fc1:索敌-27-6#r0": {
        "claim": "睡眠的索敌优先选择范围内生命比例最低的干员",
        "subject": "睡眠（格判索敌）",
        "condition": "睡眠（格判索敌）对范围内干员进行索敌",
        "note": "按 triage 建议去掉被当场否认的「光环」（[36:08]/[40:57]/[41:22] 三次否认）；"
                "建议附带的「（源 [35:18]；主播当场复测后确认）」属流程注记、非命题内容，未并入 claim；"
                "condition 原文含「睡眠光环」故一并订正；与 r1 合并为一条两级规则属结构性改动，留待父决定。"},
    "fc1:索敌-27-6#r1": {"subject": "睡眠（格判索敌）",
                         "note": "只落 subject 订正（光环→格判）；与 r0「合并为一条两级规则」属结构性改动，留待父决定。"},
    "qq_expansion:w000353:c01": {"claim_append": "（归因原话未展开）"},
    "qq_expansion:w000454:c01": {"claim_append": "（属群内成员口径，主播对该层逻辑表示不清楚）"},
    # ---- 跳过：不改本层可见文本 ----
    "fc1:帧时序与计时器-76-7#r2": {
        "claim": "再部署剩余时间按每帧 -0.0333 递减，显示值四舍五入到小数点后一位（69.966→70、69.933→69.9）。",
        "note": "两个示例数均在源字幕（69点/[45:32]933 断行）内逐字存在，检查器因断行未命中，已人工核对。"},
    "qq_expansion:w000665:c01": {
        "claim": "新约能天使 2 技能开技能时的变形斩（由天赋定义的攻击动作）不是普通攻击——加上能天使后动画与之前一样（窗内实测）。",
        "subject": "新约能天使 2 技能的变形斩",
        "note": "「新能」在 entity_index 登记为 prts_alias→新约能天使，用正名不算引入证据外实体。"},
    "qq_expansion:w000665:c02": {
        "claim": "新约能天使 2 技能开技能时的变形斩是「天赋」定义的动作（原文「是『天赋』的变形斩」）。",
        "note": "「新能」在 entity_index 登记为 prts_alias→新约能天使，用正名不算引入证据外实体。"},
    "qq_expansion:w000141:c01": {
        "claim": "丰川祥子（群内简称「祥子」）只有一个攻击、按阻挡与否改倍率，"
                 "不同于『一个模式下的两个攻击』的干员（对照对象原文只作「他们」，未指名）。",
        "subject": "丰川祥子（群内简称「祥子」）的攻击与模式关系",
        "note": "「祥子」在 entity_index 登记为 prts_alias→丰川祥子。"},
    "qq_expansion:w000215:c02": {
        "claim": "多个技力回复光环同时作用时取最高值（不叠加）；本窗示例为白面（白面鸮）的技力回复光环，"
                 "部署后下一帧按 1.65 结算一次。",
        "note": "「白面」在 entity_index 登记为 prts_alias→白面鸮。"},
    "fc1:索敌-28-7#r6": {"subject": "波卜",
                         "note": "「波普」在 entity_index 登记为 asr_mine 讹写→波卜。"},
    "qq_expansion:w000677:c02": {
        "claim": "冷却帧数化后按帧四舍五入得到动画长度（例：伊内丝攻速+8 时 30/1.08≈27.78 帧，"
                 "原文写作 27.77 帧，动画长度取 28 帧），动画结束的那一帧判断剩余冷却是否＜0.5，"
                 "若小于 0.5 就立刻抬手；整体可简记为按帧四舍五入。",
        "note": "27.78 是源内 27.77777778 的四舍五入，落库文本已注明原文写作 27.77。"},
    "qq_expansion:w001462:c01": {
        "claim": "以方程 3y-x=0 表示斜率关系时，用 3-1=2 除以 √(3²+1)=√10 得 2/√10≈0.6324555320；"
                 "原文用截断值 3.162277 算得 0.6324556641，即单位会“路过”约 0.6325 宽度的阻挡"
                 "（该阻挡物的所指依赖原文配图，本层未保留）。",
        "note": "0.6324555320 由源内算式 2/√10 现算，原文用的是截断值 3.162277；两值并列且已注明。"},
    "qq_expansion:w001791:c01": {
        "claim": "一帧 ≈ 0.0333333 秒 = 69905×2⁻²¹（二进制精确值 0.033333301544189453…秒，"
                 "与 0.0333333 非严格相等）。",
        "note": "精确值是源内表达式 69905*2^-21 的换算，已标注与 0.0333333 不严格相等。"},
}

# 跳过：建议只动 review/evidence 叙述、derived_text_repairs 登记、citation 指向，或需增补引文。
SKIP = {
    "fc1:其他-3-19#r0": "建议改 citation.transcript_file/source_files 与 t_start，落点在本层不保留的 kb_trial/evidence.jsonl（冻结试验产物，validate 要求字节不变），本轮不动",
    "fc1:索敌-16-10#r0": "同上：改 citation 文件指向与来源层标注需改 kb_trial/evidence.jsonl，本轮不动",
    "fc1:索敌-16-10#r1": "同上：改 citation 文件指向与来源层标注需改 kb_trial/evidence.jsonl，本轮不动",
    "fc1:状态效果-1-6#r2": "建议只补 citation 的 t_line_label（引文文本不变）——citation 由 evidence.jsonl 生成，本轮不动",
    "fc1:索敌-20-7#r2": "建议为「如 claim/condition 中用到该量则写成 N-1 帧」；本条 claim/condition 未用到该量，无文本改动",
    "fc1:寻路-38-0#r3": "建议改 evidence_review 叙述与引文加注，claim 不动；本轮只改 claim 层文本",
    "fc1:索敌-20-12#r3": "建议改条目内 derived_correction 叙述，claim 不变；本轮只改 claim 层文本",
    "fc1:索敌-20-7#r1": "建议补条目级 ASR 订正记录，claim 不变；本轮只改 claim 层文本",
    "fc1:伤害结算-16-15#r1": "claim 已用「帧」，建议只作 derived_text_repairs 登记与 entity_corrector 规则，claim 层无改动",
    "B085-same-frame-unblock#r0": "claim 已写「同帧」，建议只作 derived_text_repairs 登记与 entity_corrector 规则，claim 层无改动",
    "qq_expansion:w000215:c01": "建议只登记 derived_text_repairs「这一阵→这一帧」，claim 措辞已正确，无改动",
    "qq_expansion:w001181:c03": "建议只登记 derived_text_repairs「同针→同帧」，claim/subject 已正确，无改动",
    "qq_expansion:w000577:c02": "建议只登记 derived_text_repairs（claim 已按订正后文本），无改动",
    "qq_expansion:w000654:c01": "建议在 citations 补引 seq 17；本轮约束为引文一个字不动（增补引文会改变已发布引文集），留待父决定",
    "qq_expansion:w000668:c01": "建议在 citations 补引 seq 9；同上留待父决定",
    "qq_expansion:w000768:c01": "建议在 citations 补引 seq 3；同上留待父决定",
    "qq_expansion:w000408:c01": "建议只改 evidence_review.reason 的举证叙述（claim 文本不变），本轮只改 claim 层文本",
    "qq_expansion:w000338:c02": "建议只改 review/evidence_review 的 reason，claim 与引文不动",
    "qq_expansion:w000494:c02": "建议只改 review/evidence_review 的 reason，claim 可不动",
    "qq_expansion:w000582:c01": "建议只改 review/evidence 描述，claim 与引文不动",
    "qq_expansion:w000582:c02": "建议只改 review/evidence 描述，claim 与引文不动",
    "qq_expansion:w000582:c03": "建议只改 review/evidence 描述，claim 与引文不动",
    "qq_expansion:w001789:c01": "建议在 claim 末尾补注生产流程元信息（wiki 草稿出处）；该信息属编辑过程说明、不宜入 claim 正文，未落地",
    "qq_expansion:w001789:c02": "同上：建议在 claim 中补注 wiki 草稿出处与同窗争议；属编辑过程说明，未落地",
    # 仅改 citation 元数据（chapter）：chapter 由冻结的 kb_trial/docs.jsonl 在 build 阶段写入
    # （kb_curation_build.py 的 'chapter': source.get('chapter')），本层（decisions.jsonl）改不到。
    "fc1:状态效果-22-12#r0": "建议只改 citations[].chapter（赛雷亚→塞雷娅）；chapter 由冻结试验产物 docs.jsonl 生成，本层不动",
    "fc1:索敌-11-8#r0": "建议只改 citations[].chapter（三针→三帧）；chapter 由冻结试验产物 docs.jsonl 生成，本层不动",
    "fc1:索敌-11-9#r4": "同上：只改 citations[].chapter，本层不动",
    "fc1:索敌-11-9#r5": "同上：只改 citations[].chapter，本层不动",
    "fc1:索敌-12-5#r0": "同上：只改 citations[].chapter，本层不动",
    "fc1:索敌-12-5#r1": "同上：只改 citations[].chapter，本层不动",
    "fc1:索敌-12-5#r2": "同上：只改 citations[].chapter，本层不动",
    # 与既有 ASR 订正记录（curation/evidence_verdicts.jsonl 的 repaired_fields）冲突：
    # 该条早前已把 claim 的「空费针」订正为「空飞针」；triage 建议改「空费帧」，方向相反。
    # 源字幕同窗两种写法都有（BV1aTeV6yENP_p4 [56:24]「空费针」/[56:39]「空飞针」），
    # 属术语正字的两种猜测，谁对无法由文本判定 → 留给父裁定，本轮不动。
    "fc1:帧时序与计时器-27-3#r1": "与既有 ASR 订正冲突：evidence_verdicts 的 repaired_fields 已把「空费针」订为「空飞针」，"
                                  "triage 建议改「空费帧」，而源字幕同窗两种写法并存（[56:24] 空费针 / [56:39] 空飞针），"
                                  "无法由文本裁定正字，留待父决定",
    # 父裁定：该条初筛为误报（相关表述在证据中逐字存在），不做实体改写。
    "qq_expansion:w000597:c01": "父裁定跳过：初筛为误报（窗内证据逐字含该表述），不改 claim",
}

# 需人工清掉建议尾部夹带的指令片段（抽取器照抄整句时会带上）
TAIL_CUTS = (
    "。（并补引",
    "（并补引",
    "。另须脱敏",
    "。subject 同步改回",
    "。subject 同步改为",
    "。subject 改为",
)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def read_text(path):
    raw = open(path, "rb").read()
    return raw.decode("utf-8"), raw


def write_text(path, text):
    open(path, "wb").write(text.encode("utf-8"))


def write_like(path, raw, text):
    """按原文件的换行风格写回：Windows 上 Python 文本模式会写出 CRLF，字节模式不会，
    而本仓库的 JSON 产物两种都有（manifest 是 CRLF、回执是 LF）。"""
    body = text.replace("\r\n", "\n")
    if b"\r\n" in raw:
        body = body.replace("\n", "\r\n")
    open(path, "wb").write(body.encode("utf-8"))


# ----------------------------------------------------------------- 任务一：隐私统一
def privacy_pass():
    report = {"terms": dict(PRIVACY_TERMS), "files_scanned": 0, "files_changed": 0,
              "replacements": 0, "per_file": {}, "sha_resynced": [], "self_term_kept": []}
    targets = []
    for d in PRIVACY_DIRS:
        targets += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]
    for d in PRIVACY_EXTRA_DIRS:
        targets += [os.path.join(d, f) for f in sorted(os.listdir(d))
                    if f.endswith(PRIVACY_EXTRA_EXTS)]
    targets += [p for p in PRIVACY_FILES if os.path.exists(p)]
    for p in targets:
        report["files_scanned"] += 1
        # _triage_agg.json 是 GBK，其余是 UTF-8；子串替换不动换行，故按原编码逐字节写回。
        raw = open(p, "rb").read()
        text, enc = None, None
        for e in ("utf-8", "gbk"):
            try:
                text, enc = raw.decode(e), e
                break
            except UnicodeDecodeError:
                continue
        if enc is None:
            report.setdefault("skipped_undecodable", []).append(os.path.relpath(p, ROOT))
            continue
        if PRIVACY_SELF_TERM in text:
            report["self_term_kept"].append(os.path.relpath(p, ROOT))
        new = text
        n = 0
        for a, b in PRIVACY_TERMS.items():
            n += new.count(a)
            new = new.replace(a, b)
        if n:
            open(p, "wb").write(new.encode(enc))
            report["files_changed"] += 1
            report["replacements"] += n
            report["per_file"][os.path.relpath(p, ROOT)] = n
    # 材料被改写后，回执 source_sha256 与 manifest evidence 文本/哈希必须同步，否则 loader 会拒收。
    for batch, wod, rdirs, mname in BATCH_RESYNC:
        wdir = os.path.join(QQEXP, wod)
        mpath = os.path.join(QQEXP, mname)
        for rname in rdirs:
            rdir = os.path.join(QQEXP, rname)
            for fn in sorted(os.listdir(rdir)):
                wo = os.path.join(wdir, fn)
                rv = os.path.join(rdir, fn)
                if not (os.path.exists(wo) and fn.endswith(".json")):
                    continue
                want = sha256_bytes(open(wo, "rb").read())
                raw = open(rv, "rb").read()
                rtext = raw.decode("utf-8")
                rj = json.loads(rtext)
                old = rj.get("source_sha256")
                if not old or old == want:
                    continue
                # 定点替换 sha 值：这批回执的原始排版并不统一（缩进/换行各异），整体重写会
                # 把一个字段的变更放大成全文件 diff，故能定点就定点。
                if rtext.count(old) == 1:
                    write_text(rv, rtext.replace(old, want))
                else:
                    rj["source_sha256"] = want
                    write_like(rv, raw, json.dumps(rj, ensure_ascii=False, indent=1) + "\n")
                report["sha_resynced"].append(os.path.relpath(rv, ROOT))
        # manifest：evidence 文本与 evidence_sha256 重算
        mraw, _ = read_text(mpath)
        mj = json.loads(mraw)
        changed = 0
        for item in mj["entries"]:
            wopath = os.path.join(wdir, "%s.json" % item["workorder_id"])
            if not os.path.exists(wopath):
                continue
            wo = json.loads(read_text(wopath)[0])
            msgs = {m["seq"]: m for m in wo["raw_messages"]["messages"]}
            ev = []
            for e in item["evidence"]:
                m = msgs[e["seq"]]
                if m["text"] != e["text"]:
                    changed += 1
                ev.append({"seq": m["seq"], "speaker_id": m["speaker_id"],
                           "time": m["time"], "text": m["text"]})
            want = sha256_bytes(json.dumps(ev, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            if item["evidence"] != ev or item.get("evidence_sha256") != want:
                item["evidence"] = ev
                item["evidence_sha256"] = want
                if not changed:
                    changed = 1
        if changed:
            write_like(mpath, mraw.encode("utf-8"),
                       json.dumps(mj, ensure_ascii=False, indent=1) + "\n")
            report.setdefault("manifest_evidence_resynced", []).append(
                os.path.relpath(mpath, ROOT))
    return report


# ----------------------------------------------------------------- 任务二/三：动作计划
def load_triage():
    recs = {}
    for name in sorted(os.listdir(HERE)):
        if not re.match(r"triage_\d{2}\.json$", name):
            continue
        d = json.load(open(os.path.join(HERE, name), encoding="utf-8"))
        for v in d["verdicts"]:
            v["_file"] = name
            recs[v["id"]] = v
    return recs


def strip_tail(text):
    for cut in TAIL_CUTS:
        i = text.find(cut)
        if i > 0:
            return text[:i + 1] if cut.startswith("。（") or cut.startswith("。") else text[:i]
    return text


# 「改 claim 为「…」」这类建议是给编辑的指令句，抽取器在 bare 模式下会整句当 claim；
# 这里把包装剥掉取其中的正文。只处理能明确识别出「…」正文的形式，其余交给下面的安全检查。
INSTR_PREFIXES = ("改 claim 为", "改 claim/subject 用全名：", "改 claim/subject 用全名",
                  "改 claim 用全名：", "claim 改为", "将 claim 改为", "改 claim 为：")
INSTRUCTION_MARKERS = ("citations[", "补入 citations", "在 citations 中补引", "并补引",
                       "review/evidence_review", "evidence_review", "review/evidence",
                       "改 claim", "claim 改为", "改 claim/", "仅改 ", "把 review",
                       "把 seq ", "subject 同步改", "需脱敏")


def unwrap_instruction(text):
    for pre in INSTR_PREFIXES:
        if not text.startswith(pre):
            continue
        rest = text[len(pre):].lstrip("：: ").strip()
        if rest.endswith("。"):
            rest = rest[:-1].strip()
        if len(rest) > 1 and rest[0] in "「“" and rest[-1] in "」”":
            return rest[1:-1]
    return None


def instruction_hit(text):
    for mk in INSTRUCTION_MARKERS:
        if mk in text:
            return mk
    return None


def build_plan():
    agg = json.load(open(os.path.join(HERE, "_triage_agg.json"), encoding="gbk"))
    plan_in = json.load(open(PLAN_IN, encoding="utf-8"))
    triage = load_triage()
    with open(CURATED, encoding="utf-8") as fh:
        entries = {e["id"]: e for e in json.load(fh)["entries"]}

    final, skipped = {}, {}
    for eid, p in plan_in.items():
        m = MANUAL.get(eid, {})
        if eid in SKIP and SKIP[eid]:
            skipped[eid] = {"reason": SKIP[eid],
                            "suggestion": triage[eid].get("suggestion", ""),
                            "fault_type": triage[eid].get("fault_type_kept", "")}
            continue
        entry = {"fault_type": p.get("fault_type", ""), "source": p.get("source", ""),
                 "suggestion": p.get("suggestion", "")}
        e = entries[eid]
        # 有显式人工裁定时以人工裁定为准、不回落抽取结果：抽取器在 bare 模式下可能把
        # 「改 claim 为「…」」这类指令句整句当成 claim（见 INSTRUCTION_MARKERS 的安全检查）。
        src = m or p
        for f in ("claim", "subject", "condition", "scope"):
            v = src.get(f)
            if isinstance(v, str) and v and v != e[f]:
                entry[f] = v
        if not m:
            for f in ("claim", "subject", "condition"):
                if f in entry:
                    u = unwrap_instruction(entry[f])
                    if u:
                        entry[f] = u
        if "claim_append" in m:
            entry["claim"] = e["claim"] + m["claim_append"]
        if not any(k in entry for k in ("claim", "subject", "condition", "scope")):
            skipped[eid] = {"reason": m.get("note") or "建议未给出可落地的 claim/subject/condition 改写",
                            "suggestion": p.get("suggestion", ""),
                            "fault_type": p.get("fault_type", "")}
            continue
        if "note" in m:
            entry["note"] = m["note"]
        final[eid] = entry

    # 尾部夹带指令片段的清理（仅对 claim）
    for eid, e in final.items():
        if "claim" in e and eid not in MANUAL:
            fixed = strip_tail(e["claim"])
            if fixed != e["claim"]:
                e["claim"] = fixed
                e["note"] = (e.get("note", "") + "；已清掉建议尾部夹带的指令片段").strip("；")
    # 安全检查：落地文本里仍含流程/元数据指令片段的，一律不落库（改记跳过）。
    for eid in sorted(final):
        e = final[eid]
        for f in ("claim", "subject", "condition"):
            hit = instruction_hit(e.get(f, ""))
            if hit:
                skipped[eid] = {"reason": "抽取到的是指令/元数据片段（命中「%s」），不是 claim 层文本改写，未落地" % hit,
                                "suggestion": e.get("suggestion", ""),
                                "fault_type": e.get("fault_type", "")}
                del final[eid]
                break
    # 与 remove 冲突的 fix：remove 优先
    conflict = sorted(set(final) & set(agg["remove"]))
    for eid in conflict:
        skipped[eid] = {"reason": "同 id 同时被判 remove，remove 优先，fix 不落地",
                        "suggestion": final[eid].get("suggestion", "")}
        del final[eid]
    return agg, entries, final, skipped, conflict


def batch_of(entries, eid):
    if not eid.startswith("qq_expansion:"):
        return "vod"
    src = (entries[eid].get("origin") or {}).get("trial_manifest_outputs", "")
    if src.endswith("approved_manifest_b3.json"):
        return "b3"
    if src.endswith("approved_manifest_b4.json"):
        return "b4"
    return "phase2"


# ---- 下游断言同步：fix 落地的字段若被流水线里别处的“冻结值”断言约束，必须同步，否则 build 直接退出 ----
def sync_overlay(vod_fixes, rows, idx, meta):
    """QQ 轨 vod 条目（window:w…）的 claim 在 kb_curation_build.py 与 kb_curation_evidence_apply.py
    里都会被断言等于 qq_claim_overlay.json 记录的 claim_from 与 claim；fix 必须同步改该记录。"""
    touched = []
    if not vod_fixes:
        return touched
    ov = json.loads(read_text(OVERLAY)[0])
    recs = {r.get("entry_id"): r for r in ov.get("records") or []}
    changed = False
    for eid, f in sorted(vod_fixes.items()):
        r = recs.get(eid)
        if r is None:
            continue
        doc, ridx = eid.rsplit("#r", 1)
        newclaim = rows[idx[(doc, int(ridx))]]["claim"]
        sup = r.setdefault("faultcheck_superseded", {})
        sup.setdefault("claim_before_faultcheck", r["claim"])
        sup.update({"applied_at": meta["applied_at"], "source": meta["source"]["triage_files"],
                    "fault_type": f.get("fault_type", ""), "suggestion": f.get("suggestion", ""),
                    "note": f.get("note", "")})
        r["claim_from"] = newclaim
        r["claim"] = f.get("claim") or newclaim
        for k in ("subject", "condition", "scope"):
            if k in f:
                r[k] = f[k]
        touched.append(eid)
        changed = True
    if changed:
        text = json.dumps(ov, ensure_ascii=False, indent=1).replace("\n", "\r\n") + "\r\n"
        write_text(OVERLAY, text)
    return touched


def sync_repairs(final, meta):
    """kb_curation_evidence_apply.py 会按 evidence_verdicts.jsonl 的 repaired_fields 断言
    「字段值等于 from 或 to」，否则 SystemExit。本轮 fix 改写了某个被订正字段时，把该订正的
    to 更新为落地文本（原 to 记入 faultcheck_superseded.previous_to）。"""
    lines = [l for l in read_text(EVIDENCE_VERDICTS)[0].splitlines() if l.strip()]
    verdicts = [json.loads(l) for l in lines]
    touched, changed = [], False
    for v in verdicts:
        eid = v.get("entry_id")
        fix = final.get(eid)
        if not fix:
            continue
        for rep in v.get("repaired_fields") or []:
            f = rep.get("field")
            if f not in fix or rep.get("to") == fix[f]:
                continue
            sup = rep.setdefault("faultcheck_superseded", {})
            sup.setdefault("previous_to", rep.get("to"))
            sup.update({"applied_at": meta["applied_at"], "to_after_faultcheck": fix[f],
                        "note": "faultcheck 修复在该 ASR 订正之上再改写同一字段，to 已更新为落地文本"})
            rep["to"] = fix[f]
            touched.append({"entry_id": eid, "field": f})
            changed = True
    if changed:
        body = "\r\n".join(json.dumps(v, ensure_ascii=False) for v in verdicts) + "\r\n"
        write_text(EVIDENCE_VERDICTS, body)
    return touched


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--privacy-only" in sys.argv[1:]:
        # 只跑隐私统一：落地表/manifest 已按 faultcheck 收敛过一次，重跑任务二/三会二次改写，
        # 因此把「只扫昵称」单列出来，供昵称新增或范围调整后单独补救。
        priv = privacy_pass()
        print(json.dumps({"privacy_replacements": priv["replacements"],
                          "privacy_files_changed": priv["files_changed"],
                          "self_term_kept": priv["self_term_kept"],
                          "sha_resynced": len(priv["sha_resynced"]),
                          "per_file": priv["per_file"]}, ensure_ascii=False, indent=1))
        return 0
    # ---- 任务一 ----
    priv = privacy_pass()

    # ---- 任务二/三 ----
    agg, entries, final, skipped, conflict = build_plan()
    removes = {}
    for eid in agg["remove"]:
        rec = load_triage()[eid]
        removes[eid] = {"fault_type": rec.get("fault_type_kept", ""),
                        "reason": rec.get("reason", ""), "source": rec.get("_file", "")}

    by_batch = {"b3": {"removes": {}, "fixes": {}}, "b4": {"removes": {}, "fixes": {}},
                "phase2": {"removes": {}, "fixes": {}}, "vod": {"removes": {}, "fixes": {}}}
    for eid, r in removes.items():
        by_batch[batch_of(entries, eid)]["removes"][eid] = r
    for eid, f in final.items():
        by_batch[batch_of(entries, eid)]["fixes"][eid] = f

    meta = {
        "applied_at": "2026-09-22",
        "script": "kb_trial/curation/faultcheck/_faultcheck_apply.py",
        "source": {
            "triage_aggregate": "kb_trial/curation/faultcheck/_triage_agg.json",
            "triage_files": "kb_trial/curation/faultcheck/triage_01..16.json",
            "extract": "kb_trial/curation/faultcheck/_fix_plan.json",
        },
        "counts": {"fix_total": len(agg["fix"]), "fix_applied": len(final),
                   "fix_skipped": len(skipped), "remove_total": len(agg["remove"])},
        "policy": "只改 claim/subject/condition 等派生文本；引文（quotes/evidence 文本）一个字不动。"
                  "移除按批次落在产出器（b3/b4 走 faultcheck_*.json，vod 走 decisions.jsonl 的 reject）。",
    }
    for b in ("b3", "b4", "phase2"):
        payload = dict(by_batch[b])
        payload.update(meta)
        payload["counts"] = dict(meta["counts"],
                                 batch_removes=len(by_batch[b]["removes"]),
                                 batch_fixes=len(by_batch[b]["fixes"]))
        with open(os.path.join(HERE, "faultcheck_%s.json" % b), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

    # ---- vod 轨：claim 改写 + remove 落 decisions.jsonl ----
    # 注意：decisions.jsonl 原文件是 CRLF、行内键序为生产者写出的顺序；这里只改被触及的字段，
    # 逐行按原样重写（不 sort_keys），把 diff 限制在真正改动的行上。
    raw = open(DECISIONS, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    rows = [json.loads(l) for l in raw.splitlines() if l.strip()]
    idx = {(r["doc_id"], r["rule_idx"]): i for i, r in enumerate(rows)}
    vod_fix, vod_remove = 0, 0
    for eid, f in by_batch["vod"]["fixes"].items():
        doc, ridx = eid.rsplit("#r", 1)
        i = idx[(doc, int(ridx))]
        changed = False
        # curated 条的 claim/subject/condition 分别取自 decisions 行的
        # claim / suffix_subject / suffix_condition（见 kb_curation_build.py build_entries）。
        for field, rowkey in (("claim", "claim"), ("subject", "suffix_subject"),
                              ("condition", "suffix_condition")):
            if field in f and rows[i].get(rowkey) != f[field]:
                rows[i][rowkey] = f[field]
                changed = True
        if changed:
            rows[i]["derived_text_repairs_faultcheck"] = {
                "applied_at": meta["applied_at"], "source": meta["source"]["triage_files"],
                "fault_type": f.get("fault_type", ""), "suggestion": f.get("suggestion", ""),
                "note": f.get("note", ""),
            }
            vod_fix += 1
    for eid, r in by_batch["vod"]["removes"].items():
        doc, ridx = eid.rsplit("#r", 1)
        i = idx[(doc, int(ridx))]
        rows[i]["decision"] = "reject"
        rows[i]["reject_reason"] = "faultcheck_remove: %s" % r["reason"]
        rows[i]["audit_kind"] = "faultcheck_remove"
        rows[i]["audit_verdict"] = "remove"
        rows[i]["audit_reason"] = ("对抗性挑刺二审 verdict=remove（%s）；%s"
                                   % (r.get("fault_type", ""), r["reason"]))
        vod_remove += 1
    eol = "\r\n" if crlf else "\n"
    with open(DECISIONS, "wb") as fh:
        fh.write(eol.join(json.dumps(r, ensure_ascii=False) for r in rows).encode("utf-8") + eol.encode("utf-8"))
    overlay_synced = sync_overlay(by_batch["vod"]["fixes"], rows, idx, meta)
    repairs_synced = sync_repairs(final, meta)

    plan_report = {"privacy": priv, "counts": meta["counts"],
                   "by_batch": {b: {"removes": len(by_batch[b]["removes"]),
                                    "fixes": len(by_batch[b]["fixes"])} for b in by_batch},
                   "vod_fix_applied": vod_fix, "vod_remove_applied": vod_remove,
                   "qq_overlay_resynced": overlay_synced, "derived_repairs_resynced": repairs_synced,
                   "fix_skipped": skipped, "fix_remove_conflict": conflict,
                   "applied": final}
    with open(os.path.join(HERE, "_remediation_plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan_report, fh, ensure_ascii=False, indent=1, sort_keys=True)

    print(json.dumps({"privacy_replacements": priv["replacements"],
                      "privacy_files_changed": priv["files_changed"],
                      "self_term_kept": priv["self_term_kept"],
                      "sha_resynced": len(priv["sha_resynced"]),
                      "fix_applied": len(final), "fix_skipped": len(skipped),
                      "remove_total": len(removes), "conflict": conflict,
                      "by_batch": plan_report["by_batch"],
                      "vod_fix": vod_fix, "vod_remove": vod_remove,
                      "qq_overlay_resynced": overlay_synced,
                      "derived_repairs_resynced": repairs_synced},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
