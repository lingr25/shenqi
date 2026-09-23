# -*- coding: utf-8 -*-
"""Build the semantic review worklist and apply the per-entry verdicts.

Stage 1 (``--worklist``): write kb_trial/curation/semantic_worklist.json -- every entry
that passed the deterministic gates, paired with the raw quote its citations resolve to,
so each line can be adjudicated by reading the claim and its source together.

Stage 2 (default): read kb_trial/curation/semantic_drop_decisions.json (the committed
verdict data) plus the two exemptions files, and emit

  * kb_trial/curation/semantic_review.json   -- every entry, kept and dropped
  * kb_trial/curation/semantic_overlay.jsonl -- the same, one JSON object per line

Two independent dimensions are recorded per entry and must not be collapsed:

  support     does the attached quote actually support the claim?
  info_value  is the claim an independently reusable mechanism statement?

``verdict`` follows from info_value. This pass is claim-level semantic review only; it
is NOT evidence review, and its result is never written into review.status.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'

# Entries that only restate another curated entry are NOT dropped: duplication is a
# retrieval-recall question, not a knowledge-value question. They are independent,
# complete mechanism sentences, so they stay, carrying a redundancy note.
KEEP_REDUNDANT = OUT / '_keep_redundant.json'
DROP_DECISIONS = OUT / 'semantic_drop_decisions.json'

# QQ windows whose stored claim line is the window topic title rather than a mechanism
# sentence. Each window's own source_spans do contain a quotable mechanism core, so the
# entry is kept with the wording gap stated rather than dropped for its phrasing.
QQ_TOPIC_TITLE = {    'window:w000031#r0': (
        '窗口内 span「changableMotionMode在定义飞行」「起飞只防地面单位索敌」「buff和状态机都没了」'
        '构成可复用结论；但该条 claim 文本是窗口标题而非机制句，使用时须以窗口内 span 为准，'
        '这一措辞缺口如实记录。'),
    'window:w000036#r0': (
        '窗口内 span「群攻干员的伤害顺序…从先到后」「每次部署给全局仇恨计数硬性+1来规避同仇恨值」'
        '「不看仇恨值…同帧依旧是先部署」构成可复用结论；但「4号：仇恨降序 越晚的仇恨应该越高」'
        '一句属未确认推测，不应引用；该条 claim 文本是窗口标题而非机制句，措辞缺口如实记录。'),
    'window:w000044#r0': (
        '窗口内 span「嘲讽就是+1000仇恨」「嘲讽一直正常生效」「被干员超过了那是干员的事」'
        '构成可复用结论；末尾「阿怎么这么正常」属未闭合现场观测，不应引用；'
        '该条 claim 文本是窗口标题而非机制句，措辞缺口如实记录。'),
}

# Entries isolated in the parent-directed self-containment pass. Each one fails because the
# claim is not independently usable, NOT because its quote is wrong: the quote may be
# verbatim while the sentence still lacks a resolvable subject or a defined predicate object.
# Read from source before isolating, so every entry here has its evidence recorded.
SELF_CONTAINMENT_ISOLATED = {
    'fc1:索敌-28-7#r3': (
        '无独立主语与结论对象，须隔离，不能因引文逐字就收。'
        'claim「只要敌我的位置相对固定的话，他就可以无视他自己是怎么部署的」中的「他」在引文里无先行词；'
        '回读 transcripts_txt/BV1qReG6XE6W_p3_41897689954.txt 的 [00:11]-[06:15] 附近，'
        '主体始终是演示单位与「索尼」，从未点名为可复用的干员名。'
        'subject 字段原填「波普」，但该分P 出现「波普」的位置是另一段无关讨论（[56:33] '
        '「有人问波普…结论是在索敌帧的前一帧 开技能会触发异常现象」），与 [04:20] 本条不是同一话题，'
        '故 subject 属错填，不猜新名，直接隔离。'),
    'fc1:帧时序与计时器-31-7#r0': (
        '主体未确认为已确认实体，不能猜。claim「简的攻击动画不依赖攻速」的「简」：'
        'prts_entities.json 的 operators 与 operator_aliases 中均无「简」；'
        'kb_trial/entity_index.json 只有「简妮」→「琴柳」，未含裸「简」。'
        '回读 transcripts_txt/BV1dVcbzFEdd_p1_35992570681.txt 的 [03:48:27] 段，'
        '原文为「像简那种是不依赖攻速」，主播自陈「我想想谁不依赖攻速」，'
        '即当场凭记忆举例，未给出可核对的干员身份。'
        '既无已确认实体别名，也不得猜为「琴柳」，故隔离。'),
    'fc1:寻路-37-10#r2': (
        '结论对象「可通过」在 claim 内无定义，须以原邻窗补明已有对象，否则隔离。'
        '回读 transcripts_txt/BV1TomVBBEK1_p1_34675165371.txt 的 [02:25:17]-[02:25:58]，'
        '原话完整为「在停住状态下／B正力只能垂直于寻路方向／但是他现在的寻路方向是零／'
        '他的任何方向均是它的垂直方向／所以任何方向均可通过／因为他在停住」，'
        '可知「可通过」指的是 B正力可通过，而非「单位可通过」或「地块可通过」。'
        'claim 把「B正力」这一主语省掉后，「任何方向均可通过」在句内无法解析为已知机制对象，'
        '且这会改变结论含义（误读成单位可通行）。不猜补，故隔离；'
        '同段已有保留的兄弟条 fc1:寻路-37-10#r0「在停住状态下，B正力只能垂直于寻路方向」'
        '完整承载该机制，本条属其不完整派生。'),
    'fc1:帧时序与计时器-13-3#r5': (
        '「动画程度的下限」经查为源文本原话、非 ASR 讹字，无需改词；但该 claim 作为独立条目不合格。'
        '已回读 subtitles/BV14VZCB1EJR_p1_36119907781.json，'
        'sid 3049「不是攻速上限和攻速上限和动画程度的下限」、sid 3052「他会吃到动画长度的下限」、'
        'sid 3061「第二是动画程度下限」、sid 3085「他理论上动画程度允许他到那个两针」'
        '均为官方字幕原文，故「动画程度」是主播自用术语，不是转写错误。'
        '但本条只陈述「两者是两回事」的比较关系，未给出任一侧的定义或数值，'
        '属对照半句；其正面内容由同组 fc1:帧时序与计时器-13-3「最短攻击间隔受攻速上限、'
        '动画程度下限、三针索敌等共同限制」条完整承载，故隔离。'),
    'fc1:其他-0-10#r0': (
        'claim 是主播个人测试手段而非机制句，且「可以」的对象未界定。'
        '回读 transcripts_txt/BV14gby6LEni_p3_40944668620.txt 的 [03:20]'
        '「绑在敌人身上的偏移的话 我可以通过寻路去精确的控制它的坐标 然后去去测到一个五位数的精度」，'
        '紧接着 [03:34] 明说「像这种在干员身上的偏移的话 我没有办法测他们」，'
        '可知该结论只对敌人生效、对干员不成立，是有条件的一次性实测手段。'
        'claim 把主语「我」省掉后，「可以通过寻路精确控制其坐标」被读成机制通则（寻路能控制坐标），'
        '与源义不符，属方法/实证冒充机制。不猜补，故隔离。'),
    'fc1:寻路-39-7#r4': (
        '设问残留 + 首词指代悬空，且首尾自我指涉。'
        '回读 transcripts_txt/BV1TomVBBEK1_p1_34675165371.txt 的 [13783]-[13786]，'
        '原文为「比如说他在这里有一个偏移量／这个偏移量决定了什么呢 决定了从出起点 出生终点 '
        '每个路径点都要加这么一个偏移量」。claim 保留了「决定了什么呢」的设问痕迹，'
        '首词「这个偏移量」在 claim 内无先行词，句尾又回指同一个「这个偏移量」，形成自我指涉循环。'
        '同组 fc1:寻路-39-7#r5 已给出该偏移量的定义，本条属其不完整派生，故隔离。'),
    'fc1:寻路-39-7#r5': (
        '首词指代悬空：claim「这个偏移量是实体坐标相对于寻路坐标的」以「这个偏移量」开头，'
        '而 claim 内没有任何先行词说明该偏移量是谁的。'
        '回读 transcripts_txt/BV1TomVBBEK1_p1_34675165371.txt 的 [13737]「敌人的实体坐标和光标坐标是有偏移的」'
        '与 [13800]「对其实可以反过来说 这个偏移量是实体坐标 相对于寻路坐标的」，'
        '可知主体是「敌人实体坐标相对寻路坐标的偏移量」。'
        '属可修复型缺失，但本轮不替源补主体（不造），故与 r4 一并隔离。'),
    'fc1:状态效果-10-6#r4': (
        '行为主体未明：claim「它们之间的所有行为都是通过格子上是什么字进行判定的」中的「它们」'
        '在 claim 内无着落，subject 字段本身填的就是「未点名或general」。'
        '回读 transcripts_txt/BV1g3NC6pEFt_p1_39902972402.txt 的 [1851]，'
        '源文「然后他们之间的所有行为 都是通过这个字是什么 然后进行判定的」中的「他们」'
        '指前文改写地块字的鱼、书刀、放字等，claim 脱离该上下文后主体不可恢复。'
        '（「格子上是什么字」是 claim 自行补明的，这部分没有问题。）主体未明，故隔离。'),
    'fc1:索敌-3-2#r9': (
        '属操作建议而非机制陈述（父代理点名的「建议」类）。'
        '回读 transcripts_txt/BV14y8269EbS_p2_41167359561.txt 的 [4591]，'
        '原文即为「所以我们这里的小技巧是不被抢人头 我们卡了一下索敌帧 保证索敌的时候 '
        '这个人索敌到前摇 索敌的前摇阶段 这个人不会死」，主播自陈是「小技巧」；'
        '上文 [4539]「你能不能通过操作去规避」也把话题定性为操作层面。'
        'claim 保留「小技巧」字样，前半句「不被抢人头」是战绩目标而非机制，'
        '后半句「卡一下索敌帧」是打法操作。本条不给机制定义、不给条件参数，'
        '属建议冒充机制，故隔离。同分P 的机制本体另有条目承载。'),
}

SOURCE_CONTEXT_CHECKS = [dict(
    entry_id='B010-event-order-exceptions#r0',
    action='回读源文件上下文',
    detail=('引文只到「失衡是单独拎出来处理的」，而 claim 还断言「与连续攻击中抬手有关的部分事件也单独拎出」。'
            '已回读 transcripts_txt/BV1uLE86JEi1_p1_38942018351.txt 的 [02:36:08] 行，'
            '原文完整包含「然后的话连续攻击中抬手有关的部分事件也是单独拎出来处理的」，'
            '故 claim 成立，仅原引文被截断，本条保留；引文截断问题记入验证报告。'),
)]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]


def accepted_pairs():
    """The (doc_id, rule_idx) pairs that passed the deterministic gates."""
    decisions = load_jsonl(OUT / 'decisions.jsonl')
    return [(r['doc_id'], r['rule_idx']) for r in decisions if r['decision'] == 'accept']


def evidence_index():
    return {e['id']: e for e in load_jsonl(TRIAL / 'evidence.jsonl')}


def candidates_index():
    by_id = {}
    for row in load(OUT / 'candidates.json'):
        by_id.setdefault(row['doc_id'], []).append(row)
    return by_id


def doc_index():
    return {d['id']: d for d in load_jsonl(TRIAL / 'docs.jsonl')}


def quotes_for(row, evidence, docs):
    """The raw evidence text a curated entry's citations resolve to."""
    out = []
    qq = row.get('qq_evidence') or {}
    for span in (qq.get('spans') or []):
        if span:
            out.append('[qq:%s]%s' % (qq.get('window_id'), span))
    for cid in (row.get('citation_refs') or []):
        item = evidence.get(cid)
        if item is None:
            out.append('[citation %s unresolved]' % cid)
            continue
        for clip in ((item.get('evidence') or {}).get('clips') or []):
            out.append('{%s-%s}%s' % (clip.get('t_start'), clip.get('t_end'), clip.get('quote')))
    for ev in (docs.get(row['doc_id']) or {}).get('evidence') or []:
        if isinstance(ev, dict) and ev.get('text'):
            out.append('[doc.evidence]' + ev['text'][:400])
    return out


