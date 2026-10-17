#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/check_json.py - 解析全部已提交的 *.json / *.jsonl（纯标准库）

用法：python tools/check_json.py      # 任何文件解析失败则非零退出
文件清单取自 `git ls-files`，不扫描被 .gitignore 忽略的本地目录。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    files = subprocess.run(['git', 'ls-files', '-z', '*.json', '*.jsonl'], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode('utf-8').split('\0')
    files = [f for f in files if f]
    bad = 0
    lines = 0
    for rel in files:
        text = (ROOT / rel).read_text(encoding='utf-8')
        try:
            if rel.endswith('.jsonl'):
                for no, line in enumerate(text.splitlines(), 1):
                    if line.strip():
                        json.loads(line)
                        lines += 1
            else:
                json.loads(text)
        except json.JSONDecodeError as exc:
            bad += 1
            where = f':{no}' if rel.endswith('.jsonl') else ''
            print(f'FAIL {rel}{where}: {exc}', file=sys.stderr)
    n_jsonl = sum(f.endswith('.jsonl') for f in files)
    print(f'checked {len(files) - n_jsonl} json + {n_jsonl} jsonl files ({lines} jsonl records); failures: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
