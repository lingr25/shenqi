# -*- coding: utf-8 -*-
"""term-mining round2 主会话裁定落地脚本 (2026-09-27)。

输入: kb_trial/term_mining/CANDIDATES_REVIEW_R2.md (672 条 r1 未裁定项)。
裁定人: 主会话代理 (复核后待用户抽查)。裁定口径与落点:

- 无推断(low 261 + mid 实体/黑话大部): 无改写对象, 不入规则, 见 REVIEW_R2_VERDICTS.md 附表
- 推断命中词表 (130 条): 同族已在词表内, 自动采纳
- 有推断未命中词表 (172 条): 主会话逐条裁定 -> 本脚本规则
- 高危常用词/单字一律文件级; 全局仅收独特字符串或带断言的形式

幂等: 重复运行检测到 MARK_G 即跳过。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORRECTOR = ROOT / 'entity_corrector.py'
MARK_G = '# --- term_mining R2 全局规则 (2026-09-27 主会话裁定) ---'
MARK_F = '# --- term_mining R2 文件级规则 ---'

GLOBAL_RULES = [
    # ---- 帧家族 ----
    (r'16镇', '16帧'),
    (r'dot真', 'dot帧'),
    (r'停的阵', '停的帧'),
    (r'帧出售', '帧出手'),
    (r'整数阵', '整数帧'),
    (r'清Buff的阵', '清Buff的帧'),
    (r'真内', '帧内'),
    (r'真计算', '帧计算'),
    (r'真零', '帧零'),
    (r'红童真', '红同帧'),
    (r'四四枕', '四四帧'),
    (r'极限真', '极限帧'),
    (r'零帧救出停顿', '零帧就出停顿'),
    (r'丁出生帧', '盯出生帧'),
    (r'撤退J帧', '撤退几帧'),
    (r'易嗔易出怪', '一帧一出怪'),
    (r'八帧书生', '八帧受伤'),
    (r'手机半径', '索敌半径'),
    (r'台的手', '抬的手'),
    # ---- 数字/记号粘连 ----
    (r'(?<=\d)G为', '记为'),
    (r'(?<=\d)乍到', '炸到'),
    (r'减计为', '简记为'),
    (r'恩格', 'N格'),
    (r'手机三倍', '首击三倍'),
    (r'150kg', '150攻速'),
    (r'无天寺', '无天四'),
    (r'段动化', '段动画'),
    (r'(?<!分)段攻击', '断攻击'),
    # ---- 机制词 ----
    (r'B站中间量', '避障中间量'),
    (r'MOMULTIPLAYER', 'multiplier'),
    (r'RTSS点map', 'PRTS.map'),
    (r'两性动力', '两行动力'),
    (r'公务经理', '勾股定理'),
    (r'冲奶帧', '出奶帧'),
    (r'巡逻的方向', '寻路的方向'),
    (r'巡逻程序', '寻路程序'),
    (r'对猎手', '队首'),
    (r'强盗零', '降到零'),
    (r'毒帧', '对帧'),
    (r'永空中', '永控中'),
    (r'联通阁', '联通格'),
    (r'格派', '格判'),
    (r'蓝门阁', '蓝门格'),
    (r'蛋到初堂', '弹到出膛'),
    (r'铜币形', '同地形'),
    (r'(?<=个)销量', '向量'),
    (r'(?<=的)销量', '向量'),
    (r'隔墙西', '隔墙吸'),
    (r'隔心', '格心'),
    (r'势力度', '是力度'),
    (r'卓痕', '灼痕'),
    (r'无视引力', '无视隐匿'),
    (r'机智怪', '机制怪'),
    (r'in(?=的正式生效)', '印'),
    (r'(?<=不过)十天', '十点'),
    (r'三余数', '三帧余数'),
    # ---- 人名/社区 ----
    (r'早罗兔兔', '早露兔兔'),
    (r'走路兔兔', '早露兔兔'),
    (r'海雅出', '霍尔海雅厨'),
    (r'李波利', '黎波利'),
    (r'阿依零', 'Re:0'),
    # ---- 地名/活动/关卡 ----
    (r'火山吕梦', '火山旅梦'),
    (r'反向异格', '反向一格'),
    (r'句型 Both', '巨型Boss'),
    (r'绿梦幻', '绿野幻梦'),
    (r'登临沂合集', '登临意合集'),
    (r'陈影如音', '尘影余音'),
    (r'镜罪', '净罪'),
    (r'咸鱼火力覆盖', '全域火力覆盖'),
    (r'热拉(?=可可)', '热辣'),
    (r'水机(?=树海)', '黑流'),
    # ---- 干员/敌人 ----
    (r'珊比船', '珊比传'),
    (r'甲骑', '假棋'),
    (r'甲棋', '假棋'),
    (r'深池影刃', '深池伙友影刃'),  # R1 裸规则 申驰→深池 先行,
    (r'杀敌兽', '沙地兽'),
    (r'水位拉赤金', '水月拉赤金'),
    (r'九成二', '酒神二'),
    (r'余下去了', '鱼下去了'),
    (r'可可悲情', '可可被清'),
    (r'朝用', '朝右'),
    (r'木列', '木裂'),
    (r'某地人', '某敌人'),
    (r'背伸', '背身'),
    (r'(?<=是)肺癌', '废案'),
    (r'(?<=个)肺癌', '废案'),
    (r'时攻速', '实攻速'),
    (r'辅助卷', '辅助券'),
    (r'陷阱失策', '陷阱实测'),
    (r'施与德', '失与得'),
    (r'猎犬PROTO', '猎狗Pro'),
    (r'猎狗 Pro to', '猎狗Pro'),
    (r'普罗托', '猎狗Pro'),
    (r'大罢', '大bug'),
    (r'BBO1', 'BB-1'),
]

FILE_RULES = {
    'BV1wPuG6aEyY': [
        (r'4万元', '四外援'),
        (r'汇算', '会算'),
        (r'简介', '简记'),
        (r'鲜奶', '先奶'),
    ],
    'BV14gby6LEni': [
        (r'ELLADY', 'Ela的'),
        (r'小树真', '小数点'),
    ],
    'BV1UVeV66E7p': [
        (r'MV', 'MAA'),
        (r'小鸟特线', '小鸟特限'),
    ],
    'BV1WKrFBCEQL': [
        (r'wife', '外服'),
        (r'大底', '大盾'),
    ],
    'BV1TomVBBEK1': [
        (r'上册', '上侧'),
        (r'下课', '下坑'),
        (r'化妆', '画中人'),
        (r'灵芝', '零值'),
    ],
    'BV14VZCB1EJR': [
        (r'丹雷', '单雷'),
        (r'渊博', '渊默'),
    ],
    'BV1uQeV6yEQa': [
        (r'八斗', '八刀'),
    ],
    'BV1kRbQ6tEG9': [
        (r'到达事件', '到达时间'),
        (r'奇人', '七人'),
        (r'暗格', '按格'),
        (r'就记了', '就寄了'),
        (r'零迷', '0米'),
        (r'所有革新', '所有格子'),
        (r'鞋带', '携带'),
    ],
    'BV1qArGBPEQ8': [
        (r'富裕(?=最|的)', 'buff'),
        (r'稻草', 'dot'),
        (r'12岁', '12睡'),
    ],
    'BV14y8269EbS': [
        (r'小偷(?=别|好|找)', '小兔'),
    ],
    'BV1RuiiBUEfT': [
        (r'大队', '大盾'),
    ],
    'BV1jd3m68E6f': [
        (r'调令', '调零'),
    ],
    'BV17WquBEEdX': [
        (r'42层', '4.2秒'),
        (r'金帧', '金身'),
        (r'血航', '雪狼'),
    ],
    'BV1uLE86JEi1': [
        (r'E技能', '一技能'),
        (r'出剑', '出箭'),
    ],
    'BV1gsmYBwEyZ': [
        (r'button', 'bullet'),
    ],
    'BV1aTeV6yENP': [
        (r'刀功', '刀攻'),
        (r'药(?=的输出)', '羊'),
        (r'机械师凯', '机械式开'),
    ],
    'BV1CZ8t6wEyr': [
        (r'狙一', '狙医'),
    ],
    'BV1qReG6XE6W': [
        (r'驼兽(?=一|你)', '驮兽'),
    ],
    'BV1dVcbzFEdd': [
        (r'加成(?=这个|没办法)', '爱国者'),
    ],
}


def fmt_rules(pairs, indent='    '):
    return '\n'.join(f'{indent}(r"{p}", "{r}"),' for p, r in pairs)


def merge_file_rules(src):
    """同一 BV 的文件级块只允许存在一次：已有块则把规则插进块首，没有才新建块。
    追加新块统一放在 FILE_CONTEXT_RULES 收尾 } 之前。"""
    new_blocks = []
    for bv, rules in FILE_RULES.items():
        key = f'    "{bv}": [\n'
        if key in src:
            src = src.replace(key, key + fmt_rules(rules, indent='        ') + '\n', 1)
        else:
            new_blocks.append(f'    "{bv}": [\n{fmt_rules(rules, indent="        ")}\n    ],')
    if new_blocks:
        # 定位 FILE_CONTEXT_RULES 字典的收尾：从声明行起找下一行行首 }
        decl = src.index('FILE_CONTEXT_RULES = {')
        close = src.index('\n}', decl)
        src = (src[:close] + '\n    ' + MARK_F + '\n'
               + '\n'.join(new_blocks) + src[close:])
    return src


def main():
    src = CORRECTOR.read_text(encoding='utf-8')
    if MARK_G in src:
        print('already applied, skip')
        return 0

    anchor = '    (r"蜥(?!蜴)", "夕"),\n]'
    assert anchor in src, 'global anchor not found'
    block = ('    (r"蜥(?!蜴)", "夕"),\n\n    ' + MARK_G + '\n'
             + fmt_rules(GLOBAL_RULES) + '\n]')
    src = src.replace(anchor, block)

    src = merge_file_rules(src)

    CORRECTOR.write_text(src, encoding='utf-8')
    n_g = len(GLOBAL_RULES)
    n_f = sum(len(v) for v in FILE_RULES.values())
    print(f'inserted {n_g} global rules, {n_f} file-scoped rules into {len(FILE_RULES)} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
