"""Build the single local draft trial; never write production or call an API."""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial'
SEM = 'kb_pilot_synth/semantic_repair_round1/'
REV = 'kb_pilot_synth/user_review_round1/'
REF = re.compile(r'(?:ctx=)?sub:BV[\w]+:\d+|BV[\w]+:p\d+:a\d+:[0-9a-f]{8}')
SOURCES = [SEM + n for n in ('gated_default_v2.jsonl', 'gated_archive_v2.jsonl', 'gated_old_kept_v2.jsonl', 'usage_ledger_v2.json')]
SOURCES += [REV + n for n in ('revised_default.jsonl', 'archived_by_feedback.jsonl', 'feedback.jsonl', 'patches.jsonl')]
SOURCES += ['kb/docs.jsonl', 'kb/synthesized.jsonl', 'kb/entity_index.json']
SOURCES += [f'kb_pilot_synth/{folder}/{name}.jsonl' for folder in ('batch100_round2', 'evidence_round1') for name in ('mechanisms', 'experiments')]


def load(path):
    return [json.loads(s) for s in (ROOT / path).read_text(encoding='utf-8').splitlines() if s.strip()]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(d, ensure_ascii=False, sort_keys=True) + '\n' for d in sorted(rows, key=lambda x: x['id'])), encoding='utf-8')


def clusters(d):
    links = d.get('links') or {}
    result = set(links.get('cluster_ids') or [])
    for c in (d.get('cluster_id'), links.get('cluster_id')):
        if c:
            result.add(c)
    if d['id'].startswith(('fc1:', 'vod_entry:', 'vod_cluster:')):
        result.add(d['id'].split(':', 1)[1].split('#', 1)[0])
    return result


def references(d):
    found = set(REF.findall(d.get('text') or ''))
    found.update((d.get('links') or {}).get('member_atom_ids') or [])
    if d.get('atom_id'):
        found.add(d['atom_id'])
    if d['id'].startswith('vod_atom:'):
        found.add(d['id'][9:])
    ev = d.get('evidence') or {}
    if isinstance(ev, dict):
        found.update(c['atom_id'] for c in ev.get('clips', []) if c.get('atom_id'))
    return found


def split_text(text):
    sections = {'main': [], 'experiment': [], 'pending': []}
    section = 'main'
    title = text.splitlines()[0] if text else ''
    for line in text.splitlines():
        if line.startswith('## '):
            section = ('pending' if '待核' in line or '待验证' in line else
                       'experiment' if '实例佐证' in line else 'main')
        target = section
        if line.startswith('- ') and any(x in line for x in ('hypothesis', '未关闭', '未确认', '未决')):
            target = 'pending'
        sections[target].append(line)
    return {k: ('\n'.join(v).strip() if k == 'main' else title + '\n' + '\n'.join(v).strip()) for k, v in sections.items() if v}


def basic_mode(d):
    if d.get('kind') == 'reject' or d.get('status') == 'noise':
        return 'archive'
    if (d.get('kind') == 'pending' or d.get('claim_type') in ('hypothesis', 'question')
            or d.get('issue_status') in ('open', 'conflict') or d.get('novelty') == 'conflict'
            or d.get('eligibility') in ('needs_av', 'pending', 'rejected')
            or d.get('registry_action', '').startswith('keep_unknown')):
        return 'pending'
    if d.get('kind') == 'experiment' or d.get('scope') in ('instance', 'example') or d.get('record_type') == 'experiment' or d.get('instance_only'):
        return 'experiment'
    return 'mechanism'


