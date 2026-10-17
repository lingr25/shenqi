# -*- coding: utf-8 -*-
"""b3 批已发布条目的引文保真修复（父裁定 2026-09-22）：工单材料 + 回执 + 台账联动，幂等。

背景：旧的隐私规则按形态替换——把每条消息里 6–12 位连续数字整体抹成「[账号已隐去]」，
连带抹掉了机制常数的小数尾部（`0.232322` -> `0.[账号已隐去]`）。材料层随后改为按值脱敏
（只替换导出里真实的 QQ/UID/群号，其余数字一律保留），b4 批工单即按新口径生成；但 b3 批工单
是 18:25 的冻结产物，未随该修复重建。

w000511（qq_wo_b3_182）已先修。本轮修的是**已发布条目里仍带占位**的那四份工单：占位落在已判
keep 的 claim evidence 文本内，使引文不再是逐字原文：

    qq_wo_b3_054 (w000677, c02)  seq33 30/1.08=27.[账号已隐去]
    qq_wo_b3_083 (w000208, c02)  seq26 0.9667-0.[账号已隐去]=3.33334e-05
                                 seq59 鹰角是float(0.[账号已隐去])
                                 seq69 最小距离判定是根号0.[账号已隐去]
    qq_wo_b3_084 (w000211, c01)  seq56 每帧仍然-0.[账号已隐去]
    qq_wo_b3_213 (w001321, c01)  seq8  只有float(0.[账号已隐去])

新文本不是手写：由同窗源按 `kb_curation_qq_expansion_diff.render_new`（材料层修复后的渲染逻辑）
现算，与写入工单的文本逐 seq 严格相等方可通过；逐条另做**账号前提校验**：复原后的数字串必须
不是导出中真实存在的 QQ/UID/群号（与 `identity_numbers` 求交为空），否则报错退出、不得复原。

同步更新：reviews_b3 的 evidence 文本、因占位而过时的 reason/limitations/review_note/excluded 叙述
（只改陈述材料状态的那部分，不改任何 verdict）、source_sha256，并写入 `quote_fidelity_repair` 记录。

幂等：工单已无占位、回执各文本已是对应新文本时，只校验不改写。
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _b3_apply_privacy_fix as P                  # noqa: E402

PLACEHOLDER = '[账号已隐去]'
# 与 kb_curation_validate.py 的隐私闸门同形：6–12 位连续数字（不在小数/数字内部）
ACCOUNT_SHAPE = re.compile(r'(?<![\d.])\d{6,12}(?![\d.])')

TARGETS = {
    'qq_wo_b3_054': 'w000677',
    'qq_wo_b3_083': 'w000208',
    'qq_wo_b3_084': 'w000211',
    'qq_wo_b3_213': 'w001321',
}

# 修复后新收的引文（claim 里被写出的数值在此句之前没有逐字出处）
EVIDENCE_ADDITIONS = {
    ('qq_wo_b3_083', 'c02'): [59],
}

# 回执叙述里因占位而过时的句子：整串精确替换（在全文件内必须唯一命中）
REVIEW_FIXES = {
    'qq_wo_b3_054': [
        ('例子里的「30/1.08=27.77帧」是原文自带的算式与数值，本条不重算',
         '算式原文逐字为「30/1.08=27.77777778」（seq 33），原文下一条自行写作「27.77帧」（seq 34）；'
         'claim 的「30/1.08=27.77」照录原文自己的近似写法，本条不重算、也不代它改写成精确值'),
    ],    'qq_wo_b3_083': [
        ('原文中另两处截断数值被隐私规则抹除为「0.[账号已隐去]」，本条只引用以 1/30 为对比基准的表述与 0.7071/根号2/2 一组',
         '被旧隐私规则误抹的数值已按源复原：seq 59「鹰角是float(0.0333333)」已作为本条引文（claim 中该写法即出此句）；'
         '本窗另两处数值 seq 26「0.9667-0.9666666666=3.33334e-05」与 seq 69「最小距离判定是根号0.000001」本条未引用'),
        ('未给出误差的具体量级',
         '误差的具体量级只在本窗 seq 26 的差值算式里出现（0.9667-0.9666666666=3.33334e-05）；该式还建立在同人自述'
         '「0.96667我随口估的」之上，属临时估计，本条不据此写定量级'),
        ('该条原文为「最小距离判定是根号0.[账号已隐去]」，小数部分在本工单中已被隐私规则抹除，原文含量失，'
         '按判据不得凭自身游戏知识补全或纠正被抹除的数字。',
         '该条原文为「最小距离判定是根号0.000001」（seq 69）。原判 reject 的依据是该处小数被旧隐私规则抹成占位、'
         '原文含量失；材料层改为按值脱敏后该式已可在原文层逐字判读，原依据不再成立。本项属 excluded[]，'
         '本轮只按材料事实同步、不重启 excluded 裁量，verdict 暂保留待后续批次复核。'),
        ('且原始算式含被抹除的小数位，无法判读，故不立命题。',
         '故不立命题；原另举「原始算式含被抹除的小数位，无法判读」一条已因材料层修复而失效'
         '（seq 26 现逐字为「0.9667-0.9666666666=3.33334e-05」），verdict 不变。'),
        ('本窗存在多处被隐私规则抹除的小数（「0.[账号已隐去]」），相关数字型结论（最小距离判定、0.9667 差值算式）'
         '已按判据降级为 reject/pending，未写入 claims，也未用自身游戏知识补全。',
         '本窗原有三处小数被旧隐私规则误抹为「0.[账号已隐去]」占位（seq 26/59/69），材料层改为按值脱敏后'
         '已按源复原为「0.9666666666」「0.0333333」「0.000001」；相关数字型结论（最小距离判定、0.9667 差值算式）'
         '仍按判据留在 excluded[]、未写入 claims，也未用自身游戏知识补全。'),
    ],
    'qq_wo_b3_084': [
        ('一方以「cd大小」正面回答并补「每帧仍然-0.[账号已隐去]」（每帧固定扣减）',
         '一方以「cd大小」正面回答并补「每帧仍然-0.0333333」（每帧固定扣减）'),
        ('每帧扣减量的原话数值已被隐私规则抹除，本条不引用该数字',
         '每帧扣减量的原话数值逐字为 0.0333333（seq 56「每帧仍然-0.0333333」）；本条只照录该句，不据此换算或作通则化'),
        ('每帧扣减量的数字因被隐私抹除未引用。',
         '每帧扣减量的原话数字（0.0333333）已随材料层修复恢复并照录入引文。'),
    ],
    'qq_wo_b3_213': [
        ('（seq 8 把完整被写入值改写为「float(0.[账号已隐去])（0.0333333……）」）',
         '（seq 8 把完整被写入值改写为「只有float(0.0333333)」；该句小数位在被判时曾被旧隐私规则抹为占位，'
         '材料层修复后已按源复原）'),
        ('seq 8 的浮点值为「0.[账号已隐去]」，具体数位在工单材料中已脱敏截断，本条 claim 不写出该数值',
         'seq 8 逐字为「只有float(0.0333333)」（材料层修复后读出；被判时其小数位曾被抹为占位），'
         '本条 claim 不写出该数值'),
        ('seq 8 的浮点值被脱敏截断，使「直接写入值」与「开根来源」的对账关系无法在原文中核对；',
         'seq 8 的浮点值（「只有float(0.0333333)」，材料层修复后已可读出）只给出一个「直接写入的小数」实例，'
         '并不能把四项半径的「直接写入值」与「开根来源」对账关系核对出来；'),
        ('但其性质认定在窗内未闭合（脱敏截断 + 两种互相不确认的解释 + 一次保留）',
         '但其性质认定在窗内未闭合（数值性质在原文层无法对账 + 两种互相不确认的解释 + 一次保留）'),
        ('但本工单材料中 seq 8 的浮点值已脱敏，无法在原文层核对「直接写入」与「开根」的对应；',
         '工单材料中 seq 8 的浮点值（材料层修复后读出为「只有float(0.0333333)」）只给出一个「直接写入的小数」实例，'
         '仍无法在原文层核对四项半径的「直接写入」与「开根」对应；'),
    ],
}


def digit_shape(text):
    """把数字与占位符统一成 #，用于证明改写只动了数字。"""
    return re.sub(r'\[账号已隐去\]|\d+', '#', text)


