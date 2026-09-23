# -*- coding: utf-8 -*-
"""Scan every QQ-expansion artifact (produced materials AND existing reviews) for identity leaks.

Reports WHERE a leak is (file path + field + seq), never WHAT it is -- no nickname, no QQ
number, no group id is ever echoed, not even masked. Run after any change to the generator.

Only fields that can carry a person's words are scanned: message text, and the reviewer's
free prose (claim / reason / topic / note / quote ...). Structural identifiers are excluded on
purpose, because they are expected to contain window ids, doc ids, sha256 digests and our own
anonymised speaker ids -- flagging those would bury the real findings in noise.

Checks per scanned string:
  * group id, verbatim
  * any real member QQ number (every member who ever spoke, not just the slim pass)
  * any nickname, as the whole string or embedded in running text
  * any bare 6-12 digit run that is not part of an `@<speaker_id>`
  * any `@`-token that is neither a known speaker id nor the "某人" placeholder

Usage:
    python kb_curation_qq_expansion_privacy_scan.py
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial' / 'curation' / 'qq_expansion'
EXPORT = ROOT / 'qq_info' / '1097395794_桃大将军粉丝群_聊天记录.csv'
CLEAN = ROOT / 'qq_info' / 'messages_clean.jsonl'

# Read the group id from the export FILENAME so this script never hard-codes -- and so never
# re-emits -- the literal number.
GROUP_ID = EXPORT.stem.split('_')[0]
BARE_DIGITS = re.compile(r'(?<!\d)\d{6,12}(?!\d)')
AT_TOKEN = re.compile(r'@([^\s@]{1,40})')
PLACEHOLDER = '某人'

# Only these fields may hold a person's words or an identity.
SCAN_FIELD_HINTS = (
    'text', 'claim', 'subject', 'condition', 'scope', 'topic', 'reason',
    'note', 'quote', 'summary', 'evidence', 'verdict_reason', 'excluded',
    'core_conclusions', 'summary_takeaway', 'context_question',
    'underlying_parameters', 'atom_text', 'window_text', 'mapping_note',
)
# Structural fields that legitimately contain ids/digests.
SKIP_FIELD_HINTS = (
    'sha256', 'msg_id', 'doc_id', 'entry_id', 'window_id', 'canonical', 'speaker_id',
    'selection_rule', 'internal_source', 'source_msg_ids', 'file', 'path', 'id',
)


def stream_jsonl(path):
    """Parse JSONL that may contain literal newlines inside string values."""
    text = Path(path).read_text(encoding='utf-8')
    dec = json.JSONDecoder()
    out, i, n = [], 0, len(text)
    while True:
        while i < n and text[i] in ' \t\r\n':
            i += 1
        if i >= n:
            break
        obj, end = dec.raw_decode(text, i)
        out.append(obj)
        i = end
    return out


def load_identities():
    nicks, qqs, speakers = set(), set(), set()
    for m in stream_jsonl(CLEAN):
        if m.get('nick'):
            nicks.add(m['nick'])
        if m.get('qq'):
            qqs.add(str(m['qq']))
        if m.get('speaker_id'):
            speakers.add(m['speaker_id'])
    with open(EXPORT, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            q = (row.get('发送人QQ') or '').strip()
            if q:
                qqs.add(q)
    return nicks, qqs, speakers


def walk(node, path=()):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, path + (str(i),))


def is_identity_field(field_path):
    """True when this field can carry a person's words (so must be redacted)."""
    joined = '.'.join(field_path).lower()
    if any(h in joined for h in SKIP_FIELD_HINTS):
        return False
    return any(h in joined for h in SCAN_FIELD_HINTS)


def seq_of(path):
    for i, p in enumerate(path[:-1]):
        if p == 'seq':
            return path[i + 1]
    return None


def scan_file(path, nicks, qqs, speakers, results, target_label):
    try:
        if path.suffix == '.jsonl':
            payload = stream_jsonl(path)
        elif path.suffix == '.json':
            payload = json.loads(path.read_text(encoding='utf-8'))
        else:
            payload = path.read_text(encoding='utf-8')
    except Exception as exc:
        results.append({'file': str(path.relative_to(ROOT)).replace('\\', '/'),
                        'target': target_label, 'kind': 'unparsable',
                        'field': None, 'seq': None, 'detail': type(exc).__name__})
        return

    rel = str(path.relative_to(ROOT)).replace('\\', '/')
    for field_path, text in walk(payload):
        if not is_identity_field(field_path):
            continue
        base = {'file': rel, 'target': target_label,
                'field': '.'.join(field_path), 'seq': seq_of(field_path)}

        if GROUP_ID in text:
            results.append(dict(base, kind='group_id'))
        for q in qqs:
            if re.search(r'(?<!\d)' + re.escape(q) + r'(?!\d)', text):
                results.append(dict(base, kind='qq_number'))
                break
        if text in nicks:
            results.append(dict(base, kind='nickname_exact'))
        else:
            for n in nicks:
                if len(n) >= 3 and not re.fullmatch(r'[\d\W_]+', n) and n in text:
                    results.append(dict(base, kind='nickname_in_text'))
                    break
        for m in BARE_DIGITS.finditer(text):
            if re.search(r'@[0-9a-f]*$', text[max(0, m.start() - 12):m.start()]):
                continue
            results.append(dict(base, kind='bare_digit_run'))
            break
        for tok in AT_TOKEN.findall(text):
            if tok not in speakers and tok != PLACEHOLDER:
                results.append(dict(base, kind='at_token_not_an_id'))
                break


def main():
    nicks, qqs, speakers = load_identities()
    results = []

    produced = [p for p in sorted(OUT.rglob('*'))
                if p.is_file() and 'reviews' not in p.parts]
    for p in produced:
        scan_file(p, nicks, qqs, speakers, results, 'produced')

    reviews = OUT / 'reviews'
    review_files = [p for p in sorted(reviews.rglob('*')) if p.is_file()] if reviews.exists() else []
    for p in review_files:
        scan_file(p, nicks, qqs, speakers, results, 'existing_review')

    report = {
        'note': '隐私扫描：只报告命中位置（文件/字段/seq），不回显任何昵称、QQ 号或群号。'
                '只扫描可能承载个人言论的字段（消息正文、审核员的 claim/reason/topic/note 等），'
                '结构性 id 字段（msg_id/doc_id/sha256/window_id/speaker_id）按设计排除。',
        'scope': {
            'produced_files_scanned': len(produced),
            'existing_review_files_scanned': len(review_files),
            'nicknames_checked': len(nicks),
            'qq_numbers_checked': len(qqs),
            'speaker_ids_checked': len(speakers),
        },
        'hits_total': len(results),
        'hits_by_kind': dict(Counter(r['kind'] for r in results)),
        'hits_by_target': dict(Counter(r['target'] for r in results)),
        'hits': results,
    }
    (OUT / 'privacy_scan.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    print(json.dumps({k: report[k] for k in
                      ('scope', 'hits_total', 'hits_by_kind', 'hits_by_target')},
                     ensure_ascii=False, indent=1))
    if results:
        print('\nfirst hits (path / field / seq only):')
        for r in results[:25]:
            print('  %s | %s | seq=%s | %s' %
                  (r['file'], r.get('field'), r.get('seq'), r['kind']))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
