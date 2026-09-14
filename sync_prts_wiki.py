#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_prts_wiki.py
-----------------
从 PRTS Wiki (prts.wiki) 自动化抓取明日方舟全量干员、敌人、装置、
官方战斗机制、状态效果，以及 PRTS 官方维护的【全量干员外号/重定向别名】
与【明日方舟黑话·梗·成句】，并融合神祇读神奇直播代码级/算法级黑话，
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
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def api_request(params, max_retries=3, delay=0.8):
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
            time.sleep(0.2)
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
            
    # 提取二级/三级标题
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
        collected_terms.add(page)
        
        for sec in parse_data.get('sections', []):
            line = sec.get('line', '').strip()
            line = re.sub(r'<[^>]+>', '', line).strip()
            if line and 2 <= len(line) <= 12 and not line.startswith(('参考', '参见', '注释')):
                collected_terms.add(line)
                
        for link in parse_data.get('links', []):
            if link.get('ns') == 0:
                ltitle = link.get('*', '').strip()
                if ltitle and 2 <= len(ltitle) <= 10:
                    collected_terms.add(ltitle)
                    
        time.sleep(0.15)
        
    print(f"[*] 核心机制专题页面解析完成，共提取 {len(collected_terms)} 个术语。")
    return sorted(list(collected_terms))

def is_valid_alias(alias: str) -> bool:
    """过滤无意义或纯日文假名的别名"""
    # 纯假名（日文平假名/片假名）过滤
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', alias):
        return False
    # 过滤单字符非英文字母
    if len(alias) <= 1 and not alias.isascii():
        return False
    # 过滤过长特殊转写
    if len(alias) > 30:
        return False
    # 过滤特定消歧义前缀
    if alias.startswith(('文件:', '分类:', 'Template:')):
        return False
    return True

def fetch_single_operator_aliases(op_name):
    """查询单个干员的 backlinks 重定向别名"""
    params = {
        'action': 'query',
        'list': 'backlinks',
        'bltitle': op_name,
        'blfilterredir': 'redirects',
        'bllimit': '50',
        'format': 'json'
    }
    data = api_request(params)
    bl_list = data.get('query', {}).get('backlinks', [])
    valid_aliases = []
    for item in bl_list:
        if item.get('ns') == 0:
            title = item['title'].strip()
            if title and title != op_name and is_valid_alias(title):
                valid_aliases.append(title)
    return op_name, valid_aliases

def fetch_all_operator_aliases(operators):
    """多线程并发全量拉取 PRTS 干员外号与重定向别名"""
    print(f"[*] 正在通过 PRTS 重定向并发拉取 {len(operators)} 位干员的社区外号与别名 ...", flush=True)
    aliases_map = {}
    completed = 0
    total = len(operators)
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_op = {executor.submit(fetch_single_operator_aliases, op): op for op in operators}
        for future in as_completed(future_to_op):
            op_name, aliases = future.result()
            if aliases:
                aliases_map[op_name] = aliases
            completed += 1
            if completed % 50 == 0 or completed == total:
                print(f"  -> 已完成 {completed}/{total} 位干员外号抓取 ...", flush=True)
                
    total_aliases = sum(len(v) for v in aliases_map.values())
    print(f"[*] 全量干员外号同步完成，共抓取到 {len(aliases_map)} 位干员的 {total_aliases} 个有效别名！")
    return aliases_map

def fetch_prts_slangs():
    """抓取 PRTS《明日方舟黑话·梗·成句》专栏条目"""
    print("[*] 正在解析 PRTS《明日方舟黑话·梗·成句》专栏 ...", flush=True)
    params = {
        'action': 'query',
        'list': 'prefixsearch',
        'pssearch': '明日方舟黑话·梗·成句',
        'pslimit': '100',
        'format': 'json'
    }
    data = api_request(params)
    items = data.get('query', {}).get('prefixsearch', [])
    
    slangs = []
    for it in items:
        title = it['title'].replace('明日方舟黑话·梗·成句/', '')
        if '/' in title:
            category, term = title.split('/', 1)
            # 剔除成句过长的句子
            for t in term.split('·'):
                clean_t = t.strip(' *')
                if clean_t and 2 <= len(clean_t) <= 10 and clean_t not in slangs:
                    slangs.append(clean_t)
                    
    print(f"[*] PRTS 黑话专栏解析完成，共提取 {len(slangs)} 个常用黑话。")
    return slangs