def account_tokens(text):
    """文本里所有 6–12 位连续数字（含小数内部的数位串），用于账号前提校验。"""
    return set(re.findall(r'\d{6,12}', text))


def check_not_identity(seq, old, new, ctx):
    """复原后的数字不得是导出里真实存在的账号/UID/群号。"""
    ids = {str(v) for v in ctx.get('identity_numbers') or set()}
    hits = account_tokens(new) & ids
    if hits:
        raise SystemExit('seq%s 复原出的数字命中真实身份号，禁止复原：%r（旧文本 %r）'
                         % (seq, sorted(hits), old))
    shaped = ACCOUNT_SHAPE.findall(new)
    if PLACEHOLDER in new:
        raise SystemExit('seq%s 重算文本仍含占位，源未修复：%r' % (seq, new))
    return shaped


def repair_workorder(wo_id, window_id, rendered, ctx):
    path = os.path.join(HERE, 'workorders_b3', wo_id + '.json')
    raw = open(path, 'rb').read().decode('utf-8')
    wo = json.loads(raw)
    msgs = wo['raw_messages']['messages']
    stale = [m for m in msgs if PLACEHOLDER in m['text']]

    report = {'workorder': wo_id, 'window': window_id, 'repaired': [], 'account_check': []}
    if not stale:
        for m in msgs:
            want = rendered.get(m['seq'])
            if want is not None and m['text'] != want:
                raise SystemExit('%s 已无占位，但 seq%s 与重算文本不一致' % (wo_id, m['seq']))
        return raw, [], report

    patched = raw
    for m in stale:
        seq, delivered = m['seq'], m['text']
        want = rendered.get(seq)
        if want is None:
            raise SystemExit('%s seq%s 不在重算结果里' % (wo_id, seq))
        if digit_shape(delivered) != digit_shape(want):
            raise SystemExit('%s seq%s 的差异不只是数字，拒绝改写：%r vs %r' % (wo_id, seq, delivered, want))
        shaped = check_not_identity(seq, delivered, want, ctx)
        before = '"text": %s' % json.dumps(delivered, ensure_ascii=False)
        after = '"text": %s' % json.dumps(want, ensure_ascii=False)
        if before not in patched:
            raise SystemExit('%s seq%s 的 text 字段在文件里不是唯一可定位的字符串' % (wo_id, seq))
        patched = patched.replace(before, after, 1)
        report['repaired'].append({'seq': seq, 'before': delivered, 'after': want})
        report['account_check'].append({'seq': seq, 'kept_number_shapes': sorted(shaped),
                                        'in_identity_set': []})

    if PLACEHOLDER in patched:
        raise SystemExit('%s 改写后仍残留占位，说明还有未处理的消息' % wo_id)
    wo2 = json.loads(patched)
    for m in wo2['raw_messages']['messages']:
        want = rendered.get(m['seq'])
        if want is not None and m['text'] != want:
            raise SystemExit('%s 改写后 seq%s 与重算文本不一致' % (wo_id, m['seq']))
    # 原文件是 CRLF：整文件按字节替换，行尾不受影响
    with open(path, 'wb') as fh:
        fh.write(patched.encode('utf-8'))
    return patched, report['repaired'], report


