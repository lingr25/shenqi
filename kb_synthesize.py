# -*- coding: utf-8 -*-
"""kb_synthesize.py - R5 簇级合成: 议题簇 → 完整机制词条

对每个有效 vod_cluster, 把成员原子命题+原话证据+QQ counterpart 卡合成为一段完整词条。
只许用输入材料中的事实, 不许脑补; hypothesis/question 必须显式标注; conflict 簇双方并列并标 vod_wins。

产物: kb/synthesized.jsonl (缓存 kb/.synth_cache.json)
用法: GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash python kb_synthesize.py [--workers 16]
"""
import json
import os
import glob
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import grok_client


def load_source_atoms():
    import re as _re
    from entity_corrector import CORRECTION_RULES
    atoms = {}
    for f in glob.glob("knowledge_pilot/*.atoms.enriched.jsonl"):
        for l in open(f, encoding="utf-8"):
            a = json.loads(l)
            # 源文件未经回填, 套用现行纠错规则后再进 prompt
            for p, r in CORRECTION_RULES:
                a["proposition"] = _re.sub(p, r, a.get("proposition", ""))
                for ev in a.get("evidence") or []:
                    if ev.get("quote"):
                        ev["quote"] = _re.sub(p, r, ev["quote"])
            atoms[a["atom_id"]] = a
    return atoms

CACHE = "kb/.synth_cache.json"

PROMPT = """你是明日方舟机制百科的撰写员。下面是同一个机制议题下的若干条提炼命题、原话证据，可能还有QQ群讨论卡。请把它们**合成一段完整、自洽的机制词条**。

输出严格JSON：
{{"title": "词条标题(含主语)",
 "applies_to": "适用对象(干员/敌人/机制名或'通用')",
 "rules": ["规则或结论, 每条一句, 数值参数必须保留原样"],
 "conditions": ["生效条件/前提"],
 "exceptions": ["例外/边界情况"],
 "open_questions": ["尚未解决/待验证的问题"],
 "confidence": "high|mid|low"}}

铁律：
- 只许使用输入材料中的事实，严禁补充你自己的游戏知识
- 数值/帧数必须原样保留（如 2.75帧、0.05格）
- 材料标注为 hypothesis/question 的内容只能进 open_questions
- 材料间矛盾时在 rules 里并列双方并注明"(存争议)"
- 材料不足成词条时 rules 可以为空，confidence 给 low

[议题标题] {title}
[议题问题] {question}
[档案备注] {note}

[命题与证据]
{atoms}

{qq_block}"""


def fmt_atoms(members):
    lines = []
    for m in members[:12]:
        head = f"- [{m.get('claim_type','?')}] {m['proposition']}"
        if m.get("applies_to") and m["applies_to"] != "general":
            head += f" (对象:{m['applies_to']})"
        if m.get("conditions"):
            head += " (条件:" + ";".join(str(c) if not isinstance(c, dict) else f"{c.get('name','')}={c.get('value','')}" for c in m["conditions"]) + ")"
        if m.get("parameters"):
            head += " (参数:" + ";".join(f"{p.get('name','')}={p.get('value_norm') or p.get('value_raw','')}{p.get('unit','')}" for p in m["parameters"] if isinstance(p, dict)) + ")"
        lines.append(head)
        for ev in (m.get("evidence") or [])[:1]:
            if ev.get("quote"):
                lines.append(f"  原话[{ev.get('start','?')}s]: {ev['quote'][:100]}")
    return "\n".join(lines)


def render(r, cluster, members):
    lines = [f"# {r['title']}", f"适用对象: {r['applies_to']}"]
    if r.get("rules"):
        lines.append("## 规则")
        lines += [f"- {x}" for x in r["rules"]]
    if r.get("conditions"):
        lines.append("## 条件")
        lines += [f"- {x}" for x in r["conditions"]]
    if r.get("exceptions"):
        lines.append("## 例外")
        lines += [f"- {x}" for x in r["exceptions"]]
    if r.get("open_questions"):
        lines.append("## 待验证")
        lines += [f"- {x}" for x in r["open_questions"]]
    if cluster["issue_status"] == "conflict":
        lines.append("⚠ 本议题存在争议, 以上规则含存争议内容")
    return "\n".join(lines)


def main():
    workers = 16
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    atoms = load_source_atoms()
    # 用 docs 里的 noise 状态过滤
    noise_ids = {d.get("atom_id") for d in docs
                 if d["doc_type"] == "vod_atom" and d.get("status") == "noise"}
    atoms = {k: v for k, v in atoms.items() if k not in noise_ids}
    by_id = {d["id"]: d for d in docs}
    clusters = [d for d in docs if d["doc_type"] == "vod_cluster" and d.get("status") != "noise"]
    print(f"clusters to synthesize: {len(clusters)}", flush=True)

    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    todo = [c for c in clusters if c["id"] not in cache]

    lock = threading.Lock()
    done = [0]

    def work(c):
        mids = [m for m in (c["links"].get("member_atom_ids") or []) if m in atoms]
        members = [atoms[m] for m in mids]
        qq_block = ""
        cps = [by_id[q] for q in (c["links"].get("counterpart_ids") or []) if q in by_id]
        if cps:
            qq_block = "[QQ群讨论(补充线索, 与录播冲突时以录播为准)]\n" + \
                       "\n".join(f"- {q['text'][:300]}" for q in cps[:3])
        try:
            r, _ = grok_client.call_llm(PROMPT.format(
                title=c["text"].split("\n")[0],
                question="", note="", atoms=fmt_atoms(members)[:3000],
                qq_block=qq_block[:900]), retries=4)
            if not isinstance(r.get("rules"), list) or not r.get("title"):
                raise ValueError("bad synth json")
            r["_text"] = render(r, c, members)
        except Exception as e:
            r = {"error": str(e)[:150]}
        with lock:
            cache[c["id"]] = r
            done[0] += 1
            if done[0] % 50 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  {done[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    n_ok = n_err = 0
    with open("kb/synthesized.jsonl", "w", encoding="utf-8") as f:
        for c in clusters:
            r = cache.get(c["id"]) or {}
            if "error" in r or not r.get("_text"):
                n_err += 1
                continue
            f.write(json.dumps({
                "cluster_id": (c["links"].get("cluster_id")),
                "doc_id": c["id"], "title": r["title"],
                "applies_to": r.get("applies_to"), "confidence": r.get("confidence"),
                "issue_status": c["issue_status"], "audit_kind": c.get("audit_kind"),
                "text": r["_text"], "member_count": len(c["links"].get("member_atom_ids") or []),
                "counterpart_ids": c["links"].get("counterpart_ids") or [],
            }, ensure_ascii=False) + "\n")
            n_ok += 1
    print(json.dumps({"synthesized": n_ok, "errors": n_err}, ensure_ascii=False))


if __name__ == "__main__":
    main()
