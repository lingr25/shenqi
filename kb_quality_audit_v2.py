# -*- coding: utf-8 -*-
"""kb_quality_audit_v2.py - 收紧标准的复审 (v2)

v1 复审后人工抽检发现的问题 → v2 收紧:
1. mechanism 必须有明确主语(干员/敌人/机制名 或显式"通用"), 缺主语→demote/underspecified
2. 新增 kind=opinion: 主播主观强度评价/设计意图猜测, 保留但低权, RAG 须标注观点非事实
3. trivia 收紧: 纯即时反应("这不是紧急吧")/空洞口号("X很重要")→drop/noise
4. ASR 错词继续收集 asr_suspect

复审范围: v1 判 keep/mechanism、keep/question、demote 的 vod_cluster(全部重判)
产物: kb/quality_audit_v2.jsonl + kb/.quality_cache_v2.json + 回写 docs.jsonl + kb/quality_report_v2.md

用法: GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash python kb_quality_audit_v2.py [--workers 48]
"""
import json
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import grok_client

CACHE = "kb/.quality_cache_v2.json"

PROMPT = """你是明日方舟机制知识库的严格审计员(v2收紧版)。判定这张卡片的分档。

输出严格JSON：
{{"verdict": "keep|demote|drop", "kind": "mechanism|question|opinion|trivia|noise", "subject_ok": true|false, "asr_suspect": ["疑似错词"], "reason": "一句话"}}

分档标准（从严）：
- mechanism: 必须有**明确主语**(具体干员/敌人/机制名, 或显式"通用") **且**含可验证内容(数值参数/触发条件/判定规则/因果链)。缺主语的一律不算 mechanism。
- question: 明确提出的、可通过测试裁决真伪的机制问题。问题与答案同源/循环的(答案是问题换种说法)不算。
- opinion: 主播主观强度评价、打法建议、对鹰角设计意图的猜测。有参考价值但不是机制事实。
- trivia: 与当局战况强绑定但尚有一定信息量的描述。
- noise: 纯即时反应(这不是紧急吧/兄弟你怎么没下去)、空洞口号(X非常重要,无展开)、无信息量。
- verdict: keep=保留原权重; demote=降权保留; drop=移出检索。mechanism/question 通常 keep; opinion/trivia 通常 demote; noise 一律 drop。
- subject_ok: mechanism 判定时主语是否明确。
- asr_suspect: 疑似语音识别错词(如 真金范围→帧进范围, 前溜→琴柳, 落地引→落地隐, 伊德→异德)，没有则 []

[卡片]
{text}"""


def audit(text):
    r, _ = grok_client.call_llm(PROMPT.format(text=text[:900]), retries=4)
    if r.get("verdict") not in ("keep", "demote", "drop") or \
       r.get("kind") not in ("mechanism", "question", "opinion", "trivia", "noise"):
        raise ValueError("bad v2 verdict")
    return {"verdict": r["verdict"], "kind": r["kind"],
            "subject_ok": bool(r.get("subject_ok", True)),
            "asr_suspect": [str(x) for x in (r.get("asr_suspect") or [])][:5],
            "reason": str(r.get("reason", ""))[:200]}


def main():
    workers = 48
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    v1 = json.load(open("kb/.quality_cache.json", encoding="utf-8"))
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    targets = [d for d in docs if d["doc_type"] == "vod_cluster"
               and d["id"] in v1 and v1[d["id"]].get("verdict") in ("keep", "demote")
               and d.get("status") != "noise"]
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    todo = [d for d in targets if d["id"] not in cache]
    print(f"v2 targets={len(targets)} todo={len(todo)}", flush=True)

    lock = threading.Lock()
    done = [0]

    def work(d):
        try:
            r = audit(d["text"])
        except Exception as e:
            r = {"verdict": "error", "kind": "?", "subject_ok": True, "asr_suspect": [],
                 "reason": str(e)[:150]}
        with lock:
            cache[d["id"]] = r
            done[0] += 1
            if done[0] % 50 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  {done[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    # 回写: v2 判定覆盖 v1 的 boost (先恢复 v1 boost 再套 v2)
    stat = Counter()
    asr_terms = Counter()
    noise_members = set()
    with open("kb/quality_audit_v2.jsonl", "w", encoding="utf-8") as fa:
        for d in docs:
            r = cache.get(d["id"])
            if not r or d["doc_type"] != "vod_cluster" or d.get("status") == "noise":
                continue
            stat[f'{r["verdict"]}/{r["kind"]}'] += 1
            for t in r.get("asr_suspect") or []:
                asr_terms[t] += 1
            fa.write(json.dumps({"id": d["id"], **r}, ensure_ascii=False) + "\n")
            d["audit_kind"] = r["kind"]
            if r["verdict"] == "drop":
                d["status"] = "noise"
                d["retrieval_boost"] = 0.0
                noise_members.update((d["links"].get("member_atom_ids") or []))
            elif r["verdict"] == "demote":
                base = 1.4 if d.get("issue_status") == "conflict" else \
                       1.3 if d.get("issue_status") == "agreed" else 1.0
                d["retrieval_boost"] = round(base * (0.2 if r["kind"] == "opinion" else 0.3), 3)
    for d in docs:
        if d["doc_type"] == "vod_atom" and d.get("atom_id") in noise_members \
           and d.get("status") != "noise":
            d["status"] = "noise"
            d["retrieval_weight"] = 0.0
    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    rep = ["# 质量审计 v2 报告（收紧版）", "", f"- 复审 vod_cluster: {len(targets)}", ""]
    for k, v in stat.most_common():
        rep.append(f"- {k}: {v}")
    rep += ["", "## 新增疑似 ASR 错词", ""]
    for t, c in asr_terms.most_common(30):
        rep.append(f"- {t}: {c}")
    open("kb/quality_report_v2.md", "w", encoding="utf-8").write("\n".join(rep) + "\n")
    print(json.dumps({"stats": dict(stat), "asr_top": asr_terms.most_common(15)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
