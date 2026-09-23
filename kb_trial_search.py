"""Single local trial search. Mechanism is the default; other modes are explicit."""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from kb_search import BM25, bigrams

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
MODES = ('mechanism', 'experiment', 'pending', 'all', 'archive')


def load_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


class Index:
    def __init__(self, directory=TRIAL):
        self.directory = Path(directory)
        self.docs = load_rows(self.directory / 'docs.jsonl') + load_rows(self.directory / 'archive.jsonl')
        self.entities = json.loads((self.directory / 'entity_index.json').read_text(encoding='utf-8'))
        self.bm25 = BM25([bigrams(self.search_text(d)) for d in self.docs])
        self.by_id = {d['id']: d for d in self.docs}

    @staticmethod
    def search_text(d):
        text = re.sub(r'证据:[^\n)]*', '', d['text'])
        return text

    def entity_names(self, mention):
        names = {mention}
        correction = self.entities.get('trial_user_aliases', {}).get(mention)
        if correction:
            names.add(correction['canonical'])
        for entity in self.entities.get('mentions', {}).get(mention, []):
            names.add(entity['canonical'])
        return names

    def search(self, query, k=5, mode='mechanism', track=None, entity=None, doc_type=None):
        if mode not in MODES:
            raise ValueError('unknown mode: ' + mode)
        if k < 1:
            raise ValueError('k must be positive')
        query_terms = query
        for alias, value in self.entities.get('trial_user_aliases', {}).items():
            if alias in query:
                query_terms = query_terms.replace(alias, value['canonical'])
        if entity:
            names = self.entity_names(entity)
            query_terms += ' ' + ' '.join(sorted(names))
        else:
            names = set()
        scores = self.bm25.score(bigrams(query_terms))
        def score(i):
            d = self.docs[i]
            return scores[i] * (d.get('retrieval_boost') or 1.0) * (d.get('retrieval_weight') or 1.0)
        order = sorted(range(len(scores)), key=lambda i: (-score(i), self.docs[i]['id']))
        hits, groups = [], set()
        allowed = {'mechanism', 'experiment', 'pending'} if mode == 'all' else {mode}
        for i in order:
            d = self.docs[i]
            if scores[i] <= 0 or d['mode'] not in allowed:
                continue
            if track and track not in d['source_layers']:
                continue
            if doc_type and d['doc_type'] != doc_type:
                continue
            if names:
                listed = {e.get('canonical') for e in d.get('entities', [])}
                if not (names & listed or any(n in d['text'] for n in names)):
                    continue
            group = None
            if d['id'].startswith(('fc1:', 'vod_entry:', 'vod_cluster:')):
                group = (d.get('cluster_id') or (d.get('links') or {}).get('cluster_id') or d['id'].split(':', 1)[1].split('#')[0], d['mode'])
            if group and group in groups:
                continue
            if group:
                groups.add(group)
            hits.append({key: d.get(key) for key in ('id', 'text', 'doc_type', 'category', 'mode', 'track', 'source_layers', 'review', 'citation_ids', 'provenance', 'source', 'links', 'overlay', 'historical_conflict_resolution', 'conflict_policy', 'claim_type', 'isolation_reason')} | {'score': round(score(i), 4), 'usage_warning': ('待核，不得当已知' if d['mode'] == 'pending' else '归档原文，禁止作为现行结论' if d['mode'] == 'archive' else '单次实验或实例，不外推为通则' if d['mode'] == 'experiment' else '试验草稿；非权威结论') + '；冲突需核对双方证据与条件，不自动裁决'})
            if len(hits) == k:
                break
        return hits


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('query', nargs='?')
    p.add_argument('--k', type=int, default=5)
    p.add_argument('--mode', choices=MODES, default='mechanism')
    p.add_argument('--track', choices=('official', 'asr', 'qq', 'unknown'))
    p.add_argument('--entity')
    p.add_argument('--doc-type')
    p.add_argument('--json', action='store_true')
    p.add_argument('--id', dest='doc_id')
    p.add_argument('--evidence', help='exact citation id; original quote, not a corrected conclusion')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args(argv)
    if args.self_test:
        from kb_trial_verify import verify
        verify()
        return 0
    if args.evidence:
        rows = load_rows(TRIAL / 'evidence.jsonl')
        match = next((d for d in rows if d['id'] == args.evidence), None)
        if match is None:
            p.error('citation not found')
        print(json.dumps({'warning': '原始引文保持原字；ASR误译仍可能存在，不能代替修订后的正文', 'evidence': match}, ensure_ascii=False, indent=2))
        return 0
    if not args.query and not args.doc_id:
        p.error('需要 query、--id 或 --evidence')
    idx = Index()
    if args.doc_id:
        if args.doc_id not in idx.by_id:
            p.error('document id not found')
        result = idx.by_id[args.doc_id]
    else:
        if args.k < 1:
            p.error('--k must be positive')
        result = idx.search(args.query, args.k, args.mode, args.track, args.entity, args.doc_type)
    if args.json or args.doc_id:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print('本地试验草稿。机制默认；实验、待核、归档须显式选模式。')
        for rank, h in enumerate(result, 1):
            print(f"\n{rank}. [{h['mode']}|{'+'.join(h['source_layers'])}] {h['id']} score={h['score']}")
            print(h['usage_warning'])
            print(h['text'])
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
