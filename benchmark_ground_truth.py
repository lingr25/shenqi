#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_ground_truth.py
-------------------------
严格对比本地 ASR (SenseVoiceSmall + FSMN-VAD) 与 B站官方 AI 字幕 Ground Truth。
测试样本：
1. BV1qReG6XE6W_p4 (全量 284s, 杂谈/弹幕互动)
2. BV1dVcbzFEdd_p2 (前 300s, 核心机制课：辟谣仇恨与三帧索敌)
"""

import os
import sys
import time
import re
import json
import av
import numpy as np

# Ensure stdout utf-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = r"c:\Users\cheny\Downloads\shenqi"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from entity_corrector import correct_text

def clean_sensevoice_text(text: str) -> str:
    return re.sub(r"<\|.*?\|>", "", text).strip()

def load_audio(m4a_path, max_sec=None):
    container = av.open(m4a_path)
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    frames = []
    max_samples = int(max_sec * 16000) if max_sec else None
    total_samples = 0
    for frame in container.decode(audio=0):
        for r_frame in resampler.resample(frame):
            arr = r_frame.to_ndarray()
            frames.append(arr)
            total_samples += arr.shape[1]
            if max_samples and total_samples >= max_samples:
                break
        if max_samples and total_samples >= max_samples:
            break
    if not frames:
        return np.array([], dtype=np.float32)
    pcm16 = np.concatenate(frames, axis=1).squeeze()
    if max_samples:
        pcm16 = pcm16[:max_samples]
    return pcm16.astype(np.float32) / 32768.0

def compute_levenshtein_cer(ref: str, hyp: str):
    """
    计算字符级 Levenshtein 距离、S (替换)、D (删除/漏识)、I (插入/冗余)
    ref: 参考文本 (Ground Truth)
    hyp: 识别文本 (ASR)
    """
    # 过滤所有标点和空格，仅保留中文、英文字母、数字
    clean_pat = re.compile(r"[\u4e00-\u9fa5a-zA-Z0-9]")
    r_chars = clean_pat.findall(ref)
    h_chars = clean_pat.findall(hyp)
    
    n = len(r_chars)
    m = len(h_chars)
    
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
        
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if r_chars[i-1].lower() == h_chars[j-1].lower() else 1
            dp[i][j] = min(
                dp[i-1][j] + 1,      # Deletion
                dp[i][j-1] + 1,      # Insertion
                dp[i-1][j-1] + cost  # Substitution
            )
            
    total_dist = dp[n][m]
    cer = (total_dist / n) if n > 0 else 0
    
    # 回溯统计 S, D, I
    i, j = n, m
    s_cnt, d_cnt, i_cnt = 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if r_chars[i-1].lower() == h_chars[j-1].lower() else 1
            if dp[i][j] == dp[i-1][j-1] + cost:
                if cost == 1:
                    s_cnt += 1
                i -= 1
                j -= 1
                continue
        if i > 0 and dp[i][j] == dp[i-1][j] + 1:
            d_cnt += 1
            i -= 1
        else:
            i_cnt += 1
            j -= 1
            
    return {
        "ref_len": n,
        "hyp_len": m,
        "distance": total_dist,
        "cer": cer,
        "substitutions": s_cnt,
        "deletions": d_cnt,
        "insertions": i_cnt,
        "accuracy": max(0, 1 - cer)
    }

def run_benchmark():
    from funasr import AutoModel
    
    VAD_DIR = os.path.expanduser('~/.cache/modelscope/models/iic--speech_fsmn_vad_zh-cn-16k-common-pytorch/snapshots/master')
    ASR_DIR = os.path.expanduser('~/.cache/modelscope/models/iic--SenseVoiceSmall/snapshots/master')
    
    print("[1/4] Loading models...")
    vad_model = AutoModel(model=VAD_DIR, disable_update=True, device="cpu", log_level="ERROR")
    asr_model = AutoModel(model=ASR_DIR, disable_update=True, device="cpu", log_level="ERROR")
    print("Models ready!")
    
    test_cases = [
        {
            "name": "BV1dVcbzFEdd_p2 (核心机制课: 辟谣仇恨与三帧索敌)",
            "audio": "test_bench_BV1dVcbzFEdd_p2.m4a",
            "sub_json": "subtitles/BV1dVcbzFEdd_p2_35992767409.json",
            "max_sec": 300 # 测试前5分钟
        },
        {
            "name": "BV1qReG6XE6W_p4 (散漫杂谈/弹幕互动: 沉迷讲课忘细节)",
            "audio": "test_bench_BV1qReG6XE6W_p4.m4a",
            "sub_json": "subtitles/BV1qReG6XE6W_p4_41898018468.json",
            "max_sec": None # 全量 284秒
        }
    ]
    
    overall_results = []
    
    for case in test_cases:
        print("\n" + "="*70)
        print(f"BENCHMARKING: {case['name']}")
        print("="*70)
        
        # 1. Load Audio
        t_start = time.time()
        wav = load_audio(case['audio'], max_sec=case['max_sec'])
        dur = len(wav) / 16000.0
        print(f"Loaded audio: {dur:.2f}s ({dur/60:.2f} min)")
        
        # 2. VAD
        t0 = time.time()
        vad_res = vad_model.generate(input=wav)
        t_vad = time.time() - t0
        raw_segs = vad_res[0].get('value', [])
        
        # Merge adjacent segments (< 800ms)
        merged = []
        for s_ms, e_ms in raw_segs:
            if not merged:
                merged.append([s_ms, e_ms])
            else:
                if s_ms - merged[-1][1] < 800:
                    merged[-1][1] = max(merged[-1][1], e_ms)
                else:
                    merged.append([s_ms, e_ms])
                    
        total_speech_s = sum((e - s) for s, e in merged) / 1000.0
        print(f"VAD Segments: {len(merged)} | Active Speech: {total_speech_s:.2f}s ({total_speech_s/dur*100:.1f}%) | Time: {t_vad:.2f}s ({dur/t_vad:.1f}x real-time)")
        
        # 3. ASR
        t0 = time.time()
        asr_raw_lines = []
        asr_fixed_lines = []
        for s_ms, e_ms in merged:
            seg_wav = wav[int(s_ms*16):int(e_ms*16)]
            if len(seg_wav) < 1600:
                continue
            res = asr_model.generate(input=seg_wav, language="zh", use_itn=True)
            raw = clean_sensevoice_text(res[0].get('text', ''))
            fixed = correct_text(raw)
            if raw:
                asr_raw_lines.append((s_ms/1000.0, e_ms/1000.0, raw))
                asr_fixed_lines.append((s_ms/1000.0, e_ms/1000.0, fixed))
        t_asr = time.time() - t0
        print(f"ASR Completed: {len(asr_raw_lines)} segments | Time: {t_asr:.2f}s ({dur/t_asr:.1f}x real-time)")
        
        # 4. Load Ground Truth Subtitle
        with open(case['sub_json'], 'r', encoding='utf-8') as f:
            sub_meta = json.load(f)
        sub_body = sub_meta.get('body', [])
        
        if case['max_sec']:
            sub_items = [x for x in sub_body if x.get('to', 0) <= case['max_sec']]
        else:
            sub_items = sub_body
            
        ref_text = "".join(x.get('content', '') for x in sub_items)
        hyp_raw_text = "".join(x[2] for x in asr_raw_lines)
        hyp_fixed_text = "".join(x[2] for x in asr_fixed_lines)
        
        # 5. Evaluate Metrics
        metrics_raw = compute_levenshtein_cer(ref_text, hyp_raw_text)
        metrics_fixed = compute_levenshtein_cer(ref_text, hyp_fixed_text)
        
        print("\n--- Accuracy & CER Metrics ---")
        print(f"Ground Truth Ref Chars: {metrics_raw['ref_len']}")
        print(f"Raw ASR Hyp Chars:      {metrics_raw['hyp_len']}")
        print(f"  Raw CER:              {metrics_raw['cer']*100:.2f}% (Accuracy: {metrics_raw['accuracy']*100:.2f}%)")
        print(f"  Raw Edit Breakdown:   Substitutions={metrics_raw['substitutions']}, Deletions={metrics_raw['deletions']}, Insertions={metrics_raw['insertions']}")
        print(f"  Post-Corrected CER:   {metrics_fixed['cer']*100:.2f}% (Accuracy: {metrics_fixed['accuracy']*100:.2f}%)")
        print(f"  Post-Corrected Edits: Substitutions={metrics_fixed['substitutions']}, Deletions={metrics_fixed['deletions']}, Insertions={metrics_fixed['insertions']}")
        
        # Print Sample Alignments
        print("\n--- Excerpt Comparison (Ground Truth vs Local ASR) ---")
        print("[Ground Truth (First ~150 chars)]:")
        print("  " + ref_text[:150])
        print("[Raw SenseVoice ASR]:")
        print("  " + hyp_raw_text[:150])
        print("[Post-Corrected ASR (entity_corrector)]:")
        print("  " + hyp_fixed_text[:150])
        
        overall_results.append({
            "name": case['name'],
            "duration": dur,
            "raw": metrics_raw,
            "fixed": metrics_fixed,
            "ref_text": ref_text,
            "hyp_raw": hyp_raw_text,
            "hyp_fixed": hyp_fixed_text
        })
        
    with open("benchmark_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(overall_results, f, ensure_ascii=False, indent=2)
    print("\nBenchmark results saved to benchmark_eval_results.json")

if __name__ == "__main__":
    run_benchmark()
