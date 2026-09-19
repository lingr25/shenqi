# -*- coding: utf-8 -*-
"""kb_quality_audit.py - LLM 知识价值审计

对全部 vod_cluster 与 qq_window 判定知识价值:
- keep:  含可复用机制知识(判定规则/帧数/数值/因果), 或明确提出未解决的机制问题
- demote: 与具体一局强绑定/感性描述/信息量低, 降权保留
- drop:  闲聊/ASR乱码/无意义, 移出检索
同时检测 asr_suspect (疑似ASR错词)。

产物: kb/quality_audit.jsonl + 回写 docs.jsonl (status/boost) + kb/quality_report.md
缓存: kb/.quality_cache.json

用法: GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash python kb_quality_audit.py [--workers 48] [--types vod_cluster,qq_window]
"""
import json
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import grok_client

CACHE = "kb/.quality_cache.json"

PROMPT = """你是明日方舟机制知识库的质量审计员。下面是一条从直播录播或QQ群聊提炼的知识卡片。请判断它是否构成**可复用的游戏机制知识**。

输出严格JSON：
{{"verdict": "keep|demote|drop", "kind": "mechanism|question|trivia|noise", "asr_suspect": ["疑似ASR错词"], "reason": "一句话理由"}}

标准：
- keep + mechanism: 含可复用的机制判定规则、帧数/数值参数、因果机制说明（其他玩家换关卡也能用）
- keep + question: 明确提出一个尚未解决的机制问题（open议题，对研究有价值）
- demote + trivia: 与某一局具体战况强绑定的观感描述（如"重装很硬老鼠打不动"）、无参数的打法建议
- drop + noise: 纯闲聊、无信息量、明显ASR乱码、重复
- asr_suspect: 文本中疑似语音识别错误的词（如"真金范围"实为"帧进范围"），没有则 []

[知识卡片]
{text}"""

APPLY = {  # verdict -> (status, boost_factor)
    "keep": (None, None),
    "demote": ("draft", 0.3),
    "drop": ("noise", 0.0),
}


def audit(text):
    r, _ = grok_client.call_llm(PROMPT.format(text=text[:900]), retries=4)
    if r.get("verdict") not in ("keep", "demote", "drop"):
        raise ValueError("bad verdict")
    return {"verdict": r["verdict"], "kind": r.get("kind", "?"),
            "asr_suspect": [str(x) for x in (r.get("asr_suspect") or [])][:5],
            "reason": str(r.get("reason", ""))[:200]}


def main():
    workers = 48
    types = {"vod_cluster", "qq_window"}
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    if "--types" in sys.argv:
        types = set(sys.argv[sys.argv.index("--types") + 1].split(","))

    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    targets = [d for d in docs if d["doc_type"] in types and d.get("status") != "noise"]
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    todo = [d for d in targets if d["id"] not in cache]
    print(f"targets={len(targets)} todo={len(todo)}", flush=True)

    lock = threading.Lock()
    done = [0]

    def work(d):
        try:
            r = audit(d["text"])
        except Exception as e:
            r = {"verdict": "error", "kind": "?", "asr_suspect": [], "reason": str(e)[:150]}
        with lock:
            cache[d["id"]] = r
            done[0] += 1
            if done[0] % 50 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  {done[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    stat = Counter()
    asr_terms = Counter()
    n_applied = 0
    with open("kb/quality_audit.jsonl", "w", encoding="utf-8") as fa:
        for d in docs:
            r = cache.get(d["id"])
            if not r or d["doc_type"] not in types:
                continue
            stat[f'{d["doc_type"]}:{r["verdict"]}/{r["kind"]}'] += 1
            for t in r.get("asr_suspect") or []:
                asr_terms[t] += 1
            fa.write(json.dumps({"id": d["id"], **r}, ensure_ascii=False) + "\n")
            status, boost = APPLY.get(r["verdict"], (None, None))
            if status == "noise":
                d["status"] = "noise"
                d["retrieval_boost"] = 0.0
                n_applied += 1
                # drop 的 cluster 连带 member atom 降权
                if d["doc_type"] == "vod_cluster":
                    for mid in (d["links"].get("member_atom_ids") or []):
                        pass  # atom 降权在下面统一做
            elif boost is not None:
                d["retrieval_boost"] = round((d.get("retrieval_boost") or 1.0) * boost, 3)
                n_applied += 1
    # drop cluster 的 member atom 置 noise
    noise_members = set()
    by_id = {d["id"]: d for d in docs}
    for d in docs:
        if d["doc_type"] == "vod_cluster" and d.get("status") == "noise":
            noise_members.update((d["links"].get("member_atom_ids") or []))
    for d in docs:
        if d["doc_type"] == "vod_atom" and d.get("atom_id") in noise_members and d.get("status") != "noise":
            d["status"] = "noise"
            d["retrieval_weight"] = 0.0

    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    rep = ["# 知识价值审计报告", "", f"- 审计对象: {len(targets)}", ""]
    for k, v in stat.most_common():
        rep.append(f"- {k}: {v}")
    rep += ["", "## 疑似 ASR 错词 top30", ""]
    for t, c in asr_terms.most_common(30):
        rep.append(f"- {t}: {c}")
    open("kb/quality_report.md", "w", encoding="utf-8").write("\n".join(rep) + "\n")
    print(json.dumps({"applied": n_applied, "stats": dict(stat),
                      "asr_top": asr_terms.most_common(10)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
