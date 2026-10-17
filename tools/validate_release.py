#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/validate_release.py - 甄选层发布校验（只用已提交文件，纯标准库，无网络）

FAIL（非零退出）= 结构错误：
  - curated_high_quality.json 无法解析 / schema_version / entry_count 与 entries 不符
  - id 缺失、非字符串或重复；必需字段缺失或为空；review.status 取值非法
  - citation 缺 id/status/quotes，quote 缺 text；既无 transcript_file 也无 window_id
  - transcript_file 指向仓库内已提交层却不存在（不在被忽略的草稿目录里）
  - QQ citation 的 window_id 在 qq_cards/cards.jsonl 中找不到
  - 根目录 curated_high_quality.json 与 kb_trial/ 副本不一致

WARN（不影响退出码）= 已知、需人工了解的局限：
  - 引文指向未入库的本地草稿（asr_drafts/、cloud_clips/，被 .gitignore 忽略），外部无法核对
  - 引文与当前逐字稿对不上（引文保留生成时的原始逐字文本，逐字稿之后又用新规则重新清洗过）
  - curated_validation.json 记录的 sha256 与当前文件（LF/CRLF 两种口径）都不一致

用法：
  python tools/validate_release.py              # 汇总
  python tools/validate_release.py --verbose    # 列出每条 WARN 明细
  python tools/validate_release.py --json       # 机器可读报告
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'
ROOT_COPY = ROOT / 'curated_high_quality.json'
QQ_CARDS = ROOT / 'qq_cards' / 'cards.jsonl'
VALIDATION = ROOT / 'kb_trial' / 'curation' / 'curated_validation.json'

REQUIRED = ('id', 'claim', 'subject', 'condition', 'scope', 'category', 'source_layer',
            'source_layers', 'track', 'citations', 'review', 'evidence_review')
REVIEW_STATUSES = {'user_verified', 'agent_verified', 'auto_screened'}
UNTRACKED_DRAFT_DIRS = ('asr_drafts/', 'cloud_clips/')  # .gitignore 忽略的草稿层
TS_RE = re.compile(r'\[\d{1,2}:\d{2}(?::\d{2})?\]')
STRIP_RE = re.compile(r'[\s，。、！？,.!?…：:；;“”"\'（）()]')


def norm(text):
    return STRIP_RE.sub('', TS_RE.sub('', text))


def quote_found(quote, haystack):
    # 引文里用省略号连接的多段，各段分别须在原文中出现
    parts = [norm(p) for p in re.split(r'…|\.\.\.', quote)]
    parts = [p for p in parts if p]
    return bool(parts) and all(p in haystack for p in parts)