def apply_review_fixes(rv, wo_id):
    """按 REVIEW_FIXES 精确替换回执叙述；已替换过的（幂等）跳过并校验。"""
    text = json.dumps(rv, ensure_ascii=False, indent=1)
    applied = []
    for old, new in REVIEW_FIXES.get(wo_id, []):
        n_old, n_new = text.count(old), text.count(new)
        if n_old == 0 and n_new >= 1:
            continue                      # 幂等：已是修复后的文本
        if n_old != 1:
            raise SystemExit('%s：待替换串在回执里命中 %d 次（期望 1）：%r' % (wo_id, n_old, old[:60]))
        text = text.replace(old, new)
        applied.append({'before': old, 'after': new})
    return json.loads(text), applied


def sync_evidence(rv, repaired_seqs, additions):
    """evidence 文本与工单同步；按 additions 补入修复后才有逐字出处的引文。"""
    by_seq = {r['seq']: r['after'] for r in repaired_seqs}
    changed, added = [], []
    for c in rv['claims']:
        for ev in c['evidence']:
            if ev['seq'] in by_seq and ev['text'] != by_seq[ev['seq']]:
                changed.append({'local_id': c['local_id'], 'seq': ev['seq'],
                                'before': ev['text'], 'after': by_seq[ev['seq']]})
                ev['text'] = by_seq[ev['seq']]
    for (wo_id, local_id), seqs in additions.items():
        if wo_id != rv['workorder_id']:
            continue
        c = next(x for x in rv['claims'] if x['local_id'] == local_id)
        have = {e['seq'] for e in c['evidence']}
        for seq in seqs:
            if seq in have:
                continue
            text = by_seq.get(seq)
            if text is None:
                raise SystemExit('%s/%s 要补的 seq%s 不在本轮复原列表里' % (wo_id, local_id, seq))
            pos = max([i for i, e in enumerate(c['evidence']) if e['seq'] < seq] or [-1]) + 1
            c['evidence'].insert(pos, {'seq': seq, 'text': text})
            added.append({'local_id': local_id, 'seq': seq, 'text': text, 'inserted_at': pos})
    return changed, added


