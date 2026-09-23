# -*- coding: utf-8 -*-
"""b3 批（260 窗）的读源影响清单：工单原始消息层的修复对 b3 工单是否构成需重读的变化。

与阶段二的 `kb_curation_qq_expansion_diff.py` 同一套实测口径，但作用对象是 b3 批的
`workorders_b3/`（阶段二清单只覆盖其 80 窗，不含 b3）。同时把 b3 工单当前交付的
`raw_messages` 与由同一行源按同一渲染逻辑重算出的结果逐 seq 比对——这是对「当前工单
是否就是修复后的口径」的直接校验，而不是假定。

输出：kb_trial/curation/qq_expansion/review_impact_manifest_b3.json
隐私：只记 seq、计数与原因码，不回显昵称、QQ 号或群号。
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import kb_curation_qq_expansion_diff as D  # noqa: E402
import kb_curation_qq_expansion_materials as M  # noqa: E402

OUT = ROOT / 'kb_trial' / 'curation' / 'qq_expansion'
WORKORDERS = OUT / 'workorders_b3'
MANIFEST = OUT / 'review_impact_manifest_b3.json'


def main():
    cards = {c['window_id']: c for c in M.load_records(M.QQ_CARDS)}
    windows = {w['window_id']: w for w in M.load_records(M.QQ_WINDOWS)}
    old_by_id, ts_sorted, ids_sorted, _ = D.build_old_index()

    speaker_of = {}
    n2s = {}
    for m in M.load_records(M.QQ_MESSAGES):
        speaker_of[str(m['msg_id'])] = m.get('speaker_id')
        if m.get('nick') and m.get('speaker_id'):
            n2s.setdefault(m['nick'], set()).add(m['speaker_id'])
    id_order = M.IdOrder()
    msg_index = {}
    for msg_id, ts, text in M.load_chat_export(M.QQ_CHAT_EXPORT)[0]:
        msg_index[msg_id] = {'msg_id': msg_id, 'ts': ts, 'text': text,
                             'speaker_id': speaker_of.get(msg_id),
                             'time_str': M._fmt_ts(ts)}
        id_order.add(msg_id, ts)
    nick_unique = {n: next(iter(s)) for n, s in n2s.items() if len(s) == 1}
    _, nick_redactor = M.build_nick_redactor(set(n2s), nick_unique)
    ctx = {'nick_unique': nick_unique,
           'account_numbers': set(speaker_of.values()),
           'nick_redactor': nick_redactor}

    index = json.loads((WORKORDERS / 'index.json').read_text(encoding='utf-8'))
    entries = []
    tally = Counter()
    delivered_mismatch = []

    for e in index['workorders']:
        wid = e['window_id']
        wo_path = ROOT / e['file'] if not Path(e['file']).is_absolute() else Path(e['file'])
        wo = json.loads(wo_path.read_text(encoding='utf-8'))
        shipped = {m['seq']: m for m in wo['raw_messages']['messages']}

        w = windows.get(wid) or {}
        card = cards.get(wid) or {}
        cited_set = {str(i) for i in (card.get('source_msg_ids') or [])}

        old_ids = D.old_message_ids(w, ts_sorted, ids_sorted)
        new_ids = D.new_message_ids(w, id_order)
        old_seq = {mid: i + 1 for i, mid in enumerate(old_ids)}
        new_seq = {mid: i + 1 for i, mid in enumerate(new_ids)}

        changed_seq, reasons = [], set()
        for mid in new_ids:
            newm = D.render_new(msg_index[mid], ctx)
            newm['seq'] = new_seq[mid]
            if mid not in old_seq:
                reasons.add('missing_before')
                changed_seq.append(new_seq[mid])
            else:
                oldm = D.render_old(msg_index[mid], nick_unique, cited_set, new_seq[mid])
                if oldm.get('text') != newm.get('text'):
                    if len(msg_index[mid]['text']) > D.MAX_RAW_CHARS:
                        reasons.add('was_truncated')
                    full_old = D.render_old(msg_index[mid], nick_unique, cited_set, new_seq[mid])
                    full_old['text'] = D._old_redact_full(msg_index[mid]['text'], nick_unique,
                                                         msg_index[mid].get('speaker_id'))
                    if full_old['text'] != newm['text']:
                        reasons.add('identity_redacted')
                    changed_seq.append(new_seq[mid])

            # 当前交付的工单是否就是修复后的文本？（逐 seq 直接核）
            got = shipped.get(new_seq[mid])
            if got is None:
                delivered_mismatch.append('%s seq%s: 交付工单缺少该 seq' % (e['workorder_id'], new_seq[mid]))
            elif got.get('text') != newm.get('text'):
                delivered_mismatch.append('%s seq%s: 交付文本与重算文本不一致'
                                          % (e['workorder_id'], new_seq[mid]))

        dropped = [mid for mid in old_ids if mid not in new_seq]
        if dropped:
            reasons.add('dropped_before_only')

        for r in reasons:
            tally[r] += 1
        entries.append({
            'workorder_id': e['workorder_id'],
            'file': e['file'],
            'window_id': wid,
            'message_count_before': len(old_ids),
            'message_count_after': len(new_ids),
            'changes_total': len(changed_seq),
            'dropped_before_only': len(dropped),
            'needs_reread': bool(changed_seq),
            'changed_seq': sorted(changed_seq),
            'reasons': sorted(reasons),
        })

    affected = [x for x in entries if x['needs_reread']]
    clipped_before = 0
    for e in index['workorders']:
        w = windows.get(e['window_id']) or {}
        for mid in D.old_message_ids(w, ts_sorted, ids_sorted):
            m = old_by_id.get(mid)
            if m and len(m.get('text') or '') > D.MAX_RAW_CHARS:
                clipped_before += 1

    manifest = {
        'note': 'b3 批（260 窗）的读源影响清单：说明工单原始消息层修复后哪些 b3 工单的读源依据发生变化，'
                '供审核员只重读受影响的部分。口径与阶段二 review_impact_manifest.json 一致，'
                '但覆盖对象是 workorders_b3/。仅列 seq 与原因，不含任何昵称/QQ号/群号。',
        'batch': 'b3',
        'phase': 'phase3_b3_full_convergence',
        'counterpart': 'kb_trial/curation/qq_expansion/review_impact_manifest.json（阶段二 80 窗，不含 b3）',
        'what_changed': {
            'was_truncated': '旧版正文本截断到 280 字符，新版为全文。',
            'identity_redacted': '新版去除了该消息里的身份信息（正文昵称/账号数字/@对象改写），机制数值保留。',
            'missing_before': '旧版取数范围过窄而整条漏掉的消息，新版补入。',
            'dropped_before_only': '旧版按时间范围误取、而本窗并不包含的消息，新版不再收录。',
        },
        'truncation_verified': {
            'old_slice_messages_over_280_chars': clipped_before,
            'note': '生成前后均以实测统计。',
        },
        'delivered_text_check': {
            'note': '本批新增校验：把每个 b3 工单当前交付的 raw_messages 文本与该行源按同一渲染逻辑'
                    '重算出的文本逐 seq 比对。不一致条数为 0 即表示交付工单本身就是修复后的口径，'
                    '审核员读到的就是当前源；不为 0 则说明该批工单仍停留在修复前生成的版本，'
                    '交付文本里仍带旧规则抹出的身份占位（机制数值被一并抹掉），需重读或重建工单。',
            'compared_workorders': len(index['workorders']),
            'mismatches': len(delivered_mismatch),
            'mismatch_samples': delivered_mismatch[:20],
        },
        'unaffected_note': '未列出的工单其 raw_messages 逐条一致，审核员无需重读。',
        'sources': {
            'messages_before_total': sum(x['message_count_before'] for x in entries),
            'messages_after_total': sum(x['message_count_after'] for x in entries),
        },
        'affected_counts': dict(tally),
        'affected_workorders': len(affected),
        'total_workorders': len(entries),
        'total_changed_messages': sum(len(x['changed_seq']) for x in affected),
        'entries': entries,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n',
                        encoding='utf-8')
    print(json.dumps({
        'affected_workorders': len(affected),
        'total_workorders': len(entries),
        'total_changed_messages': manifest['total_changed_messages'],
        'affected_counts': dict(tally),
        'delivered_mismatches': len(delivered_mismatch),
        'sources': manifest['sources'],
    }, ensure_ascii=False, indent=1))
    return 1 if delivered_mismatch else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
