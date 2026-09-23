"""Local reproducibility, boundary, provenance and retrieval checks; no API."""
import contextlib
import io
import json
import re
from collections import Counter

import kb_build_trial as B
from kb_eval import QUERIES
from kb_search import BM25, bigrams
from kb_trial_search import Index, TRIAL, load_rows


def verify():
    before = json.loads((TRIAL / 'manifest.json').read_text(encoding='utf-8'))
    with contextlib.redirect_stdout(io.StringIO()):
        after = B.build()
    assert before == after, 'build not idempotent'
    assert all(B.digest(B.ROOT / p) == h for p, h in after['source_sha256'].items())
    idx = Index()
    docs = idx.by_id
    assert len(docs) == len(idx.docs)
    active = [d for d in idx.docs if d['mode'] != 'archive']
    assert all('无敌不是伤害' not in d['text'] for d in active)
    for d in active:
        refs = B.references(d)
        if any(r.startswith('BV1qReG6XE6W_p1_41897493495:p') for r in refs):
            assert '镜像力' not in d['text'], d['id']
        if any(r.startswith('BV14y8269EbS_p2_41167359561:p9:') for r in refs):
            assert '维尼斯' not in d['text'], d['id']
    assert docs['fc1:其他-8-8']['mode'] == 'pending'
    assert docs['fc1:技能特例-11-1']['mode'] == 'archive'
    for cid in ('技能特例-6-4', '伤害结算-15-1'):
        assert docs['fc1:' + cid]['mode'] == 'experiment'
    for cid in ('状态效果-10-9', '帧时序与计时器-1-0'):
        assert docs['fc1:' + cid]['review']['human'] == 'unreviewed'
    assert sum(d['review']['human'] == 'accepted' for d in idx.docs) == 3
    original = {d['id']: d for d in B.load('kb/docs.jsonl')}
    evidence = load_rows(TRIAL / 'evidence.jsonl')
    for e in evidence:
        if e['status'] == 'resolved_atom':
            assert e['evidence'] == original[e['source_doc_id']].get('evidence')
        if e['status'] == 'resolved_timestamp_window':
            assert e['quote_line'] in (B.ROOT / e['file']).read_text(encoding='utf-8').splitlines()
    for d in idx.docs:
        if d['id'] in original:
            assert d.get('evidence') == original[d['id']].get('evidence')
        if d['mode'] == 'mechanism':
            assert '## 待核' not in d['text'] and '## 待验证' not in d['text'] and '## 实例佐证' not in d['text']
    cases = [
        ('索敌帧与远程抬手的绑定关系', 'mechanism', 'fc1:索敌-20-14'),
        ('事件帧目标丢失重新抬手', 'mechanism', 'fc1:索敌-16-10'),
        ('逻辑帧动画帧掉帧', 'mechanism', 'fc1:帧时序与计时器-37-5'),
        ('小莫施怀雅镜像力径向力', 'experiment', 'fc1:其他-9-11'),
        ('维尼斯推海默向上刹车', 'mechanism', 'fc1:位移-4-5'),
        ('闪避格挡减伤增伤伤判分类', 'mechanism', 'fc1:伤害结算-13-0'),
    ]
    directed = []
    for q, mode, want in cases:
        hits = idx.search(q, 5, mode)
        ids = [d['id'] for d in hits]
        assert want in ids, (q, ids)
        directed.append({'query': q, 'mode': mode, 'expected': want, 'rank': ids.index(want) + 1, 'top5': ids})
    for mode in ('mechanism', 'experiment', 'pending', 'archive'):
        hits = idx.search('技能伤害索敌', 15, mode)
        assert hits and all(h['mode'] == mode for h in hits)
    assert all(h['mode'] != 'archive' for h in idx.search('无敌不是伤害', 100, 'all'))
    assert idx.search('眠兽撤退睡眠解除', 5, 'all', track='qq')[0]['id'] == 'window:w000006'
    assert idx.search('眠兽撤退', 5, 'all', track='qq', entity='夜半')
    old_docs = list(original.values())
    old_docs = [d for d in old_docs if d.get('status') != 'noise']
    bm = BM25([bigrams(d['text']) for d in old_docs])
    def old_search(q):
        scores = bm.score(bigrams(q))
        order = sorted(range(len(scores)), key=lambda i: -scores[i] * (old_docs[i].get('retrieval_boost') or 1) * (old_docs[i].get('retrieval_weight') or 1))[:5]
        return [old_docs[i] for i in order]
    manual = []
    for q, expected, note in QUERIES:
        row = {'query': q, 'note': note}
        for label, hits in [('production', old_search(q)), ('trial_mechanism', idx.search(q)), ('trial_all', idx.search(q, mode='all'))]:
            row[label] = {'hit': any(any(k in re.sub(r'[、，。,\s]', '', h['text']) for k in expected) for h in hits), 'ids': [h['id'] for h in hits]}
        manual.append(row)
    blind = B.load('kb/eval_questions.jsonl')
    entries = {(d.get('links') or {}).get('cluster_id'): d['id'] for d in old_docs if d['doc_type'] == 'vod_entry'}
    blind_rows = []
    for q in blind:
        target = q['expect_doc_id']
        expected = {target}
        if target.startswith('vod_cluster:') and target.split(':', 1)[1] in entries:
            expected.add(entries[target.split(':', 1)[1]])
        row = {'query': q['q'], 'expected': target}
        cid = target.split(':', 1)[1] if target.startswith(('vod_cluster:', 'vod_entry:')) else None
        for label, hits in [('production', old_search(q['q'])), ('trial_mechanism', idx.search(q['q'])), ('trial_all', idx.search(q['q'], mode='all'))]:
            ids = [h['id'] for h in hits]
            row[label] = {'r5': bool(expected & set(ids)), 'r1': ids[0] in expected if ids else False,
                          'family_r5': bool(expected & set(ids) or cid and any(cid in B.clusters(h) for h in hits)), 'ids': ids}
        blind_rows.append(row)
    labels = ('production', 'trial_mechanism', 'trial_all')
    summary = {label: {'manual': sum(r[label]['hit'] for r in manual), 'manual_total': len(manual),
                       'blind_r5': sum(r[label]['r5'] for r in blind_rows), 'blind_r1': sum(r[label]['r1'] for r in blind_rows),
                       'blind_family_r5': sum(r[label]['family_r5'] for r in blind_rows), 'blind_total': len(blind_rows)} for label in labels}
    assert summary['production']['manual'] == 22
    report = {'status': 'passed', 'idempotent': True, 'source_hashes_unchanged': True, 'quotes_unchanged': True,
              'external_api_calls': 0, 'directed_queries': directed, 'summary': summary,
              'manual_queries': manual, 'blind_queries': blind_rows,
              'interpretation': 'Local retrieval only. Exact legacy IDs are not semantic equivalence. Family means same cluster only; not proof of preserved propositions.'}
    B.dump(TRIAL / 'validation.json', report)
    print(json.dumps({'status': 'passed', 'directed': len(directed), 'summary': summary}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    verify()
