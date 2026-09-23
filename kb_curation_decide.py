"""Deterministic gates + reviewer-boundary application for the curated layer.

Reads kb_trial/curation/candidates.json, applies the gates, merges the frozen reviewer
decisions from kb_curation_rules.py and curation/agent_verifications.json, and writes
curation/decisions.jsonl - one line per candidate rule with its final disposition.

Every rejection carries a machine-readable reason. Nothing is admitted on doc_type,
kind, track, confidence or a "high" label.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import kb_curation_rules as R

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial/curation'

# Hard gates. Each maps to a reason string recorded on rejections.
GATE_ORDER = ('rejected_by_user_or_reviewer', 'not_affirmative_index', 'demoted_rule',
              'gated_rule', 'missing_scope', 'missing_subject', 'issue_not_agreed',
              'audit_kind_not_mechanism', 'claim_type_not_assertion', 'novelty_conflict',
              'context_incomplete', 'hedge_or_memory', 'chit_chat', 'opinion_lexicon',
              'too_short', 'fragment_tail', 'asr_suspect_term', 'no_atom_citation',
              'citation_unresolved', 'context_dependent_claim', 'no_condition_stated',
              'asr_only_needs_agent', 'numeric_needs_agent', 'basic_definition_needs_agent')

# A claim that leans on surrounding speech is not a self-contained rule.
CTX_DEP = ('这条', '那条', '这一个', '这个东西', '这个点', '这种情况', '刚才', '前面', '后面',
           '上面', '下面', '所谓', '如前', '见上', '见下', '这个数', '这个值', '该段',
           '原文', '本期', '今天', '世界线', '我们讲', '我讲', '讲了')

# Claims whose every citation sits in the ASR layer, or that state a number, or that
# merely define a basic term, are admitted only with an explicit agent verification.
# This is the brief's rule: ASR-only / numeric derivation / basic definition / conflict
# must be checked item by item against the source before they may ship.
BASIC_DEFINITION = ('是指', '叫做', '称为', '定义为', '名为', '属于', '是一种', '就是',
                    '指的是', '分成', '分为')

# Explicit in-sentence admissions that the condition was never stated. Used for
# closed_form rows, which carry no parsed condition field.
UNSTATED_CONDITION = re.compile(r'未说明|条件未知|视情况|待定|暂不确定|不确定条件')


def citation_status(row, evidence_ids):
    """Return (ok, reason) for the citation set of one candidate rule.

    Two tracks have two different provenance shapes, and neither is privileged:

    * VOD track -- evidence is a clip atom id (BV<bvid>:p<n>:a<i>:<hash>) that must resolve
      in kb_trial/evidence.jsonl.
    * QQ track -- there is no clip file; evidence is a qq_cards span, already sanitized to
      span text plus window id and message count. Requiring a BV atom here would exclude
      the entire QQ track on schema shape alone, which says nothing about whether the
      sentence is a sound, well-sourced mechanism statement.
    """
    refs = row['citation_refs']
    atoms = [r for r in refs if r.startswith('BV')]
    if atoms:
        if any(a not in evidence_ids for a in atoms):
            return False, 'citation_unresolved'
        return True, None
    qq = row.get('qq_evidence')
    if qq and qq.get('spans'):
        return True, None
    inline = row.get('inline_evidence')
    if inline and any(e.get('file') and e.get('text') for e in inline):
        return True, None
    if refs:
        return False, 'citation_unresolved'
    return False, 'no_atom_citation'


def gate(row, evidence_ids, agent_checked):
    """Apply hard gates. Returns (ok, reason)."""
    key = (row['doc_id'], row['rule_idx'])
    if R.is_rejected(*key):
        return False, 'rejected_by_user_or_reviewer'
    # An agent reading the raw quote and finding it does not support the claim is a hard
    # rejection: the claim may not be admitted just because the mechanical gates passed.
    verdict = agent_checked.get(key)
    if verdict is not None and verdict.get('verdict') == 'reject':
        return False, 'rejected_by_agent_evidence'
    flags = set(row['flags'])
    # The affirmative-rule index only exists on the fc1 rewrite layer. Cards the user
    # reviewed may have been rewritten (trim/correct) without that index being regenerated,
    # so an explicit user decision -- or an agent that has read the rewritten sentence
    # against its source -- supersedes a missing index.
    verified = agent_checked.get(key, {}).get('verdict') == 'verify'
    exempt = key in R.USER_VERIFIED or key in R.FEEDBACK_APPLIED or verified
    if row['render_mode'] == 'rubric_rule':
        if row['doc_id'].startswith('fc1:') and not exempt:
            aff = row.get('affirmative_rule_idx')
            if aff is None or row['rule_idx'] not in aff:
                return False, 'not_affirmative_index'
        if row['rule_idx'] in set(row.get('demoted_rule_idx') or []) and not exempt:
            return False, 'demoted_rule'
        if row['rule_idx'] in {g['idx'] for g in (row.get('gated_rules') or [])} and not exempt:
            return False, 'gated_rule'
        if not row.get('suffix_scope'):
            return False, 'missing_scope'
        if not row.get('suffix_subject'):
            return False, 'missing_subject'
    if row['issue_status'] in ('conflict', 'open'):
        return False, 'issue_not_agreed'
    if row['audit_kind'] in ('opinion', 'trivia', 'noise', '?'):
        return False, 'audit_kind_not_mechanism'
    if row['claim_type'] in ('hypothesis', 'question'):
        return False, 'claim_type_not_assertion'
    if row['novelty'] == 'conflict':
        return False, 'novelty_conflict'
    if row['context_incomplete'] and key not in R.USER_VERIFIED and not exempt:
        return False, 'context_incomplete'
    for flag, reason in (('hedge_or_memory', 'hedge_or_memory'), ('chit_chat', 'chit_chat'),
                         ('opinion_lexicon', 'opinion_lexicon'), ('too_short', 'too_short'),
                         ('fragment_tail', 'fragment_tail'),
                         ('asr_suspect_word', 'asr_suspect_term')):
        if flag in flags:
            return False, reason
    claim = row['claim']
    if len(claim) < 6:
        return False, 'too_short'
    if len(claim) < 12 and key not in R.USER_VERIFIED and not row.get('suffix_subject'):
        return False, 'too_short'
    if claim.endswith(('的', '是', '在', '了', '和', '与', '或', '而', '就', '也', '都', '很')):
        return False, 'fragment_tail'
    if any(c in claim for c in CTX_DEP):
        return False, 'context_dependent_claim'
    # A rule may legitimately be unconditional when it is scoped universal. What is
    # rejected is an explicitly unstated condition, or an instance/example-scoped rule
    # presented without the condition that bounds it.
    #
    # closed_form rows (QQ atoms/windows, VOD atoms/clusters) have no per-rule suffix, so
    # "no suffix condition" is a schema artefact, not evidence that the sentence lacks a
    # condition. Such a row is judged on the condition it states in its own words; the
    # documented-absence markers below are what actually disqualify it.
    condition = row.get('suffix_condition') or ''
    if condition.startswith('未说明'):
        return False, 'no_condition_stated'
    if not condition and row.get('suffix_scope') not in ('universal', None):
        return False, 'no_condition_stated'
    if not condition and row['render_mode'] == 'closed_form' and UNSTATED_CONDITION.search(row['claim']):
        return False, 'no_condition_stated'
    ok, reason = citation_status(row, evidence_ids)
    if not ok:
        return False, reason
    # Risk classes that require a positive agent check of this exact rule. A recorded
    # verdict only counts when it is 'verify'; 'reject' was already turned away above and
    # any other value is not an acceptance.
    verified = agent_checked.get(key, {}).get('verdict') == 'verify'
    if not verified and key not in R.USER_VERIFIED:
        if 'official' not in (row['source_layers'] or []):
            return False, 'asr_only_needs_agent'
        if 'contains_number' in flags:
            return False, 'numeric_needs_agent'
        if any(d in claim for d in BASIC_DEFINITION):
            return False, 'basic_definition_needs_agent'
    return True, None


def load_agent_verifications():
    path = OUT / 'agent_verifications.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {(v['doc_id'], v['rule_idx']): v for v in data['verifications']}


def decide():
    rows = json.loads((OUT / 'candidates.json').read_text(encoding='utf-8'))
    evidence = {json.loads(line)['id'] for line in
                (ROOT / 'kb_trial/evidence.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()}
    agent = load_agent_verifications()
    decisions = []
    for row in rows:
        key = (row['doc_id'], row['rule_idx'])
        ok, reason = gate(row, evidence, agent)
        if not ok:
            decisions.append(dict(row, decision='reject', reject_reason=reason,
                                  review_status=None))
            continue
        if key in R.USER_VERIFIED:
            status, note = 'user_verified', R.USER_VERIFIED[key]
        elif key in agent:
            status, note = 'agent_verified', agent[key]['reason']
        else:
            status, note = 'auto_screened', '通过全部确定性闸门；未经逐条人工或代理核听'
        decisions.append(dict(row, decision='accept', reject_reason=None,
                              review_status=status, review_note=note))
    return decisions


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    decisions = decide()
    path = OUT / 'decisions.jsonl'
    path.write_text(''.join(json.dumps(d, ensure_ascii=False, sort_keys=True) + '\n'
                            for d in sorted(decisions, key=lambda x: (x['doc_id'], x['rule_idx']))),
                    encoding='utf-8')
    accepted = [d for d in decisions if d['decision'] == 'accept']
    stats = {
        'candidates': len(decisions),
        'accepted': len(accepted),
        'rejected': len(decisions) - len(accepted),
        'by_review_status': dict(Counter(d['review_status'] for d in accepted)),
        'reject_reasons': dict(Counter(d['reject_reason'] for d in decisions if d['decision'] == 'reject').most_common()),
        'accepted_docs': len({d['doc_id'] for d in accepted}),
        'accepted_by_category': dict(Counter(d['category'] for d in accepted).most_common()),
        'accepted_by_layer': dict(Counter('+'.join(d['source_layers']) for d in accepted).most_common()),
    }
    (OUT / 'decisions_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
