import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'kb_pilot_synth/semantic_repair_round1/gated_default_v2.jsonl'
FEEDBACK = [
    (1, '技能特例-11-1', '无意义', 'archive'),
    (2, '其他-9-11', '修改后可用；镜像力是径向力的ASR误译', 'correct'),
    (3, '其他-8-8', '看不懂', 'needs_clarification'),
    (4, '技能特例-6-4', '无意义；由于被标注为单关，因此并无影响', 'retain_experiment'),
    (5, '索敌-20-14', '优秀', 'accept'),
    (6, '伤害结算-15-1', '无意义；由于被标注为单关，因此并无影响', 'retain_experiment'),
    (7, '伤害结算-13-0', '删改后可用；无敌不是伤害明显无意义', 'trim'),
    (8, '索敌-16-10', '优秀', 'accept'),
    (9, '状态效果-10-9', None, 'unreviewed'),
    (10, '帧时序与计时器-37-5', '优秀', 'accept'),
    (11, '帧时序与计时器-1-0', None, 'unreviewed'),
    (12, '位移-4-5', '修改后可用；维尼斯实际为维云斯，知名明日方舟主播', 'correct'),
]

def write_jl(name, rows):
    (OUT / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def main():
    before_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    original = [json.loads(x) for x in SOURCE.read_text(encoding='utf-8').splitlines()]
    lookup = {d['id']: d for d in original}
    feedback = []
    patches = {}
    archive = []
    views = ['# 用户抽审后的定向修订', '', '仅处理本次明确反馈，保留原样本和原始引文。没有全量重跑，没有覆盖生产库。第9、11条未审；“修改后可用”不记作修改稿已经获用户确认。', '']
    for num, cid, note, action in FEEDBACK:
        did = 'fc1:' + cid
        d = json.loads(json.dumps(lookup[did]))
        feedback.append({'sample_number': num, 'id': did, 'reviewer_type': 'user' if note else None, 'user_feedback': note, 'action': action})
        if action == 'unreviewed':
            continue
        d['user_review'] = {'feedback': note, 'sample_number': num, 'revision_approved': action == 'accept'}
        if action in ('archive', 'needs_clarification'):
            d['layer'] = 'archive'
            d['kind'] = 'reject' if action == 'archive' else 'pending'
            d['default_retrieval'] = False
            archive.append(d)
            patches[did] = None
        else:
            if num == 2:
                d['text'] = d['text'].replace('镜像力', '径向力')
                d['text'] = d['text'].replace('# 小莫与施怀雅的推拉方向模式：径向力与径向力', '# 小莫与施怀雅的径向力：推拉方向由敌我坐标连线决定')
                lines = d['text'].splitlines()
                lines = [x for x in lines if not x.startswith('- 径向力与径向力是否') and not x.startswith('- 小莫被称径向力、施怀雅被称径向力') and not x.startswith('- 证据来自同一录播片段中') and x != '## 待验证']
                d['text'] = '\n'.join(lines).rstrip() + '\n- 讨论对象为小莫与施怀雅的相应推拉效果；按用户纠正，两处术语均为径向力。'
                d['term_corrections'] = [{'from': '镜像力', 'to': '径向力', 'authority': 'user', 'scope': 'this_entry', 'entity_type': 'mechanism'}]
            elif num == 7:
                d['text'] = '\n'.join(x for x in d['text'].splitlines() if not x.startswith('- 无敌不是伤害'))
                d['text'] = d['text'].replace('（闪避/护盾/格挡/减伤/增伤/无敌）', '（闪避/护盾/格挡/减伤/增伤）')
                d['removed_assertions'] = ['无敌不是伤害']
            elif num == 12:
                d['text'] = d['text'].replace('维尼斯', '维云斯')
                d['text'] = d['text'].replace('适用对象: 维云斯', '适用对象: 维云斯（主播）演示的推海默场景；维云斯不是干员名')
                d['term_corrections'] = [{'from': '维尼斯', 'to': '维云斯', 'authority': 'user', 'scope': 'this_entry', 'entity_type': 'streamer'}]
            elif action == 'retain_experiment':
                assert d['kind'] == 'experiment'
                d['user_review']['mechanism_value'] = 'none'
            if action in ('correct', 'trim'):
                d['render_only_revision'] = True
                d['revision_note'] = '正文定向修订；上游缓存、引文和原规则索引未重写，禁止按旧索引重新渲染或宣称用户已审过修改稿。'
            patches[did] = d
        views += [f'## #{num} {did}', '', f'用户意见：{note}', '', f'处置：{action}', '', d['text'], '', '---', '']
    final = [patches.get(d['id'], d) for d in original if patches.get(d['id'], d) is not None]
    assert len(final) == len(original) - 2
    final_map = {d['id']: d for d in final}
    assert '镜像力' not in final_map['fc1:其他-9-11']['text']
    assert '无敌不是伤害' not in final_map['fc1:伤害结算-13-0']['text']
    assert '维尼斯' not in final_map['fc1:位移-4-5']['text']
    for n in (5, 8, 9, 10, 11):
        did = 'fc1:' + next(x[1] for x in FEEDBACK if x[0] == n)
        assert final_map[did]['text'] == lookup[did]['text']
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before_hash
    write_jl('feedback.jsonl', feedback)
    write_jl('revised_default.jsonl', final)
    write_jl('archived_by_feedback.jsonl', archive)
    write_jl('patches.jsonl', [{'id': k, 'replacement': v} for k, v in patches.items()])
    (OUT / 'revisions.md').write_text('\n'.join(views), encoding='utf-8')
    summary = {'source_sha256': before_hash, 'source_count': len(original), 'revised_count': len(final), 'archive_count': len(archive), 'reviewed': 10, 'unreviewed': 2, 'external_api_calls': 0, 'old_rag_overlay_applied': False, 'note': '仅派生候选修订快照，未重新构建检索索引；原库和原证据不变。'}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
