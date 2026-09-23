"""Print claim-vs-quote review dossiers for the auto-gated curated pool.

Read-only. Emits, for each surviving rule, the derived claim next to the raw quote the
rule cites, plus the surrounding transcript window when the claim carries a number or
comes from an ASR-only source. A reviewing agent reads these dossiers to decide
`agent_verified` vs pending; the script itself makes no such decision.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kb_curation_evidence import Evidence  # noqa: E402

CAND = ROOT / 'kb_trial/curation/candidates.json'


def autogate(row):
    bad = []
    flags = set(row['flags'])
    if row['render_mode'] == 'rubric_rule':
        if row['doc_id'].startswith('fc1:'):
            aff = row.get('affirmative_rule_idx')
            if aff is None or row['rule_idx'] not in aff:
                bad.append('not_affirmative')
        if row['rule_idx'] in set(row.get('demoted_rule_idx') or []):
            bad.append('demoted')
        if row['rule_idx'] in {g['idx'] for g in (row.get('gated_rules') or [])}:
            bad.append('gated')
        if not row.get('suffix_scope'):
            bad.append('no_scope')
        if not row.get('suffix_subject'):
            bad.append('no_subject')
    if 'official' not in (row['source_layers'] or []):
        bad.append('not_official')
    if row['issue_status'] in ('conflict', 'open'):
        bad.append('issue_open')
    if row['audit_kind'] in ('opinion', 'trivia', 'noise', '?'):
        bad.append('audit_bad')
    if row['claim_type'] in ('hypothesis', 'question'):
        bad.append('claim_weak')
    if row['novelty'] == 'conflict':
        bad.append('novelty_conflict')
    if row['context_incomplete']:
        bad.append('ctx_incomplete')
    for f in ('hedge_or_memory', 'chit_chat', 'opinion_lexicon', 'too_short', 'fragment_tail', 'asr_suspect_word'):
        if f in flags:
            bad.append(f)
    if not any(x.startswith('BV') for x in row['citation_refs']):
        bad.append('no_atom_cite')
    return bad


def survivors():
    rows = json.loads(CAND.read_text(encoding='utf-8'))
    return [r for r in rows if not autogate(r)]


def dossier(ev, row, window=1):
    out = [f"== {row['doc_id']} rule_idx={row['rule_idx']} conf={row['confidence']} "
           f"cat={row['category']} layers={'+'.join(row['source_layers'])}",
           f"CLAIM: {row['claim']}",
           f"SUBJ: {row['suffix_subject']} | COND: {row['suffix_condition']} | SCOPE: {row['suffix_scope']}"]
    for ref in row['citation_refs']:
        got = ev.lookup(ref, before=window, after=window)
        if not got.get('found'):
            out.append(f"  !! {ref} UNRESOLVED")
            continue
        quote = (got.get('quotes') or [{}])[0]
        out.append(f"  [{got['source_layers'][0]}] {ref} t={quote.get('t_start')}")
        out.append(f"    QUOTE: {quote.get('quote')}")
        if got.get('window', {}).get('lines'):
            for line in got['window']['lines']:
                out.append(f"      ctx| {line[:400]}")
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--doc-id')
    parser.add_argument('--window', type=int, default=1)
    parser.add_argument('--offset', type=int, default=0, help='skip N survivors before selecting')
    parser.add_argument('--step', type=int, default=1, help='take every Nth survivor')
    args = parser.parse_args(argv)
    pool = survivors()
    ev = Evidence()
    if args.doc_id:
        picked = [r for r in pool if r['doc_id'] == args.doc_id]
    else:
        picked = pool[args.offset::args.step][:args.limit]
    for row in picked:
        print(dossier(ev, row, args.window))
        print()
    print(f"# survivors={len(pool)} shown={len(picked)}")
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
