# -*- coding: utf-8 -*-
"""抽检工作表: 把 spotcheck_v2.md 的 30 随机 + 10 重点压成紧凑表格, 供代理逐条判定。

每条规则一行: 段落 / 规则文本(截断) / 规则自身 scope / 证据原子 scope 集合 / 是否可解析。
输出 spotcheck_worksheet.md (只读)。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

import sys
sys.path.insert(0, HERE)
import spotcheck_v2 as S  # noqa: E402


def main():
    d = S.L(os.path.join(HERE, "gated_default_v2.jsonl"))
    a = S.L(os.path.join(HERE, "gated_archive_v2.jsonl"))
    atoms = S.load_atoms()
    sem = {r["cluster_id"]: r for r in S.L(os.path.join(HERE, "semantic_repaired.jsonl"))}
    sample = json.load(open(os.path.join(HERE, "spotcheck_v2.md"), encoding="utf-8")) if False else None
    txt = open(os.path.join(HERE, "spotcheck_v2.md"), encoding="utf-8").read()
    m = re.search(r"抽样清单: (.+)", txt)
    sampled = re.findall(r"`([^`]+)`", m.group(1))
    out = ["# 抽检工作表（拒绝原子/证据可解析性 + 门控动作一览）", ""]
    for cid in sampled + S.FOCUS:
        out.append(f"\n## {cid}")
        for tag, rows in (("default", d), ("archive", a)):
            for x in rows:
                if x.get("cluster_id") != cid:
                    continue
                rules = S.parse_rules(x.get("text"))
                out.append(f"- layer={tag} scope={x.get('scope')} kind={x.get('kind')} "
                           f"boost={x.get('retrieval_boost')} instance_only={x.get('instance_only', False)}")
                lab = sem.get(cid, {}).get("llm_labels") or []
                ld = {str(v.get("idx")): v.get("label") for v in lab if isinstance(v, dict)}
                for i, r in enumerate(rules):
                    scopes, unresolved = [], 0
                    for e in r["evidence"]:
                        mm = S.CTX.match(e)
                        if mm:
                            scopes.append("ctx")
                            continue
                        at = atoms.get(e)
                        if not at:
                            unresolved += 1
                            continue
                        scopes.append(at.get("scope") or "?")
                    out.append(f"    - [{r['section']}] {r['text'][:70]} | rule_scope={r['scope']} "
                               f"| atom_scopes={sorted(set(scopes))} | unresolved={unresolved} "
                               f"| llm={ld.get(str(i), '-')} | flag={r['flag'] or '-'}")
    open(os.path.join(HERE, "spotcheck_worksheet.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(json.dumps({"out": "spotcheck_worksheet.md", "n_sample": len(sampled),
                      "n_focus": len(S.FOCUS), "lines": len(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
