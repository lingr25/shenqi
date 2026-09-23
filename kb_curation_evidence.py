"""Evidence lookup for curation review. Prints the raw quote(s) behind a citation id.

This is a read-only forensic helper: it shows what the speaker actually said, so a
reviewing agent can compare a derived rule against its source, spot ASR artifacts, and
see whether the surrounding transcript window is needed. It never decides acceptance.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
CTX = re.compile(r'ctx=sub:(?P<stem>[\w]+):(?P<sec>\d+)')


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


class Evidence:
    def __init__(self):
        self.rows = {d['id']: d for d in load_jsonl(TRIAL / 'evidence.jsonl')}
        self.transcripts = {}

    def transcript(self, stem):
        if stem not in self.transcripts:
            for name in (f'transcripts_txt/{stem}.txt', f'asr_drafts/{stem}_asr.txt',
                         f'asr_drafts/{stem}_asr_draft.txt'):
                path = ROOT / name
                if path.exists():
                    self.transcripts[stem] = (name, path.read_text(encoding='utf-8').splitlines())
                    break
            else:
                self.transcripts[stem] = (None, [])
        return self.transcripts[stem]

    def window(self, stem, second, before=0, after=0):
        name, lines = self.transcript(stem)
        timed = []
        for line in lines:
            m = re.match(r'^\[(?P<h>\d+):(?P<m>\d+)(?::(?P<s>\d+))?\]', line)
            if not m:
                continue
            if m.group('s') is not None:
                t = int(m.group('h')) * 3600 + int(m.group('m')) * 60 + int(m.group('s'))
            else:
                t = int(m.group('h')) * 60 + int(m.group('m'))
            timed.append((t, line))
        idx = None
        for i, (t, _) in enumerate(timed):
            if t <= second:
                idx = i
        if idx is None:
            return {'file': name, 'lines': []}
        lo = max(0, idx - before)
        hi = min(len(timed), idx + 1 + after)
        return {'file': name, 'lines': [line for _, line in timed[lo:hi]]}

    def lookup(self, ref, before=1, after=1):
        row = self.rows.get(ref)
        if row is None:
            return {'id': ref, 'found': False}
        out = {'id': ref, 'found': True, 'status': row['status'],
               'source_layers': row['source_layers']}
        if row['status'] == 'resolved_atom':
            out['transcript_file'] = row.get('transcript_file')
            out['source'] = row.get('source')
            clips = (row.get('evidence') or {}).get('clips') or []
            out['quotes'] = [{'quote': c.get('quote'), 't_start': c.get('t_start'), 't_end': c.get('t_end')}
                             for c in clips]
            stem = (row.get('source') or {}).get('bvid_stem')
            if stem and clips:
                out['window'] = self.window(stem, int(clips[0].get('t_start') or 0), before, after)
        elif row['status'] == 'resolved_timestamp_window':
            out['file'] = row.get('file')
            out['requested_second'] = row.get('requested_second')
            out['quote_line'] = row.get('quote_line')
        return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('refs', nargs='+', help='citation ids, or @path to a text file of ids')
    parser.add_argument('--before', type=int, default=1)
    parser.add_argument('--after', type=int, default=1)
    args = parser.parse_args(argv)
    ev = Evidence()
    refs = []
    for ref in args.refs:
        if ref.startswith('@'):
            refs.extend(x.strip() for x in Path(ref[1:]).read_text(encoding='utf-8').splitlines() if x.strip())
        else:
            refs.append(ref)
    for ref in refs:
        print(json.dumps(ev.lookup(ref, args.before, args.after), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
