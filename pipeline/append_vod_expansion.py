#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline/append_vod_expansion.py - 只追加 VOD 扩展批次到已提交的甄选层（纯标准库，无网络）

用途：在新克隆上无法跑完整的 kb_curation_build.py 时（它依赖被 .gitignore 排除的
kb_trial/evidence.jsonl、kb_trial/docs.jsonl、kb_pilot_synth/** 等本地缓存），
对 kb_trial/curated_high_quality.json 做"仅追加"合并：

  1. 读取已提交的 curated_high_quality.json，剔除其中已有的 vod_expansion:* 条目与
     vod_expansion_manifest_* 元数据块（保证可重复运行、幂等）；
  2. 调用 kb_curation_vod_loader.load_all_vod_expansions()——与 kb_curation_build.py
     Phase-6 完全相同的加载与逐条复核（工单/回执 sha256、audit verdict=keep、引文逐字可溯）；
     任一条复核失败即整体中止，不强行并入；
  3. 按 kb_curation_build.py 相同的元数据格式写回 entry_count 与
     vod_expansion_manifest_{batch} 块，并刷新 curated_stats.json 中的计数字段；
  4. 运行 kb_curation_quote_times.py 校准新增引文的行时间（幂等）。

不运行 kb_curation_evidence_apply.py（其 evidence_review_worklist.jsonl 未入库）；
新增条目的审核状态为 loader 赋予的 review.status=agent_verified；本脚本按 QQ 扩展批次的同一口径
为其写入 evidence_review（status=supported，置信上限 text-source-supported，依据为 loader 对
冻结工单/回执/audit 的复核与引文逐字可溯），并在 evidence_review_summary 中单列 vod_expansion_reverified。

用法（仓库根目录）：
  python pipeline/append_vod_expansion.py           # 追加并写回
  python pipeline/append_vod_expansion.py --check   # 只报告，不写盘
之后：python tools/stats.py --write && python rag_pack/build_rag_pack.py && python tools/validate_release.py
"""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kb_curation_vod_loader as VOD_LOADER  # noqa: E402

CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'
STATS = ROOT / 'kb_trial' / 'curation' / 'curated_stats.json'
PREFIX = 'vod_expansion:'


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='只报告，不写盘')
    a = ap.parse_args(argv)

    cur = json.loads(CURATED.read_text(encoding='utf-8'))
    base = [e for e in cur['entries'] if not e['id'].startswith(PREFIX)]
    for k in [k for k in cur if k.startswith('vod_expansion_manifest_')]:
        del cur[k]
    vod_entries, reports = VOD_LOADER.load_all_vod_expansions(existing_ids=[e['id'] for e in base])
    failures = {b: r['failures'] for b, r in reports.items() if r['failures']}
    summary = {b: {'status': r['manifest_status'], 'appended': r['loaded'],
                   'failures': len(r['failures']), 'skipped_reason': r['skipped_reason']}
               for b, r in reports.items()}
    print(json.dumps({'base_entries': len(base), 'batches': summary,
                      'total_after': len(base) + len(vod_entries)}, ensure_ascii=False, indent=2))
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit('VOD expansion re-verification failed; nothing written')
    if a.check:
        return 0

    for e in vod_entries:
        o = e['origin']
        e['evidence_review'] = {
            'status': 'supported',
            'reason': e['review'].get('reason'),
            'reviewer_type': 'agent',
            'confidence': 'text-source-supported',
            'review_basis': '录播扩展 %s：agent 回读冻结工单内的逐字稿窗口后确认该命题有逐字文本出处；'
                            'loader 复核回执 source_sha256、audit verdict=keep 与引文在逐字稿中逐字可溯；'
                            '未做人工核听、未回看原片，也未在游戏内复现。' % o['batch'],
            'limitation': '局限：判定依据是官方 AI 字幕/云端 ASR 文本本身，ASR 讹写与依赖画面的指代无法从文本中完全排除；'
                          '「all reviewed」不代表「all correct」。',
            'supports': 'vod_transcript_verbatim',
            'source_path': 'kb_trial/curation/vod_expansion/workorders_%s/%s.json' % (o['batch'], o['workorder_id']),
            'audit_decision': 'kb_trial/curation/vod_expansion/audit_decisions_%s.json' % o['batch'],
            'reviewer_model': e['review'].get('reviewer_model'),
        }
    entries = base + vod_entries
    ers = cur.get('evidence_review_summary')
    if isinstance(ers, dict):
        n_vod = len(vod_entries)
        prev = ers.get('vod_expansion_reverified', 0)
        ers['vod_expansion_reverified'] = n_vod
        ers['vod_expansion_reverified_by_batch'] = {b: r['loaded'] for b, r in sorted(reports.items())}
        ers['released'] = ers.get('released', 0) - prev + n_vod
    out = {}
    for k, v in cur.items():
        if k == 'entries':
            continue
        out[k] = v
    out['entry_count'] = len(entries)
    for bname, brep in sorted(reports.items()):
        if brep['loaded']:
            out[f'vod_expansion_manifest_{bname}'] = {
                'source': brep['manifest_path'],
                'manifest_status': brep['manifest_status'],
                'appended': brep['loaded'],
                'entry_ids': brep['entry_ids'],
                'note': f'录播轨增量扩展批次 {bname} 的条目：来源为 VOD 逐字稿/ASR，经代理逐条读源审查通过。只追加不改写既有条目。'
                        '本块由 pipeline/append_vod_expansion.py 仅追加写入（未跑完整 kb_curation_build.py）。',
                'skipped_reason': brep['skipped_reason'],
            }
    # keep 'entries' last, as kb_curation_build.py does for its top-level keys order
    payload = {k: v for k, v in cur.items() if k != 'entries'}
    payload.update(out)
    payload['entries'] = entries
    CURATED.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + '\n',
                       encoding='utf-8')

    rc = subprocess.run([sys.executable, 'kb_curation_quote_times.py'], cwd=ROOT,
                        stdout=subprocess.DEVNULL).returncode
    if rc != 0:
        raise SystemExit('kb_curation_quote_times.py failed with code %d' % rc)

    if STATS.exists():
        entries = json.loads(CURATED.read_text(encoding='utf-8'))['entries']
        st = json.loads(STATS.read_text(encoding='utf-8'))
        st.update({
            'entries': len(entries),
            'by_review_status': dict(Counter(e['review']['status'] for e in entries)),
            'by_source_layer': dict(Counter(e['source_layer'] for e in entries)),
            'by_category': dict(Counter(e['category'] for e in entries).most_common()),
            'by_scope': dict(Counter(str(e['scope']) for e in entries).most_common()),
            'by_track': dict(Counter(e['track'] for e in entries).most_common()),
            'source_docs': len({e['origin']['trial_doc_id'] for e in entries}),
            'vod_expansion_appended': {b: r['loaded'] for b, r in sorted(reports.items())},
            'output_sha256': sha256(CURATED),
        })
        STATS.write_text(json.dumps(st, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    print('written: %d entries' % len(entries))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