def validate():
    fails, warns = [], defaultdict(list)
    payload = json.loads(CURATED.read_text(encoding='utf-8'))
    entries = payload.get('entries')
    if not str(payload.get('schema_version', '')).startswith('curated-'):
        fails.append('schema_version 缺失或不是 curated-*')
    if not isinstance(entries, list) or not entries:
        return ['entries 缺失或为空'], warns, {}
    if payload.get('entry_count') != len(entries):
        fails.append(f"entry_count={payload.get('entry_count')} 与 entries 长度 {len(entries)} 不符")

    if ROOT_COPY.exists() and ROOT_COPY.read_bytes() != CURATED.read_bytes():
        fails.append('根目录 curated_high_quality.json 与 kb_trial/curated_high_quality.json 不一致')

    windows = set()
    if QQ_CARDS.exists():
        for line in QQ_CARDS.read_text(encoding='utf-8').splitlines():
            if line.strip():
                windows.add(json.loads(line).get('window_id'))

    ids = Counter()
    transcript_cache = {}
    n_cit = n_quote_checked = 0
    for i, e in enumerate(entries):
        eid = e.get('id')
        if not isinstance(eid, str) or not eid:
            fails.append(f'entries[{i}]: id 缺失或非字符串')
            eid = f'entries[{i}]'
        ids[eid] += 1
        for field in REQUIRED:
            if field not in e or e[field] in (None, '', [], {}):
                fails.append(f'{eid}: 必需字段 {field} 缺失或为空')
        status = (e.get('review') or {}).get('status')
        if status not in REVIEW_STATUSES:
            fails.append(f'{eid}: review.status={status!r} 非法')
        for c in e.get('citations') or []:
            n_cit += 1
            cid = c.get('id', '?')
            for field in ('id', 'status', 'quotes'):
                if not c.get(field):
                    fails.append(f'{eid} / {cid}: citation 缺少 {field}')
            quotes = c.get('quotes') or []
            if any(not (q or {}).get('text') for q in quotes):
                fails.append(f'{eid} / {cid}: quote 缺少 text')
            tf, win = c.get('transcript_file'), c.get('window_id')
            if not tf and not win:
                fails.append(f'{eid} / {cid}: 既无 transcript_file 也无 window_id')
            if win and windows and win not in windows:
                fails.append(f'{eid} / {cid}: window_id {win} 不在 qq_cards/cards.jsonl')
            if not tf:
                continue
            if tf.startswith('/') or '..' in Path(tf).parts:
                fails.append(f'{eid} / {cid}: transcript_file 不是仓库相对路径: {tf}')
                continue
            path = ROOT / tf
            if not path.exists():
                if tf.startswith(UNTRACKED_DRAFT_DIRS):
                    warns['citation_untracked_draft'].append(f'{eid} -> {tf}')
                else:
                    fails.append(f'{eid} / {cid}: transcript_file 不存在: {tf}')
                continue
            if tf.endswith('.txt'):
                if tf not in transcript_cache:
                    transcript_cache[tf] = norm(path.read_text(encoding='utf-8'))
                for q in quotes:
                    if not (q or {}).get('text'):
                        continue
                    n_quote_checked += 1
                    if not quote_found(q['text'], transcript_cache[tf]):
                        warns['quote_not_in_current_transcript'].append(
                            f"{eid} -> {tf} @{q.get('t_start')}s 「{q['text'][:40]}」")
    for eid, n in ids.items():
        if n > 1:
            fails.append(f'id 重复 {n} 次: {eid}')

    if VALIDATION.exists():
        rec = json.loads(VALIDATION.read_text(encoding='utf-8')).get('curated_sha256')
        data = CURATED.read_bytes().replace(b'\r\n', b'\n')
        lf, crlf = hashlib.sha256(data).hexdigest(), hashlib.sha256(data.replace(b'\n', b'\r\n')).hexdigest()
        if rec not in (lf, crlf):
            warns['validation_sha_stale'].append(f'curated_validation.json 记录 {rec}，当前 LF {lf} / CRLF {crlf}')

    summary = {
        'entries': len(entries),
        'citations': n_cit,
        'transcript_quotes_checked': n_quote_checked,
        'failures': len(fails),
        'warnings': {k: len(v) for k, v in sorted(warns.items())},
        'untracked_draft_files': dict(Counter(w.split(' -> ')[1] for w in warns.get('citation_untracked_draft', []))),
        'quote_mismatch_by_file': dict(Counter(w.split(' -> ')[1].split(' @')[0]
                                               for w in warns.get('quote_not_in_current_transcript', [])).most_common()),
    }
    return fails, warns, summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--verbose', '-v', action='store_true')
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)
    fails, warns, summary = validate()
    if args.json:
        print(json.dumps({'summary': summary, 'failures': fails, 'warnings': warns}, ensure_ascii=False, indent=2))
        return 1 if fails else 0
    for msg in fails:
        print('FAIL', msg)
    labels = {
        'citation_untracked_draft': '引文指向未入库的本地草稿（asr_drafts/、cloud_clips/），外部无法核对',
        'quote_not_in_current_transcript': '引文与当前逐字稿对不上（引文保留原始文本，逐字稿已重新清洗）',
        'validation_sha_stale': 'curated_validation.json 的 sha256 与当前文件不符',
    }
    for key, items in sorted(warns.items()):
        print(f'WARN {labels.get(key, key)}: {len(items)}')
        if key == 'citation_untracked_draft':
            for f, n in summary['untracked_draft_files'].items():
                print(f'       {n:4d}  {f}')
        if key == 'quote_not_in_current_transcript':
            for f, n in list(summary['quote_mismatch_by_file'].items())[:5]:
                print(f'       {n:4d}  {f}')
            if len(summary['quote_mismatch_by_file']) > 5:
                print(f"       …共 {len(summary['quote_mismatch_by_file'])} 个文件（--verbose 看逐条）")
        if args.verbose:
            for item in items:
                print('     -', item)
    print(f"entries={summary['entries']} citations={summary['citations']} "
          f"transcript_quotes_checked={summary['transcript_quotes_checked']} "
          f"failures={len(fails)} warnings={sum(len(v) for v in warns.values())}")
    print('RELEASE VALIDATION FAILED' if fails else 'release validation passed (warnings are informational)')
    return 1 if fails else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
