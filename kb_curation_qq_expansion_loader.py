# -*- coding: utf-8 -*-
"""Incremental loader: turn the approved QQ-expansion manifest into curated entries.

`kb_curation_qq_expansion.py` adjudicates the 80-window trial and writes
``qq_expansion/approved_manifest.json`` (status ``proposed_pending_parent_approval``).
This module is the only thing that may turn those propositions into entries in
``kb_trial/curated_high_quality.json``, and it does so under its own gate:

  * Nothing is accepted until the manifest itself is approved. While the manifest still
    carries a ``proposed_*`` status the loader is inert and the shipped file keeps its
    existing entry count; ``--allow-proposed`` exists so the merge can be exercised
    against a candidate path without touching the shipped set. After the merge is written
    the manifest is moved to ``approved_merged``; that status is terminal and still loads,
    so a rebuild reproduces the same file instead of silently dropping the expansion.
  * Every entry id is ``qq_expansion:<window_id>:<local_id>`` and must be unique, both
    within the manifest and against every entry already in the shipped file. A collision
    is an error, never a silent overwrite.
  * No entry may ship with an automatic review status. The expansion ships as
    ``agent_verified`` with ``scope=text_source_only`` and a per-entry reason that names
    what supports the claim; ``auto_screened``/``auto`` is rejected outright.
  * The manifest's own integrity is re-verified here rather than trusted: the workorder
    and review are re-read from disk, the review's ``source_sha256`` must still match the
    frozen workorder BYTES, the audit's decision for that pair must still be ``keep``, and
    every quote must still match ``raw_messages`` text character-for-character.

The loader never edits an existing entry and never re-derives an existing claim: it only
appends. That is what keeps the 663 already-curated entries byte-identical when this runs.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPANSION = ROOT / 'kb_trial' / 'curation' / 'qq_expansion'
WORKORDERS = EXPANSION / 'workorders'
REVIEWS = EXPANSION / 'final_reviews'
AUDIT = EXPANSION / 'audit_decisions.json'
MANIFEST = EXPANSION / 'approved_manifest.json'

# Stage-3 b3 batch (260 windows / 386 claims, keep 319 after the post-material-repair reaudit). Same schema, its own materials.
WORKORDERS_B3 = EXPANSION / 'workorders_b3'
REVIEWS_B3 = EXPANSION / 'reviews_b3'
AUDIT_B3 = EXPANSION / 'audit_decisions_b3.json'
MANIFEST_B3 = EXPANSION / 'approved_manifest_b3.json'

# Stage-4 b4 batch (441 windows / 572 claims, keep 508 after the parent ruling). Same schema.
WORKORDERS_B4 = EXPANSION / 'workorders_b4'
REVIEWS_B4 = EXPANSION / 'reviews_b4'
AUDIT_B4 = EXPANSION / 'audit_decisions_b4.json'
MANIFEST_B4 = EXPANSION / 'approved_manifest_b4.json'

BATCHES = {
    'phase2': {
        'workorders': WORKORDERS,
        'reviews': REVIEWS,
        'audit_path': AUDIT,
        'manifest': MANIFEST,
        'payload_key': 'qq_expansion',
        'manifest_label': 'approved_manifest.json',
        'claim_section': 'QQ扩展(阶段二试批)',
        'note': '阶段二 80 窗试批的增量条目。只追加，不改写既有条目；证据为已脱敏的 QQ 群聊片段，'
                '引文与冻结工单 raw_messages 逐字一致。',
        'derivation_note': '本条由阶段二 80 窗试批复审产生：final_reviews 的该窗口候选经逐条回读 raw_messages 后'
                           '由 audit_decisions.json 判为 keep，再由 approved_manifest.json 汇总。'
                           'claim 不是上游窗口标题。',
    },
    'b3': {
        'workorders': WORKORDERS_B3,
        'reviews': REVIEWS_B3,
        'audit_path': AUDIT_B3,
        'manifest': MANIFEST_B3,
        'payload_key': 'qq_expansion_b3',
        'manifest_label': 'approved_manifest_b3.json',
        'claim_section': 'QQ扩展(阶段三b3批)',
        'note': '阶段三 b3 批（260 窗）的增量条目。只追加，不改写既有条目；证据为已脱敏的 QQ 群聊片段，'
                '引文与冻结工单 raw_messages 逐字一致。',
        'derivation_note': '本条由阶段三 b3 批（260 窗）全量收敛审读产生：reviews_b3 的该窗口候选经逐条回读 '
                           'raw_messages 后由 audit_decisions_b3.json 裁定，再由 approved_manifest_b3.json 汇总。'
                           'claim 不是上游窗口标题。',
    },
    'b4': {
        'workorders': WORKORDERS_B4,
        'reviews': REVIEWS_B4,
        'audit_path': AUDIT_B4,
        'manifest': MANIFEST_B4,
        'payload_key': 'qq_expansion_b4',
        'manifest_label': 'approved_manifest_b4.json',
        'claim_section': 'QQ扩展(阶段四b4批)',
        'note': '阶段四 b4 批（441 窗）的增量条目。只追加，不改写既有条目；证据为已脱敏的 QQ 群聊片段，'
                '引文与冻结工单 raw_messages 逐字一致。',
        'derivation_note': '本条由阶段四 b4 批（441 窗 / 572 条 claim）全量收敛审读产生：reviews_b4 的该窗口候选'
                           '经逐条回读 raw_messages 后由 audit_decisions_b4.json 裁定，再由 '
                           'approved_manifest_b4.json 汇总，并经父对 28 条存疑的逐项裁决（5 条降 pending、'
                           '3 条维持 keep、7 处改写批准后入库）。claim 不是上游窗口标题。',
    },
}

ID_PREFIX = 'qq_expansion'
APPROVED_STATUS = 'approved'
# Once the merge has actually been written to the shipped file the manifest moves to this
# terminal status, so a later re-run does not describe the merge as still pending.
MERGED_STATUS = 'approved_merged'
CLAIM_SECTION = 'QQ扩展(阶段二试批)'

DISCLAIMER = ('草稿层条目：本层是草稿，不是官方发布；数值与机制结论在用于生产前应回看引文所指时刻的原片。'
              '本条的来源是 QQ 群聊片段（已脱敏，不含群号、QQ 号与昵称），不是录播轨；'
              '与录播轨条目产生分歧时按 conflict_policy 并列呈现、留待人工判断。')

CONFLICT_POLICY = ('no automatic precedence: where sources disagree, all sides must be shown '
                   'and the disagreement left standing for a human to resolve; nothing is '
                   'auto-adjudicated by source layer')


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha256_text(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def entry_id(window_id, local_id):
    return '%s:%s:%s' % (ID_PREFIX, window_id, local_id)


def manifest_is_approved(manifest):
    return str(manifest.get('status', '')).strip().lower() in (APPROVED_STATUS, MERGED_STATUS)


def load_manifest(path=MANIFEST):
    return _load(path)


def verify_entry(item, workorders=WORKORDERS, reviews=REVIEWS, audit=None):
    """Re-verify one manifest entry against the frozen materials. Returns a list of errors.

    ``audit`` is the parsed audit_decisions.json payload (or None to skip that cross-check).
    """
    errs = []
    wid, lid = item['workorder_id'], item['local_id']
    wo_path = Path(workorders) / ('%s.json' % wid)
    rv_path = Path(reviews) / ('%s.json' % wid)
    if not wo_path.exists():
        return ['%s/%s: workorder file missing' % (wid, lid)]
    if not rv_path.exists():
        return ['%s/%s: review file missing' % (wid, lid)]
    wo, rv = _load(wo_path), _load(rv_path)

    if rv.get('source_sha256') != hashlib.sha256(wo_path.read_bytes()).hexdigest():
        errs.append('%s/%s: review no longer matches the frozen workorder bytes' % (wid, lid))

    if wo['window']['window_id'] != item['window_id']:
        errs.append('%s/%s: window_id %r does not match the workorder'
                    % (wid, lid, item['window_id']))

    cand = next((c for c in (rv.get('claims') or []) if c.get('local_id') == lid), None)
    if cand is None:
        errs.append('%s/%s: not present in the review claims' % (wid, lid))
    else:
        if cand.get('scope') != item.get('scope'):
            errs.append('%s/%s: scope drifted from the review' % (wid, lid))

    if audit is not None:
        dec = next((d for d in audit['decisions']
                    if d.get('workorder') == wid and d.get('local_id') == lid), None)
        if dec is None:
            errs.append('%s/%s: audit_decisions.json has no decision for it' % (wid, lid))
        elif dec.get('verdict') != 'keep':
            errs.append('%s/%s: audit verdict is %r, not keep'
                        % (wid, lid, dec.get('verdict')))

    msgs = {m['seq']: m for m in wo['raw_messages']['messages']}
    quotes, seen_seq = [], []
    for ev in item.get('evidence') or []:
        m = msgs.get(ev.get('seq'))
        if m is None:
            errs.append('%s/%s: evidence seq %s not in raw_messages' % (wid, lid, ev.get('seq')))
        elif m['text'] != ev.get('text'):
            errs.append('%s/%s: evidence seq %s is not verbatim' % (wid, lid, ev.get('seq')))
        else:
            quotes.append({'text': m['text'], 'seq': m['seq'], 'time': m.get('time')})
            seen_seq.append(m['seq'])
    if not quotes:
        errs.append('%s/%s: no verbatim evidence survived' % (wid, lid))
        return errs

    expected = _sha256_text(json.dumps(
        [{'seq': e['seq'], 'speaker_id': e['speaker_id'], 'time': e['time'], 'text': e['text']}
         for e in item['evidence']], ensure_ascii=False, sort_keys=True))
    if item.get('evidence_sha256') != expected:
        errs.append('%s/%s: evidence_sha256 does not reproduce' % (wid, lid))

    return errs


def build_entry(item, quotes, seqs, batch='phase2'):
    """Build the curated entry for one verified manifest proposition."""
    cfg = BATCHES[batch]
    eid = entry_id(item['window_id'], item['local_id'])
    citation = {
        'id': 'qq:%s' % item['window_id'],
        'status': 'resolved_qq_span',
        'source_layers': ['qq'],
        'track': 'qq_chat',
        'window_id': item['window_id'],
        'as_of': item.get('as_of'),
        'n_source_msgs': len(quotes),
        'quotes': [{'text': q['text'], 't_start': None, 't_end': None} for q in quotes],
        'note': 'QQ 群聊原文片段，已脱敏：仅保留消息文本与窗口标识，不含群号、QQ 号或昵称。'
                '分段与时间戳见 origin.message_seqs。',
    }
    entry = {
        'id': eid,
        'claim': item['claim'],
        'subject': item.get('subject') or '未标注',
        'condition': item.get('condition') or '未标注',
        'scope': item.get('scope') or '未标注',
        'category': item.get('category'),
        'recorded_ym': (item.get('as_of') or '')[:7].replace('-', '') or None,
        'source_layer': 'QQ群聊',
        'source_layers': ['qq'],
        'track': 'qq_chat',
        'citations': [citation],
        'source_files': [],
        'origin': {
            'trial_doc_id': item['window_id'],
            'trial_rule_idx': item['local_id'],
            'trial_manifest_outputs': 'kb_trial/curation/qq_expansion/%s' % cfg['manifest_label'],
            'upstream_record': 'kb_trial/curation/qq_expansion/%s/%s.json'
                               % (Path(cfg['workorders']).name, item['workorder_id']),
            'card_section': cfg['claim_section'],
            'workorder_id': item['workorder_id'],
            'local_id': item['local_id'],
            'message_seqs': seqs,
            'message_count': len(quotes),
        },
        'claim_derivation': {
            'source': 'kb_trial/curation/qq_expansion/%s' % cfg['manifest_label'],
            'rule_idx': 0,
            'from': item.get('claim_original'),
            'to': item['claim'],
            'note': cfg['derivation_note'],
        },
        'review': {
            'status': 'agent_verified',
            'scope': 'text_source_only',
            'confidence': 'text-source-supported',
            'reason': '%s逐条回读 raw_messages 后确认该命题有逐字文本出处：%s'
                      % (cfg['claim_section'], (item.get('review_reason') or '')[:400]),
            'not_authoritative': True,
        },
        'evidence_review': {
            'status': 'supported',
            'reason': '本条的裁定过程见 kb_trial/curation/qq_expansion/%s 与 '
                      '%s/%s.json；引文已与冻结工单 raw_messages 逐字校验'
                      '（evidence_sha256=%s）。' % (Path(cfg['audit_path']).name,
                                                   Path(cfg['reviews']).name,
                                                   item['workorder_id'], item.get('evidence_sha256')),
            'reviewer_type': 'agent',
            'confidence': 'text-source-supported',
            'review_basis': 'agent 依据冻结工单的 raw_messages 全文与 %s 的 claims 逐条比对；'
                            '未做人工核听、未回看原片，也未在游戏内复现。' % Path(cfg['reviews']).name,
            'limitation': '局限：判定依据是群聊文本片段本身；片段经脱敏、丢失发言者与上下文顺序，'
                          '提问、假设与结论同形，无法从中区分发言者的确定程度。'
                          '「all reviewed」不代表「all correct」。',
            'supports': 'qq_raw_messages_verbatim',
            'source_path': 'kb_trial/curation/qq_expansion/%s/%s.json'
                           % (Path(cfg['workorders']).name, item['workorder_id']),
            'reviewer_model': item.get('reviewer_model'),
        },
        'conflict_policy': CONFLICT_POLICY,
        'disclaimer': DISCLAIMER,
    }
    if item.get('review_limitations'):
        entry['evidence_review']['review_limitations'] = item['review_limitations']
    if item.get('claim_corrected_by_audit'):
        entry['claim_derivation']['corrected_by_audit'] = True
    if item.get('audit_note'):
        entry['claim_derivation']['audit_note'] = item['audit_note']
    return entry


def load_expansion_entries(manifest=None, workorders=WORKORDERS, reviews=REVIEWS,
                           audit_path=AUDIT, require_approved=True, existing_ids=(),
                           batch='phase2'):
    """Return (entries, report). Never mutates the shipped file."""
    cfg = BATCHES[batch]
    if manifest is None:
        manifest = load_manifest(cfg['manifest'])
    audit = _load(audit_path) if Path(audit_path).exists() else None
    report = {'batch': batch, 'manifest': cfg['manifest_label'],
              'manifest_status': manifest.get('status'), 'proposed': len(manifest['entries']),
              'loaded': 0, 'skipped_reason': None, 'entry_ids': [], 'failures': []}

    if require_approved and not manifest_is_approved(manifest):
        report['skipped_reason'] = ('manifest status is %r; the expansion stays inert until the '
                                    'parent approves it (see approved_manifest.json.status)'
                                    % manifest.get('status'))
        return [], report

    entries, seen = [], set(existing_ids)
    for item in manifest['entries']:
        eid = entry_id(item['window_id'], item['local_id'])
        errs = verify_entry(item, workorders, reviews, audit)
        if eid in seen:
            errs.append('%s: duplicate entry id' % eid)
        if errs:
            report['failures'].extend(errs)
            continue
        msgs = {m['seq']: m for m in _load(Path(workorders) / ('%s.json' % item['workorder_id'])
                                          )['raw_messages']['messages']}
        quotes = [{'text': m['text'], 'seq': s} for s in
                  [e['seq'] for e in item['evidence']] for m in [msgs[s]]]
        seqs = [e['seq'] for e in item['evidence']]
        entry = build_entry(item, quotes, seqs, batch=batch)
        if not str(entry['review']['status']).startswith(('agent_verified', 'user_verified')):
            report['failures'].append('%s: refused to ship with review.status=%r'
                                      % (eid, entry['review']['status']))
            continue
        seen.add(eid)
        entries.append(entry)
        report['entry_ids'].append(eid)

    report['loaded'] = len(entries)
    report['failures'] = sorted(set(report['failures']))
    return entries, report


def append_to_payload(payload, entries, report=None, batch='phase2'):
    """Return a NEW payload with the expansion entries appended. The input is not modified."""
    cfg = BATCHES[batch]
    existing = [e['id'] for e in payload['entries']]
    clash = sorted(set(existing) & {e['id'] for e in entries})
    if clash:
        raise SystemExit('expansion entry ids already shipped: %s' % clash)
    out = dict(payload)
    out['entries'] = list(payload['entries']) + list(entries)
    out['entry_count'] = len(out['entries'])
    out[cfg['payload_key']] = {
        'source': 'kb_trial/curation/qq_expansion/%s' % cfg['manifest_label'],
        'note': cfg['note'],
        'appended': len(entries),
        'entry_ids': [e['id'] for e in entries],
        'id_scheme': '%s:<window_id>:<local_id>' % ID_PREFIX,
        'review_status': 'agent_verified',
        'confidence_ceiling': 'text-source-supported',
        'report': report,
    }
    return out


def main():
    import argparse
    import sys
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--in', dest='src', default=str(ROOT / 'kb_trial' / 'curated_high_quality.json'))
    p.add_argument('--out', default=None, help='default: print the merged entry count only')
    p.add_argument('--allow-proposed', action='store_true',
                   help='load even while the manifest is still proposed (for a candidate file)')
    p.add_argument('--batch', default='phase2', choices=sorted(BATCHES),
                   help='which approved manifest to load; b3 = the stage-3 260-window batch')
    a = p.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    cfg = BATCHES[a.batch]
    payload = _load(a.src)
    entries, report = load_expansion_entries(
        workorders=cfg['workorders'], reviews=cfg['reviews'], audit_path=cfg['audit_path'],
        batch=a.batch,
        require_approved=not a.allow_proposed,
        existing_ids=[e['id'] for e in payload['entries']])
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if report['failures']:
        return 1
    if a.out:
        merged = append_to_payload(payload, entries, report, batch=a.batch)
        Path(a.out).write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding='utf-8')
        print('wrote %s with %d entries (%d added)'
              % (a.out, merged['entry_count'], len(entries)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
