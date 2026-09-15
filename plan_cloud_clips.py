# -*- coding: utf-8 -*-
"""
plan_cloud_clips.py — 云端 ASR 音频清洗裁剪清单生成器

输入:
  vad_results/{stem}_vad.json   FSMN-VAD 合并后人声段 (start/end, 秒)
  asr_drafts/{stem}_asr.txt     SenseVoiceSmall 粗识别草稿 (与 VAD 段按下标 1:1)

处理逻辑:
  1. 逐段打分过滤: 丢弃空段/纯标点、≤2字填充、进房TTS(进入直播间)、日语文本段;
     无草稿的低活跃文件仅按段长>=1s过滤。
  2. 相邻保留段间隙 < MERGE_GAP 秒合并成块。
  3. 每块前后各 pad PAD 秒, 裁剪到 [0, duration]。
  4. 块长 > HARD_CUT 秒时硬切, 相邻片重叠 OVERLAP 秒。
  5. 整文件跳过名单 (音效/挂机) 记录在 manifest 中, 不产出切片。

输出:
  cloud_clips/manifest.json   切片清单与统计 (时间轴对回原 m4a t=0)
  cloud_clips/clips.csv       便于人工审查的明细

注意: 本脚本只生成清单, 不触碰音频文件; 切片由 cut_cloud_clips.py 执行。
输出目录 cloud_clips/ 属于实验性草稿层, 严禁混入权威字幕层。
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
VAD_DIR = ROOT / "vad_results"
ASR_DIR = ROOT / "asr_drafts"
OUT_DIR = ROOT / "cloud_clips"

PAD = 0.5          # 每块前后各 pad 的秒数
MERGE_GAP = 2.0    # 相邻保留段间隙小于该值则合并
HARD_CUT = 25.0    # 块长上限, 超过则硬切
OVERLAP = 0.4      # 硬切相邻片重叠
MIN_DUR = 1.0      # 短于该时长的气口段直接丢弃
MIN_CUT = 0.5      # 最终切片最短时长

# 整文件跳过: 非机制讲解内容 (电影/同人小游戏/挂机), 不送云端
SKIP_FILES = {
    "BV1XGiiB2EDS_p1_35160982284",   # 小游戏音效
    "BV1bbWUzcE6v_p1_33254084555",   # 挂机, 人声 0.2%
    "BV1bbWUzcE6v_p2_33254147408",   # 挂机, 人声 1.1%
    "BV14b4k6qEXt_p2_41436122513",   # 看女神异闻录电影, 非方舟机制
    "BV18YrgYxE2U_p1_27723173130",   # 明日矿工同人小游戏
    "BV1iq6GYqEHy_p1_27615429638",   # 明日矿工同人小游戏
    "BV1iq6GYqEHy_p2_27615756838",   # 明日矿工同人小游戏
    "BV1iq6GYqEHy_p3_27615822937",   # 明日矿工同人小游戏
    "BV1iq6GYqEHy_p4_27615823205",   # 明日矿工同人小游戏
}

FILLER_WORDS = {"嗯", "啊", "对", "好", "喂", "呃", "哦", "噢", "欸", "诶", "哎", "哈", "哼", "咦"}

LINE_RE = re.compile(r"^\[(\d+):(\d+)(?::(\d+))?(?:\.\d+)?\]\s*(.*)$")
KANA_RE = re.compile(r"[぀-ヿ]")


def parse_draft(path: Path):
    """解析草稿 txt, 返回 [(start_sec, text), ...]; 头部以 #/BV号 等开头跳过。"""
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        a, b, c, text = m.groups()
        if c is None:
            start = int(a) * 60 + int(b)
        else:
            start = int(a) * 3600 + int(b) * 60 + int(c)
        items.append((start, text))
    return items


def classify(text: str) -> str | None:
    """返回丢弃原因; 返回 None 表示保留。"""
    t = text.strip()
    core = re.sub(r"[\s。.,、,!?~…·\-—]+", "", t)
    if not core:
        return "empty"
    if "进入直播间" in t:
        return "room_tts"
    kana = len(KANA_RE.findall(t))
    if kana > 0 and kana / max(len(core), 1) > 0.5:
        return "japanese"
    if core in FILLER_WORDS:
        return "filler"
    if len(core) <= 2:
        return "short"
    return None


def load_segments(stem: str):
    """返回 (duration, title, [(start, end, drop_reason|None), ...])"""
    vad = json.loads((VAD_DIR / f"{stem}_vad.json").read_text(encoding="utf-8"))
    duration = vad["duration_sec"]
    title = f"{vad.get('title', '')} | {vad.get('part', '')}"
    segs = [(s["start"], s["end"]) for s in vad["segments"]]

    draft_path = ASR_DIR / f"{stem}_asr.txt"
    texts = None
    if draft_path.exists() and draft_path.stat().st_size > 500:
        draft = parse_draft(draft_path)
        if len(draft) == len(segs):
            texts = [t for _, t in draft]
        else:
            # 条数不一致: 按起点时间就近对齐 (txt 为整秒取整)
            texts = [""] * len(segs)
            used = set()
            for ds, dt in draft:
                best, bi = 2.0, -1
                for i, (vs, _ve) in enumerate(segs):
                    if i in used:
                        continue
                    if abs(vs - ds) < best:
                        best, bi = abs(vs - ds), i
                if bi >= 0:
                    texts[bi] = dt
                    used.add(bi)

    out = []
    for (s, e), text in zip(segs, texts if texts is not None else [None] * len(segs)):
        if e - s < MIN_DUR:
            out.append((s, e, "too_short"))
        elif text is None:
            out.append((s, e, None))  # 无草稿, 仅按 VAD 保留
        else:
            out.append((s, e, classify(text)))
    return duration, title, out


