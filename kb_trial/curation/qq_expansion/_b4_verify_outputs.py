# -*- coding: utf-8 -*-
"""b4 产物自检：台账覆盖、id 唯一、evidence 逐字与 sha256 复核、计数一致性。

纯本地、只读；不修改任何产物。
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEWS = os.path.join(HERE, "reviews_b4")
WORKORDERS = os.path.join(HERE, "workorders_b4")
LEDGER = os.path.join(HERE, "_b4_dec.jsonl")
AUDIT = os.path.join(HERE, "audit_decisions_b4.json")
MANIFEST = os.path.join(HERE, "approved_manifest_b4.json")

errors = []

# ---- 1. 台账
ledger = {}
with open(LEDGER, encoding="utf-8") as fh:
    for ln, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        key = (r["workorder"], r["local_id"])
        if key in ledger:
            errors.append("台账重复键 %s" % (key,))
        ledger[key] = r

# ---- 2. claim 全集
claims = {}
wids = sorted(f[9:12] for f in os.listdir(REVIEWS) if f.startswith("qq_wo_b4_"))
for n in wids:
    wid = "qq_wo_b4_" + n
    rv = json.load(open(os.path.join(REVIEWS, wid + ".json"), encoding="utf-8"))
    for c in rv.get("claims") or []:
        claims[(wid, c["local_id"])] = (rv, c)

for k in ledger:
    if k not in claims:
        errors.append("台账有裁定但 reviews 无此 claim：%s" % (k,))

audit = json.load(open(AUDIT, encoding="utf-8"))
manifest = json.load(open(MANIFEST, encoding="utf-8"))

dec_keys = [(d["workorder"], d["local_id"]) for d in audit["decisions"]]
if len(dec_keys) != len(set(dec_keys)):
    errors.append("audit_decisions 存在重复 (workorder, local_id)")
if len(dec_keys) != len(claims):
    errors.append("audit_decisions 条数 %d != claim 总数 %d" % (len(dec_keys), len(claims)))
if set(dec_keys) != set(claims):
    errors.append("audit_decisions 与 claim 集合不一致")

# ---- 3. 裁定与台账一致
by_key = {(d["workorder"], d["local_id"]): d for d in audit["decisions"]}
for k, r in ledger.items():
    d = by_key[k]
    if d["verdict"] != r["verdict"]:
        errors.append("%s 裁定不一致：台账 %s / 产物 %s" % (k, r["verdict"], d["verdict"]))
    if r["verdict"] != "keep" and d.get("reason_code") != r["reason_code"]:
        errors.append("%s reason_code 不一致" % (k,))
    if r.get("criterion_note") and d.get("criterion_note") != r["criterion_note"]:
        errors.append("%s criterion_note 不一致" % (k,))
    # 只有正文（claim/subject/condition）真的被改写时才算 claim_corrected_by_audit；
    # 只补 limitations 的 override（父裁决对 307/c02）不算改写。
    ov = r.get("override") or {}
    orig = claims[k][1]
    rewritten = bool(ov) and ((ov.get("claim") or orig["claim"]) != orig["claim"] or
                              (ov.get("subject") or orig["subject"]) != orig["subject"] or
                              (ov.get("condition") or orig["condition"]) != orig["condition"])
    if rewritten and not d.get("claim_corrected_by_audit"):
        errors.append("%s 正文已改写但产物未标 claim_corrected_by_audit" % (k,))
    if not rewritten and d.get("claim_corrected_by_audit"):
        errors.append("%s 产物标了改写但正文未变" % (k,))
    if rewritten and d.get("claim_original") != orig["claim"]:
        errors.append("%s claim_original 不等于原始 claim" % (k,))
    if not rewritten and d.get("claim_original") is not None:
        errors.append("%s 未改写却带 claim_original" % (k,))

# ---- 4. entries：id 唯一、证据逐字、sha256 复核、verdict 均为 keep
entry_ids = [(e["workorder_id"], e["local_id"]) for e in manifest["entries"]]
if len(entry_ids) != len(set(entry_ids)):
    errors.append("manifest 条目 id 有重复")
for e in manifest["entries"]:
    k = (e["workorder_id"], e["local_id"])
    if by_key[k]["verdict"] != "keep":
        errors.append("%s 进入 manifest 但裁定非 keep" % (k,))
    wo = json.load(open(os.path.join(WORKORDERS, e["workorder_id"] + ".json"), encoding="utf-8"))
    msgs = {m["seq"]: m for m in wo["raw_messages"]["messages"]}
    payload = []
    for ev in e["evidence"]:
        m = msgs.get(ev["seq"])
        if m is None:
            errors.append("%s seq%s 不在 raw_messages" % (k, ev["seq"]))
            continue
        if m["text"] != ev["text"]:
            errors.append("%s seq%s 文本与 raw_messages 不一致" % (k, ev["seq"]))
        if m.get("speaker_id") != ev["speaker_id"] or m.get("time") != ev["time"]:
            errors.append("%s seq%s speaker/time 不一致" % (k, ev["seq"]))
        payload.append({"seq": ev["seq"], "speaker_id": ev["speaker_id"],
                        "time": ev["time"], "text": ev["text"]})
    sha = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if sha != e["evidence_sha256"]:
        errors.append("%s evidence_sha256 复核失败" % (k,))

# ---- 5. 计数一致
counts = audit["counts"]
if counts["keep"] != len(manifest["entries"]):
    errors.append("counts.keep 与 entries 数不符")
if counts["keep"] + counts["reject"] + counts["pending"] != len(claims):
    errors.append("counts 合计 != claim 总数")
if manifest["entry_count"] != len(manifest["entries"]):
    errors.append("manifest.entry_count 不符")

print("claims=%d keep=%d reject=%d pending=%d entries=%d" % (
    len(claims), counts["keep"], counts["reject"], counts["pending"], len(manifest["entries"])))
print("errors=%d" % len(errors))
for e in errors[:40]:
    print(" -", e)
sys.exit(1 if errors else 0)
