# -*- coding: utf-8 -*-
"""
transcribe_cloud.py — 调用阿里云百炼 qwen3-asr-flash 批量转写 cloud_clips/ 切片

- 端点: workspace 专属 compatible-mode (OpenAI 兼容 chat/completions)
- 音频以 data URI base64 内联, system 消息携带方舟机制术语表做热词消歧
- 输出: cloud_clips/asr_cloud/{stem}.jsonl  (草稿层, 严禁混入权威层)
  每行 {"file","start","end","dur","text","audio_tokens"}
- 断点续跑: 已写入 jsonl 的切片自动跳过; 失败片不落盘, 下次自动重试
"""

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "cloud_clips" / "asr_cloud"

API_KEY = os.environ.get("BAILIAN_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("请设置环境变量 BAILIAN_API_KEY")
BASE = "https://ws-c26m8ajqo4kcuwf8.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3-asr-flash-2026-02-10"

# 本地 ASR 高频同音错词, PRTS 词表未必覆盖, 作为热词补丁
_EXTRA_TERMS = [
    "出伤", "出伤帧", "技力", "计时器", "前摇", "后摇", "判定帧", "费用尺",
    "杰斯顿", "酒神", "黍", "缇缇", "缪尔赛思", "塑心", "抬手", "余震",
    "干员", "帧", "再部署", "锁定",
]


def build_glossary() -> str:
    """从 prts_entities.json 抽取机制课热词, 不塞敌人/装置/关卡名。"""
    data = json.loads((ROOT / "prts_entities.json").read_text(encoding="utf-8"))
    seen, terms = set(), []

    def add(xs):
        for x in xs:
            t = str(x).strip()
            if not t or t in seen or len(t) > 16:
                continue
            seen.add(t)
            terms.append(t)

    for group in data.get("shenqi_slangs", {}).values():
        add(group)

    ops = set(data.get("operators", []))
    mech_keep = re.compile(
        r"仇恨|过滤器|索敌|判定|伤害|部署|阻挡|寻路|升序|降序|选择器|"
        r"弹道|优先级|重量|生命|攻击力|法抗|迷彩|沉睡|眩晕|返费|费用|"
        r"推拉|推与拉|状态机|实例|定点数|浮点数|事件|冷却|转向|网格|"
        r"地块|视野|诱移|诱导|伤判|复用|引擎|职业|阵营|随机|障碍"
    )
    add(t for t in data.get("mechanic_terms", [])
        if t not in ops and mech_keep.search(t) and not re.match(r"^[A-Z0-9]{1,4}-", t))

    status_drop = re.compile(
        r"基建|设施|技能|工作|订单|分类|杂项|小队|事务所|近卫局|学生|"
        r"骑士团|生产线|机器人|料理|天道|自动化|标准化|莱茵科技|红松|"
        r"金属工艺|仿生|独占|加成|叠加|比较|中间产物|术语$|相关$|"
        r"其他$|特殊$|状态$"
    )
    add(t for t in data.get("status_terms", []) if not status_drop.search(t) and len(t) <= 8)

    add(op for op in data.get("operators", [])
        if "卫戍协议" not in op and re.search(r"[\u4e00-\u9fff]", op) and 2 <= len(op) <= 8)

    add(_EXTRA_TERMS)
    return "、".join(terms)


SYSTEM_PROMPT = (
    "这是游戏《明日方舟》底层机制讲解直播的音频，说话人为同一位男主播。"
    "请逐字准确转写为简体中文，保留口语，不要总结或翻译。\n术语表："
    + build_glossary()
)

WORKERS = 8
MAX_RETRY = 6
_lock = threading.Lock()
_done_files = set()
_stats = {"ok": 0, "fail": 0, "audio_tokens": 0}
_fp = None


def transcribe(clip_path: Path, retries=MAX_RETRY):
    b64 = base64.b64encode(clip_path.read_bytes()).decode()
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [
                {"type": "input_audio",
                 "input_audio": {"data": "data:audio/m4a;base64," + b64}}]},
        ],
    }).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                BASE + "/chat/completions", data=body,
                headers={"Authorization": f"Bearer {API_KEY}",
                         "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=180))
            text = r["choices"][0]["message"]["content"].strip()
            usage = r.get("usage", {}).get("prompt_tokens_details", {}) or {}
            return text, usage.get("audio_tokens", 0)
        except urllib.error.HTTPError as e:
            code = e.code
            detail = e.read().decode(errors="replace")[:150]
            if code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 60))
                continue
            raise RuntimeError(f"HTTP {code}: {detail}")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 60))
                continue
            raise RuntimeError(str(e)[:150])
    raise RuntimeError("unreachable")


def worker(job):
    stem, c, clip_path, out_path = job
    try:
        text, atok = transcribe(clip_path)
        rec = {"file": c["file"], "start": c["start"], "end": c["end"],
               "dur": c["dur"], "text": text, "audio_tokens": atok}
        with _lock:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            _stats["ok"] += 1
            _stats["audio_tokens"] += atok
            n = _stats["ok"]
            if n % 200 == 0:
                print(f"progress ok={n} fail={_stats['fail']} "
                      f"audio_tokens={_stats['audio_tokens']}", flush=True)
        return None
    except Exception as e:
        with _lock:
            _stats["fail"] += 1
        return (clip_path.name, str(e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", help="只转写一个切片路径, 打印结果不落盘")
    parser.add_argument("--limit", type=int, default=0, help="最多转写 N 片后停止")
    args = parser.parse_args()

    if args.test:
        p = Path(args.test)
        print(f"glossary_chars={len(SYSTEM_PROMPT)} model={MODEL}", flush=True)
        text, atok = transcribe(p)
        print(text)
        print(f"audio_tokens={atok}", flush=True)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "cloud_clips" / "manifest.json").read_text(encoding="utf-8"))
    jobs = []
    for f in manifest["files"]:
        if f["status"] != "ok":
            continue
        stem = f["stem"]
        out_path = OUT_DIR / f"{stem}.jsonl"
        done = set()
        if out_path.exists():
            for line in out_path.read_text(encoding="utf-8").splitlines():
                try:
                    done.add(json.loads(line)["file"])
                except Exception:
                    pass
        for c in f["clips"]:
            if c["file"] in done:
                continue
            clip_path = ROOT / "cloud_clips" / stem / c["file"]
            if clip_path.exists():
                jobs.append((stem, c, clip_path, out_path))

    if args.limit:
        jobs = jobs[:args.limit]
    print(f"待转写 {len(jobs)} 片 workers={WORKERS} glossary_chars={len(SYSTEM_PROMPT)}", flush=True)
    errors = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for err in ex.map(worker, jobs):
            if err:
                errors.append(err)
                print(f"ERROR {err[0]}: {err[1]}", flush=True)
    print(f"完成 ok={_stats['ok']} fail={_stats['fail']} "
          f"audio_tokens={_stats['audio_tokens']}", flush=True)
    if errors:
        (OUT_DIR / "errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
