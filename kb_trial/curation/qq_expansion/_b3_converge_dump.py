"""阶段三b3 收敛审读：把每条 claim 及其 raw_messages 上下文(+/-3)导出为可读文本。"""
import json
import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
WO = os.path.join(BASE, 'workorders_b3')
REV = os.path.join(BASE, 'reviews_b3')

PRIV = re.compile(r'\[[^\[\]]*已隐(?:去|藏)[^\[\]]*\]|账号已隐去|已隐去')


def load_wo(wid):
    return json.load(open(os.path.join(WO, wid + '.json'), encoding='utf-8'))


def ctx(messages, seq, span=3):
    idx = {m['seq']: i for i, m in enumerate(messages)}
    if seq not in idx:
        return []
    i = idx[seq]
    return messages[max(0, i - span): i + span + 1]


def main():
    out = []
    files = sorted(glob.glob(os.path.join(REV, 'qq_wo_b3_*.json')))
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for f in files:
        r = json.load(open(f, encoding='utf-8'))
        wid = r['workorder_id']
        if only and wid not in only:
            continue
        wo = load_wo(wid)
        msgs = wo['raw_messages']['messages']
        by_seq = {m['seq']: m for m in msgs}
        win = r['window_id']
        for c in (r.get('claims') or []):
            out.append('=' * 100)
            out.append(f'WORKORDER {wid}  WINDOW {win}  local_id {c.get("local_id")}')
            out.append(f'CLAIM: {c.get("claim")}')
            out.append(f'SUBJECT: {c.get("subject")}')
            out.append(f'CONDITION: {c.get("condition")}')
            out.append(f'SCOPE: {c.get("scope")}  CATEGORY: {c.get("category")}')
            out.append(f'LIMITATIONS: {json.dumps(c.get("limitations"), ensure_ascii=False)}')
            out.append(f'REASON: {c.get("reason")}')
            evs = [e.get('seq') for e in (c.get('evidence') or [])]
            out.append(f'EVIDENCE SEQS: {evs}')
            shown = set()
            for e in (c.get('evidence') or []):
                s = e.get('seq')
                for m in ctx(msgs, s, 3):
                    if m['seq'] in shown:
                        continue
                    shown.add(m['seq'])
                    mark = '>>' if m.get('is_cited_by_card') else '  '
                    hr = '  ***PRIV***' if PRIV.search(m.get('text') or '') else ''
                    out.append(f'  {mark} [{m["seq"]}] {m.get("time")} {m.get("speaker_id")}: {m.get("text")}{hr}')
            out.append('')
    txt = '\n'.join(out)
    p = os.path.join(BASE, '_b3_context_dump.txt')
    open(p, 'w', encoding='utf-8').write(txt)
    print('claims dumped:', txt.count('WORKORDER '))
    print('privacy-marked lines:', txt.count('***PRIV***'))
    print('out:', p)


if __name__ == '__main__':
    main()
