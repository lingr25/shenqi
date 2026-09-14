import os
import sys
import json
import time
import re
import av
import numpy as np
from funasr import AutoModel

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = r"c:\Users\cheny\Downloads\shenqi"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from entity_corrector import correct_text

AUDIO_DIR = os.path.join(ROOT_DIR, "audios")
VAD_DIR = os.path.join(ROOT_DIR, "vad_results")
OUT_TXT_DIR = os.path.join(ROOT_DIR, "asr_drafts")
os.makedirs(OUT_TXT_DIR, exist_ok=True)

SENSEVOICE_DIR = os.path.expanduser(
    r"~/.cache/modelscope/models/iic--SenseVoiceSmall/snapshots/master"
)

def sec_to_hms(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"

def clean_sensevoice_text(text: str) -> str:
    cleaned = re.sub(r"<\|.*?\|>", "", text).strip()
    return cleaned

def load_full_audio(m4a_path):
    container = av.open(m4a_path)
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    frames = []
    for frame in container.decode(audio=0):
        for r_frame in resampler.resample(frame):
            frames.append(r_frame.to_ndarray())
    if not frames:
        return np.array([], dtype=np.float32)
    pcm16 = np.concatenate(frames, axis=1).squeeze()
    return pcm16.astype(np.float32) / 32768.0

def transcribe_file(vad_json_path, asr_model):
    with open(vad_json_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
        
    fname = meta['file']
    bvid = meta['bvid']
    page = meta['page']
    cid = meta['cid']
    title = meta['title']
    part = meta['part']
    segs = meta['segments']
    
    out_txt_file = os.path.join(OUT_TXT_DIR, f"{bvid}_p{page}_{cid}_asr.txt")
    if os.path.exists(out_txt_file) and os.path.getsize(out_txt_file) > 500:
        print(f"Skipping already transcribed: {os.path.basename(out_txt_file)}")
        return
        
    audio_path = os.path.join(AUDIO_DIR, fname)
    if not os.path.exists(audio_path):
        print(f"Audio file not found: {audio_path}")
        return
        
    print(f"\nTranscribing {fname}: {title} (P{page} - {part})")
    print(f"Segments to transcribe: {len(segs)}, Speech duration: {meta['speech_sec']}s")
    
    t0 = time.time()
    wav_float = load_full_audio(audio_path)
    if len(wav_float) == 0:
        return
    print(f"Audio decoded in {time.time() - t0:.2f}s")
    
    t_asr_start = time.time()
    transcript_lines = []
    
    # Process segments in small chunks or individually
    for idx, seg in enumerate(segs, 1):
        s_sec = seg['start']
        e_sec = seg['end']
        s_sample = int(s_sec * 16000)
        e_sample = int(e_sec * 16000)
        chunk = wav_float[s_sample:e_sample]
        if len(chunk) < 1600: # < 0.1s
            continue
            
        res = asr_model.generate(input=chunk, language="zh", use_itn=True)
        raw_text = res[0].get('text', '') if res else ''
        clean = clean_sensevoice_text(raw_text)
        fixed = correct_text(clean)
        
        if fixed:
            ts_str = sec_to_hms(s_sec)
            line = f"[{ts_str}] {fixed}"
            transcript_lines.append(line)
            if idx % 50 == 0 or idx == len(segs):
                pct = idx / len(segs) * 100
                print(f"  [{pct:4.1f}%] [{ts_str}] {fixed[:35]}...")
                
    dt = time.time() - t_asr_start
    print(f"Transcribed {len(transcript_lines)} speech blocks in {dt:.1f}s ({meta['speech_sec'] / dt:.1f}x real-time)")
    
    header = [
        f"# {title}",
        f"BV号: {bvid} | 分P: P{page} - {part} | CID: {cid}",
        f"转写引擎: SenseVoiceSmall (本地CPU) + FSMN-VAD 人声切片",
        f"有效人声时长: {meta['speech_sec']}秒 | 总分P时长: {meta['duration_sec']}秒",
        "=" * 60,
        ""
    ]
    with open(out_txt_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(header + transcript_lines))
    print(f"Saved: {out_txt_file} ({len(transcript_lines)} lines)")

def main():
    with open(os.path.join(VAD_DIR, "vad_summary.json"), 'r', encoding='utf-8') as f:
        summary = json.load(f)
        
    items = summary['results']
    # Filter high value files (speech_ratio >= 15.0 or speech_sec >= 600)
    targets = [x for x in items if x.get('speech_ratio', 0) >= 15.0 or x.get('speech_sec', 0) >= 600]
    print(f"Found {len(targets)} high-value targets for ASR transcription.")
    
    print("\nLoading SenseVoiceSmall model...")
    t_load = time.time()
    asr = AutoModel(model=SENSEVOICE_DIR, disable_update=True, device="cpu", log_level="ERROR")
    print(f"Loaded in {time.time() - t_load:.2f}s")
    
    for idx, target in enumerate(targets, 1):
        bvid = target['bvid']
        page = target['page']
        cid = target['cid']
        vad_file = os.path.join(VAD_DIR, f"{bvid}_p{page}_{cid}_vad.json")
        if os.path.exists(vad_file):
            print(f"\n[{idx}/{len(targets)}] Progressing target...")
            transcribe_file(vad_file, asr)

if __name__ == '__main__':
    main()
