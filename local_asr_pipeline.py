#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local_asr_pipeline.py
---------------------
极轻量本地 ASR & VAD 语音段提取与粗转写 Pipeline：
1. 依赖本地缓存的 FSMN-VAD (1.7MB) 与 SenseVoiceSmall 模型。
2. 纯 CPU 运行，VAD 速度达 70~80x 实时，SenseVoice 速度达 30~50x 实时。
3. 自动检测并截取有效人声段（剔除挂机、静音与纯背景音）。
4. 输出带时间戳的粗逐字稿与人声活跃度（Speech Ratio）统计。
"""

import os
import sys
import time
import argparse
import json
import re
import numpy as np

# 保证标准输出为 UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = r"c:\Users\cheny\Downloads\shenqi"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from entity_corrector import correct_text

try:
    import av
except ImportError:
    print("Error: PyAV (av) is required for audio decoding. Run: pip install av")
    sys.exit(1)

try:
    from funasr import AutoModel
except ImportError:
    print("Error: funasr is required. Run: pip install funasr")
    sys.exit(1)

VAD_MODEL_DIR = os.path.expanduser(
    r"~/.cache/modelscope/models/iic--speech_fsmn_vad_zh-cn-16k-common-pytorch/snapshots/master"
)
SENSEVOICE_MODEL_DIR = os.path.expanduser(
    r"~/.cache/modelscope/models/iic--SenseVoiceSmall/snapshots/master"
)

def sec_to_hms(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:05.2f}"
    else:
        return f"{m:02d}:{s:05.2f}"

def load_audio_segment(m4a_path, start_sec=0, max_dur=None):
    """
    使用 PyAV 高速将 m4a 纯音频解码并重采样为 16kHz 单声道 float32 数组。
    """
    container = av.open(m4a_path)
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    
    skip_samples = int(start_sec * 16000)
    max_samples = int(max_dur * 16000) if max_dur else None
    
    audio_frames = []
    current_idx = 0
    total_loaded = 0
    
    for frame in container.decode(audio=0):
        for r_frame in resampler.resample(frame):
            arr = r_frame.to_ndarray()
            n = arr.shape[1]
            if current_idx + n < skip_samples:
                current_idx += n
                continue
            elif current_idx < skip_samples:
                cut = skip_samples - current_idx
                arr = arr[:, cut:]
                current_idx += cut
                
            audio_frames.append(arr)
            total_loaded += arr.shape[1]
            current_idx += arr.shape[1]
            
            if max_samples and total_loaded >= max_samples:
                break
        if max_samples and total_loaded >= max_samples:
            break
            
    if not audio_frames:
        return np.array([], dtype=np.float32)
        
    pcm16 = np.concatenate(audio_frames, axis=1).squeeze()
    if max_samples:
        pcm16 = pcm16[:max_samples]
        
    wav_float = pcm16.astype(np.float32) / 32768.0
    return wav_float

def clean_sensevoice_text(text: str) -> str:
    """清理 SenseVoiceSmall 的特殊标签，如 <|zh|><|EMO_UNKNOWN|><|Speech|><|withitn|>"""
    cleaned = re.sub(r"<\|.*?\|>", "", text).strip()
    return cleaned

def run_pipeline(audio_file, start_sec=0, duration=None, vad_only=False, output_dir="asr_drafts"):
    if not os.path.exists(audio_file):
        print(f"Error: file not found: {audio_file}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(audio_file))[0]
    
    print("=" * 65)
    print(f"音频文件: {os.path.basename(audio_file)}")
    print(f"截取范围: 从 {start_sec}s 开始, 时长: {duration if duration else '全量'}")
    print("=" * 65)
    
    # 1. 解码音频
    t0 = time.time()
    wav_float = load_audio_segment(audio_file, start_sec=start_sec, max_dur=duration)
    loaded_dur = len(wav_float) / 16000.0
    print(f"音频解码完毕: {loaded_dur:.2f} 秒 (耗时 {time.time() - t0:.2f}s)")
    if len(wav_float) == 0:
        print("未加载到有效音频数据。")
        return
        
    # 2. VAD 端点检测
    print("\n[Step 1/2] 正在执行 FSMN-VAD 端点检测 (剔除空白与背景音)...")
    vad_model = AutoModel(model=VAD_MODEL_DIR, disable_update=True, device="cpu", log_level="ERROR")
    t1 = time.time()
    vad_res = vad_model.generate(input=wav_float)
    vad_time = time.time() - t1
    
    raw_segments = vad_res[0].get('value', [])
    print(f"VAD 检测完成: 耗时 {vad_time:.2f}s (RTF={vad_time/loaded_dur:.4f}, 相当于 {loaded_dur/vad_time:.1f}x 实时速度!)")
    
    # 合并紧邻的语音段（间隔小于 0.8 秒合并）
    merged_segments = []
    total_speech_ms = 0
    for s_ms, e_ms in raw_segments:
        total_speech_ms += (e_ms - s_ms)
        if not merged_segments:
            merged_segments.append([s_ms, e_ms])
        else:
            prev_s, prev_e = merged_segments[-1]
            if s_ms - prev_e < 800: # 800ms 内不停顿视为同一句话
                merged_segments[-1][1] = e_ms
            else:
                merged_segments.append([s_ms, e_ms])
                
    total_speech_sec = total_speech_ms / 1000.0
    speech_ratio = (total_speech_sec / loaded_dur * 100) if loaded_dur > 0 else 0
    print(f"检测到原始人声片段: {len(raw_segments)} 个, 合并后片段: {len(merged_segments)} 个")
    print(f"有效人声总时长: {total_speech_sec:.1f}s / {loaded_dur:.1f}s ({speech_ratio:.1f}% 人声活跃度)")
    
    if vad_only:
        out_json_path = os.path.join(output_dir, f"{basename}_vad.json")
        res_data = {
            "file": basename,
            "total_duration": loaded_dur,
            "speech_duration": total_speech_sec,
            "speech_ratio": f"{speech_ratio:.1f}%",
            "segments": [
                {
                    "start": start_sec + s_ms / 1000.0,
                    "end": start_sec + e_ms / 1000.0,
                    "start_hms": sec_to_hms(start_sec + s_ms / 1000.0),
                    "end_hms": sec_to_hms(start_sec + e_ms / 1000.0),
                    "duration": (e_ms - s_ms) / 1000.0
                }
                for s_ms, e_ms in merged_segments
            ]
        }
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(res_data, f, ensure_ascii=False, indent=2)
        print(f"VAD 结果已保存至: {out_json_path}")
        return
        
    # 3. SenseVoice 粗识别与专有名词消歧
    print("\n[Step 2/2] 正在加载 SenseVoiceSmall 执行粗识别与时间戳转写...")
    t2 = time.time()
    asr_model = AutoModel(
        model=SENSEVOICE_MODEL_DIR,
        disable_update=True,
        device="cpu",
        log_level="ERROR"
    )
    print(f"ASR 模型加载完毕 (耗时 {time.time() - t2:.2f}s)")
    
    transcript_items = []
    t3 = time.time()
    for idx, (s_ms, e_ms) in enumerate(merged_segments, 1):
        s_sample = int(s_ms * 16)
        e_sample = int(e_ms * 16)
        seg_audio = wav_float[s_sample:e_sample]
        if len(seg_audio) < 1600: # 小于 0.1s 忽略
            continue
            
        res = asr_model.generate(input=seg_audio, language="zh", use_itn=True)
        raw_text = res[0].get('text', '') if res else ''
        clean_text = clean_sensevoice_text(raw_text)
        fixed_text = correct_text(clean_text)
        
        abs_start = start_sec + s_ms / 1000.0
        abs_end = start_sec + e_ms / 1000.0
        
        if fixed_text:
            ts_str = sec_to_hms(abs_start)
            transcript_items.append({
                "from": abs_start,
                "to": abs_end,
                "hms": ts_str,
                "text": fixed_text
            })
            print(f"  [{ts_str}] {fixed_text}")
            
    asr_time = time.time() - t3
    print(f"\nASR 转写完成: 耗时 {asr_time:.2f}s (有效人声推理速度: {total_speech_sec / asr_time:.1f}x 实时!)")
    
    # 4. 保存逐字稿与分析报告
    out_txt_path = os.path.join(output_dir, f"{basename}_asr_draft.txt")
    with open(out_txt_path, "w", encoding="utf-8") as f:
        f.write(f"# 本地极轻量 ASR 转写草稿: {basename}\n")
        f.write(f"截取范围: {start_sec}s - {start_sec + loaded_dur:.1f}s | 有效人声活跃度: {speech_ratio:.1f}%\n")
        f.write("=" * 60 + "\n\n")
        for item in transcript_items:
            f.write(f"[{item['hms']}] {item['text']}\n")
            
    print(f"逐字稿草稿已保存至: {out_txt_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="本地极轻量 VAD 人声切片与 SenseVoice 语音转写")
    parser.add_argument("--file", "-f", type=str, default=r"audios\BV1bbWUzcE6v_p1_33254084555.m4a", help="待处理的音频文件路径")
    parser.add_argument("--start", "-s", type=float, default=60.0, help="起始时间偏移 (秒)")
    parser.add_argument("--duration", "-d", type=float, default=180.0, help="处理时长 (秒)，默认试跑 3 分钟")
    parser.add_argument("--vad-only", action="store_true", help="仅执行 VAD 人声端点检测并输出时间戳，不跑 ASR")
    parser.add_argument("--output-dir", "-o", type=str, default="asr_drafts", help="输出文件目录")
    
    args = parser.parse_args()
    
    target_file = args.file
    if not os.path.isabs(target_file):
        target_file = os.path.join(ROOT_DIR, target_file)
        
    run_pipeline(
        audio_file=target_file,
        start_sec=args.start,
        duration=args.duration,
        vad_only=args.vad_only,
        output_dir=os.path.join(ROOT_DIR, args.output_dir)
    )
