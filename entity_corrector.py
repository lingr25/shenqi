#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_corrector.py
-------------------
机制专有名词与高频同音消歧纠错模块。
整合 PRTS Wiki 全量实体词库与神祇读神奇直播代码级/算法级黑话，
针对语音识别（ASR）的高频同音错别字进行精准消歧与正则清洗。
"""

import os
import re
import json

# 加载本地 PRTS 实体词库（若存在）
PRTS_ENTITIES_PATH = os.path.join(os.path.dirname(__file__), "prts_entities.json")
PRTS_ENTITIES = {}
if os.path.exists(PRTS_ENTITIES_PATH):
    try:
        with open(PRTS_ENTITIES_PATH, "r", encoding="utf-8") as f:
            PRTS_ENTITIES = json.load(f)
    except Exception as e:
        print(f"[Warn] 读取 PRTS 词典失败: {e}")

# 高频同音错别字与机制专有名词消歧规则库
CORRECTION_RULES = [
    # ================= 0. ASR 同音误识(审核反馈新增) =================
    (r"真金范围", "帧进范围"),
    (r"真金帧", "帧进帧"),
    (r"真金(?=判定|范围)", "帧进"),
    (r"前溜拐", "琴柳拐"),
    (r"前溜(?=时|的|下)", "琴柳"),
    (r"落地引", "落地隐"),
    (r"(?<![一-鿿])伊德(?![一-鿿])", "异德"),
    (r"易德(?=稍|的|想|攻|控)", "异德"),
    # v2 审计新增
    (r"锁敌", "索敌"),
    (r"素心", "塑心"),
    (r"童真(?=撤|时|部|开|判|索)", "同帧"),
    # 系统化挖掘 (kb/asr_mine.jsonl, 人工筛后)
    (r"紫兰", "梓兰"),
    (r"[赛塞]雷亚", "塞雷娅"),
    (r"火辰", "火陈"),
    (r"维云斯|维斯代尔", "维什戴尔"),
    (r"纳斯迪", "纳斯提"),
    (r"(?<![一-鿿])翔子(?![一-鿿])", "祥子"),
    (r"三匕|三比", "珊比"),
    (r"波普", "波卜"),
    (r"三帧帧", "三帧"),
    (r"两针帧", "两帧"),
    (r"两针(?![一二三四五六七八九十])", "两帧"),
    (r"免疫鼠传", "免疫传送"),
    (r"号十字路", "十字路口"),
    (r"字形态(?=的)", "鱼形态"),
    (r"醒来针", "醒来帧"),
    (r"避障针", "避障帧"),
    (r"翼德", "异德"),
    (r"三针(?=一索|索敌|判定|循环)", "三帧"),  # 质量审计 asr_suspect
    (r"两针(?=判定|一次|一索)", "两帧"),
    (r"第一针", "第一帧"),
    (r"一针(?=内|判定|索)", "一帧"),

    # ================= 1. 主播名号与外部数据库 =================
    (r"PRTSVK|PRTS\s*点\s*wiki|PRTS点Wiki|prts\s*点\s*wiki", "PRTS Wiki"),
    (r"神[，,\s]+奇是地下的神", "神，祇是地下的神"),
    (r"统称神奇(?=让我想了半天|我感觉非常)", "统称神祇"),
    (r"叫神奇\s*读神奇", "叫神祇读神奇"),
    (r"选露(?=\s*机制|\s*算法)", "寻路"),

    # ================= 2. 底层寻路与平整化算法 (Straightening) =================
    (r"地块的便利顺序", "地块的遍历顺序"),
    (r"地块便利(?=顺序|排完)", "地块遍历"),
    (r"便利地块", "遍历地块"),
    (r"巡逻地图", "寻路地图"),
    (r"平整化算法", "平整化算法"),
    (r"凭证化(?=操作|算法|的顺序)", "平整化"),
    (r"(?i)next\s*node", "Next Node"),
    (r"尝试连接的两个地块(行差列差为一|行差列差为1)", "尝试连接的两个地块行差与列差为1"),
    (r"二乘[SXsx]长方形", "2×X长方形"),
    (r"二乘[SXsx](长方形|区域)", r"2×X\1"),
    (r"对二乘[SXsx]", "对2×X"),
    (r"二乘[SXsx]", "2×X"),

    # 网格坐标与连接动作消歧
    (r"四期格|四气格", "四七格"),
    (r"([0-9一二三四五六七八九十])期格", r"\1七格"),
    (r"([0-9一二三四五六七八九十])气格", r"\1七格"),
    (r"六散(?=\s*判定|\s*连)", "六三"),
    (r"(?i)4S", "四三"),
    (r"(?i)4e", "四一"),
    (r"(?i)C1(?=[^\w]|$)|(?<=[^\w])C1", "四一"),
    (r"C1", "四一"),
    (r"他练([一二三四五六七八九十0-9]{2})", r"他连\1"),
    (r"([一二三四五六七八九十0-9]{2})练([一二三四五六七八九十0-9]{2})", r"\1连\2"),
    (r"练不到([一二三四五六七八九十0-9]{2}|C1|4E)", r"连不到\1"),
    (r"退到([一二三四五六七八九十0-9]{2})", r"推到\1"),
    (r"后背推的", "后被推的"),
    (r"第一部被排除", "第一步被排除"),
    (r"这个歌(?=\s*它往|\s*指向)", "这个格"),
    (r"这个往这里值", "这个往这里指"),
    (r"这个格往这里值", "这个格往这里指"),

    # ================= 3. 战斗时序、判定帧与底层机制 =================
    (r"Tech动画|tech动画", "Attack动画"),
    (r"(?i)\btech\b(?=\s*帧|\s*动画)", "Attack"),
    (r"索敌[真正针]|锁敌[真正针]", "索敌帧"),
    (r"卡那个[针真]", "卡那个帧"),
    (r"卡那个索敌[针真]", "卡那个索敌帧"),
    (r"刚好在死的那一阵", "刚好在死的那一帧"),
    (r"刚好那一阵(?=巧吧|巧了)", "刚好那一帧"),
    (r"童真撤重构体", "同帧撤重构体"),
    (r"童真(?=撤|卡死|判定|退)", "同帧"),
    (r"组党|祖统|组当|阻党", "阻挡"),
    (r"弊杖|臂脏|B帐|必涨|币涨", "避障"),
    (r"避障力", "避障力"),
    (r"(回复|回|扣|攒|满|点)(激励|纪力|记力)", r"\1技力"),
    (r"(激励|纪力|记力)(?=回复|自然回复|拐|充能)", "技力"),
    (r"弹到(?=判定|轨迹|速度|碰撞)", "弹道"),
    (r"(子弹|投射物|远程)(谈到|弹到)", r"\1弹道"),
    (r"锁敌|索地", "索敌"),
    (r"选择组", "选择组"),
    (r"仇恨排序", "仇恨排序"),
    (r"对轴", "对轴"),
    (r"dot伤害|dot时序|DOT时序", "DoT时序"),
    (r"大盾在第一次报调", "大盾在第一次爆条"),
    (r"酒神A他五下或者六下加起来把他暴条", "酒神A他五下或者六下加起来把他爆条"),
    (r"这一次暴调", "这一次爆条"),
    (r"通过这次暴调", "通过这次爆条"),
    (r"报调|暴调", "爆条"),

    # ================= 4. 干员、召唤物与敌方单位消歧 =================
    # 维什戴尔 / EW
    (r"(?i)\b1w\b", "EW"),
    (r"卫士戴尔|维斯戴尔|为什戴尔", "维什戴尔"),

    # Mon3tr / 重构体
    (r"(?i)\bm3\b", "M3"),

    # 黍 (针对容易识别成 鼠/属/数/署 的情况)
    (r"(播种|种子|地块|天赋|三技能)(属|鼠|数|暑|署)", r"\1黍"),
    (r"(属|鼠|数|暑|署)(?=的种子|的地块|播种|天赋|三技能|开大)", "黍"),
    (r"(黍|提丰|维什戴尔)(属|鼠|数)", r"\1黍"),
    (r"我们这个时间是绝对没有(数|属)", "我们这个时间是绝对没有黍"),
    (r"我们(数|属)(?=不可能开三套|开大|播种)", "我们黍"),

    # 娜斯提 (Nasty)
    (r"纳斯提", "娜斯提"),
    (r"娜斯提二天赋", "娜斯提第二天赋"),

    # 佩佩 / 珊比
    (r"山比", "珊比"),
    (r"(重装|打|抽)(佩佩|山比)", r"\1珊比"),

    # 艾拉 (Ella)
    (r"减的是物理和法术命中率，都是(爱拉|埃拉)宝的", "减的是物理和法术命中率，都是艾拉宝的"),
    (r"都是(爱拉|埃拉)宝的", "都是艾拉宝的"),
    (r"讲下(爱拉|埃拉)和麦哲伦", "讲下艾拉和麦哲伦"),
    (r"一个是(爱拉|埃拉)，一个是麦哲伦", "一个是艾拉，一个是麦哲伦"),
    (r"(爱拉|埃拉)(?=和麦哲伦|保住了|减命中率|埋雷|雷)", "艾拉"),

    # 麦哲伦 / 铃兰 / 惊蛰
    (r"麦哲伦可以触发三辅助加天四", "麦哲伦可以触发三辅助加天四"),
    (r"天4", "第二天赋"),
]

def correct_text(text: str) -> str:
    """对单段文本应用机制与干员专有名词纠错"""
    res = text
    for pattern, repl in CORRECTION_RULES:
        res = re.sub(pattern, repl, res)
    return res

def clean_subtitle_items(items):
    """
    清洗字幕条目列表：
    - 应用专有名词纠错规则
    - 计算规范持续时长
    """
    cleaned = []
    for it in items:
        raw_c = it.get('content', '').strip()
        if not raw_c:
            continue
        norm_c = correct_text(raw_c)
        cleaned.append({
            "from": it.get('from'),
            "to": it.get('to'),
            "duration": round(it.get('to', 0) - it.get('from', 0), 2),
            "content": norm_c
        })
    return cleaned

def format_timestamp(seconds: float) -> str:
    """将秒数转为 [HH:MM:SS] 或 [MM:SS]"""
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    else:
        return f"[{minutes:02d}:{secs:02d}]"

def build_natural_transcript(cleaned_items, max_pause=1.2, max_len=60):
    """
    将碎句字幕进行自然断句与时间符合并：
    - 停顿小于 max_pause 秒且总字数不超过 max_len 时平滑合并
    - 过滤纯单字无意义结巴或空停顿
    - 行首保留规范时间戳
    """
    if not cleaned_items:
        return []

    lines = []
    current_start = cleaned_items[0]['from']
    current_end = cleaned_items[0]['to']
    current_tokens = [cleaned_items[0]['content']]

    for it in cleaned_items[1:]:
        t_from = it['from']
        t_to = it['to']
        text = it['content']
        
        # 停顿间隔
        pause = t_from - current_end
        combined_len = sum(len(t) for t in current_tokens) + len(text)
        
        if pause <= max_pause and combined_len <= max_len:
            current_tokens.append(text)
            current_end = t_to
        else:
            merged_text = correct_text(" ".join(current_tokens))
            lines.append(f"{format_timestamp(current_start)} {merged_text}")
            current_start = t_from
            current_end = t_to
            current_tokens = [text]

    if current_tokens:
        merged_text = correct_text(" ".join(current_tokens))
        lines.append(f"{format_timestamp(current_start)} {merged_text}")

    return lines
