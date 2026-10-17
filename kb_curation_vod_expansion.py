# -*- coding: utf-8 -*-
"""kb_curation_vod_expansion.py - 录播轨 (VOD) 增量甄选扩展管线

两阶段 CLI:
  1. export: 从 knowledge_pilot/{stem}.atoms.enriched.jsonl (或 atoms.jsonl)
     与 transcripts_txt/{stem}.txt 导出审查工单与任务卡
     python kb_curation_vod_expansion.py export --stem <STEM> --batch <BATCH_ID> [--limit N]

  2. converge: 汇总 reviews_{batch}/ 下的审查回执, 验证 source_sha256 与引文字符级对齐,
     产出 audit_decisions_{batch}.json 与 approved_manifest_{batch}.json
     python kb_curation_vod_expansion.py converge --batch <BATCH_ID> [--approve]

完全本地运行, 不调用任何外部 API.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from entity_corrector import correct_text

ROOT = Path(__file__).resolve().parent
PILOT_DIR = ROOT / "knowledge_pilot"
TRANSCRIPTS_DIR = ROOT / "transcripts_txt"
CLOUD_ASR_DIR = ROOT / "cloud_clips" / "asr_cloud"
EXPANSION_DIR = ROOT / "kb_trial" / "curation" / "vod_expansion"

# BVID -> 发布日期缓存
VIDEOS_FILE = ROOT / "all_search_videos.json"
BVID_DATE = {}
if VIDEOS_FILE.exists():
    try:
        raw_v = json.loads(VIDEOS_FILE.read_text(encoding="utf-8"))
        vlist = raw_v if isinstance(raw_v, list) else raw_v.get("videos", [])
        for v in vlist:
            if isinstance(v, dict) and v.get("bvid") and v.get("created"):
                dt = datetime.fromtimestamp(v["created"], tz=timezone(timedelta(hours=8)))
                BVID_DATE[v["bvid"]] = dt.strftime("%Y-%m-%d")
    except Exception:
        pass


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fmt_ts(sec: int | float) -> str:
    s = int(sec)
    h = s // 3600
    m = (s % 3600) // 60
    sec_rem = s % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec_rem:02d}"
    return f"{m:02d}:{sec_rem:02d}"


def parse_ts(ts_str: str) -> int:
    parts = [int(p) for p in ts_str.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def load_transcript(stem: str) -> tuple[str, list[dict], str]:
    """读取转写文本, 返回 (source_file, lines, raw_text).
    每个 line: {"t": int, "time": str, "text": str}.
    """
    txt_path = TRANSCRIPTS_DIR / f"{stem}.txt"
    if txt_path.exists():
        raw_text = txt_path.read_text(encoding="utf-8")
        lines = []
        for line in raw_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            m = re.match(r"^\[(\d+:\d+(?::\d+)?)\]\s*(.*)$", line_str)
            if m:
                ts_sec = parse_ts(m.group(1))
                corr = correct_text(m.group(2), stem)
                lines.append({"t": ts_sec, "time": m.group(1), "text": corr})
            elif lines:
                corr = correct_text(line_str, stem)
                lines[-1]["text"] += " " + corr
        return f"transcripts_txt/{stem}.txt", lines, raw_text

    cloud_path = CLOUD_ASR_DIR / f"{stem}.jsonl"
    if cloud_path.exists():
        lines = []
        raw_text = cloud_path.read_text(encoding="utf-8")
        for line in raw_text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            ts = int(item.get("t_start", item.get("start", 0)))
            corr = correct_text(item.get("text", ""), stem)
            lines.append({"t": ts, "time": fmt_ts(ts), "text": corr})
        return f"cloud_clips/asr_cloud/{stem}.jsonl", lines, raw_text

    return "", [], ""


def is_candidate_atom(atom: dict) -> bool:
    """过滤候选原子命题:
    - 排除 hypothesis/question
    - 排除未通过 quote 校验者
    - 排除无条件且无参数的纯 observation
    """
    ctype = atom.get("claim_type") or "conclusion"
    if ctype in ("hypothesis", "question"):
        return False
    if atom.get("quote_check") and atom.get("quote_check") != "pass":
        return False
    if atom.get("claim_status") == "dropped":
        return False

    prop = (atom.get("proposition") or "").strip()
    if not prop or len(prop) < 4:
        return False

    conds = atom.get("conditions") or []
    params = atom.get("parameters") or []
    if ctype == "observation" and not conds and not params:
        return False

    return True


def export_batch(stems: list[str], batch: str, limit: int = 0):
    EXPANSION_DIR.mkdir(parents=True, exist_ok=True)
    wos_dir = EXPANSION_DIR / f"workorders_{batch}"
    tasks_dir = EXPANSION_DIR / f"tasks_{batch}"
    wos_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir.mkdir(parents=True, exist_ok=True)

    index_records = []
    wo_count = 0

    for stem in stems:
        src_file, transcript_lines, raw_text = load_transcript(stem)
        if not transcript_lines:
            print(f"[{stem}] 未找到逐字稿或 ASR 转写, 跳过", flush=True)
            continue

        atoms_file = PILOT_DIR / f"{stem}.atoms.enriched.jsonl"
        if not atoms_file.exists():
            atoms_file = PILOT_DIR / f"{stem}.atoms.jsonl"
        if not atoms_file.exists():
            print(f"[{stem}] 未找到原子命题文件, 跳过", flush=True)
            continue

        raw_atoms = [
            json.loads(l) for l in atoms_file.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        candidates = [a for a in raw_atoms if is_candidate_atom(a)]
        print(f"[{stem}] 候选原子卡: {len(candidates)} / {len(raw_atoms)}", flush=True)

        # 按 parent_idx 分组
        groups: dict[int, list[dict]] = {}
        for a in candidates:
            pidx = a.get("parent_idx", 0)
            groups.setdefault(pidx, []).append(a)

        bvid = stem.split("_p")[0]
        recorded_at = BVID_DATE.get(bvid)

        for pidx in sorted(groups):
            if limit > 0 and wo_count >= limit:
                break
            atom_list = groups[pidx]
            wo_count += 1
            wo_id = f"vod_wo_{batch}_{wo_count:03d}"

            # 确定时间窗口
            starts = []
            ends = []
            for a in atom_list:
                for ev in a.get("evidence") or []:
                    if ev.get("start") is not None:
                        starts.append(int(ev["start"]))
                    if ev.get("end") is not None:
                        ends.append(int(ev["end"]))
                w = a.get("window") or {}
                if w.get("start") is not None:
                    starts.append(int(w["start"]))
                if w.get("end") is not None:
                    ends.append(int(w["end"]))

            min_s = min(starts) if starts else 0
            max_s = max(ends) if ends else min_s + 300
            w_start = max(0, min_s - 30)
            w_end = max_s + 30

            # 截取窗口转写
            win_lines = [l for l in transcript_lines if w_start <= l["t"] <= w_end]
            if not win_lines:
                win_lines = [l for l in transcript_lines if abs(l["t"] - min_s) <= 120]

            wo_data = {
                "workorder_id": wo_id,
                "batch": batch,
                "stem": stem,
                "bvid": bvid,
                "recorded_at": recorded_at,
                "parent_idx": pidx,
                "parent_topic": atom_list[0].get("parent_topic"),
                "chapter": atom_list[0].get("chapter"),
                "window": {
                    "start": w_start,
                    "end": w_end,
                },
                "source_file": src_file,
                "candidates": [
                    {
                        "local_id": f"c{ci+1:02d}",
                        "atom_id": a.get("atom_id"),
                        "proposition": a.get("proposition"),
                        "claim_type": a.get("claim_type"),
                        "category": a.get("category"),
                        "conditions": a.get("conditions") or [],
                        "applies_to": a.get("applies_to") or "general",
                        "parameters": a.get("parameters") or [],
                        "evidence": a.get("evidence") or [],
                    }
                    for ci, a in enumerate(atom_list)
                ],
                "transcript_window": win_lines,
            }

            raw_bytes = json.dumps(wo_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
            wo_data["source_sha256"] = sha256_bytes(raw_bytes)

            wo_path = wos_dir / f"{wo_id}.json"
            wo_path.write_text(json.dumps(wo_data, ensure_ascii=False, indent=2), encoding="utf-8")

            # 生成 task markdown
            task_md = [
                f"# 审查任务: {wo_id}",
                f"- **视频分P**: `{stem}` (发布日期: {recorded_at or '未知'})",
                f"- **所属章节**: {wo_data['chapter'].get('title', '未命名') if wo_data['chapter'] else '无'}",
                f"- **窗口时间**: {fmt_ts(w_start)} ~ {fmt_ts(w_end)}",
                f"- **源文件**: `{src_file}`",
                f"- **source_sha256**: `{wo_data['source_sha256']}`",
                "",
                "## 候选命题列表",
            ]
            for c in wo_data["candidates"]:
                task_md.append(f"### 候选 [{c['local_id']}] ({c['claim_type']} / {c['category']})")
                task_md.append(f"- **命题**: {c['proposition']}")
                task_md.append(f"- **条件**: {', '.join(c['conditions']) if c['conditions'] else '无'}")
                task_md.append(f"- **对象**: {c['applies_to']}")
                for ev in c["evidence"]:
                    task_md.append(f"- **原始引文**: [{fmt_ts(ev.get('start',0))}] {ev.get('quote','')}")
                task_md.append("")

            task_md.append("## 逐字稿上下文片段")
            task_md.append("```text")
            for wl in win_lines:
                task_md.append(f"[{wl['time']}] {wl['text']}")
            task_md.append("```")
            task_md.append("")
            task_md.append("## 回执契约提示")
            task_md.append(f"请审读上文，将结构化回执写入 `reviews_{batch}/{wo_id}.json`。")
            task_md.append("必须遵守四大闸门: 1. 自包含 2. 逐字引文对齐 3. 显式三元约束 4. 排除未定论假说。")

            task_path = tasks_dir / f"task_{wo_count:03d}.md"
            task_path.write_text("\n".join(task_md) + "\n", encoding="utf-8")

            index_records.append({
                "workorder_id": wo_id,
                "stem": stem,
                "candidates_count": len(atom_list),
                "source_sha256": wo_data["source_sha256"],
            })

        if limit > 0 and wo_count >= limit:
            break

    idx_path = wos_dir / "index.json"
    idx_path.write_text(json.dumps({
        "batch": batch,
        "workorder_count": wo_count,
        "workorders": index_records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Batch [{batch}] 导出完成: 共 {wo_count} 个工单及任务文件至 {wos_dir}")


def converge_batch(batch: str, approve: bool = False):
    wos_dir = EXPANSION_DIR / f"workorders_{batch}"
    reviews_dir = EXPANSION_DIR / f"reviews_{batch}"
    if not wos_dir.exists():
        print(f"工单目录不存在: {wos_dir}")
        return 1

    wo_files = sorted(wos_dir.glob("vod_wo_*.json"))
    if not wo_files:
        print(f"未找到工单: {wos_dir}")
        return 1

    decisions = []
    approved_entries = []
    errors = []

    for wop in wo_files:
        wo = json.loads(wop.read_text(encoding="utf-8"))
        wid = wo["workorder_id"]
        rv_path = reviews_dir / f"{wid}.json"

        if not rv_path.exists():
            # 未完成审读，默认记录 pending
            for c in wo.get("candidates", []):
                decisions.append({
                    "workorder": wid,
                    "local_id": c["local_id"],
                    "stem": wo["stem"],
                    "verdict": "pending",
                    "reason": "尚未收到审读回执",
                    "reviewer_model": None,
                })
            continue

        rv = json.loads(rv_path.read_text(encoding="utf-8"))
        # 验证 source_sha256
        if rv.get("source_sha256") != wo.get("source_sha256"):
            errors.append(f"{wid}: source_sha256 不匹配 (回执 {rv.get('source_sha256')} vs 工单 {wo.get('source_sha256')})")

        reviewer_model = rv.get("reviewer_model") or "unknown_reviewer"

        # 校验逐字稿
        _, _, raw_text = load_transcript(wo["stem"])
        norm_raw = re.sub(r"[\s，。、；：()（）,.;:！？、]", "", raw_text)

        # 检查 accepted claims
        for cl in rv.get("claims", []):
            lid = cl.get("local_id")
            claim = cl.get("claim", "").strip()
            subject = cl.get("subject", "").strip()
            condition = cl.get("condition", "").strip()
            scope = cl.get("scope", "universal").strip()
            quotes = cl.get("evidence", [])

            if not claim:
                errors.append(f"{wid}/{lid}: claim 为空")
                continue
            if not quotes:
                errors.append(f"{wid}/{lid}: 无引文 evidence")
                continue

            # 校验引文逐字存在
            quote_ok = True
            for q in quotes:
                qtext = q.get("text", "")
                norm_q = re.sub(r"[\s，。、；：()（）,.;:！？、]", "", qtext)
                if norm_q not in norm_raw:
                    quote_ok = False
                    errors.append(f"{wid}/{lid}: 引文在逐字稿中未找到逐字匹配: {qtext[:30]}...")

            if not quote_ok:
                decisions.append({
                    "workorder": wid,
                    "local_id": lid,
                    "stem": wo["stem"],
                    "verdict": "reject",
                    "reason": "引文未能在转写中逐字核验",
                    "reviewer_model": reviewer_model,
                })
                continue

            dec = {
                "workorder": wid,
                "local_id": lid,
                "stem": wo["stem"],
                "verdict": "keep",
                "claim": claim,
                "subject": subject or "未标注",
                "condition": condition or "未标注",
                "scope": scope or "universal",
                "category": cl.get("category") or wo.get("candidates", [{}])[0].get("category", "未标注"),
                "reviewer_model": reviewer_model,
                "reason": cl.get("reason", "审读通过"),
            }
            decisions.append(dec)

            ev_sha = sha256_text(json.dumps(quotes, ensure_ascii=False, sort_keys=True))
            approved_entries.append({
                "workorder_id": wid,
                "batch": batch,
                "stem": wo["stem"],
                "local_id": lid,
                "claim": claim,
                "subject": subject or "未标注",
                "condition": condition or "未标注",
                "scope": scope or "universal",
                "category": cl.get("category") or wo.get("candidates", [{}])[0].get("category", "未标注"),
                "recorded_at": wo.get("recorded_at"),
                "source_file": wo.get("source_file"),
                "evidence": quotes,
                "evidence_sha256": ev_sha,
                "reviewer_model": reviewer_model,
                "reason": cl.get("reason", "审读通过"),
            })

        # 检查 excluded
        for ex in rv.get("excluded", []):
            decisions.append({
                "workorder": wid,
                "local_id": ex.get("local_id", "excl"),
                "stem": wo["stem"],
                "verdict": ex.get("verdict", "reject"),
                "reason": ex.get("reason", "审读排除"),
                "reviewer_model": reviewer_model,
            })

    if errors:
        print("CONVERGE 校验发现错误:")
        for err in errors[:20]:
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  ... 另有 {len(errors) - 20} 条错误")

    # 写入 audit_decisions_{batch}.json
    audit_file = EXPANSION_DIR / f"audit_decisions_{batch}.json"
    audit_payload = {
        "batch": batch,
        "schema": "vod-expansion-audit-1.0",
        "workorders_total": len(wo_files),
        "decisions_count": len(decisions),
        "keep_count": len(approved_entries),
        "errors": errors,
        "decisions": decisions,
    }
    audit_file.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入裁定文件: {audit_file} (keep: {len(approved_entries)})")

    # 写入 approved_manifest_{batch}.json
    manifest_file = EXPANSION_DIR / f"approved_manifest_{batch}.json"
    manifest_status = "approved" if approve else "proposed_pending_parent_approval"
    manifest_payload = {
        "schema": "vod-expansion-approved-1.0",
        "batch": batch,
        "status": manifest_status,
        "entry_count": len(approved_entries),
        "source": {
            "workorders": f"kb_trial/curation/vod_expansion/workorders_{batch}/",
            "reviews": f"kb_trial/curation/vod_expansion/reviews_{batch}/",
            "audit_decisions": f"kb_trial/curation/vod_expansion/audit_decisions_{batch}.json",
        },
        "entries": approved_entries,
    }
    manifest_file.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入清单文件: {manifest_file} (status: {manifest_status}, entries: {len(approved_entries)})")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="导出审读工单与任务")
    p_export.add_argument("--batch", required=True, help="批次标识 (如 vod_b1)")
    p_export.add_argument("--stem", help="单个视频 stem (如 BV1xxx_p1_xxx)")
    p_export.add_argument("--stems", help="逗号分隔的多个 stem")
    p_export.add_argument("--limit", type=int, default=0, help="最多导出的工单数量")

    p_conv = sub.add_parser("converge", help="汇聚回执产出裁定与清单")
    p_conv.add_argument("--batch", required=True, help="批次标识")
    p_conv.add_argument("--approve", action="store_true", help="直接标记为 approved 状态")

    args = parser.parse_args()

    if args.cmd == "export":
        stems = []
        if args.stem:
            stems.append(args.stem.strip())
        if args.stems:
            stems.extend([s.strip() for s in args.stems.split(",") if s.strip()])
        if not stems:
            # 扫描 pilot 目录下的 enriched
            found = sorted([p.name.replace(".atoms.enriched.jsonl", "") for p in PILOT_DIR.glob("*.atoms.enriched.jsonl")])
            stems = found[:3]
            print(f"未指定 --stem, 默认采用前 3 个: {stems}")
        export_batch(stems, args.batch, limit=args.limit)

    elif args.cmd == "converge":
        return converge_batch(args.batch, approve=args.approve)

    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
