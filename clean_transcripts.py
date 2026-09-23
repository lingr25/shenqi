#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_transcripts.py
--------------------
执行字幕清洗与逐字稿重构 Pipeline：
1. 读取 subtitles/ 原始 JSON
2. 调用 entity_corrector 进行专有名词消歧与纠错
3. 生成规范化的 cleaned_subtitles/ JSON
4. 生成带 [MM:SS] 或 [HH:MM:SS] 时间戳的自然断句逐字稿至 transcripts_txt/
"""

import os
import sys
import json
from glob import glob
from entity_corrector import clean_subtitle_items, build_natural_transcript

# 保证标准输出为 UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SUBTITLES_DIR = os.path.join(ROOT_DIR, "subtitles")
CLEANED_DIR = os.path.join(ROOT_DIR, "cleaned_subtitles")
TRANSCRIPTS_DIR = os.path.join(ROOT_DIR, "transcripts_txt")

os.makedirs(CLEANED_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

# 针对特定重点录播的章节标注（提升逐字稿知识库可读性）
CHAPTER_MARKERS = {
    "BV1MimABGEjs_p1_34575026662": [
        (0.0, "【热身与游戏杂谈】"),
        (232.0, "【核心机制正文：明日方舟底层寻路算法 & 平整化（Straightening）推演】"),
        (1596.0, "【机制答疑与勘误：装置充电部署顺序误判原因（娜斯提天赋同帧触发）】"),
        (1820.0, "【机制答疑与实机验证：飞行兵入水坑坑杀判定改动机制】"),
        (2316.0, "【专栏草稿编写与绘图】"),
        (4156.0, "【主播杂谈：“神祇读神奇”ID来历与汉字听写大赛典故】"),
        (5060.0, "【专栏校对与发布完成】")
    ]
}

def clean_file(raw_json_path):
    filename = os.path.basename(raw_json_path)
    base_id = os.path.splitext(filename)[0]
    
    with open(raw_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    bvid = data.get("bvid", "")
    title = data.get("title", "")
    page = data.get("page", 1)
    part = data.get("part", "")
    raw_body = data.get("body", [])
    
    # 1. 实体纠错与清洗
    cleaned_body = clean_subtitle_items(raw_body, base_id)
    
    # 2. 保存清洗后的结构化 JSON
    cleaned_data = {
        "bvid": bvid,
        "title": title,
        "page": page,
        "part": part,
        "body": cleaned_body
    }
    cleaned_json_path = os.path.join(CLEANED_DIR, filename)
    with open(cleaned_json_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        
    # 3. 生成自然断句逐字稿
    transcript_lines = build_natural_transcript(cleaned_body, file_tag=base_id)
    
    # 检查是否有章节标记注入
    final_lines = []
    markers = CHAPTER_MARKERS.get(base_id, [])
    m_idx = 0
    
    for line in transcript_lines:
        # 解析时间戳秒数
        time_part = line.split("]")[0].strip("[")
        parts = [int(p) for p in time_part.split(":")]
        if len(parts) == 2:
            sec = parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            sec = 0
            
        while m_idx < len(markers) and sec >= markers[m_idx][0]:
            final_lines.append("")
            final_lines.append(f"--- {markers[m_idx][1]} ---")
            final_lines.append("")
            m_idx += 1
            
        final_lines.append(line)
        
    # 补充头部元信息
    header = [
        f"# {title}",
        f"BV号: {bvid} | 分P: P{page} - {part}",
        f"总字幕条数: {len(raw_body)}",
        "=" * 50,
        ""
    ]
    txt_content = "\n".join(header + final_lines)
    txt_path = os.path.join(TRANSCRIPTS_DIR, f"{base_id}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content)
        
    return len(raw_body), len(cleaned_body), len(transcript_lines)

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    
    if target:
        if not os.path.isabs(target):
            if not os.path.exists(target):
                target = os.path.join(SUBTITLES_DIR, target)
        files = [target]
    else:
        files = sorted(glob(os.path.join(SUBTITLES_DIR, "*.json")))
        
    print(f"[*] 开始执行字幕清洗 Pipeline，目标文件数: {len(files)}")
    for i, fpath in enumerate(files, 1):
        fname = os.path.basename(fpath)
        try:
            raw_c, clean_c, lines_c = clean_file(fpath)
            print(f"[{i}/{len(files)}] ✅ {fname}: 原始 {raw_c} 条 -> 清洗 {clean_c} 条 -> 逐字稿 {lines_c} 行")
        except Exception as e:
            print(f"[{i}/{len(files)}] ❌ {fname} 失败: {e}", file=sys.stderr)
            
    print("[*] 清洗 Pipeline 全部完成！")

if __name__ == '__main__':
    main()
