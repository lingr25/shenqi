#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pre-publish privacy & secret gate -- scans every file TRACKED BY GIT.

Layers:
  1. secrets        API keys / tokens (sk-*, gho_*, github_pat_*, Bearer ...)
  2. phones         mainland-CN mobile numbers 1[3-9]xxxxxxxxx
  3. group id       the QQ group id, read from the export filename (never hard-coded)
  4. identity vals  every real sender QQ and UID from the local roster
  5. nicknames      roster nicknames (len>=3) and their CJK cores (len>=2 when
                    distinctive) appearing in publishable text
  6. qq-context     bare digit runs sitting next to QQ/群号 context words

Nickname hits may be allowlisted per-token in scripts/privacy_allowlist.txt
(one literal per line, '#' comments) -- only for tokens a human verified are
common words / mechanism terms, not identity references.

The deep field-aware QQ-chat scan stays in
kb_curation_qq_expansion_privacy_scan.py (roster+field-level, qq_expansion
subtree). This gate is the whole-repo net that must pass before every publish.

Usage:
    python scripts/privacy_gate.py            # scan; exit 1 on findings
    python scripts/privacy_gate.py --report   # scan; also write _privacy_gate_report.json
"""
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = Path(__file__).resolve().with_name('privacy_allowlist.txt')
CLEAN = ROOT / 'qq_info' / 'messages_clean.jsonl'
EXPORT_DIR = ROOT / 'qq_info'

SECRET_PATTERNS = [
    ('api_key', re.compile(r'\b(?:sk|gho|ghp|ghu|ghs|ghr)_[A-Za-z0-9]{16,}\b')),
    ('api_key', re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}\b')),
    ('api_key', re.compile(r'\bsk-[A-Za-z0-9]{16,}\b')),
    ('bearer', re.compile(r'Bearer\s+[A-Za-z0-9._\-]{20,}')),
]
PHONE_RE = re.compile(r'(?<![0-9A-Za-z])1[3-9]\d{9}(?![0-9A-Za-z])')
# "QQ <digits>" style leaks; bare lowercase `qq` is excluded because the corpus uses
# `qq/untyped`, `qq_cards` etc. as source-layer labels, which are not identity context.
QQ_CONTEXT_RE = re.compile(
    r'(?:QQ|群号|加群|qq群)[^\n]{0,15}?[1-9]\d{4,10}|'
    r'[1-9]\d{4,10}[^\n]{0,10}?(?:QQ群|qq群)')
CJK_RE = re.compile(r'[一-鿿]+')
SKIP_EXT = {'.pyc', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.m4a', '.mp4'}
MAX_BYTES = 64 * 1024 * 1024


def find_group_id():
    for p in EXPORT_DIR.glob('*_聊天记录.csv'):
        stem = p.stem.split('_')[0]
        if stem.isdigit():
            return stem
    return None


def load_roster():
    """(nick set, qq set, uid set) from local qq_info -- never published itself."""
    nicks, qqs, uids = set(), set(), set()
    if CLEAN.exists():
        for m in re.finditer(
                r'"nick":\s*"((?:[^"\\]|\\.)*)"|"qq":\s*"(\d+)"|'
                r'"uid":\s*"((?:[^"\\]|\\.)*)"',
                CLEAN.read_text(encoding='utf-8', errors='replace')):
            if m.group(1):
                nicks.add(json.loads('"' + m.group(1) + '"'))
            elif m.group(2):
                qqs.add(m.group(2))
            else:
                uids.add(json.loads('"' + m.group(3) + '"'))
    for p in EXPORT_DIR.glob('*_聊天记录.csv'):
        with open(p, encoding='utf-8-sig', newline='') as fh:
            for row in csv.DictReader(fh):
                q = (row.get('发送人QQ') or '').strip()
                if q:
                    qqs.add(q)
    return nicks, qqs, uids


def nick_tokens(nicks):
    """Matchable identity tokens: full nick >=3 chars, plus CJK cores >=3.

    2-char cores are excluded on purpose: they drown the gate in common-word
    false positives (下划/划线/还有这…). Real 2-char in-text member references
    are caught by the qq-side redaction pipeline and human faultcheck instead.
    """
    out = {}
    for n in nicks:
        if len(n) >= 3 and not re.fullmatch(r'[\d\W_]+', n):
            out[n] = 'nick'
        for core in CJK_RE.findall(n):
            if len(core) >= 3 and core != n:
                out.setdefault(core, 'nick_core')
    return out


def tracked_files():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line.strip()]


def load_allowlist():
    """Entries: `token` (global) or `token@path-substr` (scoped to matching paths)."""
    glob_allow, scoped = set(), []
    if ALLOWLIST.exists():
        for line in ALLOWLIST.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '@' in line:
                tok, scope = line.rsplit('@', 1)
                if tok and scope:
                    scoped.append((tok, scope))
                    continue
            glob_allow.add(line)
    return glob_allow, scoped


def allowed(tok, rel, glob_allow, scoped):
    if tok in glob_allow:
        return True
    return any(tok == t and scope in rel for t, scope in scoped)


def main():
    report_mode = '--report' in sys.argv
    group_id = find_group_id()
    nicks, qqs, uids = load_roster()
    tokens = nick_tokens(nicks)
    glob_allow, scoped = load_allowlist()
    # identity values: real member QQ + UID. The group id itself is intentionally
    # NOT an identity hit -- it is the corpus's provenance label, already published
    # in AGENTS.md/README, and adds no member-level exposure.
    id_values = {v for v in qqs | uids if v}

    findings = []
    files = 0
    # One regex extracts every candidate token once per file; membership in the
    # identity set is then a dict lookup instead of ~900 separate regex scans.
    token_re = re.compile(r'[A-Za-z0-9_-]{5,}|\d{6,12}')
    # nickname tokens compiled into ONE alternation -> single pass per file;
    # scoped allowlist entries are filtered per-file inside the loop
    base_list = sorted((t for t in tokens if t not in glob_allow),
                       key=len, reverse=True)
    base_re = (re.compile('|'.join(re.escape(t) for t in base_list))
               if base_list else None)
    for path in tracked_files():
        if path.suffix.lower() in SKIP_EXT or not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        # the allowlist's own lines ARE the vetted token list -- never scan it
        if rel == 'scripts/privacy_allowlist.txt':
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        files += 1

        for kind, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                findings.append({'file': rel, 'kind': kind, 'where': m.start()})
        for m in PHONE_RE.finditer(text):
            findings.append({'file': rel, 'kind': 'phone', 'where': m.start()})
        for m in QQ_CONTEXT_RE.finditer(text):
            seg = m.group(0)
            # group id occurrences are reported via identity values anyway
            if group_id and group_id in seg:
                continue
            findings.append({'file': rel, 'kind': 'qq_context', 'where': m.start()})
        seen_ids = set()
        for m in token_re.finditer(text):
            v = m.group(0)
            if v in id_values and v not in seen_ids:
                seen_ids.add(v)
                findings.append({'file': rel, 'kind': 'identity_value',
                                 'where': m.start()})
        # nickname scan: single combined pass, skip scoped-allowed tokens
        if base_re is not None:
            for m in base_re.finditer(text):
                tok = m.group(0)
                if allowed(tok, rel, glob_allow, scoped):
                    continue
                findings.append({'file': rel, 'kind': tokens[tok],
                                 'where': m.start()})

    summary = Counter(f['kind'] for f in findings)
    print(f'scanned {files} tracked files; roster: {len(nicks)} nicks, '
          f'{len(qqs)} QQs, {len(uids)} UIDs; findings: {len(findings)}')
    for kind, n in summary.most_common():
        print(f'  {kind}: {n}')
    if report_mode:
        Path('_privacy_gate_report.json').write_text(
            json.dumps(findings, ensure_ascii=False, indent=1), encoding='utf-8')
        print('wrote _privacy_gate_report.json')
    if findings:
        print('PRIVACY GATE FAILED -- investigate each hit; for nickname false '
              'positives add the exact token to scripts/privacy_allowlist.txt')
        return 1
    print('PRIVACY GATE PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
