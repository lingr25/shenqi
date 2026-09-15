# -*- coding: utf-8 -*-
"""
cut_cloud_clips.py — 按 cloud_clips/manifest.json 用 ffmpeg 从原 m4a 无损抽段

切片输出到 cloud_clips/{stem}/ 下, 文件名携带原音频绝对时间轴:
  {stem}_{start}-{end}.m4a  (秒, 对回原 m4a t=0, 可对齐 B 站进度条)
采用流拷贝 (-c copy) 不重编码, 配合清单中每块 0.5s pad 可覆盖 AAC 帧对齐误差。
cloud_clips/ 属实验性草稿层, 已被 .gitignore 忽略。
"""

import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
AUD_DIR = ROOT / "audios"
OUT_DIR = ROOT / "cloud_clips"

FFMPEG = shutil.which("ffmpeg") or str(
    Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    / "ffmpeg-9.0.1-full_build/bin/ffmpeg.exe"
)


def cut_one(args):
    src, dst, start, end = args
    if dst.exists() and dst.stat().st_size > 0:
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [FFMPEG, "-nostdin", "-y", "-loglevel", "error",
         "-ss", f"{start:.2f}", "-to", f"{end:.2f}",
         "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return (dst.name, r.stderr.strip()[:200])
    return None


def main():
    manifest = json.loads((OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    jobs = []
    for f in manifest["files"]:
        if f["status"] != "ok":
            continue
        src = AUD_DIR / f"{f['stem']}.m4a"
        if not src.exists():
            print(f"!! 缺音频 {src.name}", flush=True)
            continue
        for c in f["clips"]:
            jobs.append((src, OUT_DIR / f["stem"] / c["file"], c["start"], c["end"]))

    print(f"ffmpeg: {FFMPEG}", flush=True)
    print(f"待切 {len(jobs)} 片", flush=True)
    errors = []
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for err in ex.map(cut_one, jobs):
            done += 1
            if err:
                errors.append(err)
                print(f"ERROR {err[0]}: {err[1]}", flush=True)
            if done % 1000 == 0:
                print(f"progress {done}/{len(jobs)}", flush=True)
    print(f"完成 {done - len(errors)}/{len(jobs)}, 失败 {len(errors)}", flush=True)
    if errors:
        (OUT_DIR / "cut_errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
