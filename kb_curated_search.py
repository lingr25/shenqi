"""Search the curated high-quality layer only. Never mixes in the wider trial layers.

Default source is kb_trial/curated_high_quality.json. The index is built from exactly
that file's entries, so a hit is always a rule that passed the curation gates and
carries its own review status and citation.

Usage:
  python kb_curated_search.py --self-test
  python kb_curated_search.py "索敌帧 远程抬手"
  python kb_curated_search.py "事件帧 目标丢失" --review agent_verified
  python kb_curated_search.py --id "fc1:索敌-20-14#r0"
  python kb_curated_search.py "位移" --json
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from kb_search import BM25, bigrams

ROOT = Path(__file__).resolve().parent
CURATED = ROOT / 'kb_trial/curated_high_quality.json'
STATUSES = ('user_verified', 'agent_verified', 'auto_screened')
LAYERS = ('official', 'asr', 'qq')


class CuratedIndex:
    def __init__(self, path=CURATED):
        self.path = Path(path)
        self.payload = json.loads(self.path.read_text(encoding='utf-8'))
        self.entries = self.payload['entries']
        self.bm25 = BM25([bigrams(self.text_of(e)) for e in self.entries])
        self.by_id = {e['id']: e for e in self.entries}

    @staticmethod
    def text_of(entry):
        parts = [entry['claim'], entry.get('subject') or '', entry.get('condition') or '',
                 entry.get('category') or '']
        return ' '.join(parts)

    def search(self, query, k=5, review=None, layer=None, category=None):
        if k < 1:
            raise ValueError('k must be positive')
        if review and review not in STATUSES:
            raise ValueError('unknown review status: ' + review)
        scores = self.bm25.score(bigrams(query))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], self.entries[i]['id']))
        hits = []
        for i in order:
            e = self.entries[i]
            if scores[i] <= 0:
                continue
            if review and e['review']['status'] != review:
                continue
            if layer and layer not in e['source_layers']:
                continue
            if category and e['category'] != category:
                continue
            hits.append({'score': round(scores[i], 4), **e})
            if len(hits) == k:
                break
        return hits

    def stats(self):
        return {
            'source': str(self.path.relative_to(ROOT)),
            'schema_version': self.payload['schema_version'],
            'entry_count': len(self.entries),
            'by_review_status': dict(Counter(e['review']['status'] for e in self.entries)),
            'by_source_layer': dict(Counter(e['source_layer'] for e in self.entries)),
            'by_category': dict(Counter(e['category'] for e in self.entries).most_common()),
        }


def render(hit):
    lines = [f"[{hit['review']['status']}|{'+'.join(hit['source_layers'])}] {hit['id']} score={hit['score']}",
             hit['claim'],
             f"  主语: {hit['subject']} | 条件: {hit['condition']} | 范围: {hit['scope']} | 类别: {hit['category']}"]
    for c in hit['citations']:
        for q in c.get('quotes') or []:
            loc = f"{c.get('transcript_file')}@{q.get('t_start')}s" if c.get('transcript_file') else c['id']
            lines.append(f"  引文: {loc} 「{(q.get('text') or '')[:110]}」")
    lines.append(f"  审核: {hit['review']['reason']}")
    return '\n'.join(lines)


def self_test():
    idx = CuratedIndex()
    payload = idx.payload
    assert payload['schema_version'].startswith('curated-'), 'schema_version missing'
    assert payload['entry_count'] == len(idx.entries)
    assert len(idx.by_id) == len(idx.entries), 'duplicate ids'
    for e in idx.entries:
        assert e['review']['status'] in STATUSES, e['id']
        assert e['citations'], e['id']
        for c in e['citations']:
            assert c['status'] != 'unresolved', (e['id'], c['id'])
            assert (c.get('quotes') and c['quotes'][0].get('text')), (e['id'], c['id'])
    # The negative examples must not be reachable.
    assert not any('无敌不是伤害' in e['claim'] for e in idx.entries)
    originals = {e['origin']['trial_doc_id'] for e in idx.entries}
    for banned in ('fc1:技能特例-11-1', 'fc1:其他-8-8', 'fc1:其他-9-11',
                   'fc1:技能特例-6-4', 'fc1:伤害结算-15-1'):
        assert banned not in originals, banned
    # The approved cards must be reachable, and the search must hit them.
    cases = [
        ('索敌帧 远程抬手 阻挡状态机', 'fc1:索敌-20-14'),
        ('事件帧 目标丢失 重新抬手', 'fc1:索敌-16-10'),
        ('逻辑帧 动画帧 掉帧', 'fc1:帧时序与计时器-37-5'),
        ('伤判 闪避 格挡 减伤 增伤', 'fc1:伤害结算-13-0'),
    ]
    results = []
    for query, want in cases:
        hits = idx.search(query, 10)
        origin_of = [{h['origin']['trial_doc_id']} | {a['trial_doc_id'] for a in h.get('also_from', [])}
                     for h in hits]
        rank = next((r for r, o in enumerate(origin_of, 1) if want in o), None)
        assert rank, (query, [sorted(o) for o in origin_of])
        results.append({'query': query, 'expected': want, 'rank': rank,
                        'top10_ids': [h['id'] for h in hits]})
    # Filters must not leak other statuses. A status that no entry currently carries is
    # not a failure: the shipped set has no auto_screened entries at this revision, and
    # forcing one in just to satisfy a filter check would be inventing data. Assert the
    # filter's exclusivity only for statuses that actually occur, and require that an
    # unavailable status returns nothing rather than falling back to a wider layer.
    present = {e['review']['status'] for e in idx.entries}
    for status in STATUSES:
        hits = idx.search('帧 索敌 位移', 20, review=status)
        if status in present:
            assert hits and all(h['review']['status'] == status for h in hits), status
        else:
            assert not hits, ('status filter %r returned hits but no entry carries it' % status)
    # Same rule for the source-layer filter: check exclusivity for layers that occur, and
    # for an empty layer require no hits rather than silently widening the search.
    present_layers = {l for e in idx.entries for l in e['source_layers']}
    for layer in LAYERS:
        hits = idx.search('帧 索敌 位移', 20, layer=layer)
        if layer in present_layers:
            assert hits and all(layer in h['source_layers'] for h in hits), layer
        else:
            assert not hits, ('layer filter %r returned hits but no entry carries it' % layer)
    # No fallback to the wider trial layers.
    wider = json.loads((ROOT / 'kb_trial/docs.jsonl').read_text(encoding='utf-8').splitlines()[0])
    assert wider['id'] not in idx.by_id, 'curated index leaked wider trial docs'
    print(json.dumps({'status': 'passed', 'source': idx.stats(), 'directed': results},
                     ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('query', nargs='?')
    parser.add_argument('--k', type=int, default=5)
    parser.add_argument('--review', choices=STATUSES)
    parser.add_argument('--layer', choices=LAYERS)
    parser.add_argument('--category')
    parser.add_argument('--id', dest='doc_id')
    parser.add_argument('--stats', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    idx = CuratedIndex()
    if args.stats:
        print(json.dumps(idx.stats(), ensure_ascii=False, indent=2))
        return 0
    if args.doc_id:
        entry = idx.by_id.get(args.doc_id)
        if entry is None:
            parser.error('entry id not found in curated layer')
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0
    if not args.query:
        parser.error('需要 query、--id 或 --stats')
    hits = idx.search(args.query, args.k, args.review, args.layer, args.category)
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        print('甄选层（curated_high_quality.json）。仅返回通过闸门的条目；'
              'auto_screened 未经逐条核听，不宣称权威。')
        for rank, h in enumerate(hits, 1):
            print(f"\n{rank}. " + render(h))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
