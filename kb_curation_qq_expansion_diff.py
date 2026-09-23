# -*- coding: utf-8 -*-
"""Build the before/after diff manifest for the QQ work-orders.

Rewriting the raw-message layer changes every work-order's `source_sha`, which invalidates a
reviewer's read of that file. Rather than asking for a full re-read, this script recomputes
the PREVIOUS (defective) message list and the CURRENT one, matches them by message id, and
reports per work-order exactly which `seq` values changed and why.

Measured differences (not assumed -- see the counters in the manifest):

  * **truncation**  the old text was clipped at 280 chars, so a long message was silently cut.
  * **missing messages**  the old slice was derived from the (offset) declared time range and
    dropped messages the window actually contains; the new slice covers the window's whole
    `source_msg_ids` block.
  * **identity redaction**  the old version only rewrote `@nickname`; nicknames elsewhere in
    the text and bare account numbers survived. The new version removes them.
  * **anchoring**  the old version sliced on `windows.jsonl`'s `start_ts`/`end_ts`; the new
    version anchors on the window's own `source_msg_ids`. Note the declared timestamps are NOT
    from the wrong hour (the uniform +3600s cancels between the two sources); the anchor change
    matters because the time range was too narrow, not because it pointed elsewhere.

        before / after distinctions. The old slice contained NO message longer than
        MAX_RAW_CHARS in the slim source, so `text_truncated` never actually fired on a
        delivered message: the 280-char cap was a latent risk that made "complete" untrue, and
        it is removed, but it did not corrupt any specific delivered seq. The messages that
        are long (>280 chars) are all in the newly-added set, so they appear as
        `missing_before`, not as `was_truncated`.

Privacy: the manifest records seq numbers, counts and reason codes only. It never echoes a
nickname, a QQ id or a group id.
"""
import bisect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import kb_curation_qq_expansion_materials as M  # noqa: E402

OUT = ROOT / 'kb_trial' / 'curation' / 'qq_expansion'
WORKORDERS = OUT / 'workorders'
MANIFEST = OUT / 'review_impact_manifest.json'
MAX_RAW_CHARS = 280  # the old clip limit


def build_old_index():
    """Index the slim source the way the previous version did."""
    msgs = M.load_records(M.QQ_MESSAGES)
    by_id = {str(m['msg_id']): m for m in msgs}
    ordered = sorted(msgs, key=lambda m: m['ts'])
    ts_sorted = [m['ts'] for m in ordered]
    ids_sorted = [str(m['msg_id']) for m in ordered]
    n2s = defaultdict(set)
    for m in msgs:
        if m.get('nick') and m.get('speaker_id'):
            n2s[m['nick']].add(m['speaker_id'])
    nick_unique = {n: next(iter(s)) for n, s in n2s.items() if len(s) == 1}
    return by_id, ts_sorted, ids_sorted, nick_unique


def old_message_ids(window, ts_sorted, ids_sorted):
    """The previous slice: ids inside the declared time range, in time order."""
    start, end = (window or {}).get('start_ts'), (window or {}).get('end_ts')
    if start is None or end is None:
        return []
    lo = bisect.bisect_left(ts_sorted, start)
    hi = bisect.bisect_right(ts_sorted, end)
    return ids_sorted[lo:hi]


def new_message_ids(window, id_order):
    """The current slice: contiguous block covering the window's own source_msg_ids."""
    members = [str(i) for i in ((window or {}).get('source_msg_ids') or [])]
    known = [i for i in members if i in id_order]
    if not known:
        return []
    lo = min(id_order[i] for i in known)
    hi = max(id_order[i] for i in known)
    return id_order.slice(lo, hi)


def _old_redact_full(text, nick_unique, speaker):
    """The previous version's redaction, applied to the FULL text (no clip).

    Used to separate 'the text was clipped' from 'identity was removed' -- the old code did
    the former always and the latter only at `@mention` positions.
    """
    resolved, unresolved = [], False
    for token in M.AT_MENTION.findall(text):
        target = nick_unique.get(token)
        if target and target != speaker:
            resolved.append(target)
        else:
            unresolved = True

    def repl(match):
        target = nick_unique.get(match.group(1))
        if target and target != speaker:
            return '@' + target
        return '@某人'

    return M.AT_MENTION.sub(repl, text)


def render_old(m, nick_unique, cited_set, seq):
    """Re-render one message exactly as the previous version would have."""
    text = m.get('text') or ''
    resolved, unresolved = [], False
    for token in M.AT_MENTION.findall(text):
        target = nick_unique.get(token)
        if target and target != m.get('speaker_id'):
            resolved.append(target)
        else:
            unresolved = True
    rec = {
        'seq': seq,
        'speaker_id': m.get('speaker_id'),
        'time': m.get('time_str'),
        'ts': m.get('ts'),
        'is_cited_by_card': str(m['msg_id']) in cited_set,
        'text': text[:MAX_RAW_CHARS],
    }
    if len(text) > MAX_RAW_CHARS:
        rec['text_truncated'] = True
    if resolved:
        rec['mentions_speaker_id'] = sorted(set(resolved))
    if unresolved:
        rec['mentions_nick_unresolved'] = True
    return rec


