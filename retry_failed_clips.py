# -*- coding: utf-8 -*-
"""
retry_failed_clips.py — 修复并补跑 transcribe_cloud.py 的失败片

HTTP 400 (audio format illegal): 低码率录制的流拷贝切片云端拒收,
  用 ffmpeg 重编码为 16kHz mono wav 后以 data:audio/wav 重试。
HTTP 429 (限流): 直接按原 m4a 重试。
成功后按 stem 追加写入对应 jsonl, 全部收齐后删除 errors.json。
"""

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import transcribe_cloud as tc

ROOT = Path(__file__).parent
FFMPEG = Path(tc.FFMPEG) if hasattr(tc, "FFMPEG") else None
FFMPEG = str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
             / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
             / "ffmpeg-9.0.1-full_build/bin/ffmpeg.exe")


def transcribe_raw(raw: bytes, mime: str, fmt: str, retries=6):
    b64 = base64.b64encode(raw).decode()
    body = json.dumps({
        "model": tc.MODEL,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": tc.SYSTEM_PROMPT}]},
            {"role": "user", "content": [
                {"type": "input_audio",
                 "input_audio": {"data": f"data:{mime};base64,{b64}"}}]},
        ],
    }).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                tc.BASE + "/chat/completions", data=body,
                headers={"Authorization": f"Bearer {tc.API_KEY}",
                         "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=180))
            return r["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            code, detail = e.code, e.read().decode(errors="replace")[:150]
            if code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 60))
                continue
            raise RuntimeError(f"HTTP {code}: {detail}")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 60))
                continue
            raise RuntimeError(str(e)[:150])


def to_wav16k(clip: Path) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
        tmp = t.name
    try:
        subprocess.run([FFMPEG, "-nostdin", "-y", "-loglevel", "error",
                        "-i", str(clip), "-ar", "16000", "-ac", "1", tmp],
                       check=True, capture_output=True)
        return Path(tmp).read_bytes()
    finally:
        Path(tmp).unlink(missing_ok=True)


def main():
    errors = json.loads((tc.OUT_DIR / "errors.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "cloud_clips" / "manifest.json").read_text(encoding="utf-8"))
    clip_meta = {}
    for f in manifest["files"]:
        if f["status"] != "ok":
            continue
        for c in f["clips"]:
            clip_meta[c["file"]] = (f["stem"], c)

    ok, fail = 0, []
    for i, (name, err) in enumerate(errors):
        stem, c = clip_meta[name]
        clip = ROOT / "cloud_clips" / stem / name
        try:
            if err.startswith("HTTP 400"):
                text = transcribe_raw(to_wav16k(clip), "audio/wav", "wav")
            else:
                text = transcribe_raw(clip.read_bytes(), "audio/m4a", "m4a")
            rec = {"file": c["file"], "start": c["start"], "end": c["end"],
                   "dur": c["dur"], "text": text}
            with open(tc.OUT_DIR / f"{stem}.jsonl", "a", encoding="utf-8") as fp:
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ok += 1
        except Exception as e:
            fail.append((name, str(e)))
            print(f"STILL FAIL {name}: {e}", flush=True)
        if (i + 1) % 20 == 0:
            print(f"retry progress {i+1}/{len(errors)} ok={ok}", flush=True)

    print(f"补跑完成 ok={ok} fail={len(fail)}", flush=True)
    if fail:
        (tc.OUT_DIR / "errors.json").write_text(
            json.dumps(fail, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    (tc.OUT_DIR / "errors.json").unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