def get_shenqi_core_slangs():
    """神奇直播特有的源码/算法级黑话"""
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
        ]
    }

def main():
    print("=" * 60)
    print("明日方舟机制库 - PRTS Wiki 实体、外号与术语全量同步")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 抓取干员列表
    raw_operators = fetch_category_members("干员")
    clean_operators = set()
    for op in raw_operators:
        clean_operators.add(op)
        base_name = re.sub(r'\(.*?\)', '', op).strip()
        if base_name:
            clean_operators.add(base_name)
    operators_list = sorted(list(clean_operators))
    
    # 2. 并发抓取 PRTS 官方外号与重定向
    operator_aliases = fetch_all_operator_aliases(operators_list)
    
    # 3. 抓取敌人列表
    raw_enemies = fetch_category_members("敌人")
    clean_enemies = set()
    for en in raw_enemies:
        clean_en = en.strip('“”"\' ')
        clean_enemies.add(clean_en)
        base_en = re.sub(r'\(.*?\)', '', clean_en).strip()
        if base_en:
            clean_enemies.add(base_en)
    enemies_list = sorted(list(clean_enemies))
    
    # 4. 抓取装置列表
    raw_devices = fetch_category_members("装置")
    devices_list = sorted(list(set([d.strip('“”"\' ') for d in raw_devices])))
    
    # 5. 解析《术语释义》官方战斗术语
    status_terms = parse_terms_glossary()
    
    # 6. 解析核心机制专题页面
    mechanic_terms = parse_mechanic_pages()
    
    # 7. 解析 PRTS 黑话·梗·成句
    prts_slangs = fetch_prts_slangs()
    
    # 8. 整合神奇直播源码/算法级黑话
    shenqi_slangs = get_shenqi_core_slangs()
    
    # 构建输出实体库
    entities_db = {
        "metadata": {
            "source": "PRTS Wiki (prts.wiki)",
            "updated_at": datetime.now().isoformat(),
            "counts": {
                "operators": len(operators_list),
                "operator_with_aliases": len(operator_aliases),
                "total_aliases": sum(len(v) for v in operator_aliases.values()),
                "enemies": len(enemies_list),
                "devices": len(devices_list),
                "status_terms": len(status_terms),
                "mechanic_terms": len(mechanic_terms),
                "prts_slangs": len(prts_slangs),
                "shenqi_slangs": len(shenqi_slangs["pathfinding_and_algorithms"]) + len(shenqi_slangs["combat_and_frame_timing"])
            }
        },
        "operators": operators_list,
        "operator_aliases": operator_aliases,
        "enemies": enemies_list,
        "devices": devices_list,
        "status_terms": status_terms,
        "mechanic_terms": mechanic_terms,
        "prts_slangs": prts_slangs,
        "shenqi_slangs": shenqi_slangs
    }
    
    output_path = os.path.join(os.path.dirname(__file__), "prts_entities.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entities_db, f, ensure_ascii=False, indent=2)
        
    print("=" * 60)
    print(f"全量同步完成！数据已持久化至: {output_path}")
    print(f"  - 全量干员数:       {len(operators_list)}")
    print(f"  - 收录外号干员数:   {len(operator_aliases)}")
    print(f"  - PRTS社区外号总数: {sum(len(v) for v in operator_aliases.values())}")
    print(f"  - 全量敌人数:       {len(enemies_list)}")
    print(f"  - 地图装置数:       {len(devices_list)}")
    print(f"  - 官方状态术语:     {len(status_terms)}")
    print(f"  - 机制专题词汇:     {len(mechanic_terms)}")
    print(f"  - PRTS社区黑话数:   {len(prts_slangs)}")
    print(f"  - 神奇底层黑话数:   {entities_db['metadata']['counts']['shenqi_slangs']}")
    print("=" * 60)
    
    # 打印一些大家最关心的干员外号验证
    sample_ops = ["维什戴尔", "艾雅法拉", "假日威龙陈", "史尔特尔", "玛恩纳", "银灰", "桃金娘", "Mon3tr", "纯烬艾雅法拉"]
    print("【重点干员外号抽样校验】:")
    for op in sample_ops:
        print(f"  • {op}: {operator_aliases.get(op, [])}")
    print("=" * 60)

if __name__ == '__main__':
    main()
