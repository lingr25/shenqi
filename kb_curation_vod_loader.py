# -*- coding: utf-8 -*-
"""Incremental loader: turn approved VOD expansion manifests into curated entries.

Modeled after `kb_curation_qq_expansion_loader.py`.
Discovers approved_manifest_*.json in kb_trial/curation/vod_expansion/.
Only manifests with status 'approved' or 'approved_merged' are appended.
While a manifest is 'proposed_*' the loader is inert (returns 0 entries),
keeping the shipped curated_high_quality.json byte-identical until approved.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPANSION = ROOT / 'kb_trial' / 'curation' / 'vod_expansion'
APPROVED_STATUS = 'approved'
MERGED_STATUS = 'approved_merged'


def _load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def entry_id(batch: str, stem: str, local_id: str) -> str:
    return f'vod_expansion:{batch}:{stem}:{local_id}'


def manifest_is_approved(manifest: dict) -> bool:
    return str(manifest.get('status', '')).strip().lower() in (APPROVED_STATUS, MERGED_STATUS)


def discover_manifests():
    """Discover all manifest files in vod_expansion/."""
    if not EXPANSION.exists():
        return {}
    out = {}
    for mf_path in sorted(EXPANSION.glob('approved_manifest_*.json')):
        m = re.match(r'approved_manifest_(.+)\.json$', mf_path.name)
        if m:
            batch = m.group(1)
            out[batch] = mf_path
    return out


def verify_vod_entry(item: dict, batch: str, workorders_dir: Path, reviews_dir: Path, audit_path: Path):
    """Re-verify one VOD manifest entry against frozen materials."""
    errs = []
    wid, lid = item['workorder_id'], item['local_id']
    wo_path = workorders_dir / f'{wid}.json'
    rv_path = reviews_dir / f'{wid}.json'

    if not wo_path.exists():
        return [f'{wid}/{lid}: workorder file missing']
    if not rv_path.exists():
        return [f'{wid}/{lid}: review file missing']

    wo = _load(wo_path)
    rv = _load(rv_path)

    if rv.get('source_sha256') != wo.get('source_sha256'):
        errs.append(f'{wid}/{lid}: review source_sha256 does not match workorder')

    cand = next((c for c in (rv.get('claims') or []) if c.get('local_id') == lid), None)
    if cand is None:
        errs.append(f'{wid}/{lid}: not present in review claims')

    if audit_path.exists():
        audit = _load(audit_path)
        dec = next((d for d in (audit.get('decisions') or [])
                    if d.get('workorder') == wid and d.get('local_id') == lid), None)
        if dec is None:
            errs.append(f'{wid}/{lid}: audit_decisions has no record for this claim')
        elif dec.get('verdict') != 'keep':
            errs.append(f'{wid}/{lid}: audit verdict is {dec.get("verdict")!r}, not keep')

    # 验证引文在 source_file 中的存在性
    src_file = ROOT / item['source_file']
    if not src_file.exists():
        errs.append(f'{wid}/{lid}: source_file {item["source_file"]} missing')
    else:
        raw_text = src_file.read_text(encoding='utf-8')
        norm_raw = re.sub(r'[\s，。、；：()（）,.;:！？、]', '', raw_text)
        for ev in item.get('evidence') or []:
            norm_q = re.sub(r'[\s，。、；：()（）,.;:！？、]', '', ev.get('text', ''))
            if norm_q not in norm_raw:
                errs.append(f'{wid}/{lid}: quote not traceable in {item["source_file"]}')

    return errs


def build_vod_entry(item: dict, batch: str):
    """Construct one curated entry dict from an approved manifest item."""
    eid = entry_id(batch, item['stem'], item['local_id'])
    is_official = 'transcripts_txt' in item.get('source_file', '')
    source_layer = '官方AI字幕' if is_official else '云端ASR重转写(无官方字幕分P)'
    source_layers = ['official'] if is_official else ['asr']
    track = 'vod_official' if is_official else 'vod_cloud'

    quotes = [
        {
            'text': q.get('text', ''),
            't_start': q.get('t_start'),
            't_end': q.get('t_end'),
        }
        for q in item.get('evidence') or []
    ]

    citation = {
        'id': eid,
        'status': 'resolved_atom',
        'source_layers': source_layers,
        'transcript_file': item.get('source_file'),
        'bvid_stem': item.get('stem'),
        'recorded_at': item.get('recorded_at'),
        'quotes': quotes,
        '_upstream_quote': quotes[0]['text'] if quotes else None,
    }

    entry = {
        'id': eid,
        'claim': item['claim'],
        'subject': item.get('subject') or '未标注',
        'condition': item.get('condition') or '未标注',
        'scope': item.get('scope') or 'universal',
        'category': item.get('category') or '未标注',
        'recorded_ym': item.get('recorded_at')[:7] if item.get('recorded_at') else None,
        'source_layer': source_layer,
        'source_layers': source_layers,
        'track': track,
        'citations': [citation],
        'source_files': [item['source_file']],
        'origin': {
            'batch': batch,
            'stem': item.get('stem'),
            'workorder_id': item.get('workorder_id'),
            'manifest': f'kb_trial/curation/vod_expansion/approved_manifest_{batch}.json',
            'card_section': '规则',
        },
        'review': {
            'status': 'agent_verified',
            'reviewer_model': item.get('reviewer_model'),
            'reason': item.get('reason') or '代理逐条读源审查通过',
            'not_authoritative': True,
        },
        'conflict_policy': (
            'no automatic precedence: where sources disagree, all sides must be shown '
            'and the disagreement left standing for a human to resolve; nothing is '
            'auto-adjudicated by source layer'
        ),
        'disclaimer': (
            '草稿层条目：本层是草稿，不是官方发布；数值与机制结论在用于生产前应回看引文所指时刻的原片。'
            '上游授权与公开范围由项目负责人决定。'
        ),
    }
    return entry


def load_vod_expansion_entries(batch: str, manifest_path: Path = None, require_approved: bool = True, existing_ids: list = None):
    manifest_path = manifest_path or (EXPANSION / f'approved_manifest_{batch}.json')
    report = {
        'batch': batch,
        'manifest_path': str(manifest_path.relative_to(ROOT)).replace('\\', '/'),
        'manifest_status': None,
        'loaded': 0,
        'entry_ids': [],
        'failures': [],
        'skipped_reason': None,
    }
    if not manifest_path.exists():
        report['skipped_reason'] = 'manifest file missing'
        return [], report

    mf = _load(manifest_path)
    status = str(mf.get('status', '')).strip().lower()
    report['manifest_status'] = status

    if require_approved and not manifest_is_approved(mf):
        report['skipped_reason'] = f'manifest status is {status!r}, requires approved or approved_merged'
        return [], report

    workorders_dir = EXPANSION / f'workorders_{batch}'
    reviews_dir = EXPANSION / f'reviews_{batch}'
    audit_path = EXPANSION / f'audit_decisions_{batch}.json'

    existing_set = set(existing_ids or [])
    entries = []

    for item in mf.get('entries', []):
        eid = entry_id(batch, item['stem'], item['local_id'])
        if eid in existing_set:
            report['failures'].append(f'{eid}: already present in existing curated set')
            continue

        verr = verify_vod_entry(item, batch, workorders_dir, reviews_dir, audit_path)
        if verr:
            report['failures'].extend(verr)
            continue

        entry = build_vod_entry(item, batch)
        entries.append(entry)
        existing_set.add(eid)
        report['entry_ids'].append(eid)

    report['loaded'] = len(entries)
    report['failures'] = sorted(set(report['failures']))
    return entries, report


def load_all_vod_expansions(existing_ids: list = None, allow_proposed: bool = False):
    """Discover and load all approved VOD expansion manifests."""
    manifests = discover_manifests()
    all_entries = []
    reports = {}
    current_ids = list(existing_ids or [])

    for batch, mf_path in sorted(manifests.items()):
        entries, rep = load_vod_expansion_entries(
            batch, manifest_path=mf_path,
            require_approved=not allow_proposed,
            existing_ids=current_ids,
        )
        reports[batch] = rep
        if entries:
            all_entries.extend(entries)
            current_ids.extend([e['id'] for e in entries])

    return all_entries, reports


def main():
    import argparse
    import sys
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', default=None, help='specific batch to load, or all if omitted')
    p.add_argument('--allow-proposed', action='store_true', help='load proposed manifests')
    args = p.parse_args()

    if args.batch:
        entries, rep = load_vod_expansion_entries(args.batch, require_approved=not args.allow_proposed)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        print(f"Loaded {len(entries)} entries for batch {args.batch}")
    else:
        entries, reps = load_all_vod_expansions(allow_proposed=args.allow_proposed)
        print(json.dumps(reps, ensure_ascii=False, indent=2))
        print(f"Total loaded: {len(entries)} entries across {len(reps)} batches")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
