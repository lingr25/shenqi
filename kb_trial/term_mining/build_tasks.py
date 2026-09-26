# -*- coding: utf-8 -*-
"""Generate one term-mining task file per transcript. Run from repo root:
    python kb_trial/term_mining/build_tasks.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    tpl = (HERE / 'PROMPT.md').read_text(encoding='utf-8')
    transcripts = sorted((ROOT / 'transcripts_txt').glob('*.txt'))
    for old in HERE.glob('task_*.md'):
        old.unlink()
    for i, t in enumerate(transcripts, 1):
        (HERE / f'task_{i:02d}.md').write_text(
            tpl.replace('{{FILE}}', t.stem).replace('{{IDX}}', f'{i:02d}'),
            encoding='utf-8')
    print(f'wrote {len(transcripts)} task files')


if __name__ == '__main__':
    main()