def build_clips(duration, tagged):
    """合并 + pad + 硬切, 返回 [(start, end), ...]"""
    kept = [(s, e) for s, e, r in tagged if r is None]
    if not kept:
        return []
    blocks = []
    cs, ce = kept[0]
    for s, e in kept[1:]:
        if s - ce < MERGE_GAP:
            ce = max(ce, e)
        else:
            blocks.append([cs, ce])
            cs, ce = s, e
    blocks.append([cs, ce])

    clips = []
    for s, e in blocks:
        s = max(0.0, s - PAD)
        e = min(duration, e + PAD)
        while e - s > HARD_CUT:
            cut_end = min(s + HARD_CUT, e)
            if cut_end - s >= MIN_CUT:
                clips.append((round(s, 2), round(cut_end, 2)))
            s = cut_end - OVERLAP
        if e - s >= MIN_CUT:
            clips.append((round(s, 2), round(e, 2)))
    return clips


def main():
    OUT_DIR.mkdir(exist_ok=True)
    manifest = {"params": {"pad": PAD, "merge_gap": MERGE_GAP, "hard_cut": HARD_CUT,
                           "overlap": OVERLAP, "min_dur": MIN_DUR},
                "files": []}
    rows = []
    tot = {"audio": 0.0, "kept": 0.0, "clips": 0, "skipped_files": 0}
    drop_totals = {}

    for vad_path in sorted(VAD_DIR.glob("*_vad.json")):
        stem = vad_path.name[:-len("_vad.json")]
        if stem == "vad_summary":
            continue
        duration, title, tagged = load_segments(stem)
        audio_h = duration / 3600
        tot["audio"] += duration

        drops = {}
        for _s, _e, r in tagged:
            if r:
                drops[r] = drops.get(r, 0) + 1
                drop_totals[r] = drop_totals.get(r, 0) + 1

        if stem in SKIP_FILES:
            tot["skipped_files"] += 1
            manifest["files"].append({"stem": stem, "title": title, "status": "skipped",
                                      "reason": "whole-file skip list",
                                      "duration_sec": round(duration, 2), "drops": drops})
            continue

        clips = build_clips(duration, tagged)
        kept_sec = sum(e - s for s, e in clips)
        tot["kept"] += kept_sec
        tot["clips"] += len(clips)

        bvid, pN, cid = stem.rsplit("_", 2)
        clip_files = []
        for s, e in clips:
            fname = f"{stem}_{s:.2f}-{e:.2f}.m4a"
            clip_files.append({"file": fname, "start": s, "end": e,
                               "dur": round(e - s, 2)})
            rows.append([stem, fname, s, e, round(e - s, 2)])

        manifest["files"].append({
            "stem": stem, "bvid": bvid, "title": title, "status": "ok",
            "duration_sec": round(duration, 2),
            "clips_sec": round(kept_sec, 2),
            "keep_ratio": round(kept_sec / duration * 100, 1),
            "n_clips": len(clips), "drops": drops,
            "clips": clip_files,
        })

    manifest["summary"] = {
        "total_audio_sec": round(tot["audio"], 1),
        "total_audio_h": round(tot["audio"] / 3600, 2),
        "total_clips_sec": round(tot["kept"], 1),
        "total_clips_h": round(tot["kept"] / 3600, 2),
        "keep_ratio": round(tot["kept"] / tot["audio"] * 100, 1),
        "n_clips": tot["clips"],
        "skipped_files": tot["skipped_files"],
        "drop_segments_total": drop_totals,
    }

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT_DIR / "clips.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["stem", "clip_file", "start", "end", "dur"])
        w.writerows(rows)

    s = manifest["summary"]
    print(f"音频总时长 {s['total_audio_h']}h -> 切片 {s['total_clips_h']}h "
          f"(保留 {s['keep_ratio']}%), 共 {s['n_clips']} 片, 跳过 {s['skipped_files']} 个文件")
    print("丢弃段统计:", json.dumps(drop_totals, ensure_ascii=False))
    per_file = [(f["stem"], f.get("keep_ratio"), f.get("n_clips"))
                for f in manifest["files"]]
    for stem, ratio, n in per_file:
        print(f"  {stem}: keep={ratio}% clips={n}" if ratio is not None else f"  {stem}: SKIPPED")


if __name__ == "__main__":
    sys.exit(main())
