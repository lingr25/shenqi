import re
import json

# 专有名词与高频同音错别字映射表
CORRECTION_RULES = [
    # 核心干员/实体消歧
    (r"山比", "珊比"),
    (r"(?<=重装)(佩佩|山比)", "珊比"),
    (r"(?<=打)(山比)", "珊比"),
    (r"(?<=抽)(山比)", "珊比"),
    
    # 黍 (针对容易识别成 鼠/属/数/署 的情况)
    (r"(?<=播种|种子|地块|天赋|三技能)(属|鼠|数|暑|署)", "黍"),
    (r"(属|鼠|数|暑|署)(?=的种子|的地块|播种|天赋|三技能|开大)", "黍"),
    (r"(?<=黍|提丰|维什戴尔)(属|鼠|数)", "黍"),

    # 维什戴尔 / EW
    (r"(?i)\b1w\b", "EW"),
    (r"卫士戴尔|维斯戴尔|为什戴尔", "维什戴尔"),
    
    # 核心方舟底层机制术语
    (r"Tech动画", "Attack动画"),
    (r"(?i)\btech\b(?=\s*帧|\s*动画)", "Attack"),
    (r"组党|祖统|组当|阻党", "阻挡"),
    (r"弊杖|臂脏|B帐|必涨|币涨", "避障"),
    (r"避障力", "避障力"),
    (r"(?<=回复|回|扣|攒|满|点)(激励|纪力|记力)", "技力"),
    (r"(激励|纪力|记力)(?=回复|自然回复|拐|充能)", "技力"),
    (r"弹到(?=判定|轨迹|速度|碰撞)", "弹道"),
    (r"(?<=子弹|投射物|远程)(谈到|弹到)", "弹道"),
    (r"锁敌|索地", "索敌"),
    (r"索敌真|索敌正", "索敌帧"),
    (r"平整化算法", "平整化算法"),
    (r"凭证化", "平整化"),
    (r"选择组", "选择组"),
    (r"仇恨排序", "仇恨排序"),
    (r"对轴", "对轴"),
    (r"dot伤害|dot时序|DOT时序", "DoT时序"),
]

def correct_text(text: str) -> str:
    """对单段文本应用机制与干员专有名词纠错"""
    res = text
    for pattern, repl in CORRECTION_RULES:
        res = re.sub(pattern, repl, res)
    return res

def clean_subtitle_items(items):
    """
    清洗字幕列表，合并过短的碎句（如0.2秒一两个字），
    过滤纯语气助词/静音空白，并应用术语校准
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
