#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_prts_wiki.py
-----------------
从 PRTS Wiki (prts.wiki) 自动化抓取明日方舟全量干员、敌人、装置、
战斗机制与官方状态效果，并结合神奇直播代码级/算法级黑话，
构建高精准度、零知识库截止限制的本地实体字典：prts_entities.json。
"""

import os
import re
import sys
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime

# 保证标准输出为 UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PRTS_API_URL = "https://prts.wiki/api.php"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Host': 'prts.wiki'
}

def api_request(params, max_retries=3, delay=1.0):
    """向 PRTS API 发起 HTTP GET 请求，内置重试机制"""
    url = PRTS_API_URL + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read().decode('utf-8')
                return json.loads(data)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                print(f"[Warn] API 请求失败 ({url[:80]}...): {e}", file=sys.stderr)
                return {}

def fetch_category_members(category_name, ns=0):
    """递归遍历指定分类下的所有词条"""
    members = []
    cmcontinue = None
    print(f"[*] 正在抓取 Category:{category_name} ...", end="", flush=True)
    
    count = 0
    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category_name}',
            'cmlimit': '500',
            'format': 'json'
        }
        if cmcontinue:
            params['cmcontinue'] = cmcontinue
            
        data = api_request(params)
        cm_list = data.get('query', {}).get('categorymembers', [])
        for item in cm_list:
            if item.get('ns') == ns:
                title = item['title'].strip()
                if title:
                    members.append(title)
                    count += 1
                    
        if 'continue' in data and 'cmcontinue' in data['continue']:
            cmcontinue = data['continue']['cmcontinue']
            time.sleep(0.3)
        else:
            break
            
    print(f" 完成，共获取 {count} 条。")
    return members

def fetch_page_wikitext(page_name):
    """获取指定页面的 raw wikitext"""
    params = {
        'action': 'parse',
        'page': page_name,
        'prop': 'wikitext',
        'format': 'json'
    }
    data = api_request(params)
    return data.get('parse', {}).get('wikitext', {}).get('*', '')

def parse_terms_glossary():
    """解析《术语释义》页面的全部官方战斗与状态术语"""
    print("[*] 正在解析《术语释义》页面官方词条 ...", flush=True)
    wt = fetch_page_wikitext("术语释义")
    if not wt:
        print("[!] 获取《术语释义》失败")
        return []
        
    terms = []
    # 提取 {{术语释义|名称|...}}
    matches = re.findall(r'\{\{术语释义\|([^\|\}]+)', wt)
    for m in matches:
        term = m.strip()
        if term and term not in terms:
            terms.append(term)
            
    # 提取二级/三级标题，如 ===状态===, ===机制===
    headers = re.findall(r'={2,4}\s*([^=\n]+?)\s*={2,4}', wt)
    for h in headers:
        clean_h = h.strip()
        if clean_h and len(clean_h) <= 8 and clean_h not in terms:
            terms.append(clean_h)
            
    print(f"[*] 《术语释义》提取完成，共 {len(terms)} 个官方术语。")
    return terms

def parse_mechanic_pages():
    """解析核心机制专题页面提取关键术语"""
    mechanic_pages = [
        "索敌的概念", "索敌逻辑", "仇恨", "仇恨公式",
        "推拉", "弹道", "伤害分类", "伤害类型", "伤害规避效果",
        "命中率", "选择器", "诱发移动", "可抵抗状态", "伤判效果",
        "数值范围", "特殊机制", "部署费用"
    ]
    
    collected_terms = set()
    print("[*] 正在解析核心机制专题页面 ...", flush=True)
    
    for page in mechanic_pages:
        params = {
            'action': 'parse',
            'page': page,
            'prop': 'links|sections',
            'format': 'json'
        }
        data = api_request(params)
        parse_data = data.get('parse', {})
        
        # 页面标题自身就是关键机制词
        collected_terms.add(page)
        
        # 提取章节标题
        for sec in parse_data.get('sections', []):
            line = sec.get('line', '').strip()
            # 过滤带特殊标记的
            line = re.sub(r'<[^>]+>', '', line).strip()
            if line and 2 <= len(line) <= 12 and not line.startswith(('参考', '参见', '注释')):
                collected_terms.add(line)
                
        # 提取相关内链
        for link in parse_data.get('links', []):
            if link.get('ns') == 0:
                ltitle = link.get('*', '').strip()
                if ltitle and 2 <= len(ltitle) <= 10:
                    collected_terms.add(ltitle)
                    
        time.sleep(0.2)
        
    print(f"[*] 核心机制专题页面解析完成，共提取 {len(collected_terms)} 个术语。")
    return sorted(list(collected_terms))

def get_shenqi_core_slangs():
    """
    梳理神祇读神奇直播中高频使用的代码级/算法级逆向机制术语与口语黑话。
    这些是 PRTS 页面可能仅从表象描述，而神奇深入到底层 Unity / 逻辑架构的特有词汇。
    """
    return {
        "pathfinding_and_algorithms": [
            "平整化", "平整化算法", "Straightening", "Next Node", "next_node",
            "向前链接", "上右下左", "BFS遍历", "推地块", "不可通行地块", "可通行地块",
            "不可通行区", "行差列差", "2xX长方形", "2×X长方形", "2*X区域",
            "网格坐标", "路径点", "连通性", "射线检测", "Raycast", "寻路地图"
        ],
        "combat_and_frame_timing": [
            "Attack动画", "Attack帧", "攻击前摇", "攻击后摇", "攻击间隔",
            "同帧", "同帧撤退", "换位跳", "索敌帧", "仇恨排序", "选择组",
            "避障力", "避障", "爆条", "DoT时序", "DoT伤害", "伤害时序",
            "0.2半径", "阻挡偏移", "自然回复", "强掷", "近地悬浮",
            "落地刷新判定", "进格判定", "进坑判定", "坑杀", "时停", "重构体",
            "失衡抗性", "元素损伤", "凋亡损伤", "神圣伤害"
        ],
        "common_corrections": [
            {"wrong": "便利顺序", "correct": "遍历顺序"},
            {"wrong": "四期格", "correct": "四七格"},
            {"wrong": "四气格", "correct": "四七格"},
            {"wrong": "练四一", "correct": "连四一"},
            {"wrong": "练四六", "correct": "连四六"},
            {"wrong": "退到四二", "correct": "推到四二"},
            {"wrong": "六散", "correct": "六三"},
            {"wrong": "4S", "correct": "四三"},
            {"wrong": "二乘S", "correct": "2×X"},
            {"wrong": "二乘X", "correct": "2×X"},
            {"wrong": "巡逻地图", "correct": "寻路地图"},
            {"wrong": "选露", "correct": "寻路"},
            {"wrong": "弊杖", "correct": "避障"},
            {"wrong": "臂脏", "correct": "避障"},
            {"wrong": "B帐", "correct": "避障"},
            {"wrong": "必涨", "correct": "避障"},
            {"wrong": "索敌真", "correct": "索敌帧"},
            {"wrong": "索敌正", "correct": "索敌帧"},
            {"wrong": "索敌针", "correct": "索敌帧"},
            {"wrong": "报调", "correct": "爆条"},
            {"wrong": "暴调", "correct": "爆条"},
            {"wrong": "童真撤重构体", "correct": "同帧撤重构体"},
            {"wrong": "童真", "correct": "同帧"},
            {"wrong": "PRTSVK", "correct": "PRTS Wiki"},
            {"wrong": "PRTS点wiki", "correct": "PRTS Wiki"}
        ]
    }

def get_operator_and_community_aliases():
    """
    社区常用外号、简称及异格对照表
    """
    return {
        "维什戴尔": ["EW", "ew", "W异格"],
        "Mon3tr": ["M3", "m3", "重构体", "怪怪"],
        "黍": ["禾", "数", "属", "鼠"],
        "玛恩纳": ["叔叔"],
        "纯烬艾雅法拉": ["小羊", "火羊", "羊二"],
        "艾雅法拉": ["小羊"],
        "银灰": ["老板"],
        "提丰": ["提丰"],
        "艾拉": ["雷"],
        "娜斯提": ["纳斯提"],
        "佩佩": ["小狗"],
        "珊比": ["山比"],
        "神祇读神奇": ["神奇"]
    }

def main():
    print("=" * 60)
    print("明日方舟机制库 - PRTS Wiki 实体与术语全量同步")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 抓取干员列表
    raw_operators = fetch_category_members("干员")
    # 规范化干员名（去除消歧义括号等）
    clean_operators = set()
    for op in raw_operators:
        clean_operators.add(op)
        base_name = re.sub(r'\(.*?\)', '', op).strip()
        if base_name:
            clean_operators.add(base_name)
    operators_list = sorted(list(clean_operators))
    
    # 2. 抓取敌人列表
    raw_enemies = fetch_category_members("敌人")
    clean_enemies = set()
    for en in raw_enemies:
        clean_en = en.strip('“”"\' ')
        clean_enemies.add(clean_en)
        base_en = re.sub(r'\(.*?\)', '', clean_en).strip()
        if base_en:
            clean_enemies.add(base_en)
    enemies_list = sorted(list(clean_enemies))
    
    # 3. 抓取装置与特殊单位列表
    raw_devices = fetch_category_members("装置")
    devices_list = sorted(list(set([d.strip('“”"\' ') for d in raw_devices])))
    
    # 4. 解析《术语释义》官方战斗术语
    status_terms = parse_terms_glossary()
    
    # 5. 解析核心机制专题页面
    mechanic_terms = parse_mechanic_pages()
    
    # 6. 整合神奇直播源码/算法级黑话
    shenqi_slangs = get_shenqi_core_slangs()
    
    # 7. 整合常用别名表
    aliases = get_operator_and_community_aliases()
    
    # 构建输出实体库
    entities_db = {
        "metadata": {
            "source": "PRTS Wiki (prts.wiki)",
            "updated_at": datetime.now().isoformat(),
            "counts": {
                "operators": len(operators_list),
                "enemies": len(enemies_list),
                "devices": len(devices_list),
                "status_terms": len(status_terms),
                "mechanic_terms": len(mechanic_terms),
                "shenqi_slangs": len(shenqi_slangs["pathfinding_and_algorithms"]) + len(shenqi_slangs["combat_and_frame_timing"])
            }
        },
        "operators": operators_list,
        "enemies": enemies_list,
        "devices": devices_list,
        "status_terms": status_terms,
        "mechanic_terms": mechanic_terms,
        "shenqi_slangs": shenqi_slangs,
        "aliases": aliases
    }
    
    output_path = os.path.join(os.path.dirname(__file__), "prts_entities.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entities_db, f, ensure_ascii=False, indent=2)
        
    print("=" * 60)
    print(f"同步完成！数据已成功持久化至: {output_path}")
    print(f"  - 全量干员数:   {len(operators_list)}")
    print(f"  - 全量敌人数:   {len(enemies_list)}")
    print(f"  - 地图装置数:   {len(devices_list)}")
    print(f"  - 官方状态术语: {len(status_terms)}")
    print(f"  - 机制专题词汇: {len(mechanic_terms)}")
    print(f"  - 神奇黑话词汇: {entities_db['metadata']['counts']['shenqi_slangs']}")
    print("=" * 60)

if __name__ == '__main__':
    main()
