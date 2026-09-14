import os
import sys
import json
import time
import glob
import av
import numpy as np
from funasr import AutoModel

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = r"c:\Users\cheny\Downloads\shenqi"
AUDIO_DIR = os.path.join(ROOT_DIR, "audios")
OUT_DIR = os.path.join(ROOT_DIR, "vad_results")
os.makedirs(OUT_DIR, exist_ok=True)

VAD_MODEL_DIR = os.path.expanduser(
    r"~/.cache/modelscope/models/iic--speech_fsmn_vad_zh-cn-16k-common-pytorch/snapshots/master"
)

# Load metadata for title and part mapping
search_file = os.path.join(ROOT_DIR, "all_search_videos.json")
with open(search_file, 'r', encoding='utf-8') as f:
    search_data = json.load(f)
v_map = {v['bvid']: v for v in search_data.get('videos', [])}

inv_file = os.path.join(ROOT_DIR, "subtitle_inventory.json")
with open(inv_file, 'r', encoding='utf-8') as f:
    inv_data = json.load(f)
inv_map = {}
for v in inv_data:
    for p in v.get('pages', []):
        inv_map[(v['bvid'], p['page'])] = p

audio_files = sorted(glob.glob(os.path.join(AUDIO_DIR, "*.m4a")))
print(f"Found {len(audio_files)} audio files in {AUDIO_DIR}")

# Pre-load VAD model
print("Loading FSMN-VAD model...")
t_load = time.time()
vad = AutoModel(model=VAD_MODEL_DIR, disable_update=True, device="cpu", log_level="ERROR")
print(f"VAD model loaded in {time.time() - t_load:.2f}s\n")

def sec_to_hms(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02.0f}"
    else:
        return f"{m:02d}:{s:02.0f}"

results = []
t_all = time.time()

for idx, fpath in enumerate(audio_files, 1):
    fname = os.path.basename(fpath)
    base_stem = os.path.splitext(fname)[0]
    parts = base_stem.split('_')
    bvid = parts[0]
    p_num = int(parts[1].replace('p', '')) if len(parts) > 1 and parts[1].startswith('p') else 1
    cid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    
    v_info = v_map.get(bvid, {})
    p_info = inv_map.get((bvid, p_num), {})
    title = v_info.get('title', bvid)
    part_name = p_info.get('part', f"P{p_num}")
    
    out_json = os.path.join(OUT_DIR, f"{base_stem}_vad.json")
    
    # Check if already processed
    if os.path.exists(out_json):
        try:
            with open(out_json, 'r', encoding='utf-8') as jf:
                cached = json.load(jf)
            if cached.get('status') == 'ok':
                sz_mb = cached.get('speech_sec', 0)
                dur_s = cached.get('duration_sec', 0)
                ratio = cached.get('speech_ratio', 0)
                print(f"[{idx}/{len(audio_files)}] (Cached) {fname} | dur: {sec_to_hms(dur_s)} | speech: {sec_to_hms(sz_mb)} ({ratio:.1f}%) | {title[:20]}")
                results.append(cached)
                continue
        except Exception:
            pass

    t0 = time.time()
    try:
        container = av.open(fpath)
        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
        audio_frames = []
        for frame in container.decode(audio=0):
            for r_frame in resampler.resample(frame):
                audio_frames.append(r_frame.to_ndarray())
                
        if not audio_frames:
            print(f"[{idx}/{len(audio_files)}] ⚠️ Empty audio: {fname}")
            continue
            
        pcm16 = np.concatenate(audio_frames, axis=1).squeeze()
        wav_float = pcm16.astype(np.float32) / 32768.0
        dur_sec = len(wav_float) / 16000.0
        t_dec = time.time() - t0
        
        # Run VAD
        t1 = time.time()
        vad_res = vad.generate(input=wav_float)
        t_vad = time.time() - t1
        
        raw_segs = vad_res[0].get('value', [])
        
        # Merge close segments (< 800ms)
        merged_segs = []
        total_speech_ms = 0
        for s_ms, e_ms in raw_segs:
            total_speech_ms += (e_ms - s_ms)
            if not merged_segs:
                merged_segs.append([s_ms, e_ms])
            else:
                prev_s, prev_e = merged_segs[-1]
                if s_ms - prev_e < 800:
                    merged_segs[-1][1] = e_ms
                else:
                    merged_segs.append([s_ms, e_ms])
                    
        speech_sec = total_speech_ms / 1000.0
        speech_ratio = (speech_sec / dur_sec * 100.0) if dur_sec > 0 else 0.0
        
        item_data = {
            "status": "ok",
            "file": fname,
            "bvid": bvid,
            "page": p_num,
            "cid": cid,
            "title": title,
            "part": part_name,
            "duration_sec": round(dur_sec, 2),
            "speech_sec": round(speech_sec, 2),
            "speech_ratio": round(speech_ratio, 2),
            "raw_segments_count": len(raw_segs),
            "merged_segments_count": len(merged_segs),
            "decode_time_sec": round(t_dec, 2),
            "vad_time_sec": round(t_vad, 2),
            "segments": [
                {
                    "start": round(s_ms / 1000.0, 2),
                    "end": round(e_ms / 1000.0, 2),
                    "dur": round((e_ms - s_ms) / 1000.0, 2)
                }
                for s_ms, e_ms in merged_segs
            ]
        }
        
        with open(out_json, 'w', encoding='utf-8') as jf:
            json.dump(item_data, jf, ensure_ascii=False, indent=2)
            
        results.append(item_data)
        print(f"[{idx}/{len(audio_files)}] ✅ {fname} | dur: {sec_to_hms(dur_sec)} | speech: {sec_to_hms(speech_sec)} ({speech_ratio:.1f}%) | VAD {t_vad:.1f}s | {title[:20]}")
        
    except Exception as e:
        print(f"[{idx}/{len(audio_files)}] ❌ Error on {fname}: {e}")

