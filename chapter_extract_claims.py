# -*- coding: utf-8 -*-
"""
chapter_extract_claims.py — 方案2: 章节优先的机制知识卡抽取管线 (准确度优先)

两轮结构:
  Pass1 章节切分: 整场转写(带[HH:MM:SS])一次性交给 grok-4.6,
    输出章节边界+标题+类型(热身闲聊/机制正文/实战验证/答疑/其他),
    程序校验: 时间戳单调递增、覆盖完整、边界吸附到最近文本行、落在稀疏处。
  Pass2 章节内抽取: 每章若 >10min 内部按 600s 窗(60s 重叠)二次切分,
    沿用知识提炼契约抽论断, 卡片附带章节标题/类型/时间轴标记;
    重叠区重复卡按 quote 归一化去重。

产出 (草稿层, knowledge_pilot/, 人工审核后才可发布):
  {stem}.chapters.json          章节大纲
  {stem}.chapter_claims.jsonl   章节知识卡 (含 quote_check)
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pilot_extract_claims as base

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "knowledge_pilot"

SUB_WIN = 600      # 章节内子窗长度(秒)
SUB_OVERLAP = 60   # 子窗重叠
WORKERS = 4

CHAPTER_CONTRACT = """你是直播录播的内容结构分析器。输入是主播"神祇读神奇"(明日方舟底层机制主播)一场直播的完整转写, 每行带 [时:分:秒] 时间戳。

