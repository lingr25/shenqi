# -*- coding: utf-8 -*-
"""把本轮对抗性挑刺（faultcheck）的 phase2 批 fix 落到 approved_manifest.json。

phase2 的 manifest 由 kb_curation_qq_expansion.py 写入，本批只有 fix（无 remove）。之所以不重跑
那个产出器：它会把 status 从终态 approved_merged 打回 proposed，使 loader 拒收整批。故本脚本
只做字段级覆盖，保持 status / entry_count / schema 与文件的 CRLF、indent=1 形态不变，
并对同一份 faultcheck_phase2.json 幂等（重复运行不叠加 limitations、不重复追加叙述）。

只改 claim/subject/condition 三类派生文本：citations / evidence / evidence_sha256 一个字不动。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _b3_converge_build import merged_result_entry_count  # noqa: E402  同一套「现算不写死」口径

MANIFEST = os.path.join(HERE, "approved_manifest.json")
FAULTCHECK = os.path.join(HERE, "..", "faultcheck", "faultcheck_phase2.json")
LABEL = "kb_trial/curation/qq_expansion/approved_manifest.json"
LIM_PREFIX = "对抗性挑刺（faultcheck）修复（"


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main():
    raw = read_text(MANIFEST)
    newline = "\r\n" if "\r\n" in raw else "\n"
    doc = json.loads(raw)
    with open(FAULTCHECK, encoding="utf-8") as fh:
        fc = json.load(fh)
    fixes = fc.get("fixes") or {}
    if not fixes:
        raise SystemExit("faultcheck_phase2.json 里没有 fix，拒绝改写 manifest")

    index = {(e["window_id"], e["local_id"]): e for e in doc["entries"]}
    applied, missing = [], []
    for eid, spec in sorted(fixes.items()):
        _, win, lid = eid.split(":", 2)
        e = index.get((win, lid))
        if e is None:
            missing.append(eid)
            continue
        before = {k: e.get(k) for k in ("claim", "subject", "condition")}
        for field in ("claim", "subject", "condition"):
            if spec.get(field):
                e[field] = spec[field]
        changed = any(before[k] != e.get(k) for k in before)
        if changed:
            if e.get("claim_corrected_by_audit") and e.get("claim_original"):
                pass  # 保留更早一轮的原值，不被本轮覆盖
            else:
                e["claim_corrected_by_audit"] = True
                e["claim_original"] = before["claim"]
        lims = [x for x in (e.get("review_limitations") or []) if not str(x).startswith(LIM_PREFIX)]
        lims.append("%s%s）：%s" % (LIM_PREFIX, spec.get("fault_type", ""),
                                   spec.get("note") or spec.get("suggestion", "")))
        e["review_limitations"] = lims
        e["audit_note"] = "%s对抗性挑刺修复（%s）：%s" % (
            (e.get("audit_note") or "").split("；对抗性挑刺修复（")[0] + "；" if e.get("audit_note") else "",
            spec.get("fault_type", ""), spec.get("note") or spec.get("suggestion", ""))
        applied.append({"id": eid, "fault_type": spec.get("fault_type", ""),
                        "fields": sorted(k for k in ("claim", "subject", "condition") if spec.get(k)),
                        "source": spec.get("source", "")})

    if missing:
        raise SystemExit("faultcheck 命中了 manifest 里不存在的条目：%s" % missing)

    doc["faultcheck"] = {
        "applied_at": fc.get("applied_at"),
        "script": "kb_trial/curation/faultcheck/_faultcheck_apply.py",
        "source": "kb_trial/curation/faultcheck/faultcheck_phase2.json"
                  "（由 kb_trial/curation/faultcheck/_faultcheck_apply.py 汇总批 16 份 triage_*.json 的二审结论）",
        "note": "对抗性挑刺（faultcheck）本轮落地：二审逐条对已发布条目挑刺，本批 0 条 remove、%d 条 fix。"
                "fix 只改 claim/subject/condition 三类派生文本，引文（citations 的原文片段）与 "
                "evidence_sha256 一个字未动；faultcheck 说明已追加进各条 review_limitations。" % len(applied),
        "fix_count": len(applied),
        "fixes": applied,
    }
    tail = ("**本轮对抗性挑刺（faultcheck，%s）**：二审逐条挑刺后本批 0 条 verdict=remove、%d 条 "
            "verdict=fix 改写派生文本（引文与 evidence_sha256 未动），条目数不变（%d）。"
            % (fc.get("applied_at") or "", len(applied), len(doc["entries"])))
    if "faultcheck" not in doc.get("note", ""):
        doc["note"] = doc.get("note", "") + tail
    doc["merged_result_entry_count"] = merged_result_entry_count(len(doc["entries"]), LABEL)

    out = json.dumps(doc, ensure_ascii=False, indent=1)
    if newline != "\n":
        out = out.replace("\n", newline)
    if raw.endswith(newline):
        out += newline
    with open(MANIFEST, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)

    # loader 只在 scope 上比对回执，claim 改写不触发它的任何断言；这里回读一遍确认没写坏。
    back = json.loads(read_text(MANIFEST))
    assert len(back["entries"]) == len(doc["entries"]), "entry_count drifted"
    assert back["status"] == doc["status"] == "approved_merged", "status drifted"
    print(json.dumps({"fix_applied": len(applied), "entry_count": back["entry_count"],
                      "merged_result_entry_count": back["merged_result_entry_count"],
                      "status": back["status"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
