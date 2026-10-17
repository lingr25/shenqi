# -*- coding: utf-8 -*-
"""E1/I/E2 交集的**可追溯性本地三分** (纯本地, 不调 API)。

对 scope_units.jsonl 里每条「进入 gated_default 且仍在肯定段」的规则:
  1. 解析 evidence_atom_ids:
     - 真实原子 id -> 在 kb/docs.jsonl 里查 vod_atom 文档 (是否存在 / status / scope / applies_to / 原文);
     - ctx=sub:<stem>:<sec> -> 用 transcripts_txt / asr_drafts 时间戳行解析出**真实字幕原文**;
  2. 给每条规则打本地可判定的标签:
     - untraceable_atom : 真实原子 id 在 docs.jsonl 里找不到, 或 status=noise;
     - atom_scope_narrow: 规则自称 universal, 但其证据原子 scope 是 instance/example;
     - named_subject    : 规则 subject 字段不是占位词;
     - ctx_resolved     : ctx=sub 引用能解析到具体字幕行 (可追溯);
  3. 输出 e1_triage.jsonl / triage_summary.json, 供人工抽样校准与后续 LLM 定向补证使用。
"""
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
TS_LINE = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")
CTX = re.compile(r"^(?:ctx=)?sub:([^:]+):(\d+)")
PLACEHOLDER = ("未点名", "general", "通用", "未明确", "无")


def load_ts_rows():
    idx = {}
    for d in ("transcripts_txt", "asr_drafts"):
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            continue
        for fn in os.listdir(p):
            if not fn.endswith(".txt"):
                continue
            stem = fn[:-4]
            if stem.endswith("_asr"):
                stem = stem[:-4]
            elif stem.endswith("_asr_draft"):
                stem = stem[:-9]
            if stem in idx:
                continue
            idx[stem] = os.path.join(d, fn)
    return idx


def _rows(path):
    rows = {}
    for line in open(os.path.join(ROOT, path), encoding="utf-8"):
        m = TS_LINE.match(line.rstrip())
        if not m:
            continue
        sec = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        rows.setdefault(sec, m.group(4))
    return rows


def load_atoms():
    atoms = {}
    for l in open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        if d.get("doc_type") == "vod_atom":
            atoms[d["id"].split(":", 1)[1]] = d
    return atoms


def main():
    tsfiles = load_ts_rows()
    tscache = {}
    atoms = load_atoms()
    units = [json.loads(l) for l in open(os.path.join(HERE, "scope_units.jsonl"), encoding="utf-8")]
    keep = [u for u in units if u["in_gated_default"] and u["still_affirmative"]]
    out, cnt = [], collections.Counter()
    for u in keep:
        flags, detail = [], []
        real, ctxs = [], []
        for e in (u.get("evidence") or []):
            e = str(e)
            m = CTX.match(e)
            if m:
                stem, sec = m.group(1), int(m.group(2))
                row = tscache.get(stem)
                if row is None:
                    row = tscache[stem] = _rows(tsfiles[stem]) if stem in tsfiles else {}
                ctxs.append({"id": e, "stem": stem, "t": sec, "text": row.get(sec)})
            else:
                a = atoms.get(e)
                real.append({"id": e, "found": bool(a and a.get("status") != "noise"),
                             "status": (a or {}).get("status"),
                             "scope": (a or {}).get("scope"),
                             "applies_to": (a or {}).get("applies_to"),
                             "text": (a or {}).get("text")})
        if real and any(not r["found"] for r in real):
            flags.append("untraceable_atom")
        if real and any(r["scope"] in ("instance", "example") for r in real if r["found"]):
            flags.append("atom_scope_narrow")
        if real and all(r["scope"] in ("instance", "example") for r in real if r["found"]):
            flags.append("atom_scope_all_narrow")
        if ctxs:
            if all(c["text"] for c in ctxs):
                flags.append("ctx_resolved")
            else:
                flags.append("ctx_unresolved")
        if not real and not ctxs:
            flags.append("no_evidence_at_all")
        subj = None
        nm = re.match(r"^\[", u.get("rule_text") or "")
        flags.append("legacy_bracket_rule" if nm else "plain_rule")
        out.append({**u, "triage": flags, "resolved_real_atoms": real, "resolved_ctx": ctxs})
        for f in flags:
            cnt[f] += 1
    with open(os.path.join(HERE, "e1_triage.jsonl"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"n_units_kept": len(keep), "n_units_total": len(units),
               "triage_counts": dict(cnt.most_common()),
               "by_flag": {}}
    for f in ("E1", "I", "E2"):
        sub = [r for r in out if f in r["flag"].split("+")]
        summary["by_flag"][f] = {
            "n": len(sub),
            "with_untraceable_atom": sum(1 for r in sub if "untraceable_atom" in r["triage"]),
            "with_atom_scope_all_narrow": sum(1 for r in sub if "atom_scope_all_narrow" in r["triage"]),
            "with_atom_scope_narrow": sum(1 for r in sub if "atom_scope_narrow" in r["triage"]),
            "no_real_atom_only_ctx": sum(1 for r in sub if not r["resolved_real_atoms"]),
            "ctx_unresolved": sum(1 for r in sub if "ctx_unresolved" in r["triage"]),
            "no_evidence_at_all": sum(1 for r in sub if "no_evidence_at_all" in r["triage"]),
        }
    json.dump(summary, open(os.path.join(HERE, "triage_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
