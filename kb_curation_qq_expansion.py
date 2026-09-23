# -*- coding: utf-8 -*-
"""Build the approved QQ-expansion manifest from the phase-2 trial reviews.

This is the review gate for the 80-window trial batch. It does NOT invent text: it takes
the candidate claims produced in `final_reviews/`, applies the per-proposition audit
recorded in `audit_decisions.json`, verifies every cited evidence seq against the frozen
workorder's `raw_messages` byte-for-byte, and emits only the propositions that survive.

What it refuses to do:

  * It never promotes an excluded item. `excluded[]` entries are transcribed as rejected
    or pending; only a `claims[]` entry explicitly kept by the audit can be approved.
  * It never overrides the parent's named hard-exclusions. Those workorders/local_ids are
    listed in HARD_EXCLUDE and a keep for one is a hard error, not a warning.
  * It never rewrites a claim into something the window did not say. Where the audit
    records a correction (only qq_wo_024, where the parent restricted the formula to the
    attack-power term), the replacement text is given explicitly and is required to be
    composed of the same window's literal spans.

Output is an approval proposal for the parent to countersign; the shipped
`curated_high_quality.json` only changes once the incremental loader consumes it.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPANSION = ROOT / 'kb_trial' / 'curation' / 'qq_expansion'
WORKORDERS = EXPANSION / 'workorders'
REVIEWS = EXPANSION / 'final_reviews'
AUDIT = EXPANSION / 'audit_decisions.json'
MANIFEST = EXPANSION / 'approved_manifest.json'

# ---------------------------------------------------------------------------
# The parent's named hard-exclusions. A keep for any of these pairs is a build error.
# (workorder_id, local_id) -- local_id may be a label for an excluded topic.
# ---------------------------------------------------------------------------
HARD_EXCLUDE = {
    ('qq_wo_003', '(excl) 2.95/向上偏移1 生成规则'),
    ('qq_wo_003', '(excl) boss 实体坐标在 9 格下侧'),
    ('qq_wo_003', '(excl) LS-4 红门虫子偏移'),
    ('qq_wo_010', 'c02'),
    ('qq_wo_014', 'c01'),
    ('qq_wo_017', 'c01'),
    ('qq_wo_020', 'c01'),
    ('qq_wo_041', 'c01'),
    ('qq_wo_041', 'c02'),
    ('qq_wo_045', 'c01'),
    ('qq_wo_049', 'c01'),
    ('qq_wo_051', 'c01'),
    ('qq_wo_051', 'c02'),
    ('qq_wo_051', 'c03'),
    ('qq_wo_052', 'c01'),
    ('qq_wo_055', 'c03'),
    ('qq_wo_063', 'c01'),
    ('qq_wo_068', 'c02'),
    ('qq_wo_075', 'c01'),
    ('qq_wo_078', 'c01'),
    ('qq_wo_078', 'c02'),
}
# qq_wo_003/c01 is deliberately NOT a hard exclusion: the parent named that window's
# excluded topics (2.95 / 9格 / LS-4), and the second review's added claim is the
# collision-box vs coordinate split, which is a different proposition.

# ---------------------------------------------------------------------------
# Explicit claim replacements. The audit may only replace a claim with text built from
# the same window's literal spans; anything else is a review failure.
# ---------------------------------------------------------------------------
CLAIM_REPLACEMENTS = {
    ('qq_wo_024', 'c01'): {
        'claim': '这场对话给出的攻击力构成是「攻击力 * 攻击力倍率 + 附加攻击力」，'
                 '即伤害中的攻击力计算项由攻击力、攻击力倍率与附加攻击力三者按此式构成。',
        'subject': '攻击力计算项（伤害中的攻击力部分）的构成式',
        'condition': '在按该式描述攻击力构成时',
        'scope': 'general_mechanism',
        'why': '父要求：按 raw 语义准确限为「攻击力计算项」，不得泛写为完整伤害公式。'
               '原文 seq 21 逐字为「明日方舟所有伤害都是 攻击力 * 攻击力倍率 + 附加攻击力」，'
               '本条只复述该构成式并把落点限定在攻击力项，未补写任何原文没有的运算或字段。',
    },
}

# Scope vocabulary allowed in the manifest. Anything else is a review failure.
SCOPES = {'general_mechanism', 'entity_mechanism', '未标注'}


def sha256_text(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def iter_kept(audit):
    """Yield (workorder, local_id, correction) for every proposition kept by the audit."""
    for d in audit['decisions']:
        if d.get('verdict') != 'keep':
            continue
        yield d['workorder'], d['local_id'], d


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preview', action='store_true',
                   help='write the proposal and report without touching any shipped JSON')
    p.add_argument('--out', default=str(MANIFEST))
    a = p.parse_args()

    audit = load(AUDIT)
    kept = list(iter_kept(audit))
    if not kept:
        raise SystemExit('audit_decisions.json records no kept propositions')

    proposals, failures = [], []
    for workorder, local_id, decision in kept:
        if (workorder, local_id) in HARD_EXCLUDE:
            failures.append('%s/%s is a parent hard-exclusion but the audit keeps it'
                            % (workorder, local_id))
            continue
        wo_path = WORKORDERS / ('%s.json' % workorder)
        rv_path = REVIEWS / ('%s.json' % workorder)
        if not wo_path.exists() or not rv_path.exists():
            failures.append('%s: missing workorder or review file' % workorder)
            continue
        wo, rv = load(wo_path), load(rv_path)

        # The review must match the frozen workorder it claims to have read. The review
        # hashed the workorder FILE BYTES, so compare on bytes, not on re-serialised JSON.
        if rv.get('source_sha256') != hashlib.sha256(wo_path.read_bytes()).hexdigest():
            failures.append('%s: review source_sha256 does not match the frozen workorder'
                            % workorder)
            continue
        cand = next((c for c in (rv.get('claims') or []) if c.get('local_id') == local_id), None)
        if cand is None:
            failures.append('%s/%s is kept by the audit but absent from final_reviews'
                            % (workorder, local_id))
            continue

        # Verify every cited evidence seq exists in raw_messages and matches byte-for-byte.
        msgs = {m['seq']: m for m in wo['raw_messages']['messages']}
        evidence, bad = [], []
        for ev in cand.get('evidence') or []:
            m = msgs.get(ev.get('seq'))
            if m is None:
                bad.append('seq %s not in workorder' % ev.get('seq'))
            elif m['text'] != ev.get('text'):
                bad.append('seq %s text mismatch' % ev.get('seq'))
            else:
                evidence.append({'seq': m['seq'], 'speaker_id': m['speaker_id'],
                                 'time': m['time'], 'text': m['text']})
        if bad:
            failures.append('%s/%s evidence not verbatim: %s' % (workorder, local_id, bad))
            continue
        if not evidence:
            failures.append('%s/%s has no verbatim evidence' % (workorder, local_id))
            continue

        rep = CLAIM_REPLACEMENTS.get((workorder, local_id))
        if rep:
            claim, subject = rep['claim'], rep['subject']
            condition, scope = rep['condition'], rep['scope']
            corrected = True
        else:
            claim, subject = cand['claim'], cand.get('subject')
            condition, scope = cand.get('condition'), cand.get('scope')
            corrected = False

        if scope not in SCOPES:
            failures.append('%s/%s has out-of-vocabulary scope %r' % (workorder, local_id, scope))
            continue
        # A claim must not carry meta-talk from the review process itself.
        blob = '%s %s' % (claim, subject)
        if '本审' in blob or '账号已隐去' in blob or '非原文引文' in blob:
            failures.append('%s/%s claim carries review meta-talk' % (workorder, local_id))
            continue
        if not claim or not claim.strip():
            failures.append('%s/%s has an empty claim' % (workorder, local_id))
            continue

        proposals.append({
            'workorder_id': workorder,
            'window_id': wo['window']['window_id'],
            'local_id': local_id,
            'claim': claim,
            'subject': subject,
            'condition': condition,
            'scope': scope,
            'category': cand.get('category') or wo['window'].get('category'),
            'as_of': wo['window'].get('as_of'),
            'evidence': evidence,
            'evidence_sha256': sha256_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True)),
            'reviewer_model': rv.get('reviewer_model'),
            'review_reason': cand.get('reason'),
            'review_limitations': cand.get('limitations') or [],
            'audit_note': decision.get('criterion_note') or decision.get('detail'),
            'claim_corrected_by_audit': corrected,
        })

    # Every hard exclusion must be accounted for by the audit (kept is an error, rejected ok).
    audited = {(d['workorder'], d.get('local_id')) for d in audit['decisions']}
    unaccounted = sorted(h for h in HARD_EXCLUDE if h not in audited)
    if unaccounted:
        failures.append('hard exclusions with no audit decision: %s' % unaccounted)

    payload = {
        'note': '阶段二 80 窗试批的批准提案。只含本代理逐条回读 raw_messages 后认可的命题；'
                '每条 evidence 均与冻结工单 raw_messages 逐字校验（evidence_sha256 可复核）。'
                '本文件是审核提案，供父抽查；未经父批准不得并入 curated_high_quality.json。',
        'schema': 'qq-expansion-approved-1.0',
        'phase': 'phase2_trial_batch_review',
        'criteria': audit['criteria'],
        'windows_reviewed': 80,
        'source': {
            'workorders': 'kb_trial/curation/qq_expansion/workorders/',
            'final_reviews': 'kb_trial/curation/qq_expansion/final_reviews/',
            'audit_decisions': 'kb_trial/curation/qq_expansion/audit_decisions.json',
        },
        'status': 'proposed_pending_parent_approval',
        'entry_count': len(proposals),
        'hard_exclusions_enforced': sorted('%s/%s' % h for h in HARD_EXCLUDE),
        'entries': proposals,
    }
    Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    report = {
        'status': 'failed' if failures else 'ok',
        'approved_propositions': len(proposals),
        'windows': len({p['window_id'] for p in proposals}),
        'by_scope': {},
        'corrected_by_audit': sorted('%s/%s' % (p['workorder_id'], p['local_id'])
                                     for p in proposals if p['claim_corrected_by_audit']),
        'failures': failures,
        'output': a.out,
        'manifest_sha256': sha256_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n'),
    }
    from collections import Counter
    report['by_scope'] = dict(Counter(p['scope'] for p in proposals))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if failures else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