def build():
    OUT.mkdir(exist_ok=True)
    hashes = {p: digest(ROOT / p) for p in SOURCES}
    production = {d['id']: d for d in load('kb/docs.jsonl')}
    original = {d['id']: d for d in load(SEM + 'gated_default_v2.jsonl')}
    revised = load(REV + 'revised_default.jsonl')
    feedback = {d['id']: d for d in load(REV + 'feedback.jsonl')}
    fc_modes = {d['cluster_id']: basic_mode(d) for d in revised}
    gated_refs = set()
    for d in revised:
        for name, text in split_text(d['text']).items():
            if name == 'pending':
                gated_refs.update(REF.findall(text))
    user_targets = {}
    for did, f in feedback.items():
        if f['action'] in ('correct', 'trim', 'archive', 'needs_clarification', 'retain_experiment'):
            cid = did.split(':', 1)[1]
            p = production.get('vod_cluster:' + cid, {})
            user_targets[cid] = {'action': f['action'], 'refs': references(original[did]) | (references(p) if p else set())}
    rows, archive, operations = [], [], []
    evidence_files = set()
    evidence_table = {}
    transcript_cache = {}

    def transcript(stem):
        for name in (f'transcripts_txt/{stem}.txt', f'asr_drafts/{stem}_asr.txt', f'asr_drafts/{stem}_asr_draft.txt'):
            if (ROOT / name).exists():
                return name
        return None

    def resolve(ref):
        if ref in evidence_table:
            return evidence_table[ref]
        if 'sub:' in ref:
            stem, sec = ref.split('sub:', 1)[1].rsplit(':', 1)
            path = transcript(stem)
            value = {'id': ref, 'status': 'unresolved', 'source_layers': ['unknown']}
            if path:
                evidence_files.add(path)
                if path not in transcript_cache:
                    timed = []
                    for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
                        m = re.match(r'\[(\d+:\d+(?::\d+)?)\]', line)
                        if m:
                            t = 0
                            for n in m[1].split(':'):
                                t = t * 60 + int(n)
                            timed.append((t, line))
                    transcript_cache[path] = timed
                timed = transcript_cache[path]
                prior = [x for x in timed if x[0] <= int(sec)]
                if prior and int(sec) - prior[-1][0] <= 120:
                    value = {'id': ref, 'status': 'resolved_timestamp_window', 'file': path,
                             'requested_second': int(sec), 'quote_line': prior[-1][1],
                             'source_layers': ['official' if path.startswith('transcripts') else 'asr']}
        else:
            atom = production.get('vod_atom:' + ref)
            if atom:
                stem = (atom.get('source') or {}).get('bvid_stem') or ref.split(':')[0]
                path = transcript(stem)
                if path:
                    evidence_files.add(path)
                layer = 'official' if path and path.startswith('transcripts') else 'asr' if path else 'unknown'
                value = {'id': ref, 'status': 'resolved_atom', 'source_doc_id': atom['id'],
                         'source': atom.get('source'), 'evidence': atom.get('evidence'),
                         'transcript_file': path, 'source_layers': [layer]}
            else:
                value = {'id': ref, 'status': 'unresolved', 'source_layers': ['unknown']}
        evidence_table[ref] = value
        return value

    def enrich(d, source_path, original_id=None):
        d = copy.deepcopy(d)
        d['status'] = 'draft'
        if 'conflict_resolution' in d:
            d['historical_conflict_resolution'] = d.pop('conflict_resolution')
        d['conflict_policy'] = 'review_both_evidence_and_conditions_no_automatic_verdict'
        d['provenance'] = {'file': source_path, 'sha256': hashes[source_path], 'record_id': original_id or d['id']}
        d['citation_ids'] = sorted(references(d))
        layers = set()
        for ref in d['citation_ids']:
            layers.update(resolve(ref)['source_layers'])
        ev = d.get('evidence')
        if isinstance(ev, list):
            for e in ev:
                path = e.get('file')
                if path and (ROOT / path).exists():
                    evidence_files.add(path)
                    layers.add('official' if path.startswith('transcripts_txt/') else 'asr' if path.startswith('asr_drafts/') else 'unknown')
        if d.get('track') == 'qq':
            layers.add('qq')
        if not layers:
            src = d.get('source') or {}
            if isinstance(src, dict):
                stems = src.get('stems') or [src.get('bvid_stem')]
                for stem in filter(None, stems):
                    path = transcript(stem)
                    if path:
                        evidence_files.add(path)
                        layers.add('official' if path.startswith('transcripts') else 'asr')
        d['source_layers'] = sorted(layers or {'unknown'})
        d['track'] = ('qq' if d['source_layers'] == ['qq'] else 'vod_official' if d['source_layers'] == ['official'] else 'vod_cloud' if d['source_layers'] == ['asr'] else 'mixed_or_unknown')
        own = feedback.get(original_id or d['id'])
        d['review'] = {'human': 'unreviewed', 'agent': 'inherited_draft_labels', 'not_authoritative': True}
        if own and own.get('reviewer_type') == 'user':
            d['review']['human'] = 'accepted' if own['action'] == 'accept' else 'feedback_applied_not_reapproved'
            d['review']['feedback'] = own
        candidates = sorted(c for c in clusters(d) if re.search(r'-\d+-\d+$', c))
        d['category'] = d.get('category') or (candidates[0].split('-')[0] if candidates else '未分类')
        if d.get('render_only_revision'):
            d['legacy_rule_indices_not_for_rendering'] = {k: d.pop(k) for k in ('affirmative_rule_idx', 'demoted_rule_idx', 'gated_rules') if k in d}
            d['revision_note'] = '用户反馈已应用于本试验检索及旧来源隔离；以当前派生正文为准，禁止旧规则索引重新渲染。修改稿未获用户再次确认。'
        d['doc_type'] = d.get('doc_type') or 'trial_archive'
        return d

    def add(d, path, mode=None):
        d = enrich(d, path)
        mode = mode or basic_mode(d)
        if mode != 'archive':
            corrections = []
            refs = references(d)
            for before, after, cid, prefixes in (
                ('镜像力', '径向力', '其他-9-11', ('BV1qReG6XE6W_p1_41897493495:p22:', 'BV1qReG6XE6W_p1_41897493495:p23:', 'BV1qReG6XE6W_p1_41897493495:p24:', 'BV1qReG6XE6W_p1_41897493495:p25:')),
                ('维尼斯', '维云斯', '位移-4-5', ('BV14y8269EbS_p2_41167359561:p9:',)),
            ):
                if before in d['text'] and any(r.startswith(prefixes) for r in refs):
                    d['text'] = d['text'].replace(before, after)
                    corrections.append({'from': before, 'to': after, 'authority': 'user', 'feedback_id': 'fc1:' + cid,
                                        'application': 'agent propagation over exact source atom prefixes', 'prefixes': list(prefixes)})
                    if before == '镜像力':
                        d['text'] = '\n'.join(line for line in d['text'].splitlines() if not ('径向力' in line and any(cue in line for cue in ('关系未说明', '两说', '档案备注'))))
                    if before == '维尼斯':
                        d['text'] += '\n实体消歧: 维云斯为主播，非干员。'
            if corrections:
                d['term_corrections'] = d.get('term_corrections', []) + corrections
                operations.append({'id': d['id'], 'authority': 'user', 'action': 'derived_text_correction', 'corrections': corrections})
            if any(resolve(ref)['status'] == 'unresolved' for ref in refs):
                mode = 'pending'
                d['isolation_reason'] = 'unresolved citation; retained for review'
        parts = split_text(d.get('text') or '')
        if mode in ('pending', 'archive'):
            d['mode'] = mode
            archive.append(d)
            return
        d['text'] = parts.get('main', '')
        d['mode'] = mode
        if d['text'].strip():
            rows.append(d)
        for key, part_mode in (('experiment', 'experiment'), ('pending', 'pending')):
            if key in parts:
                sub = copy.deepcopy(d)
                sub['id'] += '#' + key
                sub['text'], sub['mode'] = parts[key], part_mode
                sub['review']['human'] = 'unreviewed'
                sub['review']['derived_section_from'] = d['id']
                (archive if part_mode == 'pending' else rows).append(sub)

    for d in revised:
        add(d, REV + 'revised_default.jsonl')
    for path in (SEM + 'gated_archive_v2.jsonl', REV + 'archived_by_feedback.jsonl'):
        for d in load(path):
            mode = 'archive' if d.get('kind') == 'reject' or 'reject' in d.get('archive_reason', '') or 'registry_drop' in d.get('archive_reason', '') else 'pending'
            add(d, path, mode)
    archived_cids = set().union(*(clusters(d) for d in archive if d['id'].startswith('fc1:') and '#' not in d['id']))
    legacy = [(d, SEM + 'gated_old_kept_v2.jsonl') for d in load(SEM + 'gated_old_kept_v2.jsonl')]
    for path in SOURCES:
        if '/mechanisms.jsonl' in path or '/experiments.jsonl' in path:
            for d in load(path):
                d = dict(d)
                if '/evidence_round1/' in path:
                    d['id'] = 'er1:' + d['id']
                d['doc_type'] = 'pilot_evidence'
                d['kind'] = 'experiment' if '/experiments.' in path else 'mechanism'
                d['retrieval_boost'] = 1.6 if d.get('rag_gate') else 0.4
                if not d.get('rag_gate') and d['kind'] != 'experiment':
                    d['kind'] = 'pending'
                legacy.append((d, path))
    for d, path in legacy:
        cids, refs = clusters(d), references(d)
        matched = sorted(cid for cid, target in user_targets.items() if cid in cids or refs & target['refs'])
        mode = basic_mode(d)
        if matched:
            actions = {user_targets[c]['action'] for c in matched}
            if actions <= {'retain_experiment'}:
                mode = 'experiment'
            else:
                mode = 'pending' if 'needs_clarification' in actions else 'archive'
            d = dict(d, overlay={'authority': 'user', 'cluster_ids': matched, 'actions': sorted(actions),
                                'reason': 'exact cluster/member/citation provenance; original retained; use revised fc1 representation'})
            operations.append({'id': d['id'], **d['overlay'], 'mode': mode})
        elif cids & archived_cids or refs & gated_refs:
            mode = 'pending'
            d = dict(d, isolation_reason='exact archived cluster or gated evidence reference; conservative, not semantic coverage')
        elif any(fc_modes.get(c) == 'experiment' for c in cids):
            mode = 'experiment'
        add(d, path, mode)
    # Some legacy registry rows occur in both gate files.
    archive = list({d['id']: d for d in archive}.values())
    archive_ids = {d['id'] for d in archive}
    rows = [d for d in rows if d['id'] not in archive_ids]
    assert len(rows) == len({d['id'] for d in rows})
    for path in sorted(evidence_files):
        hashes[path] = digest(ROOT / path)
    for name, data in (('docs.jsonl', rows), ('archive.jsonl', archive), ('evidence.jsonl', list(evidence_table.values())), ('overlay.jsonl', operations)):
        write_rows(OUT / name, data)
    entities = json.loads((ROOT / 'kb/entity_index.json').read_text(encoding='utf-8'))
    entities['trial_user_aliases'] = {'镜像力': {'canonical': '径向力', 'type': 'mechanic', 'authority': 'user', 'scope_cluster': '其他-9-11'},
                                      '维尼斯': {'canonical': '维云斯', 'type': 'streamer', 'authority': 'user', 'scope_cluster': '位移-4-5'},
                                      '鼠传送': {'canonical': '黍传送', 'type': 'operator_mechanic', 'authority': 'user', 'scope_cluster': '位移-1-0,寻路-0-11'},
                                      '血屋': {'canonical': '血霭遮月', 'type': 'enemy_skill', 'authority': 'user', 'scope_cluster': '索敌-13-8'}}
    dump(OUT / 'entity_index.json', entities)
    all_docs = rows + archive
    stats = {'docs': len(rows), 'archive': len(archive), 'modes': dict(Counter(d['mode'] for d in all_docs)),
             'categories': dict(Counter(d['category'] for d in all_docs)),
             'source_layers': dict(Counter('+'.join(d['source_layers']) for d in all_docs)),
             'doc_types': dict(Counter(d['doc_type'] for d in all_docs)),
             'human_review': dict(Counter(d['review']['human'] for d in all_docs)),
             'evidence_resolution': dict(Counter(e['status'] for e in evidence_table.values())),
             'user_overlay_operations': len(operations),
             'user_overlay_old_records': sum('mode' in op for op in operations),
             'user_term_propagation_records': sum(op.get('action') == 'derived_text_correction' for op in operations)}
    manifest = {'schema_version': 1, 'entrypoint': 'kb_trial_search.py', 'build_command': 'python kb_build_trial.py',
                'status': 'local_draft', 'external_api_calls': 0, 'source_sha256': hashes, 'statistics': stats,
                'code_sha256': {p: digest(ROOT / p) for p in ('kb_build_trial.py', 'kb_trial_search.py')},
                'outputs_sha256': {p.name: digest(p) for p in sorted(OUT.iterdir()) if p.name in ('docs.jsonl', 'archive.jsonl', 'evidence.jsonl', 'overlay.jsonl', 'entity_index.json')}}
    assert all(digest(ROOT / p) == h for p, h in hashes.items())
    dump(OUT / 'manifest.json', manifest)
    print(json.dumps(stats, ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