total_elapsed = time.time() - t_all
total_audio_s = sum(x.get('duration_sec', 0) for x in results)
total_speech_s = sum(x.get('speech_sec', 0) for x in results)
overall_ratio = (total_speech_s / total_audio_s * 100) if total_audio_s > 0 else 0

print("\n" + "=" * 65)
print(f"All {len(results)} files processed in {total_elapsed/60:.1f} minutes!")
print(f"Total audio duration: {total_audio_s/3600:.2f} hours")
print(f"Total active speech duration: {total_speech_s/3600:.2f} hours")
print(f"Overall active speech ratio: {overall_ratio:.1f}%")
print(f"Saved {total_audio_s - total_speech_s:.0f} seconds of wasted silence/idle time!")
print("=" * 65)

# Save summary JSON
with open(os.path.join(OUT_DIR, "vad_summary.json"), 'w', encoding='utf-8') as f:
    json.dump({
        "files_count": len(results),
        "total_audio_hours": round(total_audio_s / 3600, 2),
        "total_speech_hours": round(total_speech_s / 3600, 2),
        "overall_speech_ratio": f"{overall_ratio:.1f}%",
        "results": sorted(results, key=lambda x: x.get('speech_ratio', 0), reverse=True)
    }, f, ensure_ascii=False, indent=2)

# Generate Markdown Report
md = []
md.append("# 神祇读神奇 录播无AI字幕分P：全量 VAD 人声活跃度检测报告\n")
md.append(f"- **总分析音频数**：{len(results)} 个分P")
md.append(f"- **总音频时长**：**{total_audio_s/3600:.2f} 小时**（{total_audio_s:,.0f} 秒）")
md.append(f"- **有效人声总时长**：**{total_speech_s/3600:.2f} 小时**（{total_speech_s:,.0f} 秒）")
md.append(f"- **平均人声活跃度**：**{overall_ratio:.1f}%**（通过 VAD 自动过滤了 **{(total_audio_s - total_speech_s)/3600:.2f} 小时** 的无意义静音、挂机与纯背景音乐！）\n")

md.append("## 1. 优先级分类概览\n")
high_value = [x for x in results if x.get('speech_ratio', 0) >= 15.0 or x.get('speech_sec', 0) >= 600]
medium_value = [x for x in results if 5.0 <= x.get('speech_ratio', 0) < 15.0 and x.get('speech_sec', 0) < 600]
low_value = [x for x in results if x.get('speech_ratio', 0) < 5.0]

md.append(f"- 🔥 **第一梯队·高价值核心录播**（人声占比 $\\ge 15\%$ 或 说话时长 $> 10$ 分钟）：共 **{len(high_value)}** 个分P，包含真正密集的讲课、机制解析与互动，**必须重点进行 ASR 转写**。")
md.append(f"- 🟡 **第二梯队·中等活跃录播**（人声占比 $5\% \\sim 15\%$）：共 **{len(medium_value)}** 个分P，包含少量解说与测试，建议按区间切片转写。")
md.append(f"- ❄️ **第三梯队·低活跃/纯挂机录播**（人声占比 $< 5\%$）：共 **{len(low_value)}** 个分P，主播几乎全程静音刷图/放歌/挂机，无需转写，节省海量算力。\n")

md.append("## 2. 全量 39 个分P人声活跃度排行榜（从高到低）\n")
md.append("| 排名 | 梯队 | BV号 | 视频标题 | 分P | 总时长 | 有效人声时长 | 人声占比 | 语音片段数 | 建议动作 |")
md.append("| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |")

sorted_results = sorted(results, key=lambda x: (x.get('speech_ratio', 0) >= 15.0, x.get('speech_sec', 0)), reverse=True)

for r_idx, item in enumerate(sorted_results, 1):
    s_rat = item.get('speech_ratio', 0)
    s_sec = item.get('speech_sec', 0)
    t_sec = item.get('duration_sec', 0)
    
    if s_rat >= 15.0 or s_sec >= 600:
        tier = "🔥 核心"
        action = "✅ 重点优先转写"
    elif s_rat >= 5.0:
        tier = "🟡 中等"
        action = "🔍 按需切片转写"
    else:
        tier = "❄️ 挂机"
        action = "⏭️ 建议跳过"
        
    md.append(
        f"| {r_idx} | {tier} | [`{item['bvid']}`](https://www.bilibili.com/video/{item['bvid']}) "
        f"| {item['title'][:22]} | P{item['page']} | {sec_to_hms(t_sec)} | {sec_to_hms(s_sec)} | {s_rat:.1f}% "
        f"| {item['merged_segments_count']} | {action} |"
    )

report_file = os.path.join(OUT_DIR, "vad_report.md")
with open(report_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(md))

print(f"\nMarkdown report generated at: {report_file}")
