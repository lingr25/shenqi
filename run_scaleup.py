# -*- coding: utf-8 -*-
"""run_scaleup.py - 全量扩覆盖驱动: 官方45分P + 云端timeline_ok 18分P

按 KNOWLEDGE_PIPELINE.md §3 顺序执行: 每场 ①章节抽卡 -> ②原子化,
全部完成后 ③聚类 -> ④归并 -> ⑤增强 -> ⑥评测。
单步失败只记录不中断; 全部脚本自带断点, 重跑本驱动自动续。

场级并行: PHASE1_JOBS 路同时跑不同分P (默认 2)。
每场内部 chapter/atomize 仍是 4 worker, 合计约 8 路在途,
对应 grok 10 RPM × ~80s/次 的稳态预算 (~6 RPM, 留余量)。

用法: python run_scaleup.py [--only-phase1]
环境变量: GROK_API_KEY 必需; SCALEUP_JOBS 覆盖并行场数
"""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "knowledge_pilot"
LOG = OUT / "scaleup.log"
DONE_MARK = ".phase1_done"

ONLY_PHASE1 = "--only-phase1" in sys.argv
PHASE1_JOBS = int(os.environ.get("SCALEUP_JOBS", "2"))

_log_lock = threading.Lock()


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    OUT.mkdir(exist_ok=True)
    with _log_lock:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def run(script, *args):
    cmd = [sys.executable, "-u", "-X", "utf8", str(ROOT / script), *args]
    t0 = time.time()
    # 长任务日志写文件, 禁止灌进 Kimi 会话 (100 路 [done] 会把 TUI 打爆)
    log_path = OUT / (Path(script).stem + ".run.log")
    with log_path.open("w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    dt = time.time() - t0
    tail = []
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-3:]
        for line in lines[-8:]:
            log(f"  {script}: {line}")
    return r.returncode, dt, tail, ""


def is_complete(stem):
    """原子卡完整: 存在完成标记, 或存在非空 atoms 且无正在覆盖写的半截风险。
    atomize 启动即 unlink 再写, 完成后由本驱动打 .phase1_done。
    兼容试点 3 场 (无标记但已有完整 atoms)。"""
    mark = OUT / f"{stem}{DONE_MARK}"
    atoms = OUT / f"{stem}.atoms.jsonl"
    if mark.exists() and atoms.exists() and atoms.stat().st_size > 0:
        return True
    # 试点遗留: 无标记但 atoms 与 claims 都在, 且近期没有 atomize 进程在写
    if atoms.exists() and atoms.stat().st_size > 0 and (OUT / f"{stem}.chapter_claims.jsonl").exists():
        return True
    return False


def mark_done(stem):
    (OUT / f"{stem}{DONE_MARK}").write_text("ok", encoding="utf-8")


def stems_official():
    stems = [f.stem for f in sorted((ROOT / "transcripts_txt").glob("*.txt"))]
    todo = [s for s in stems if not is_complete(s)]
    done = [s for s in stems if is_complete(s)]
    return todo, done


def stems_cloud_ok():
    aud = json.loads((ROOT / "cloud_clips" / "timeline_audit.json").read_text(encoding="utf-8"))
    flags = {f["stem"]: f["timeline"] for f in aud["files"]}
    todo, done = [], []
    for f in sorted((ROOT / "cloud_clips" / "asr_cloud").glob("*.jsonl")):
        s = f.stem
        if flags.get(s) != "timeline_ok":
            continue
        (done if is_complete(s) else todo).append(s)
    return todo, done


def process_one(idx, total, stem, source):
    claims = OUT / f"{stem}.chapter_claims.jsonl"
    atoms = OUT / f"{stem}.atoms.jsonl"
    fail = None
    if not claims.exists() or claims.stat().st_size == 0:
        # 0 字节残留会挡住 Pass2 断点, 先清掉
        if claims.exists():
            claims.unlink()
        rc, dt, tail, err = run("chapter_extract_claims.py", "--stem", stem, "--source", source)
        log(f"({idx}/{total}) ① {stem} [{source}] rc={rc} {dt:.0f}s | {' / '.join(tail)}")
        if rc != 0:
            fail = (stem, "chapter", err)
            log(f"  STDERR: {err}")
            return fail
    else:
        log(f"({idx}/{total}) ① {stem} 已有章节卡, 跳过")
    # 无完成标记则重跑原子化 (atomize 自己会覆盖写, 半截会被清掉)
    if not (OUT / f"{stem}{DONE_MARK}").exists():
        rc, dt, tail, err = run("atomize_claims.py", "--stem", stem)
        log(f"({idx}/{total}) ② {stem} rc={rc} {dt:.0f}s | {' / '.join(tail)}")
        if rc != 0:
            fail = (stem, "atomize", err)
            log(f"  STDERR: {err}")
            return fail
    else:
        log(f"({idx}/{total}) ② {stem} 已有原子卡, 跳过")
    mark_done(stem)
    return None


def main():
    if not os.environ.get("GROK_API_KEY"):
        raise SystemExit("请设置环境变量 GROK_API_KEY")
    off_todo, off_done = stems_official()
    cld_todo, cld_done = stems_cloud_ok()
    log(f"官方: 待跑 {len(off_todo)}, 已完成 {len(off_done)}; "
        f"云端ok: 待跑 {len(cld_todo)}, 已完成 {len(cld_done)}; "
        f"场并行={PHASE1_JOBS}")

    failures = []
    plan = [(s, "official") for s in off_todo] + [(s, "cloud") for s in cld_todo]
    total = len(plan)
    if plan:
        with ThreadPoolExecutor(max_workers=PHASE1_JOBS) as ex:
            futs = [ex.submit(process_one, i, total, stem, src)
                    for i, (stem, src) in enumerate(plan, 1)]
            for fut in as_completed(futs):
                fail = fut.result()
                if fail:
                    failures.append(fail)

    log(f"phase1 完成, 失败 {len(failures)}: {[f[:2] for f in failures]}")
    if ONLY_PHASE1:
        return
    if failures:
        log("phase1 有失败场, 跳过 ③④⑤⑥; 修好后续跑即可")
        return

    # 原子卡未变时保留聚类断点; 仅 SCALEUP_RESET_CLUSTER=1 才清
    if os.environ.get("SCALEUP_RESET_CLUSTER") == "1":
        for stale in (".cluster_cache.json", ".merge_cache.json"):
            p = OUT / stale
            if p.exists():
                p.unlink()
                log(f"已清除过期缓存 {stale}")
    else:
        log("保留聚类/归并断点缓存 (SCALEUP_RESET_CLUSTER=1 可强制重算)")
    for script in ("cluster_atoms.py", "merge_clusters.py", "enrich_atoms.py", "rag_eval.py"):
        rc, dt, tail, err = run(script)
        log(f"{script} rc={rc} {dt:.0f}s | {' / '.join(tail)}")
        if rc != 0:
            log(f"  STDERR: {err}")
            failures.append((script, "global", err))
            break
    log(f"全部结束, 总失败 {len(failures)}")


if __name__ == "__main__":
    main()
