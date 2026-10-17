#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/stats.py - 统一统计 + 刷新文档里的数字（纯标准库，无网络）

从已提交的产物直接实测：
  - kb_trial/curated_high_quality.json：条数、来源层/轨、审核状态、证据审核、scope、类别、sha256
  - glossary.json：词条数、带释义数
  - transcripts_txt/ cleaned_subtitles/ subtitles/：文件数

文档中两种受管区域（本脚本只改区域内部，区域外正文不动）：
  1. 块：  <!-- stats:start -->  …生成的统计表…  <!-- stats:end -->
  2. 行内：<!-- stat:KEY -->值<!-- /stat -->      （KEY 见 inline_values()）

用法（在仓库根目录）：
  python tools/stats.py            # 打印统计 JSON
  python tools/stats.py --write    # 刷新 README.md / AGENTS.md / kb_trial/CURATED_OVERVIEW.md
  python tools/stats.py --check    # 文档数字过期或缺少受管区域时以非零退出（CI 用）

sha256 口径：按 LF 换行计算（即 git 仓库内的内容）。Windows 上若开启 core.autocrlf，
工作区文件是 CRLF，直接对其求 sha 会得到另一个值；本脚本同时给出 CRLF 口径以便对账。
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'
GLOSSARY = ROOT / 'glossary.json'
STAGING = ROOT / 'kb_trial' / 'curation' / 'curated_staging.json'
DOCS = ['README.md', 'AGENTS.md', 'kb_trial/CURATED_OVERVIEW.md']

BLOCK_RE = re.compile(r'(<!-- stats:start -->\n)(.*?)(<!-- stats:end -->)', re.S)
INLINE_RE = re.compile(r'(<!-- stat:([a-z0-9_]+) -->)(.*?)(<!-- /stat -->)')


def sha256_lf(path):
    data = path.read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest(), hashlib.sha256(data.replace(b'\n', b'\r\n')).hexdigest()


def compute():
    payload = json.loads(CURATED.read_text(encoding='utf-8'))
    entries = payload['entries']
    gloss = json.loads(GLOSSARY.read_text(encoding='utf-8'))['entries']
    staging = json.loads(STAGING.read_text(encoding='utf-8')) if STAGING.exists() else {}
    lf, crlf = sha256_lf(CURATED)
    qq_batches = Counter(('早期QQ窗口卡(window:*)' if e['track'] == 'qq' else e['origin'].get('card_section'))
                         for e in entries if e['track'] in ('qq', 'qq_chat'))
    cats = Counter(e['category'] for e in entries)
    return {
        'curated_file': 'kb_trial/curated_high_quality.json',
        'schema_version': payload.get('schema_version'),
        'card_count': len(entries),
        'entry_count_field': payload.get('entry_count'),
        'curated_sha256': lf,
        'curated_sha256_crlf': crlf,
        'by_source_layer': dict(Counter(e['source_layer'] for e in entries).most_common()),
        'by_track': dict(Counter(e['track'] for e in entries).most_common()),
        'qq_by_batch': dict(qq_batches.most_common()),
        'by_review_status': dict(Counter(e['review']['status'] for e in entries).most_common()),
        'by_evidence_status': dict(Counter(e['evidence_review']['status'] for e in entries).most_common()),
        'by_scope': dict(Counter(e['scope'] for e in entries).most_common()),
        'category_count': len(cats),
        'category_singletons': sum(1 for v in cats.values() if v == 1),
        'top_categories': dict(cats.most_common(10)),
        'derived_text_repairs': sum(1 for e in entries if e.get('derived_text_repairs')),
        'staging_count': len(staging.get('entries', [])),
        'glossary_count': len(gloss),
        'glossary_short_def': sum(1 for t in gloss if t.get('short_def')),
        'glossary_mechanic_def': sum(1 for t in gloss if t.get('mechanic_def')),
        'transcript_count': len(list((ROOT / 'transcripts_txt').glob('*.txt'))),
        'cleaned_subtitle_count': len(list((ROOT / 'cleaned_subtitles').glob('*.json'))),
        'subtitle_count': len(list((ROOT / 'subtitles').glob('*.json'))),
    }


