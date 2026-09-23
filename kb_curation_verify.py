"""Forensic verification worksheet for rules that need an agent check.

Emits the deferred-risk rules (numeric / ASR-only / basic-definition) with their claim
next to the raw quote and surrounding transcript window, grouped so a reviewing agent
can record `agent_verified` or `pending` per rule. Read-only; writes nothing.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kb_curation_evidence import Evidence  # noqa: E402

DEC = ROOT / 'kb_trial/curation/decisions.jsonl'
DEFERRED = ('numeric_needs_agent', 'asr_only_needs_agent', 'basic_definition_needs_agent')


def deferred_rows(reasons=DEFERRED):
    rows = [json.loads(line) for line in DEC.read_text(encoding='utf-8').splitlines() if line.strip()]
    return [r for r in rows if r['decision'] == 'reject' and r['reject_reason'] in reasons]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reason', action='append', choices=DEFERRED)
    parser.add_argument('--doc-id')
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--window', type=int, default=1)
    parser.add_argument('--stats', action='store_true')
    args = parser.parse_args(argv)
    rows = deferred_rows(tuple(args.reason) if args.reason else DEFERRED)
    if args.stats:
        print(json.dumps({
            'deferred_total': len(rows),
            'by_reason': dict(Counter(r['reject_reason'] for r in rows).most_common()),
            'by_category': dict(Counter(r['category'] for r in rows).most_common()),
            'by_layer': dict(Counter('+'.join(r['source_layers']) for r in rows).most_common()),
            'docs': len({r['doc_id'] for r in rows}),
        }, ensure_ascii=False, indent=2))
        return 0
    ev = Evidence()
    picked = [r for r in rows if r['doc_id'] == args.doc_id] if args.doc_id else rows[args.offset:args.offset + args.limit]
    for row in picked:
        print(f"== {row['doc_id']} idx={row['rule_idx']} [{row['reject_reason']}] "
              f"layers={'+'.join(row['source_layers'])} cat={row['category']}")
        print(f"   CLAIM: {row['claim']}")
        print(f"   SUBJ: {row['suffix_subject']} | COND: {row['suffix_condition']} | SCOPE: {row['suffix_scope']}")
        for ref in row['citation_refs']:
            got = ev.lookup(ref, before=0, after=0)
            if not got.get('found'):
                print(f"   !! {ref} UNRESOLVED")
                continue
            quote = (got.get('quotes') or [{}])[0]
            print(f"   [{got['source_layers'][0]}] {ref} t={quote.get('t_start')} QUOTE: {quote.get('quote')}")
        if args.window:
            for ref in row['citation_refs']:
                got = ev.lookup(ref, before=args.window, after=args.window)
                for line in (got.get('window') or {}).get('lines', []):
                    print(f"     ctx| {line[:380]}")
        print()
    print(f"# deferred_total={len(rows)} shown={len(picked)}")
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