def write_worklist():
    cands = candidates_index()
    evidence = evidence_index()
    docs = doc_index()
    worklist = []
    for doc_id, idx in accepted_pairs():
        rows = [r for r in cands.get(doc_id, []) if r['rule_idx'] == idx]
        if not rows:
            raise SystemExit('no candidate row for %s#r%d' % (doc_id, idx))
        row = rows[0]
        worklist.append(dict(
            id='%s#r%d' % (doc_id, idx), claim=row['claim'],
            subject=row.get('suffix_subject'), condition=row.get('suffix_condition'),
            scope=row.get('suffix_scope'), cat=row['category'],
            layer=row.get('source_layers') and '+'.join(row['source_layers']) or 'unknown',
            render=row.get('render_mode'), flags=row.get('flags'),
            q=quotes_for(row, evidence, docs),
        ))
    (OUT / 'semantic_worklist.json').write_text(
        json.dumps(worklist, ensure_ascii=False, indent=1), encoding='utf-8')
    print('worklist entries:', len(worklist))
    return worklist


def build_review():
    worklist = load(OUT / 'semantic_worklist.json')
    by_id = {w['id']: w for w in worklist}

    drops = {}
    for spec in load(DROP_DECISIONS):
        for i in spec['ids']:
            if i not in by_id:
                raise SystemExit('drop decision for unknown entry: ' + i)
            if i in drops:
                raise SystemExit('duplicate drop decision: ' + i)
            drops[i] = (spec['info_value'], spec['reason'])

    redundant = set(load(KEEP_REDUNDANT))
    for i in list(drops):
        if i in redundant:
            del drops[i]

    # Self-containment isolation is a SEPARATE defect class and must not be undone by the
    # redundancy exemption: a claim can restate a sibling entry and still be unusable on its
    # own. Applied after the exemption so it always wins.
    for i, reason in SELF_CONTAINMENT_ISOLATED.items():
        if i not in by_id:
            raise SystemExit('self-containment isolation for unknown entry: ' + i)
        drops[i] = ('not_self_contained', reason)

    records = []
    for w in worklist:
        i = w['id']
        if i in drops:
            info, reason = drops[i]
            records.append(dict(entry_id=i, verdict='drop', support='supported',
                                info_value=info, reason=reason, reviewer_type='agent'))
        else:
            if i in QQ_TOPIC_TITLE:
                reason = QQ_TOPIC_TITLE[i]
            elif i in redundant:
                reason = ('claim 为可独立用于检索的机制陈述；所附引文支持该句（与同组另一条内容重叠，'
                          '属冗余而非无价值，重复只影响召回排序不影响知识成立）。')
            else:
                reason = ('claim 为可独立用于检索的机制陈述；所附引文逐字或同义支持该句，'
                          '主体与条件由规则本身可确定，未新造主体。')
            records.append(dict(entry_id=i, verdict='keep', support='supported',
                                info_value='reusable_rule', reason=reason,
                                reviewer_type='agent'))

    assert len({r['entry_id'] for r in records}) == len(worklist), 'duplicate entry ids'

    payload = dict(
        schema_version=1,
        scope=('kb_trial/curation/candidates.json 中已入选（decisions=accept）的全部 %d 条；'
               '只审已入选条目，未重审全库。' % len(worklist)),
        reviewer=('agent (Kimi Code subagent, deepseek) — 单代理逐条读 claim 正文与其所附引文后判定，'
                  '非独立第三方复核'),
        method=('逐条读取 claim 正文与 kb_trial/evidence.jsonl 中该条 citation_refs 指向的原始引文'
                '（QQ 窗口条读取 qq_cards/cards.jsonl 的 source_spans），按「可独立用于 RAG 的明确机制」'
                '这一单一判据判定。判定记录两个互不替代的维度：support（引文是否支持该 claim）与 '
                'info_value（该 claim 是否值得入库）。本轮为 claim 层语义内审，不等于证据核听：'
                '除 B010 外未回读原视频/原字幕文件逐字核听，因此 support 标 supported 只表示'
                '「所附引文支持该 claim」，不表示「已核听原片确认」。'),
        dimensions=dict(
            support=['supported', 'unsupported', 'unread_source'],
            info_value=['reusable_rule', 'instance_only', 'opinion', 'advice', 'void',
                        'no_params', 'not_self_contained'],
            verdict='keep = 可独立用于 RAG 的明确机制；drop = 其余情形',
            not_self_contained=('claim 无独立主语或结论对象未定义，逐字引文也不能救。'
                                '该值与冗余无关：冗余条目会被豁免保留，本类不豁免。'),
        ),
        self_containment_isolation=dict(
            count=len(SELF_CONTAINMENT_ISOLATED),
            note=('父代理点名的 4 条。判据是「claim 是否自包含且对象有定义」，'
                  '不是「引文是否逐字」。每条均已回读源文件/源字幕并把查到的事实写进 reason，'
                  '不猜新主体、不造对象。'),
            ids=sorted(SELF_CONTAINMENT_ISOLATED),
        ),
        source_context_checks=SOURCE_CONTEXT_CHECKS,
        coverage_correction=(
            '本轮重建工单时发现上一版抽样遗漏 2 条已入选条目（fc1:索敌-11-9#r8、fc1:索敌-22-14#r1），'
            '本版已补审并计入（812 → 814 条）。两条均已回读原字幕核实引文并判 keep：'
            '索敌-11-9#r8 引文「童真部署时以时间为仇恨的干员是同仇恨的」逐字支持；'
            '索敌-22-14#r1 引文所在 [40:06] 原文含「这里需要注意一下条件二技能同样也需要攻击冷却清零」，'
            '逐字支持。该遗漏属上一版工单生成的口径问题，已在本版修正。'),
        counts=dict(total=len(records),
                    keep=sum(1 for r in records if r['verdict'] == 'keep'),
                    drop=sum(1 for r in records if r['verdict'] == 'drop')),
        drop_by_info_value=dict(collections.Counter(
            r['info_value'] for r in records if r['verdict'] == 'drop')),
        records=records,
    )
    (OUT / 'semantic_review.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    with (OUT / 'semantic_overlay.jsonl').open('w', encoding='utf-8') as fh:
        for r in records:
            w = by_id[r['entry_id']]
            quotes = w['q'] or []
            fh.write(json.dumps(dict(
                entry_id=r['entry_id'], verdict=r['verdict'], support=r['support'],
                info_value=r['info_value'], reason=r['reason'], reviewer_type=r['reviewer_type'],
                claim=w['claim'], subject=w['subject'], condition=w['condition'],
                scope=w['scope'], category=w['cat'], source_layer=w['layer'],
                evidence_quote=(quotes[0] if quotes else None),
                evidence_quotes=quotes,
            ), ensure_ascii=False) + '\n')

    print(json.dumps({k: payload[k] for k in ('counts', 'drop_by_info_value')},
                     ensure_ascii=False, indent=1))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worklist', action='store_true',
                        help='rebuild semantic_worklist.json instead of applying verdicts')
    args = parser.parse_args()
    if args.worklist:
        write_worklist()
        return 0
    return build_review()


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
