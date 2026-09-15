# -*- coding: utf-8 -*-
"""
audit_timeline.py — VAD 采样时间轴 vs 原媒体时间轴审计 (草稿层)

背景: 部分源 m4a 的 AAC 帧损坏/稀疏, FSMN-VAD 只跑在可解码样本上,
其 duration_sec 是"采样时长"而非媒体时长, 时间戳越往后偏移越大。
本脚本逐文件对比 ffprobe 媒体时长与 VAD duration_sec,
输出 cloud_clips/timeline_audit.json:
  timeline_ok            diff <= 2s, 云端转写时间戳可信
  timeline_unverified    diff > 2s, 文本可用但时间戳不可直接引用
"""

import glob
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
FFPROBE = str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
              / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
              / "ffmpeg-9.0.1-full_build/bin/ffprobe.exe")
THRESHOLD_SEC = 2.0


def main():
    rows = []
    for vp in sorted(glob.glob(str(ROOT / "vad_results" / "*_vad.json"))):
        stem = os.path.basename(vp)[:-len("_vad.json")]
        if stem == "vad_summary":
            continue
        ap = ROOT / "audios" / f"{stem}.m4a"
        if not ap.exists():
            continue
        vad = json.loads(Path(vp).read_text(encoding="utf-8"))["duration_sec"]
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(ap)],
            capture_output=True, text=True).stdout.strip()
        media = float(out)
        diff = media - vad
        rows.append({
            "stem": stem,
            "media_sec": round(media, 2),
            "vad_sec": round(vad, 2),
            "diff_sec": round(diff, 2),
            "timeline": "timeline_ok" if abs(diff) <= THRESHOLD_SEC else "timeline_unverified",
        })

    bad = [r for r in rows if r["timeline"] != "timeline_ok"]
    doc = {
        "note": "diff>2s 的文件源 m4a 存在 AAC 帧损坏/稀疏, VAD/切片/云端转写的时间戳为采样时间, "
                "不可直接对回 B 站进度条; 文本内容仍可作为候选证据。",
        "threshold_sec": THRESHOLD_SEC,
        "ok_count": len(rows) - len(bad),
        "unverified_count": len(bad),
        "files": rows,
    }
    out = ROOT / "cloud_clips" / "timeline_audit.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ok={doc['ok_count']} unverified={doc['unverified_count']}")
    for r in bad:
        print(f"  {r['stem']}: diff={r['diff_sec']}s")


if __name__ == "__main__":
    main()
