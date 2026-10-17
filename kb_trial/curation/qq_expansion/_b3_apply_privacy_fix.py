# -*- coding: utf-8 -*-
"""b3 批 w000511（qq_wo_b3_182）的隐私占位修复：工单材料 + 回执同步，幂等。

背景：旧的隐私规则按形态替换——把每条消息里 6–12 位连续数字整体抹成「[账号已隐去]」，
连带抹掉了机制常数的小数尾部（`0.232322` -> `0.[账号已隐去]`）。材料层随后改为按值脱敏
（见 `kb_curation_qq_expansion_materials.redact_text` 的 `identity_numbers` 分支：只替换导出
里真实的 QQ/UID/群号，其余数字一律保留），b4 批工单即按新口径生成。

但 b3 批工单是 18:25 的冻结产物，未随该修复重建，故 w000511 的两条关键消息仍以占位形态交付。
本脚本只把这一份工单里被误抹的两条消息改回原文，且新文本不是手写的：必须与「同一行源按
修复后的渲染逻辑重算」的结果逐字相同，否则报错退出。同步更新回执的 evidence 文本与
source_sha256，并把回执里因占位而过时的那条 limitation 改写为修复后的事实。

幂等：若工单已无占位、且回执 evidence 与重算文本一致、source_sha256 已对齐，则只校验不改写。
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

import kb_curation_qq_expansion_diff as D          # noqa: E402
import kb_curation_qq_expansion_materials as M     # noqa: E402

WORKORDER_ID = 'qq_wo_b3_182'
WINDOW_ID = 'w000511'
WO_PATH = os.path.join(HERE, 'workorders_b3', WORKORDER_ID + '.json')
RV_PATH = os.path.join(HERE, 'reviews_b3', WORKORDER_ID + '.json')
PLACEHOLDER = '[账号已隐去]'

REPAIR_NOTE = (
    '材料层修复（按值脱敏，机制数值保留）落地后，本条工单在 18:25 冻结时仍带旧规则的占位。'
    '本轮按同一行源用修复后的渲染逻辑重算，把 seq1/seq3 两条被误抹的消息改回原文；'
    '改写仅涉及被抹掉的数字，@ 指向与昵称的脱敏形态与冻结版逐字相同。'
)


def build_context():
    """复刻 kb_curation_qq_expansion_diff_b3.py 的取数与渲染上下文。"""
    windows = {w['window_id']: w for w in M.load_records(M.QQ_WINDOWS)}
    speaker_of = {}
    n2s = defaultdict(set)
    for m in M.load_records(M.QQ_MESSAGES):
        speaker_of[str(m['msg_id'])] = m.get('speaker_id')
        if m.get('nick') and m.get('speaker_id'):
            n2s[m['nick']].add(m['speaker_id'])
    id_order = M.IdOrder()
    msg_index = {}
    rows, identity_numbers = M.load_chat_export(M.QQ_CHAT_EXPORT)
    for msg_id, ts, text in rows:
        msg_index[msg_id] = {'msg_id': msg_id, 'ts': ts, 'text': text,
                             'speaker_id': speaker_of.get(msg_id),
                             'time_str': M._fmt_ts(ts)}
        id_order.add(msg_id, ts)
    nick_unique = {n: next(iter(s)) for n, s in n2s.items() if len(s) == 1}
    _, nick_redactor = M.build_nick_redactor(set(n2s), nick_unique)
    ctx = {'nick_unique': nick_unique,
           'account_numbers': set(v for v in speaker_of.values() if v),
           'nick_redactor': nick_redactor,
           'identity_numbers': identity_numbers | {v for v in speaker_of.values() if v}}
    return windows, id_order, msg_index, ctx


def rendered_window(windows, id_order, msg_index, ctx):
    """修复后的口径下，本窗应交付的 raw_messages 文本（seq -> text）。"""
    new_ids = D.new_message_ids(windows[WINDOW_ID], id_order)
    out = {}
    for i, mid in enumerate(new_ids):
        rec = D.render_new(msg_index[mid], ctx)
        out[i + 1] = rec['text']
    return out


def digit_shape(text):
    """把数字与占位符统一成 #，用于证明改写只动了数字。"""
    return re.sub(r'\[账号已隐去\]|\d+', '#', text)


