# -*- coding: utf-8 -*-
"""kb_llm_align.py - 阶段C+: LLM 跨轨仲裁 (deepseek-v4.1-flash)

对 kb/cross_links.jsonl 中 score>=MIN_SCORE 的 vod_cluster × qq 文档对,
用 LLM 判定 relation(same_issue/related/unrelated) 与 verdict(agree/conflict/independent)。
- same_issue → counterpart_ids 双向写回
- same_issue+conflict → QQ 侧 novelty=conflict, conflict_resolution=vod_wins (录播为权威)
- same_issue+agree → QQ 侧 novelty=also_in_vod
带断点缓存 kb/.align_cache.json。

用法:
  GROK_API_KEY=sk-... GROK_MODEL=deepseek-v4.1-flash python kb_llm_align.py [--workers 32]
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import grok_client

MIN_SCORE = 1.5
CACHE = "kb/.align_cache.json"

PROMPT = """你是明日方舟机制知识库的跨源对齐仲裁员。下面有两条材料：[录播议题]来自主播"神祇读神奇"的机制讲解录播（权威真值），[群聊卡片]来自QQ群讨论（补充线索）。

请判断两者的关系，输出严格JSON：
{{"relation": "same_issue|related|unrelated", "verdict": "agree|conflict|independent", "reason": "一句话理由"}}

判定标准：
- same_issue: 讨论的是同一个机制问题/同一个判定逻辑（即使细节深浅不同）
- related: 同一大类机制但问题不同
- unrelated: 仅共享名词，问题无关
- agree: 双方结论一致或互补不矛盾
- conflict: 双方对同一问题给出矛盾结论
- independent: 只有单方有结论或无法比较

[录播议题]
{vod}

[群聊卡片]
{qq}"""


def adjudicate(pair, vod_text, qq_text):
    prompt = PROMPT.format(vod=vod_text[:800], qq=qq_text[:600])
    r, usage = grok_client.call_llm(prompt, retries=4)
    ok = r.get("relation") in ("same_issue", "related", "unrelated") and \
         r.get("verdict") in ("agree", "conflict", "independent")
    if not ok:
        raise ValueError("bad verdict json")
    return {"relation": r["relation"], "verdict": r["verdict"],
            "reason": str(r.get("reason", ""))[:200]}


def main():
    workers = 32
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    by_id = {d["id"]: d for d in docs}
    links = [json.loads(l) for l in open("kb/cross_links.jsonl", encoding="utf-8")]
    pairs = [l for l in links if l["score"] >= MIN_SCORE]

    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    todo = [p for p in pairs if f"{p['vod_doc_id']}|{p['qq_doc_id']}" not in cache]
    print(f"pairs={len(pairs)} cached={len(pairs)-len(todo)} todo={len(todo)}", flush=True)

    lock = threading.Lock()
    done = [0]

    def work(p):
        key = f"{p['vod_doc_id']}|{p['qq_doc_id']}"
        try:
            r = adjudicate(p, by_id[p["vod_doc_id"]]["text"], by_id[p["qq_doc_id"]]["text"])
        except Exception as e:
            r = {"relation": "error", "verdict": "error", "reason": str(e)[:150]}
        with lock:
            cache[key] = r
            done[0] += 1
            if done[0] % 50 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  {done[0]}/{len(todo)}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    # 汇总写回
    from collections import Counter, defaultdict
    stat = Counter()
    cp_v, cp_q = defaultdict(set), defaultdict(set)
    conflicts = []
    for p in pairs:
        r = cache.get(f"{p['vod_doc_id']}|{p['qq_doc_id']}", {})
        rel, verd = r.get("relation"), r.get("verdict")
        stat[f"{rel}/{verd}"] += 1
        if rel != "same_issue":
            continue
        cp_v[p["vod_doc_id"]].add(p["qq_doc_id"])
        cp_q[p["qq_doc_id"]].add(p["vod_doc_id"])
        q = by_id[p["qq_doc_id"]]
        if verd == "conflict":
            q["novelty"] = "conflict"
            q["conflict_resolution"] = "vod_wins"
            conflicts.append({"vod_doc_id": p["vod_doc_id"], "qq_doc_id": p["qq_doc_id"],
                              "score": p["score"], "reason": r.get("reason", "")})
        elif verd == "agree" and q.get("novelty") in ("group_only", "unknown", None):
            q["novelty"] = "also_in_vod"

    for did, s in cp_v.items():
        old = set(by_id[did]["links"].get("counterpart_ids") or [])
        by_id[did]["links"]["counterpart_ids"] = sorted(old | s)
    for did, s in cp_q.items():
        old = set(by_id[did]["links"].get("counterpart_ids") or [])
        by_id[did]["links"]["counterpart_ids"] = sorted(old | s)

    with open("kb/docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open("kb/cross_conflicts.jsonl", "w", encoding="utf-8") as f:
        for c in conflicts:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(json.dumps({"verdicts": dict(stat), "vod_linked": len(cp_v),
                      "qq_linked": len(cp_q), "cross_conflicts": len(conflicts)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