def main():
    windows, id_order, msg_index, ctx = P.build_context()
    out = {'repairs': [], 'evidence_text_updated': [], 'evidence_added': [],
           'review_texts_fixed': [], 'workorder_sha256': {}, 'placeholders_left': {}}
    for wo_id, window_id in TARGETS.items():
        rendered = {}
        for i, mid in enumerate(P.D.new_message_ids(windows[window_id], id_order)):
            rendered[i + 1] = P.D.render_new(msg_index[mid], ctx)['text']
        raw, repaired, rep = repair_workorder(wo_id, window_id, rendered, ctx)
        wo_sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()

        rv_path = os.path.join(HERE, 'reviews_b3', wo_id + '.json')
        rv_before = json.loads(open(rv_path, encoding='utf-8').read())
        rv_before.pop('quote_fidelity_repair', None)
        rv, text_fixes = apply_review_fixes(rv_before, wo_id)
        changed, added = sync_evidence(rv, repaired, EVIDENCE_ADDITIONS)

        rv['source_sha256'] = wo_sha
        rv['quote_fidelity_repair'] = {
            'applied_at': '2026-09-22',
            'script': 'kb_trial/curation/qq_expansion/_b3_apply_quote_fidelity_fix.py',
            'workorder': wo_id,
            'window_id': window_id,
            'cause': 'b3 工单为 18:25 冻结产物，早于材料层「按值脱敏」修复；旧形态规则把 6–12 位连续数字'
                     '整体抹成占位，连带抹掉了同句机制数值的小数尾部，使已发布条目的引文不再是逐字原文。',
            'repaired_seqs': [r['seq'] for r in repaired],
            'note': '新文本由同窗源按 kb_curation_qq_expansion_diff.render_new 现算，与写入工单的文本逐 seq '
                    '严格相等；改写只改变被误抹的数字（占位与数字统一为 # 后逐字相同），@ 指向与昵称的脱敏'
                    '形态与冻结版逐字相同。逐条另核：复原出的数字串不在导出身份号集合内（非账号）。',
            'verification': '账号前提校验通过：复原后的数字串与材料层身份号集合无交集，工单内占位归零；'
                            '回执 evidence 文本与工单 raw_messages 逐字一致（由 _b3_converge_build.py 复核）。',
        }
        with open(rv_path, 'w', encoding='utf-8', newline='') as fh:
            json.dump(rv, fh, ensure_ascii=False, indent=1)
            fh.write('\n')

        out['repairs'].append(rep)
        out['evidence_text_updated'].extend(changed)
        out['evidence_added'].extend([dict(x, workorder=wo_id) for x in added])
        out['review_texts_fixed'].append({'workorder': wo_id, 'count': len(text_fixes)})
        out['workorder_sha256'][wo_id] = wo_sha
        out['placeholders_left'][wo_id] = raw.count(PLACEHOLDER)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
