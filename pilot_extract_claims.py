# -*- coding: utf-8 -*-
"""
pilot_extract_claims.py — M1 试点: 从转写文本抽取原子机制知识卡

按约 4 分钟窗口切分, 调用 grok-4.6 (aitreez) 按"知识提炼提示词契约"抽取:
  - 只从给定窗口文本抽取, 不用训练知识补全
  - 区分 提问/假设/推导/实测/结论/勘误
  - 每条论断必须绑定窗口内原文引用与时间范围, 缺失填 unknown
  - 数字/单位/否定/条件原样保留, 不规范化改写

输入来源:
  --source cloud    cloud_clips/asr_cloud/{stem}.jsonl (云端ASR, 草稿层)
  --source official transcripts_txt/{stem}.txt         (B站官方字幕逐字稿, 权威层)

输出 (草稿层, 需人工审核后才可发布):
  knowledge_pilot/{stem}.claims.jsonl   每窗口一张草稿卡
  knowledge_pilot/{stem}.windows.jsonl  窗口原文快照(供审核对照)
"""

import argparse
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from grok_client import LLM_BASE, LLM_KEY, MODEL, call_llm

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "knowledge_pilot"
WINDOW_SEC = 240
WORKERS = 4

CONTRACT = """你是《明日方舟》底层机制知识库的信息抽取器。输入是主播"神祇读神奇"直播录播的一段转写文本(带秒级时间戳)。

契约(必须严格遵守):
1. 只从给定文本中抽取论断, 禁止用你自己的明日方舟知识补全、纠正或扩写。
2. 区分论断类型 claim_type: question(提问) / hypothesis(假设猜测) / derivation(推导过程) / observation(实测观察) / conclusion(定论) / correction(勘误撤回)。主播说"我猜""应该是""没测过"等必须如实标注, 不得升级为结论。
3. 每条论断必须绑定 evidence: 原文逐字引用 quote 及该引用大致的起止秒数 [start, end]。引用必须是输入文本中真实存在的连续子串。
4. 数字、单位(帧/秒/百分比)、否定词、条件、对象原样保留; 缺失的信息填 "unknown"。
5. 闲聊、操作过程、纯游戏实况不报卡; 没有机制知识的窗口返回空 claims。
6. 参数必须逐字来自原文 source_span。

输出严格 JSON(不要输出其他文字):
{"window_topic": "本窗口主题, 一句话",
 "claims": [{"topic": "...", "category": "机制类别(如 帧时序/索敌/寻路/伤害结算/位移/状态效果/技能特例)",
   "entities": ["..."], "context_question": "该论断回答什么问题",
   "core_conclusions": [{"conclusion": "...", "claim_type": "..."}],
   "underlying_parameters": [{"name": "...", "value": "...", "unit": "...", "source_span": "..."}],
   "summary_takeaway": "一句话总结",
   "evidence": [{"start": 秒, "end": 秒, "quote": "原文引用"}]}]}"""