任务: 把整场直播切成语义章节。要求:
1. 按话题切换切分, 每章给出 title(一句话主题)、start、end(秒, 必须对齐到文本中真实出现的某一行的时间戳)、kind、summary(两三句)。
2. kind 只能是: warmup(热身闲聊/调设备) / lecture(机制正文讲解) / combat(实战打图/凹图) / qa(弹幕答疑) / other(其他)。
3. 章节必须首尾相接覆盖全场: 第一章 start=第一行时间, 每章 end=下一章 start, 最后一章 end=最后一行时间。宁多勿漏。
4. 机制推导、实测验证、勘误辟谣是本场最有价值的内容, 切分时要保证一个完整话题不被拦腰截断; 闲聊碎段可以合并成大章。
5. 只输出 JSON, 不要输出其他文字:
{"chapters": [{"title": "...", "start": 秒, "end": 秒, "kind": "...", "summary": "..."}]}"""


def full_text(items):
    return "\n".join(f"[{base.fmt_ts(t)}] {x}" for t, x in items)


def snap(ts, valid, duration):
    """把章节边界吸附到最近的真实行时间戳。"""
    return min(valid, key=lambda v: abs(v - ts)) if valid else min(max(ts, 0), duration)


def load_timeline_flags():
    p = ROOT / "cloud_clips" / "timeline_audit.json"
    if not p.exists():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {f["stem"]: f["timeline"] for f in doc["files"]}


def pass1_chapters(stem, items):
    valid_ts = [t for t, _ in items]
    duration = items[-1][0] if items else 0
    result, usage = base.call_llm(
        CHAPTER_CONTRACT + "\n\n=== 完整转写 ===\n" + full_text(items))
    raw = result.get("chapters", [])
    if not raw:
        raise RuntimeError("章节切分返回空")

    chapters, problems = [], []
    for ch in sorted(raw, key=lambda c: c.get("start", 0)):
        chapters.append({
            "title": str(ch.get("title", ""))[:80],
            "start": snap(int(ch.get("start", 0)), valid_ts, duration),
            "end": snap(int(ch.get("end", 0)), valid_ts, duration),
            "kind": ch.get("kind", "other"),
            "summary": str(ch.get("summary", ""))[:300],
        })
    # 单调与覆盖校验
    for i in range(1, len(chapters)):
        if chapters[i]["start"] < chapters[i - 1]["start"]:
            problems.append(f"非单调: ch{i}")
        if chapters[i]["start"] != chapters[i - 1]["end"]:
            chapters[i]["start"] = chapters[i - 1]["end"]  # 强制首尾相接
        if chapters[i - 1]["end"] <= chapters[i - 1]["start"]:
            problems.append(f"空章: ch{i-1}")
    if chapters and chapters[0]["start"] != valid_ts[0]:
        chapters[0]["start"] = valid_ts[0]
    chapters = [c for c in chapters if c["end"] > c["start"]]
    return chapters, problems, usage


def chapter_subwindows(ch, items):
    """章节内按 SUB_WIN/SUB_OVERLAP 切子窗, 返回 [(start,end,text)]。"""
    core = [it for it in items if ch["start"] <= it[0] < ch["end"]]
    if not core:
        return []
    if ch["end"] - ch["start"] <= SUB_WIN:
        text = "\n".join(f"[{base.fmt_ts(t)}] {x}" for t, x in core)
        return [(ch["start"], ch["end"], text)]
    wins, s = [], ch["start"]
    while s < ch["end"]:
        e = min(s + SUB_WIN, ch["end"])
        part = [it for it in core if s <= it[0] < e]
        if part:
            wins.append((s, e, "\n".join(
                f"[{base.fmt_ts(t)}] {x}" for t, x in part)))
        if e >= ch["end"]:
            break
        s = e - SUB_OVERLAP
    return wins


def norm_key(s):
    return re.sub(r"[\s，。、,.!?~…·\-—\"'“”]+", "", s or "")[:24]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stem", required=True)
    ap.add_argument("--source", choices=["cloud", "official"], required=True)
    ap.add_argument("--chapters-only", action="store_true", help="只跑章节切分")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    items = base.load_items(args.stem, args.source)
    if not items:
        print("无文本"); return 1
    timeline_flags = load_timeline_flags()
    timeline = timeline_flags.get(args.stem,
                                  "timeline_ok" if args.source == "official" else "unknown")

    ch_path = OUT_DIR / f"{args.stem}.chapters.json"
    claims_path = OUT_DIR / f"{args.stem}.chapter_claims.jsonl"

    if ch_path.exists():
        doc = json.loads(ch_path.read_text(encoding="utf-8"))
        chapters, problems = doc["chapters"], doc.get("problems", [])
    else:
        print(f"Pass1 章节切分: {args.stem} [{args.source}] {len(items)} 行", flush=True)
        chapters, problems, u1 = pass1_chapters(args.stem, items)
        doc = {"stem": args.stem, "source": args.source, "timeline": timeline,
               "model": base.MODEL, "problems": problems, "chapters": chapters}
        ch_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {len(chapters)} 章, 边界问题: {problems or '无'}", flush=True)
    for c in chapters:
        print(f"  [{base.fmt_ts(c['start'])}-{base.fmt_ts(c['end'])}] "
              f"{c['kind']:8s} {c['title'][:40]}", flush=True)
    if args.chapters_only:
        return 0

    # Pass2
    done = set()
    if claims_path.exists():
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                done.add((r["chapter"]["start"], r["window"]["start"]))
            except Exception:
                pass

    jobs = []
    for ch in chapters:
        for ws, we, text in chapter_subwindows(ch, items):
            if (ch["start"], ws) in done:
                continue
            ctx = (f"本段属于章节《{ch['title']}》。章节摘要: {ch['summary']}\n"
                   f"章节类型: {ch['kind']}\n\n")
            jobs.append((ch, ws, we, ctx, text))
    print(f"Pass2 抽取: {len(jobs)} 个子窗", flush=True)

    def process(job):
        ch, ws, we, ctx, text = job
        try:
            result, usage = base.call_llm(base.CONTRACT + "\n\n" + ctx +
                                          "=== 转写文本 ===\n" + text)
        except Exception as e:
            return job, None, {"error": str(e)[:150]}
        cards = []
        for card in result.get("claims", []):
            card["window"] = {"start": ws, "end": we}
            card["chapter"] = {"title": ch["title"], "kind": ch["kind"],
                               "start": ch["start"], "end": ch["end"]}
            card["source_id"] = args.stem
            card["track"] = args.source
            card["timeline"] = timeline
            card["status"] = "draft"
            card["quote_check"] = "pass" if base.validate(card, text) else "quote_mismatch"
            cards.append(card)
        return job, cards, result

    n_ok = n_bad = n_dup = 0
    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0}
    seen_keys = set()
    with open(claims_path, "a", encoding="utf-8") as fc:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for job, cards, result in ex.map(process, jobs):
                ch, ws, we, _ctx, _t = job
                if cards is None:
                    print(f"LLM FAIL ch={ch['start']} win={ws}: {result}", flush=True)
                    n_bad += 1
                    continue
                for cc in result.get("_usage", []):
                    pass
                for card in cards:
                    key = (norm_key(card.get("topic", "")),
                           norm_key((card.get("evidence") or [{}])[0].get("quote", "")))
                    if key in seen_keys or any(
                            k[0] == key[0] and k[1] and key[1] and
                            (k[1] in key[1] or key[1] in k[1]) for k in seen_keys):
                        n_dup += 1
                        continue
                    seen_keys.add(key)
                    fc.write(json.dumps(card, ensure_ascii=False) + "\n")
                    fc.flush()
                    if card["quote_check"] == "pass":
                        n_ok += 1
                    else:
                        n_bad += 1
                print(f"ch《{ch['title'][:20]}》win {base.fmt_ts(ws)}: "
                      f"{len(cards)} 卡", flush=True)
    print(f"完成: 通过 {n_ok}, 引用不匹配 {n_bad}, 重叠去重 {n_dup}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
