# -*- coding: utf-8 -*-
"""Apply the per-entry evidence-review verdicts to the shipped set.

Reads kb_trial/curation/evidence_verdicts.jsonl -- one record per reviewed entry, written
by the reviewer after reading that entry's source window -- and writes

  * kb_trial/curation/evidence_review.json  -- every verdict, with per-entry reasons
  * kb_trial/curated_high_quality.json      -- entries gain an `evidence_review` block
                                               and are partitioned into released vs staging

Rules that keep this honest:

  * A verdict is per ENTRY. There is no shared/template reason: the reason must name what
    in the source supports or fails to support the claim.
  * `supported` -> entry stays in the released set and review.status becomes agent_verified.
  * `unsupported` -> entry is REJECTED and moves to the staging file, not silently deleted.
  * `pending` -> entry keeps auto_screened and moves to staging; it is never dropped
    silently and never shipped as verified.
  * Nothing here invents text. When a sub-claim is not supported the entry is either
    rejected or, if the claim was split, the split is recorded explicitly.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'
WORKLIST = OUT / 'evidence_review_worklist.jsonl'
VERDICTS = OUT / 'evidence_verdicts.jsonl'
QQ_OVERLAY = OUT / 'qq_claim_overlay.json'
QQ_HELD_OUT = OUT / 'qq_claim_held_out.json'
CURATED = TRIAL / 'curated_high_quality.json'
STAGING = OUT / 'curated_staging.json'
EXPANSION_MANIFEST = OUT / 'qq_expansion' / 'approved_manifest.json'
EXPANSION_MANIFEST_B3 = OUT / 'qq_expansion' / 'approved_manifest_b3.json'
EXPANSION_MANIFEST_B4 = OUT / 'qq_expansion' / 'approved_manifest_b4.json'


def load_expansion_index(batch, manifest_path):
    """eid -> (manifest item, verify errors) for one approved QQ-expansion batch.

    Every batch carries its own verdict source, so this stage must not fall back to the
    `inherited_verified` default for its entries. The batch's paths come from the loader's
    BATCHES registry, so adding a batch there is enough for it to be honoured here too.
    """
    import kb_curation_qq_expansion_loader as _EXL
    if not manifest_path.exists():
        return {}
    mf = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not _EXL.manifest_is_approved(mf):
        raise SystemExit('shipped file has %s entries but manifest status is %r'
                         % (batch, mf.get('status')))
    cfg = _EXL.BATCHES[batch]
    audit = json.loads(Path(cfg['audit_path']).read_text(encoding='utf-8'))
    out = {}
    for item in mf['entries']:
        eid = _EXL.entry_id(item['window_id'], item['local_id'])
        out[eid] = (item, _EXL.verify_entry(item, workorders=cfg['workorders'],
                                            reviews=cfg['reviews'], audit=audit), cfg)
    return out


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verdicts', default=str(VERDICTS))
    a = p.parse_args()

    worklist = {r['entry_id']: r for r in load_jsonl(WORKLIST)}
    verdicts = {r['entry_id']: r for r in load_jsonl(a.verdicts)}
    overlay = {r['entry_id']: r for r in json.loads(QQ_OVERLAY.read_text(encoding='utf-8'))['records']}
    held_out = {r['entry_id']: r for r in json.loads(QQ_HELD_OUT.read_text(encoding='utf-8'))['records']}

    unknown = sorted(set(verdicts) - set(worklist))
    if unknown:
        raise SystemExit('verdict for unknown entry: %s' % unknown[:5])

    missing = sorted(set(worklist) - set(verdicts))
    cur = json.loads(CURATED.read_text(encoding='utf-8'))

    # QQ expansion entries (all batches) carry their own verdict source: this stage must not
    # fall back to the `inherited_verified` default for them. Re-verify each against its own
    # frozen workorder and audit decision before letting it keep its released status.
    expansion = {}
    for _batch, _mf in (('phase2', EXPANSION_MANIFEST), ('b3', EXPANSION_MANIFEST_B3),
                        ('b4', EXPANSION_MANIFEST_B4)):
        expansion.update(load_expansion_index(_batch, _mf))

    released, staging = [], []
    counts = {'supported': 0, 'unsupported': 0, 'pending': 0,
              'held_out_qq_overlay_pending': 0, 'qq_expansion_reverified': 0,
              'qq_expansion_reverified_by_batch': {}}
    for e in cur['entries']:
        exp = expansion.get(e['id'])
        if exp is not None:
            item, errs, cfg = exp
            if errs:
                raise SystemExit('qq_expansion entry %s failed re-verification: %s' % (e['id'], errs))
            # The loader verified the quote verbatim against the frozen workorder raw_messages
            # and the audit verdict; record that as this entry's own evidence review rather than
            # inheriting a status from an earlier round.
            label = cfg['claim_section']
            # Phase 2's shipped text uses its own shorter label; keep it byte-identical so the
            # 663 pre-existing entries do not change when this stage is re-run.
            short = '阶段二试批' if cfg['claim_section'] == 'QQ扩展(阶段二试批)' else label
            e['evidence_review'] = {
                'status': 'supported',
                'reason': item.get('review_reason'),
                'reviewer_type': 'agent',
                'confidence': 'text-source-supported',
                'review_basis': '%s：agent 逐条回读冻结工单 raw_messages 全文后确认该命题有逐字文本出处；'
                                '未做人工核听、未回看原片，也未在游戏内复现。' % short,
                'limitation': '局限：判定依据是群聊文本片段本身；片段经脱敏、丢失发言者与上下文顺序，'
                              '提问、假设与结论同形，无法从中区分发言者的确定程度。'
                              '「all reviewed」不代表「all correct」。',
                'supports': 'qq_raw_messages_verbatim',
                'source_path': 'kb_trial/curation/qq_expansion/%s/%s.json'
                               % (Path(cfg['workorders']).name, item['workorder_id']),
                'audit_decision': 'kb_trial/curation/qq_expansion/%s'
                                  % Path(cfg['audit_path']).name,
                'reviewer_model': item.get('reviewer_model'),
            }
            if item.get('review_limitations'):
                e['evidence_review']['review_limitations'] = item['review_limitations']
            e['review'] = {
                'status': 'agent_verified',
                'scope': 'text_source_only',
                'confidence': 'text-source-supported',
                'reason': '%s逐条回读 raw_messages 后确认该命题有逐字文本出处：%s'
                          % (short, (item.get('review_reason') or '')[:200]),
                'not_authoritative': True,
            }
            counts['supported'] = counts.get('supported', 0) + 1
            counts['qq_expansion_reverified'] += 1
            b = counts['qq_expansion_reverified_by_batch']
            b[label] = b.get(label, 0) + 1
            released.append(e)
            continue
        ho = held_out.get(e['id'])
        if ho:
            # The window spans cannot settle a mechanism sentence. Hold the entry out of
            # the released set and keep whatever text it has as clearly-labelled material
            # for a human to adjudicate -- never as a shipped claim.
            e['evidence_review'] = {
                'status': 'pending',
                'pending_code': ho['code'],
                'reason': ho['reason'],
                'reviewer_type': 'agent',
                'confidence': 'text-source-inconclusive',
                'review_basis': 'agent 依据 qq_worklist.json 的窗口 span 逐条比对；未做人工核听、未回看原片。',
                'limitation': '局限：判定依据是群聊文本片段本身；片段经脱敏且丢失发言者与上下文顺序，'
                              '无法区分提问、假设与结论。「all reviewed」不代表「all correct」。',
                'retained_claim': e['claim'],
                'retained_subject': e['subject'],
                'upstream_title': ho['claim_from'],
            }
            e['review'] = {
                'status': 'auto_screened',
                'reason': '该条窗口 span 无法确定机制主张，已隔离待人工判读；'
                          '其 claim/subject/condition 保留为待判读文本，不再标注为已核实。'
                          '隔离理由见 evidence_review.reason。',
            }
            counts['held_out_qq_overlay_pending'] += 1
            staging.append(e)
            continue
        ov = overlay.get(e['id'])
        if ov:
            # QQ entries are re-derived from their window spans before shipping: the
            # upstream text was the chat window's TITLE, which is not a mechanism sentence.
            if e.get('claim') != ov['claim']:
                raise SystemExit('QQ overlay mismatch for %s: entry %r != overlay %r'
                                 % (e['id'], e.get('claim'), ov['claim']))
            e['claim_derivation'] = {'source': 'kb_trial/curation/qq_claim_overlay.json',
                                     'from': ov['claim_from'], 'to': ov['claim'],
                                     'note': ov['note']}
            e['subject'] = ov['subject']
            e['condition'] = ov['condition']
            e['scope'] = ov['scope']
        v = verdicts.get(e['id'])
        if v is None:
            # Non-auto entries (already agent/user verified) pass through with their own
            # evidence_review recorded as inherited: this run did NOT re-read them, and the
            # reason must not claim otherwise.
            if e['review']['status'] in ('agent_verified', 'user_verified'):
                e['evidence_review'] = {
                    'status': 'inherited_verified',
                    'reason': '本条未进入本轮证据审读工单；其 review.status=%s 来自上一轮由用户反馈'
                              '与代理文本审核作出的判定，本轮未重读、未核听。'
                              % e['review']['status'],
                    'reviewer_type': 'agent',
                    'limitation': '继承的旧判定未经本轮复核，也未做人工核听；'
                                  '「all reviewed」不代表「all correct」。',
                }
                released.append(e)
                continue
            e['evidence_review'] = {'status': 'pending',
                                    'reason': '本轮证据审读尚未覆盖到本条。',
                                    'reviewer_type': 'agent'}
            counts['pending'] += 1
            staging.append(e)
            continue

        st = v['status']
        counts[st] = counts.get(st, 0) + 1
        e['evidence_review'] = {
            'status': st,
            'reason': v['reason'],
            'reviewer_type': v.get('reviewer_type', 'agent'),
            # Confidence ceiling: this is a TEXT-source judgement, not verified game truth.
            'confidence': v.get('confidence', 'text-source-supported'),
            'review_basis': v.get('review_basis'),
            'limitation': v.get('limitation'),
        }
        for k in ('source_path', 'source_line_time', 'supports', 'unsupported_part',
                  'split', 'derived_correction', 'derived_correction_disposition',
                  'pending_code', 'repaired_fields'):
            if v.get(k):
                e['evidence_review'][k] = v[k]

        # Apply derived-text repairs. Quotes are never touched; only the derived
        # claim/subject/condition are corrected, and the change is recorded.
        repairs = v.get('repaired_fields') or []
        if repairs:
            applied = []
            for rep in repairs:
                f = rep['field']
                before, after = rep['from'], rep['to']
                if e.get(f) == before:
                    e[f] = after
                    applied.append({'field': f, 'from': before, 'to': after})
                elif e.get(f) == after:
                    applied.append({'field': f, 'from': before, 'to': after, 'already_applied': True})
                else:
                    raise SystemExit('repair mismatch for %s.%s: have %r want %r'
                                     % (e['id'], f, e.get(f), before))
            e['derived_text_repairs'] = {'count': len(applied), 'changes': applied,
                                         'note': '仅订正派生 claim/subject/condition；引文保持原始逐字文本不变。'}

        if st == 'supported':
            e['review'] = {
                'status': 'agent_verified',
                'scope': 'text_source_only',
                'confidence': v.get('confidence', 'text-source-supported'),
                'reason': '本轮逐条读源核实（文本层，未核听原片）：%s' % v['reason'][:200],
                'not_authoritative': True,
            }
            released.append(e)
        elif st == 'unsupported':
            e['review'] = {'status': 'auto_screened',
                           'reason': '本轮逐条读源后判定源不支持：%s' % v['reason'][:160]}
            staging.append(e)
        else:
            e['review'] = {'status': 'auto_screened',
                           'reason': '本轮读源后判定源无法确定该 claim：%s' % v['reason'][:160]}
            staging.append(e)

    out = dict(cur)
    out['entries'] = released
    out['entry_count'] = len(released)
    from collections import Counter as _C
    disp = _C((e.get('evidence_review') or {}).get('derived_correction_disposition')
              for e in released if (e.get('evidence_review') or {}).get('derived_correction_disposition'))
    out['evidence_review_summary'] = {
        'reviewed_supported': counts.get('supported', 0),
        'reviewed_unsupported': counts.get('unsupported', 0),
        'reviewed_pending': counts.get('pending', 0),
        'inherited_verified': sum(1 for e in released
                                  if (e.get('evidence_review') or {}).get('status') == 'inherited_verified'),
        'held_out_qq_overlay_pending': counts['held_out_qq_overlay_pending'],
        'qq_expansion_reverified': counts['qq_expansion_reverified'],
        'qq_expansion_reverified_by_batch': counts['qq_expansion_reverified_by_batch'],
        'released': len(released),
        'staging': len(staging),
        'entries_with_derived_text_repairs': sum(1 for e in released if e.get('derived_text_repairs')),
        'derived_correction_disposition': dict(disp),
        'confidence_ceiling': 'text-source-supported',
        'review_basis': 'agent 依据 packet 内嵌 SOURCE WINDOW 与已解析引文逐条比对；未做人工核听、未回看原片。',
        'note': '本层为逐条读源的文本层证据审核，置信上限是「有文本出处支持该派生表述」，'
                '不等于游戏内真值已验证。supported=文本层有出处支持，留在发布集并标记 '
                'review.status=agent_verified(scope=text_source_only)；'
                'unsupported=源不支持；pending=源无法确定该 claim（例如依赖具体关卡或自建模拟器语境），'
                '二者均留在 staging，不静默丢弃。'
                '派生文本中经同源上下文自证的 ASR 讹写已订正（见 entries_with_derived_text_repairs），'
                '引文一律保持原始逐字文本不变。'
                '「all reviewed」不代表「all correct」。',
    }
    CURATED.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    STAGING.write_text(json.dumps({'entry_count': len(staging), 'entries': staging},
                                  ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(out['evidence_review_summary'], ensure_ascii=False, indent=1))
    print('worklist entries:', len(worklist), '| verdicts supplied:', len(verdicts),
          '| uncovered:', len(missing))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
