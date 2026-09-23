"""Build curation/agent_verifications.json from the agent's forensic review.

The reviewer entries are literal decisions recorded while reading each rule's raw quote
and transcript window via kb_curation_verify.py / kb_curation_dossier.py. Anything not
listed here stays `pending` and never ships, which is the conservative default: an
unverified rule is not a rejected rule, it is an unshipped one.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'kb_trial/curation'

# (doc_id, rule_idx) -> (verdict, reason)
# verdict 'verify': the claim is a standalone mechanism statement and the raw quote
#   supports it. Evidence trail recorded in the reason.
# verdict 'reject': the claim misstates its source - over-claim, mis-citation, ASR
#   artifact, or non-standalone text. Must not ship.
REVIEW = {
    # ---- ASR-only rules that the agent checked against the raw ASR quote ----
    ('fc1:伤害结算-0-4', 0): ('verify',
        'ASR 引文逐字支持：p8:a0「但在肉鸽中侵蚀损伤削弱的是肉鸽加成前的基础防御」；'
        '邻窗确认语境为侵蚀损伤与肉鸽加成的结算层次'),
    ('fc1:伤害结算-0-9', 0): ('verify', 'ASR 引文逐字支持 p40:a1；邻窗 p40:a4 给出"这是抗性结算环节"'),
    ('fc1:伤害结算-0-9', 1): ('verify', 'ASR 引文逐字支持 p40:a5「伤判环节，然后去改写这个伤害」'),
    ('fc1:伤害结算-0-9', 2): ('verify', 'ASR 引文逐字支持 p40:a2「伤判是用来计算增伤和减伤的」'),
    ('fc1:伤害结算-0-9', 4): ('verify', 'ASR 引文逐字支持 p40:a0；p42:a1 复述同一区分'),
    ('fc1:伤害结算-0-9', 5): ('verify', 'ASR 引文逐字支持 p40:a3「是面板加成，通过四则运算确定属性」'),
    ('fc1:伤害结算-0-9', 6): ('verify', 'ASR 引文逐字支持 p42:a1'),
    ('fc1:伤害结算-12-20', 0): ('verify', 'ASR 引文逐字支持 p76:a0；邻窗确认"和命中率定义的不命中是区分开的"'),
    ('fc1:伤害结算-12-20', 1): ('verify', 'ASR 引文逐字支持 p76:a1'),
    ('fc1:伤害结算-12-20', 2): ('verify', 'ASR 引文 p76:a2 + p76:a4 两句合证；邻窗给出爱国者四连击实例'),
    ('fc1:伤害结算-12-20', 4): ('verify', 'ASR 引文 p76:a6；邻窗确认比较对象为四连击闪避'),
    ('fc1:伤害结算-12-20', 5): ('verify', 'ASR 引文逐字支持 p76:a7'),
    ('fc1:伤害结算-13-2', 0): ('verify', 'ASR 引文逐字支持 p78:a0（商判为伤判的 ASR 误写，语义为伤判）'),
    ('fc1:伤害结算-13-2', 1): ('verify', 'ASR 引文逐字支持 p78:a3；邻窗给出罗比拉塔护盾非零优先级的反例'),
    ('fc1:伤害结算-13-2', 2): ('verify', 'ASR 引文逐字支持 p78:a4'),
    # ---- ASR-only rules rejected on source grounds ----
    ('fc1:伤害结算-12-17', 0): ('reject',
        'ASR 原文为「公回」(0 次正确写法「攻回」，6 次误写)，属 ASR 术语错写；'
        '且引文 p75:a1 只支持"不管命不命中"，不支持"从事件帧加技力"这一断言'),
    ('fc1:伤害结算-12-17', 1): ('reject',
        'ASR 原文为「公会不管命不命中」，「公会」是「攻回」的 ASR 误写；'
        '按原字入库会把术语写错，且该条为对话确认句而非独立机制陈述'),
    ('fc1:伤害结算-12-18', 1): ('reject',
        'ASR 原文为「弓回是不需要命中的」(「弓回」是「攻回」的误写)；'
        '同一课 p75:a2 已有正确写法「攻回」，本条为重复且带错字'),
    # ---- numeric rules the agent checked against the raw quote ----
    ('fc1:伤害结算-16-15', 0): ('verify', 'official 引文 p38:a0 + p38:a1 两句逐字支持'),
    ('fc1:伤害结算-16-15', 1): ('verify', 'official 引文 p38:a2 + p38:a3 两句支持；引文自带"上下横跳"的波动限定'),
    ('fc1:伤害结算-16-15', 2): ('verify', 'official 引文 p39:a0 + p39:a1 两句逐字支持'),
    ('fc1:伤害结算-18-15', 0): ('verify', 'official 引文 p43:a0 逐字一致「面对无法推动的正常敌人横射 每个敌人三次判定」'),
    ('fc1:伤害结算-18-15', 1): ('verify', 'official 引文 p43:a1「竖射 每个敌人四次判定」；与 idx0 同段，主语正确'),
    ('fc1:位移-10-1', 7): ('verify', 'official 引文 p34:a0 逐字一致「每一帧有0.1635的摩擦力」'),
    ('fc1:位移-10-1', 10): ('verify', 'official 引文 p40:a1 支持该等效说法'),
    ('fc1:位移-10-1', 13): ('verify', 'official 引文 p26:a1 逐字支持；「无弹倒推」为"无弹道推"的 ASR 近似，语义未变'),
    ('fc1:伤害结算-15-9', 0): ('reject',
        '引文 p84:a0 只有「这19A是19次 1.3对吧 我们是这么算的」，'
        '不支持"有五次吃不到1.3倍率"这一具体数值断言（该数值来自别处，引文未闭合）'),
    ('fc1:伤害结算-18-13', 1): ('reject',
        '引文 p42:a0 是"横射"句，却用来支持"竖射每个敌人四次判定"，属于引文与断言不匹配；'
        '正确引文 p43:a1 已被 伤害结算-18-15 idx1 使用，本条为误引'),
    ('fc1:伤害结算-18-16', 1): ('reject',
        '引文只有「因为横着打的话他太正了」，不支持"判定数要么是1、要么是3、要么是5"的枚举；'
        '数值部分无引文支持，属未闭合推导'),
}


def main():
    verifications = [{'doc_id': doc_id, 'rule_idx': idx, 'verdict': verdict, 'reason': reason}
                     for (doc_id, idx), (verdict, reason) in sorted(REVIEW.items())]
    payload = {
        'reviewer': 'agent (Kimi Code subagent, deepseek)',
        'method': '逐条读取 kb_trial/evidence.jsonl 的原始引文与字幕/ASR 邻窗，比对派生规则句；'
                  '拒绝记为 reject 而非删除，未列出的条目保持 pending 且不入库',
        'source_files': ['kb_trial/evidence.jsonl', 'transcripts_txt/', 'asr_drafts/'],
        'counts': {'verify': sum(1 for v in REVIEW.values() if v[0] == 'verify'),
                   'reject': sum(1 for v in REVIEW.values() if v[0] == 'reject')},
        'verifications': verifications,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'agent_verifications.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload['counts'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