def inline_values(s):
    layer = s['by_source_layer']
    rv = s['by_review_status']
    return {
        'card_count': str(s['card_count']),
        'card_qq': str(layer.get('QQ群聊', 0)),
        'card_official': str(layer.get('官方AI字幕', 0)),
        'card_cloud': str(layer.get('云端ASR重转写(无官方字幕分P)', 0)),
        'card_mixed': str(layer.get('官方AI字幕+云端ASR重转写', 0)),
        'agent_verified': str(rv.get('agent_verified', 0)),
        'user_verified': str(rv.get('user_verified', 0)),
        'glossary_count': str(s['glossary_count']),
        'glossary_mechanic_def': str(s['glossary_mechanic_def']),
        'transcript_count': str(s['transcript_count']),
        'curated_sha256': s['curated_sha256'],
    }


def fmt(d):
    return '、'.join(f'{k} {v}' for k, v in d.items())


def block(s):
    rows = [
        ('甄选知识卡条数（`entries`）', f"**{s['card_count']}**（`entry_count` 字段 {s['entry_count_field']}）"),
        ('来源层 `source_layer`', fmt(s['by_source_layer'])),
        ('来源轨 `track`', fmt(s['by_track'])),
        ('QQ 轨按批次（`origin.card_section`）', fmt(s['qq_by_batch'])),
        ('`review.status`', fmt(s['by_review_status'])),
        ('`evidence_review.status`', fmt(s['by_evidence_status'])),
        ('`scope`', fmt(s['by_scope'])),
        ('类别 `category`', f"{s['category_count']} 种（其中 {s['category_singletons']} 种仅 1 条）；前 10：{fmt(s['top_categories'])}"),
        ('含 `derived_text_repairs` 的条目', str(s['derived_text_repairs'])),
        ('隔离（`curation/curated_staging.json`）', str(s['staging_count'])),
        ('黑话词表 `glossary.json`', f"{s['glossary_count']} 条（`short_def` {s['glossary_short_def']}、`mechanic_def` {s['glossary_mechanic_def']}）"),
        ('逐字稿 / 清洗字幕 / 原始字幕', f"{s['transcript_count']} / {s['cleaned_subtitle_count']} / {s['subtitle_count']} 个分P文件"),
        ('`curated_high_quality.json` sha256（LF）', f"`{s['curated_sha256']}`"),
        ('同上（CRLF 工作区口径）', f"`{s['curated_sha256_crlf']}`"),
    ]
    out = ['> 本区块由 `python tools/stats.py --write` 生成，请勿手改；CI 以 `--check` 校验。',
           '> 区块外正文中带日期的数字是当时时点的记录，以本区块为准。', '',
           '| 维度 | 实测值 |', '| --- | --- |']
    out += [f'| {k} | {v} |' for k, v in rows]
    return '\n'.join(out) + '\n'


def render(text, s):
    vals = inline_values(s)
    unknown = []

    def sub_inline(m):
        key = m.group(2)
        if key not in vals:
            unknown.append(key)
            return m.group(0)
        return m.group(1) + vals[key] + m.group(4)

    text = INLINE_RE.sub(sub_inline, text)
    text = BLOCK_RE.sub(lambda m: m.group(1) + block(s) + m.group(3), text)
    return text, unknown


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument('--write', action='store_true', help='刷新文档受管区域')
    g.add_argument('--check', action='store_true', help='文档过期则非零退出')
    args = p.parse_args(argv)
    s = compute()
    if not (args.write or args.check):
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    problems = []
    if s['entry_count_field'] != s['card_count']:
        problems.append(f"curated entry_count 字段 {s['entry_count_field']} != entries {s['card_count']}")
    for rel in DOCS:
        path = ROOT / rel
        raw = path.read_bytes().decode('utf-8')
        text = raw.replace('\r\n', '\n')
        if not BLOCK_RE.search(text):
            problems.append(f'{rel}: 缺少 <!-- stats:start --> … <!-- stats:end --> 区块')
        new, unknown = render(text, s)
        for key in unknown:
            problems.append(f'{rel}: 未知的行内统计键 {key}')
        if new != text:
            if args.write:
                path.write_bytes(new.encode('utf-8'))
                print(f'updated {rel}')
            else:
                problems.append(f'{rel}: 统计数字过期，请运行 python tools/stats.py --write')
    for msg in problems:
        print('STATS:', msg, file=sys.stderr)
    if problems:
        return 1
    print('stats ok' if args.check else 'stats written')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
