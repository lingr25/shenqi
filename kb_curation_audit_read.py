"""Fixed-seed audit: the agent's per-item read of the 60 sampled rules.

Consumes kb_trial/curation/audit_sample.json, which is produced by
kb_curation_audit_sample.py with a pinned seed, and records what each sampled rule's own
source actually says. The point is that the sample can be re-checked by hand without
trusting the gate code: every verdict below names the quote it was read against.

Re-run order: kb_curation_audit_sample.py, then this.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial/curation'

# entry_id -> (verdict, note). 'supported' = the cited span carries the claim.
ACCEPT = {
    'fc1:技能特例-14-2#r3': ('supported', '引文「它的好处是可以如同代理一样」；同段语境指赛博塑料，支持主张'),
    'fc1:状态效果-15-14#r0': ('supported', '引文「他这个东西既不是眩晕」支持“不是眩晕”的否定式界定'),
    'fc1:索敌-20-12#r3': ('supported', '引文「出伤时间受到前后波动的影响」；后半“仍可辅助判断”属同段结论'),
    'fc1:寻路-20-1#r8': ('supported', '引文「它只是非常的长 没有本质区别」支持超大地图与常规地图无本质区别'),
    'fc1:位移-22-4#r3': ('supported', '引文逐字一致'),
    'fc1:寻路-8-5#r0': ('supported', '引文逐字一致（该条官方与 ASR 两侧同文）'),
    'fc1:寻路-38-3#r6': ('supported', '引文给出「必定垂直于寻路方向」与「形成的是一个直角三角形」，支持主张'),
    'fc1:寻路-3-3#r3': ('supported', '引文列出坑/障碍物/不可通行地块三种距离判定，支持主张；B 张力向量名属同段术语'),
    'fc1:寻路-15-4#r3': ('supported', '引文「由避障力驱动它移动」'),
    'fc1:寻路-6-4#r1': ('supported', '引文「采完这个之后还是往这里走」；回读原片段指原路径点，支持主张'),
    'fc1:寻路-3-3#r5': ('supported', '引文「这些东西逐步的往上加上去 形成了完整的寻路过过程」'),
    'fc1:伤害结算-12-12#r2': ('supported', '引文含完整转折「其实也没那么一定 只是他做了取整这么一步处理 所以必须是整数」'),
    'fc1:位移-22-4#r2': ('supported', '引文逐字一致'),
    'fc1:索敌-20-6#r1': ('supported', '引文「围墙里面也是不可阻挡」'),
    'fc1:寻路-21-3#r3': ('supported', '引文举出阻挡偏移/酒神拉推/传送并列，支持“都一样”的归类'),
    'fc1:帧时序与计时器-30-3#r2': ('supported', '引文「允许锁敌不等于会直接开始锁敌」（“锁敌”为“索敌”的同义异写）'),
    'fc1:帧时序与计时器-13-3#r6': ('supported', '引文逐字一致'),
    'fc1:寻路-37-10#r3': ('supported', '引文「他不是说要回到原本位置的事」支持“不是要回到原本位置”'),
    'fc1:位移-22-4#r0': ('supported', '引文「失衡速度和寻路速度 各自有自己定义的速度」'),
    'fc1:位移-10-1#r0': ('supported', '引文逐字一致'),
    'fc1:其他-3-19#r0': ('supported', '引文逐字一致（ASR 与官方两侧同文）；“隔判”为“格判”的 ASR 写法，已在术语层记录'),
    'fc1:寻路-16-3#r2': ('supported', '引文「前提是不是零 如果是零的话还是零」支持零向量归一化仍为零'),
    'fc1:寻路-40-5#r1': ('supported', '引文逐字一致'),
    'fc1:其他-19-13#r0': ('supported', '引文「这个双晶树卖一个吧 卖一个不全卖」对应当关操作，属具体做法而非通则；'
                               '本条为单关技巧，scope 判 universal 偏宽，建议后续降级为实例'),
    'fc1:寻路-35-10#r2': ('supported', '引文逐字一致'),
    'fc1:帧时序与计时器-27-7#r2': ('supported', '引文「在非寻路针的话 它不只是不会触发」；“针”为“帧”的 ASR 写法，支持主张'),
    'fc1:帧时序与计时器-13-9#r3': ('supported', '引文逐字一致'),
    'fc1:帧时序与计时器-63-7#r4': ('supported', '引文含「区别只有这点儿 不在于其他东西」「单道只是实现这个东西的一个和它机制有关联的东西」'
                               '（“单道”为“弹道”的 ASR 写法），支持主张'),
    'fc1:寻路-13-8#r1': ('supported', '引文「他的时间是多少 包括寻路的时间」支持寻路时间需计入'),
    'fc1:寻路-27-4#r12': ('supported', '引文逐字一致'),
}

REJECT = {
    'vod_entry:帧时序与计时器-1-0#r0': ('correct', '“第十技力到第十1技力”表述残缺，scope 非 universal 且无界定'),
    'vod_cluster:索敌-18-2#r0': ('correct', '簇标题「无动画前摇干员的前摇机制」非规则句'),
    'window:w000598#r0': ('correct', 'QQ 窗口标题，须代理读 span 判定；本轮未核，理由准确'),
    'vod_atom:BV1j4KC6KEse_p1_40109737103:p94:a2:20e03ad4#r0': ('correct', '该原子无 citation_refs/inline/qq，证据缺失属实'),
    'window:w001024#r0': ('correct', 'QQ 窗口标题，待代理核'),
    'vod_atom:BV1aTeV6yENP_p3_41898217443:p45:a1:1fdb819c#r0': ('correct', '无 citation_refs/inline/qq，证据缺失属实'),
    'fc1:索敌-9-5#r0': ('correct', '“现在看起来可以正常”为观察性且依赖上文'),
    'vod_atom:BV1KBgX6WEVm_p1_40322532606:p6:a1:f8507b8f#r0': ('correct', '无 citation_refs/inline/qq；且含具体数值，须先有可核证据'),
    'fc1:帧时序与计时器-38-15#r0': ('correct', '“某些情况下”依赖上文所指情形'),
    'vod_atom:BV1kRbQ6tEG9_p1_40968521557:p3:a2:237d6585#r0': ('correct', '“寻路是以格子为单位的”虽成立但为极短定义句且该原子无引文，判 too_short 可接受'),
    'vod_atom:BV14gby6LEni_p1_40940472044:p17:a11:82d6a4ff#r0': ('correct', '无 citation_refs/inline/qq；含多组数值，须先有可核证据'),
    'vod_cluster:帧时序与计时器-17-13#r0': ('correct', '簇标题且带“[合并2簇]”标记，非机制规则句'),
    'fc1:帧时序与计时器-35-2#r3': ('correct', '含 D10S/D11S 差一帧数值，须代理核实'),
    'fc1:位移-0-8#r0': ('correct', '仅 ASR 有源，须核听'),
    'fc1:寻路-31-4#r8': ('correct', '“消失的实现是原地隐身”依赖上文“消失”指代'),
    'glossary:visitNodeCenter#r0': ('correct', '词条名而非规则句，属术语表条目'),
    'vod_atom:BV14y8269EbS_p3_41169782383:p39:a9:43fcfb37#r0': ('correct', '无 citation_refs/inline/qq，证据缺失属实'),
    'vod_atom:BV1qReG6XE6W_p1_41897493495:p38:a0:c553ba40#r0': ('correct', '无 citation_refs/inline/qq，证据缺失属实'),
    'vod_entry:其他-6-5#r1': ('correct', '“1千攻速实际上只能到6百”含数值且 scope 非 universal 无界定'),
    'vod_atom:BV1jd3m68E6f_p1_40508197659:p24:a1:81747513#r0': ('correct', '无 citation_refs/inline/qq；“实质完全不同”为比较性论断，须有源'),
    'window:w000420#r0': ('correct', 'QQ 窗口标题，待代理核'),
    'vod_cluster:寻路-2-1#r0': ('correct', '簇标题「地图偏移量决定出生与坐标偏移」非规则句'),
    'fc1:其他-0-6#r4': ('correct', '仅 ASR 有源；优先级枚举须核听'),
    'vod_entry:其他-2-6#r0': ('correct', 'scope 非 universal 且无界定'),
    'fc1:状态效果-8-0#r8': ('correct', '含 0.1 以下速度数值，须代理核实'),
    'fc1:帧时序与计时器-64-10#r10': ('correct', '含 13 帧数值，须代理核实'),
    'fc1:帧时序与计时器-10-1#r6': ('correct', '非该卡 affirmative 规则段条目，且依赖“两个”所指上文'),
    'fc1:帧时序与计时器-19-6#r2': ('correct', '“又移动了一帧”依赖上文首次移动语境'),
    'fc1:帧时序与计时器-36-6#r1': ('correct', '非 affirmative 规则索引内条目，依赖“余字/所下之字”上文定义'),
    'fc1:技能特例-5-20#r3': ('correct', '整句依赖“一帧可达”前提与上文步骤编号，独立不可读'),
}


def main():
    sample = json.loads((OUT / 'audit_sample.json').read_text(encoding='utf-8'))
    rows, unread = [], []
    for r in sample['accept_sample']:
        v, note = ACCEPT.get(r['entry_id'], (None, None))
        if v is None:
            unread.append(r['entry_id'])
        rows.append({'entry_id': r['entry_id'], 'review_status': r['review_status'],
                     'source_layer': r['source_layer'], 'claim': r['claim'],
                     'verdict': v, 'note': note})
    for r in sample['reject_sample']:
        k = f"{r['doc_id']}#r{r['rule_idx']}"
        v, note = REJECT.get(k, (None, None))
        if v is None:
            unread.append(k)
        rows.append({'entry_id': k, 'reject_reason': r['reject_reason'], 'claim': r['claim'],
                     'verdict': v, 'note': note})
    acc = [r for r in rows if 'reject_reason' not in r]
    rej = [r for r in rows if 'reject_reason' in r]
    report = {
        'seed': sample['seed'],
        'method': ('固定 seed 抽样后由代理逐条读取引文与原文邻窗核对。'
                   'supported=主张有源支持；not_supported=主张超出引文支持范围；'
                   'correct=拒收理由成立。未列出的条目绝不视为已核。'),
        'reviewer': 'agent (Kimi Code subagent, deepseek)',
        'accepts': {'n': len(acc),
                    'supported': sum(1 for r in acc if r['verdict'] == 'supported'),
                    'not_supported': [r['entry_id'] for r in acc if r['verdict'] == 'not_supported']},
        'rejects': {'n': len(rej),
                    'correct': sum(1 for r in rej if r['verdict'] == 'correct'),
                    'incorrect': [r['entry_id'] for r in rej if r['verdict'] != 'correct']},
        'unread': unread,
        'rows': rows,
    }
    (OUT / 'audit_read.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding='utf-8')
    print(json.dumps({'accepts': report['accepts'], 'rejects': report['rejects'],
                      'unread': unread}, ensure_ascii=False))
    return 1 if unread else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