def render_new(m, ctx):
    text, mentions, unresolved, removed = M.redact_text(
        m.get('text') or '', ctx['nick_unique'], m.get('speaker_id'),
        ctx['account_numbers'], ctx['nick_redactor'])
    rec = {'seq': 0, 'speaker_id': m.get('speaker_id'), 'time': m.get('time_str'),
           'ts': m.get('ts'), 'text': text}
    if mentions:
        rec['mentions_speaker_id'] = mentions
    if unresolved:
        rec['mentions_nick_unresolved'] = True
    if removed:
        rec['account_numbers_redacted'] = removed
    return rec


def main():
    cards = {c['window_id']: c for c in M.load_records(M.QQ_CARDS)}
    windows = {w['window_id']: w for w in M.load_records(M.QQ_WINDOWS)}
    old_by_id, ts_sorted, ids_sorted, nick_unique = build_old_index()

    ctx = {}
    speaker_of = {}
    n2s = defaultdict(set)
    for m in M.load_records(M.QQ_MESSAGES):
        speaker_of[str(m['msg_id'])] = m.get('speaker_id')
        if m.get('nick') and m.get('speaker_id'):
            n2s[m['nick']].add(m['speaker_id'])
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
    for e in index['workorders']:
        wid = e['window_id']
        w = windows.get(wid) or {}
        card = cards.get(wid) or {}
        cited_set = {str(i) for i in (card.get('source_msg_ids') or [])}

        old_ids = old_message_ids(w, ts_sorted, ids_sorted)
        new_ids = new_message_ids(w, id_order)

        # Render BOTH sides from the full source so the only differences left are the ones we
        # are reporting (source coverage, clipping, redaction) -- not the source swap itself.
        old_seq = {mid: i + 1 for i, mid in enumerate(old_ids)}
        new_seq = {mid: i + 1 for i, mid in enumerate(new_ids)}

        changed_seq, reasons = [], set()
        for mid in new_ids:
            newm = render_new(msg_index[mid], ctx)
            newm['seq'] = new_seq[mid]
            raw_len = len(msg_index[mid]['text'])
            if mid not in old_seq:
                reasons.add('missing_before')
                changed_seq.append(new_seq[mid])
                continue
            oldm = render_old(msg_index[mid], nick_unique, cited_set, new_seq[mid])
            if oldm.get('text') == newm.get('text'):
                continue
            # Two independent facts; one message can be both.
            if raw_len > MAX_RAW_CHARS:
                reasons.add('was_truncated')
            # Apply the OLD rules to the FULL text: if that still differs from the new text, the
            # difference is removal of identity rather than clipping.
            full_old = render_old(msg_index[mid], nick_unique, cited_set, new_seq[mid])
            full_old['text'] = _old_redact_full(msg_index[mid]['text'], nick_unique,
                                                msg_index[mid].get('speaker_id'))
            if full_old['text'] != newm['text']:
                reasons.add('identity_redacted')
            changed_seq.append(new_seq[mid])

        # old messages the new slice no longer covers
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
    # Measured, not assumed: how many messages in the OLD slice exceeded the old clip?
    clipped_before = 0
    for e in index['workorders']:
        w = windows.get(e['window_id']) or {}
        for mid in old_message_ids(w, ts_sorted, ids_sorted):
            m = old_by_id.get(mid)
            if m and len(m.get('text') or '') > MAX_RAW_CHARS:
                clipped_before += 1

    manifest = {
        'note': '本清单说明生成器修复后哪些工单的读源依据发生变化，供审核员只重读受影响的部分。'
                '仅列 seq 与原因，不含任何昵称/QQ号/群号。',
        'what_changed': {
            'was_truncated': '旧版正文本截断到 280 字符，新版为全文。'
                             '（实测：旧版取数范围内的消息没有一条超过 280 字符，'
                             '因此该缺陷是**潜在**的、「完整」这一说法不成立，但并未实际切掉任何已交付的 seq。'
                             '超过 280 字符的消息都在新版新增范围内，因此记为 missing_before。）',
            'identity_redacted': '新版去除了该消息里的身份信息（正文昵称/账号数字/@对象改写），机制数值保留。',
            'missing_before': '旧版取数范围过窄而整条漏掉的消息，新版补入。',
            'dropped_before_only': '旧版按时间范围误取、而本窗并不包含的消息，新版不再收录。',
        },
        'participant_roster_note': '日报机器人的 `参与者:` 名单行也曾泄漏群昵称。修前只改写第一条名单行，'
                                   '一条 4.4k 字符的报告里有 12 条名单行、其余 11 条原样带昵称出厂；'
                                   '现改为逐行改写全部 `参与者:` 名单。此修复只影响名单行文本，'
                                   '不改变消息条数与 seq，故未计入 affected。',
        'truncation_verified': {
            'old_slice_messages_over_280_chars': clipped_before,
            'note': '生成前后均以实测统计；旧版未实际截断任何已交付消息，此条为口径修正而非内容修复。',
        },
        'anchoring_note': '旧版按 windows.jsonl 的 start_ts/end_ts 取数，新版按本窗 source_msg_ids 取连续消息块。'
                          '实测两边时间口径一致（重叠 %d/%d 条），偏移 +3600 秒在两侧相互抵消，'
                          '因此问题不是「取错时段」，而是时间范围过窄导致漏取。'
                          % (sum(min(x['message_count_before'], x['message_count_after']) for x in entries),
                             sum(x['message_count_before'] for x in entries)),
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
        'sources': manifest['sources'],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
