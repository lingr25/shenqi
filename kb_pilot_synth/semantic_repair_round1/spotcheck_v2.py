# -*- coding: utf-8 -*-
"""修复后抽检落盘: 确定性随机 30 条 + 指定重点 cluster 的完整证据上下文。

用途: 供代理人工复核「修复后是否仍可追溯、降级是否有据」, 不是 LLM 判定。
随机种子固定, 便于复现; 输出 markdown 只读。

用法:
  python spotcheck_v2.py                # 30 随机 + 内置重点清单
  python spotcheck_v2.py --n 30 --seed 20260920
"""
import argparse
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")

FOCUS = ["伤害结算-0-10", "伤害结算-0-4", "伤害结算-12-18", "伤害结算-4-3",
         "状态效果-8-0", "技能特例-15-1", "技能特例-21-11", "其他-3-17",
         "其他-9-5", "寻路-36-5"]


def L(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_atoms():
    atoms = {}
    for d in L(os.path.join(ROOT, "kb/docs.jsonl")):
        if d.get("doc_type") == "vod_atom":
            atoms[d["id"].split(":", 1)[1]] = d
    return atoms


TS_LINE = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")
CTX = re.compile(r"^(?:ctx=)?sub:([^:]+):(\d+)$")


def ts_rows(stem):
    for p in (f"transcripts_txt/{stem}.txt", f"asr_drafts/{stem}_asr.txt",
              f"asr_drafts/{stem}_asr_draft.txt"):
        fp = os.path.join(ROOT, p)
        if not os.path.exists(fp):
            continue
        rows = {}
        for line in open(fp, encoding="utf-8"):
            m = TS_LINE.match(line.rstrip())
            if m:
                sec = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                rows.setdefault(sec, m.group(4))
        return rows, p
    return {}, None


def parse_rules(text):
    """把渲染后的卡正文拆成 (section, {text, subject, when, scope, evidence}) 列表。"""
    out, sect = [], None
    for line in (text or "").split("\n"):
        if line.startswith("## "):
            sect = line[3:].strip()
            continue
        m = re.match(r"^- (.*?)\s*\(主语:(.*?) \| 条件:(.*?) \| scope:(.*?) \| 证据:(.*?)\)"
                     r"(?:\s*\[(.*?)\])?$", line)
        if m:
            out.append({"section": sect, "text": m.group(1), "subject": m.group(2),
                        "when": m.group(3), "scope": m.group(4),
                        "evidence": [x.strip() for x in m.group(5).split(",")],
                        "flag": m.group(6)})
    return out


def dump_evidence(atoms, ev, indent="      "):
    lines = []
    for e in ev:
        m = CTX.match(e)
        if m:
            rows, path = ts_rows(m.group(1))
            sec = int(m.group(2))
            near = [k for k in sorted(rows) if abs(k - sec) <= 25]
            lines.append(f"{indent}ctx {e} (file={path})")
            for k in near[:4]:
                lines.append(f"{indent}    t={k} {rows[k][:200]}")
            if not near:
                lines.append(f"{indent}    (未找到 {sec} 附近字幕行)")
            continue
        a = atoms.get(e)
        if not a:
            lines.append(f"{indent}ATOM {e}  ✗ 未在 kb/docs.jsonl 找到")
            continue
        lines.append(f"{indent}ATOM {e} status={a.get('status')} scope={a.get('scope')} "
                     f"applies_to={a.get('applies_to')} claim={a.get('claim_type')}")
        lines.append(f"{indent}    proposition: {(a.get('text') or '').splitlines()[0][:220]}")
        for c in ((a.get("evidence") or {}).get("clips") or [])[:2]:
            lines.append(f"{indent}    quote t={c.get('t_start')}-{c.get('t_end')}: "
                         f"{(c.get('quote') or '')[:260]}")
    return lines


def render(cid, atoms, default, archive, out):
    out.append(f"\n### {cid}")
    for tag, rows in (("default", default), ("archive", archive)):
        for x in rows:
            if x.get("cluster_id") != cid:
                continue
            out.append(f"- layer=**{tag}** scope={x.get('scope')} kind={x.get('kind')} "
                       f"boost={x.get('retrieval_boost')} conf={x.get('confidence')} "
                       f"instance_only={x.get('instance_only', False)}")
            rules = parse_rules(x.get("text"))
            for r in rules:
                out.append(f"  - [{r['section']}] {r['text'][:160]}")
                out.append(f"    subject={r['subject']} when={r['when']} scope={r['scope']}"
                           + (f"  flag={r['flag']}" if r["flag"] else ""))
                out.extend(dump_evidence(atoms, r["evidence"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260920)
    args = ap.parse_args()

    sem = L(os.path.join(HERE, "semantic_repaired.jsonl"))
    default = L(os.path.join(HERE, "gated_default_v2.jsonl"))
    archive = L(os.path.join(HERE, "gated_archive_v2.jsonl"))
    atoms = load_atoms()

    cids = sorted({r["cluster_id"] for r in sem})
    rng = random.Random(args.seed)
    sample = sorted(rng.sample(cids, min(args.n, len(cids))))

    out = ["# 修复后抽检落盘（只读，供代理复核）",
           "",
           f"- 语义复核覆盖 {len(cids)} 张卡；确定性随机 {len(sample)} 张（seed={args.seed}）",
           f"- 重点议题 {len(FOCUS)} 张全量列出",
           "- 每条规则下方给出其证据（原子命题 + 原片引文 / ctx 字幕行），用于判断「降级是否有据」",
           ""]

    out.append("\n## A. 确定性随机 30 张")
    out.append("- 抽样清单: `" + "`, `".join(sample) + "`")
    for cid in sample:
        render(cid, atoms, default, archive, out)
        semrow = [r for r in sem if r["cluster_id"] == cid]
        if semrow:
            labels = (semrow[0].get("labels") or {})
            dist = {}
            for v in labels.values():
                dist[v.get("label")] = dist.get(v.get("label"), 0) + 1
            out.append(f"  - LLM 标签分布(仅参考, 非审核真值): {dist}")

    out.append("\n## B. 重点议题全量")
    for cid in FOCUS:
        render(cid, atoms, default, archive, out)

    p = os.path.join(HERE, "spotcheck_v2.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(json.dumps({"out": p, "n_sampled": len(sample), "n_focus": len(FOCUS),
                      "seed": args.seed, "sample": sample}, ensure_ascii=False))


if __name__ == "__main__":
    main()
