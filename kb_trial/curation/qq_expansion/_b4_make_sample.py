# -*- coding: utf-8 -*-
"""生成 user_sample_round4.md：从 b4 已入库的 508 条中分层抽 20 条供用户抽审。

选取口径（确定性，不随机）：
  * 必含：父裁决的 8 条改写条中的 6 条、2 条带 audit_note 的留注条、
    1 条父要求补「未实战验证」limitations 的条目、1 条触发隐私闸门豁免的条目；
  * 其余按类别覆盖补齐：每个未覆盖类别取工单号最小的一条，直到 20 条；
  * 只取已入库（curated_high_quality.json 内 card_section=QQ扩展(阶段四b4批)）的条目。
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'
WORKORDERS = HERE / 'workorders_b4'
OUT = HERE / 'user_sample_round4.md'

B4 = 'QQ扩展(阶段四b4批)'
MUST = [
    ('qq_wo_b4_434', 'c01'), ('qq_wo_b4_325', 'c01'), ('qq_wo_b4_156', 'c01'),
    ('qq_wo_b4_347', 'c01'), ('qq_wo_b4_154', 'c01'), ('qq_wo_b4_358', 'c01'),
    ('qq_wo_b4_383', 'c02'), ('qq_wo_b4_307', 'c02'),
    ('qq_wo_b4_425', 'c01'), ('qq_wo_b4_296', 'c01'), ('qq_wo_b4_390', 'c02'),
    ('qq_wo_b4_315', 'c01'),
]  # 父裁决改写条 6 + 留注条 2 + 机制密度最高的 4 条（含后段工单）
TARGET = 20


def esc(t):
    return t.replace('\r\n', '\n')


def quote_bullets(evs):
    out = []
    for e in evs:
        text = esc(e['text'])
        if '\n' in text:
            parts = [p for p in text.split('\n')]
            out.append('  - ' + ' / '.join('`%s`' % p for p in parts) + '（同一条的换行原文）')
        else:
            out.append('  - `%s`' % text)
    return out


def main():
    payload = json.loads(CURATED.read_text(encoding='utf-8'))
    entries = [e for e in payload['entries'] if e['origin'].get('card_section') == B4]
    by_key = {(e['origin']['workorder_id'], e['origin']['local_id']): e for e in entries}

    picked, seen = [], set()

    def take(key):
        if key in seen or key not in by_key:
            return
        seen.add(key)
        picked.append(by_key[key])

    for k in MUST:
        take(k)
    # 1 条长表格外的必含：验证闸门豁免条（w001525:c01）
    for e in entries:
        if e['origin']['trial_doc_id'] == 'w001525':
            take((e['origin']['workorder_id'], e['origin']['local_id']))
            break
    # 类别覆盖：把候选池按工单号四等分，轮转各四分位取「未覆盖类别」的第一条，
    # 使补齐项横跨 b4_001–b4_441 全程而不是挤在区间前段。
    covered = {e['category'] for e in picked}
    pool = sorted(entries, key=lambda e: e['origin']['workorder_id'])
    n = len(pool)
    buckets = [pool[i * n // 4:(i + 1) * n // 4] for i in range(4)]
    progress = True
    while len(picked) < TARGET and progress:
        progress = False
        for q in range(4):
            if len(picked) >= TARGET:
                break
            for e in buckets[q]:
                k = (e['origin']['workorder_id'], e['origin']['local_id'])
                if k in seen or e['category'] in covered:
                    continue
                take(k)
                covered.add(e['category'])
                progress = True
                break
    # 仍不足则按工单号补
    for e in pool:
        if len(picked) >= TARGET:
            break
        take((e['origin']['workorder_id'], e['origin']['local_id']))

    picked = picked[:TARGET]
    lines = []
    A = lines.append
    A('# 阶段四 b4 批 508 条 — 人工抽审样本（%d 条）' % len(picked))
    A('')
    A('**用途**：供用户对阶段四 b4 批（441 窗 / 572 条候选 claim，父裁决后 keep 508）并入')
    A('`kb_trial/curated_high_quality.json` 的 508 条新条目做人工抽审。')
    A('**材料**：已脱敏的 QQ 群聊窗口片段（仅保留消息文本，已剔除群号、QQ 号与昵称；少量出现的')
    A('`[账号已隐去]` 为隐私脚本对连续数字的占位替换，非真实账号；`[表情]` 为表情占位）。')
    A('**置信上限**：`text-source-supported` —— 判定基于转写/聊天文本逐条比对，**未核听原片音画、未做游戏内实测**，')
    A('不等同于权威结论。条目标记 `not_authoritative`。')
    A('**引文口径**：引文一律保留原始逐字文本（含原文错字、表情占位、不完整句与换行），')
    A('仅在 `claim`/`condition` 中做同源自证范围内的派生订正。')
    A('')
    wo_min = min(e['origin']['workorder_id'] for e in picked)[-3:]
    wo_max = max(e['origin']['workorder_id'] for e in picked)[-3:]
    A('**抽取口径**：从 508 条中分层抽取 %d 条，覆盖 %d 个类别桶与 `general_mechanism` / `entity_mechanism`'
      % (len(picked), len({e['category'] for e in picked})))
    A('两种 scope，工单横跨 b4_001–b4_441 审核区间（本样本实际落在 b4_%s–b4_%s）。样本必含父裁决的改写条（6 条）、'
      % (wo_min, wo_max))
    A('带留注条（`383/c02` 的 500/1000 数差、`307/c02` 的父要求「未实战验证」limitations）')
    A('与触发隐私闸门豁免的系数条（`w001525:c01`）。')
    A('')
    A('---')
    A('')
    for i, e in enumerate(picked, 1):
        wo = e['origin']['workorder_id']
        wo_path = WORKORDERS / ('%s.json' % wo)
        wo_data = json.loads(wo_path.read_text(encoding='utf-8'))
        n_msg = wo_data['raw_messages'].get('message_count')
        A('## %d. `%s` — %s' % (i, e['id'], e['subject']))
        A('')
        A('- **窗口**：`%s`（工单 `%s`），窗口日期 `%s`，窗口原始消息 %s 条'
          % (e['origin']['trial_doc_id'], wo, wo_data['window']['as_of'], n_msg))
        A('- **分类**：%s ｜ **scope**：`%s`' % (e['category'], e['scope']))
        A('- **claim**：%s' % esc(e['claim']))
        if e.get('condition') and e['condition'] != '未标注':
            A('- **condition**：%s' % esc(e['condition']))
        A('- **原文引文**：')
        lines.extend(quote_bullets(e['citations'][0]['quotes']))
        A('')
        notes = []
        cd = e.get('claim_derivation') or {}
        if cd.get('corrected_by_audit'):
            notes.append('> **父裁决改写条**：原回执 claim 写作「%s」；父已审阅并批准按改写后文本入库，'
                         '原值保留在 `claim_derivation.from` / `claim_original`。'
                         % (cd.get('from') or '').replace('\n', ' '))
        if cd.get('audit_note'):
            notes.append('> **留注（audit_note）**：%s' % cd['audit_note'].replace('\n', ' '))
        if (e.get('evidence_review') or {}).get('review_limitations'):
            notes.append('> **limitations**：%s' % ' '.join(e['evidence_review']['review_limitations']))
        for n in notes:
            A(n)
            A('')
    A('---')
    A('')
    A('## 抽审指引')
    A('')
    A('- 本样本 %d 条均取自阶段四 b4 批已入库的 508 条（`id` 前缀 `qq_expansion:`）；' % len(picked))
    A('  剩余 %d 条可按 `e[\'origin\'][\'card_section\'] == \'QQ扩展(阶段四b4批)\'` 在'
      % (len(entries) - len(picked)))
    A('  `kb_trial/curated_high_quality.json` 中全量查看；裁定全集见')
    A('  `audit_decisions_b4.json`（572 条：keep 508 / reject 34 / pending 30，含父裁决段）。')
    A('- **若判定为「不可用」**：在 `kb_trial/curation/qq_expansion/_b4_dec.jsonl` 中把对应')
    A('  `(workorder, local_id)` 那行的 `verdict` 改为 `reject`（并给 `reason_code` 与 `criterion_note`），')
    A('  重跑 `_b4_converge_build.py` → `kb_curation_build.py`；若只是 claim/condition 措辞问题，')
    A('  在该行加 `override.claim` 改写（会记入 `claim_original`）。')
    A('- 台账改动可用 `python _b4_verify_outputs.py` 独立复核（要求 errors=0），')
    A('  再跑 `python kb_curation_validate.py`（要求 passed + idempotent）。')
    A('- 阶段二 30 条与阶段三 b3 317 条的样本另见 `user_sample_round2.md` / `user_sample_round3.md`。')
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('wrote %s (%d 条)' % (OUT.name, len(picked)))
    for e in picked:
        print('  - %s %s %s' % (e['origin']['workorder_id'], e['origin']['local_id'], e['category']))


if __name__ == '__main__':
    main()