def repair_workorder(rendered):
    raw = open(WO_PATH, encoding='utf-8').read()
    wo = json.loads(raw)

    if PLACEHOLDER not in raw:
        # 已修复：只做一致性校验。
        for m in wo['raw_messages']['messages']:
            want = rendered.get(m['seq'])
            if want is not None and m['text'] != want:
                raise SystemExit('已无占位，但 seq%s 与重算文本不一致' % m['seq'])
        return raw, wo, []

    stale = [m for m in wo['raw_messages']['messages'] if PLACEHOLDER in m['text']]
    patched = raw
    repaired_seqs = []
    for m in stale:
        seq, delivered = m['seq'], m['text']
        want = rendered.get(seq)
        if want is None:
            raise SystemExit('seq%s 不在重算结果里' % seq)
        if digit_shape(delivered) != digit_shape(want):
            raise SystemExit('seq%s 的差异不只是数字，拒绝改写：%r vs %r' % (seq, delivered, want))
        if PLACEHOLDER in want:
            raise SystemExit('seq%s 重算文本仍含占位，源未修复：%r' % (seq, want))
        # 以「整条 text 字段整体替换」的方式落地，不逐个占位子串猜：文本里可能有数处占位。
        before = '"text": %s' % json.dumps(delivered, ensure_ascii=False)
        after = '"text": %s' % json.dumps(want, ensure_ascii=False)
        if before not in patched:
            raise SystemExit('seq%s 的 text 字段在文件里不是唯一可定位的字符串' % seq)
        patched = patched.replace(before, after, 1)
        repaired_seqs.append({'seq': seq, 'before': delivered, 'after': want})

    if PLACEHOLDER in patched:
        raise SystemExit('改写后仍残留占位，说明还有未处理的消息')
    if patched == raw:
        raise SystemExit('未发生改写')

    wo2 = json.loads(patched)
    for m in wo2['raw_messages']['messages']:
        want = rendered.get(m['seq'])
        if want is not None and m['text'] != want:
            raise SystemExit('改写后 seq%s 与重算文本不一致' % m['seq'])
    with open(WO_PATH, 'w', encoding='utf-8', newline='') as fh:
        fh.write(patched)
    return patched, wo2, repaired_seqs


def repair_review(wo_sha, repaired_seqs):
    rv = json.loads(open(RV_PATH, encoding='utf-8').read())
    by_seq = {r['seq']: r['after'] for r in repaired_seqs}
    changed = []
    for c in rv['claims']:
        for ev in c['evidence']:
            if ev['seq'] in by_seq and ev['text'] != by_seq[ev['seq']]:
                changed.append({'local_id': c['local_id'], 'seq': ev['seq'],
                                'before': ev['text'], 'after': by_seq[ev['seq']]})
                ev['text'] = by_seq[ev['seq']]

    c02 = next(c for c in rv['claims'] if c['local_id'] == 'c02')
    stale_lim = '系数部分在工单内已被隐私规则隐去，无法复核算式'
    fixed_lim = ('原算式已按原文逐字恢复（10*0.0333333*3=0.999999），可复核；'
                 '但原文说「每格」，而该算式是 3 格累计差 1e-6，「每格」与「累计」在原文中不可区分')
    lims = []
    for l in c02.get('limitations') or []:
        if l.startswith(stale_lim):
            lims.append(fixed_lim)
        elif l == '原文只写「误差」未给单位与量纲（距离/平方距离未区分），不得据此换算或通则化':
            lims.append(l)
        else:
            lims.append(l)
    c02['limitations'] = lims
    if not any(l.startswith('原算式已按原文逐字恢复') for l in lims):
        raise SystemExit('c02 limitation 未被替换，回执形态与预期不符')
    c02['reason'] = c02['reason'].replace(
        'seq 3 给出算式（原文以 10*系数*3 形式书写）',
        'seq 3 给出算式「弹道飞行本身就是10*0.0333333*3=0.999999」')

    rv['source_sha256'] = wo_sha
    rv['material_repair'] = {
        'applied_at': '2026-09-21',
        'script': 'kb_trial/curation/qq_expansion/_b3_apply_privacy_fix.py',
        'workorder': WORKORDER_ID,
        'window_id': WINDOW_ID,
        'cause': 'b3 工单为 18:25 冻结产物，早于材料层「按值脱敏」修复，故仍带旧形态规则的占位；b4 批（20:20）已按新口径生成。',
        'repaired_seqs': [r['seq'] for r in repaired_seqs],
        'note': REPAIR_NOTE,
        'verification': '新文本由同窗源按 kb_curation_qq_expansion_diff.render_new 现算，与写入文本逐 seq 严格相等；改写只改变数字（占位形态统一为 # 后逐字相同）。',
    }
    with open(RV_PATH, 'w', encoding='utf-8', newline='') as fh:
        json.dump(rv, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    return changed


def main():
    windows, id_order, msg_index, ctx = build_context()
    rendered = rendered_window(windows, id_order, msg_index, ctx)
    raw, wo, repaired = repair_workorder(rendered)
    wo_sha = hashlib.sha256(open(WO_PATH, 'rb').read()).hexdigest()
    changed = repair_review(wo_sha, repaired)
    print(json.dumps({
        'workorder': WORKORDER_ID,
        'window': WINDOW_ID,
        'repaired_messages': [{'seq': r['seq'], 'before': r['before'], 'after': r['after']}
                              for r in repaired],
        'evidence_texts_updated': changed,
        'workorder_sha256': wo_sha,
        'placeholder_left_in_workorder': raw.count(PLACEHOLDER),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