def load_items(stem: str, source: str):
    """返回 [(start_sec, text)] 按时间排序。"""
    if source == "cloud":
        items = []
        for line in (ROOT / "cloud_clips" / "asr_cloud" / f"{stem}.jsonl").read_text(
                encoding="utf-8").splitlines():
            r = json.loads(line)
            items.append((r["start"], r["text"]))
        return sorted(items)
    items = []
    for line in (ROOT / "transcripts_txt" / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\[(\d+):(\d+)(?::(\d+))?\]\s*(.*)$", line.strip())
        if not m:
            continue
        a, b, c, t = m.groups()
        if c is None:
            items.append((int(a) * 60 + int(b), t))
        else:
            items.append((int(a) * 3600 + int(b) * 60 + int(c), t))
    return items


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec//3600:02d}:{sec%3600//60:02d}:{sec%60:02d}"


def make_windows(items):
    if not items:
        return []
    end_t = items[-1][0]
    windows = []
    w_start = 0
    while w_start <= end_t:
        w_end = w_start + WINDOW_SEC
        core = [it for it in items if w_start <= it[0] < w_end]
        if core:
            text = "\n".join(f"[{fmt_ts(t)}] {x}" for t, x in core)
            windows.append({"start": w_start, "end": w_end, "text": text})
        w_start = w_end
    return windows


def _norm(s: str) -> str:
    return re.sub(r"[\s，。、,.!?~…·\-—\"'“”]+", "", s or "")


_TS_PREFIX = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")


def _flatten(win_text: str) -> str:
    """去掉行首时间戳与换行, 允许引用跨字幕条。"""
    return _TS_PREFIX.sub("", win_text or "").replace("\n", "")


def validate(card, win_text):
    """程序校验: 引用必须能在窗口原文中找到 (允许标点/空白差异与跨行)。"""
    flat = _flatten(win_text)
    nt = _norm(flat)
    ok = True
    for ev in card.get("evidence", []):
        q = ev.get("quote", "")
        if not q or (_norm(q) not in nt and q not in flat and q not in win_text):
            ok = False
    for p in card.get("underlying_parameters", []):
        s = p.get("source_span", "")
        if not s or (_norm(s) not in nt and s not in flat and s not in win_text):
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stem", required=True)
    ap.add_argument("--source", choices=["cloud", "official"], required=True)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个窗口(试跑)")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    items = load_items(args.stem, args.source)
    windows = make_windows(items)
    if args.limit:
        windows = windows[:args.limit]
    print(f"{args.stem} [{args.source}] {len(items)} 条文本, {len(windows)} 个窗口", flush=True)

    claims_path = OUT_DIR / f"{args.stem}.claims.jsonl"
    windows_path = OUT_DIR / f"{args.stem}.windows.jsonl"
    done_windows = set()
    if claims_path.exists():
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            try:
                done_windows.add(json.loads(line)["window"]["start"])
            except Exception:
                pass

    n_ok = n_empty = n_bad = 0
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def process(w):
        try:
            result, usage = call_llm(CONTRACT + "\n\n=== 转写文本 ===\n" + w["text"])
        except Exception as e:
            print(f"LLM FAIL win={w['start']}: {e}", flush=True)
            return w, [], {"llm_fail": True}, {}
        cards = []
        for card in result.get("claims", []):
            card["window"] = {"start": w["start"], "end": w["end"]}
            card["source_id"] = args.stem
            card["track"] = args.source
            card["status"] = "draft"
            card["quote_check"] = "pass" if validate(card, w["text"]) else "quote_mismatch"
            cards.append(card)
        return w, cards, result, usage

    todo = [w for w in windows if w["start"] not in done_windows]
    print(f"待处理 {len(todo)} 窗口 model={MODEL} base={LLM_BASE}", flush=True)
    with open(claims_path, "a", encoding="utf-8") as fc, \
         open(windows_path, "a", encoding="utf-8") as fw:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for w, cards, result, usage in ex.map(process, todo):
                fw.write(json.dumps(
                    {"stem": args.stem, "source": args.source, **w},
                    ensure_ascii=False) + "\n")
                fw.flush()
                if result.get("llm_fail"):
                    n_bad += 1
                    continue
                for k in total_usage:
                    total_usage[k] += usage.get(k, 0)
                if not cards:
                    n_empty += 1
                    continue
                for card in cards:
                    fc.write(json.dumps(card, ensure_ascii=False) + "\n")
                    fc.flush()
                    if card["quote_check"] == "pass":
                        n_ok += 1
                    else:
                        n_bad += 1
                print(f"win {fmt_ts(w['start'])}-{fmt_ts(w['end'])}: "
                      f"{result.get('window_topic','')[:40]} | {len(cards)} 卡", flush=True)

    print(f"完成: 通过校验 {n_ok} 卡, 引用不匹配 {n_bad}, 空窗口 {n_empty}", flush=True)
    print(f"token 用量: {total_usage}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
