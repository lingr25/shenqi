import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
rows = [json.loads(x) for x in (OUT / 'gated_default_v2.jsonl').read_text(encoding='utf-8').splitlines()]
sample = random.Random(2026092017).sample(rows, 20)
ids = set()
for d in sample:
    ids.update(re.findall(r'BV[A-Za-z0-9]+_p\d+_\d+:p\d+:a\d+:[a-f0-9]+', d['text']))
atoms = {}
for path in (ROOT / 'knowledge_pilot').glob('*.atoms.enriched.jsonl'):
    for line in path.read_text(encoding='utf-8').splitlines():
        a = json.loads(line)
        if a.get('atom_id') in ids:
            atoms[a['atom_id']] = a

def sources(d):
    result = []
    seen = set()
    for aid in re.findall(r'BV[A-Za-z0-9]+_p\d+_\d+:p\d+:a\d+:[a-f0-9]+', d['text']):
        if aid in seen:
            continue
        seen.add(aid)
        a = atoms.get(aid, {})
        result.append({'atom_id': aid, 'proposition': a.get('proposition'), 'evidence': a.get('evidence', [])})
    return result

manifest = {'seed': 2026092017, 'population': len(rows), 'source': str((OUT / 'gated_default_v2.jsonl').relative_to(ROOT)), 'assistant_ids': [d['id'] for d in sample[:8]], 'user_ids': [d['id'] for d in sample[8:]]}
(OUT / 'sample_manifest_personal.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
with (OUT / 'personal8_sources.jsonl').open('w', encoding='utf-8') as f:
    for d in sample[:8]:
        f.write(json.dumps({'id': d['id'], 'text': d['text'], 'sources': sources(d)}, ensure_ascii=False) + '\n')
text = ['# 随机审阅样本：12 条', '', '从最终试验默认层 1339 条抽取，不代表全部 2418 个候选，也不是正式生产库。固定 seed=2026092017，随机抽 20 条，前 8 条由助手核查，后 12 条原样交给你。未按好坏筛选。kind/confidence 是原产物标签，不是这轮审核结论。', '', '正文保留原样，包括 ASR 错字、证据标记及待验证项。以下引文来自上游原子证据字段，可能已有历史清洗；视频才是回查入口。', '']
for i, d in enumerate(sample[8:], 1):
    text += [f'## #{i} {d["id"]}', '', f'模型标签：{d["kind"]} / {d.get("confidence", "未提供")}', '', d['text'], '', '### 回查证据', '']
    evs = []
    for a in sources(d):
        stem = a['atom_id'].split(':')[0]
        m = re.match(r'(BV\w+)_p(\d+)_\d+', stem)
        for ev in a['evidence']:
            if not ev.get('quote'):
                continue
            start = ev.get('start')
            key = (stem, start, ev['quote'])
            if key in evs:
                continue
            evs.append(key)
            if m and isinstance(start, (int, float)):
                sec = int(start)
                url = f'https://www.bilibili.com/video/{m[1]}?p={m[2]}&t={sec}'
                text += [f'- [{stem} · {sec // 3600:02}:{sec // 60 % 60:02}:{sec % 60:02}]({url})', f'  原子证据引文：{ev["quote"]}', '']
            else:
                text += [f'- {a["atom_id"]}，时间：{start}', f'  原子证据引文：{ev["quote"]}', '']
            if len(evs) >= 3:
                break
        if len(evs) >= 3:
            break
    if not evs:
        text += ['未找到可导出的原子引文；请按正文证据 ID 回查。', '']
    text += ['判定：___（可用 / 修改后可用 / 仅实验线索 / 无意义 / 错误）', '', '修改意见：___', '', '---', '']
(OUT / 'review_user_random12.md').write_text('\n'.join(text), encoding='utf-8')
print(json.dumps({'population': len(rows), 'assistant': 8, 'user': 12, 'matched_atoms': len(atoms), 'requested_atoms': len(ids)}, ensure_ascii=False))
