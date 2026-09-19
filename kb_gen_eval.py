# -*- coding: utf-8 -*-
"""kb_gen_eval.py - 评测题加厚: 从 keep/mechanism 卡自动生成盲测题

按分桶分层抽样 → LLM 反向生成"用户提问" + 期望关键词 → kb/eval_questions.jsonl
kb_eval.py 读取该文件, 以 expect_doc_id 命中 top5 为主指标。

用法: GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash python kb_gen_eval.py [--n 80] [--workers 16]
"""
import json
import random
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import grok_client

CACHE = "kb/.eval_gen_cache.json"

PROMPT = """下面是明日方舟机制知识库里的一条卡片。请扮演一个**不知道答案的玩家**，提出一个需要通过检索这条卡片才能回答的问题。

输出严格JSON：
{{"question": "玩家的提问(口语化, 不要照抄卡片标题)", "keywords": ["答案里应出现的2-4个关键术语或数值"]}}

要求：
- 像真实玩家提问，用俗称也可以，不要直接复述卡片里的专有表述
- keywords 必须是卡片原文中出现过的词或数值
- 如果卡片缺主语或内容空洞无法出题，输出 {{"question": null}}

[卡片]
{text}"""


def main():
    n_target, workers = 80, 16
    if "--n" in sys.argv:
        n_target = int(sys.argv[sys.argv.index("--n") + 1])
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    random.seed(20260919)

    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    pool = [d for d in docs if d.get("status") != "noise" and
            ((d["doc_type"] == "vod_cluster" and d.get("audit_kind") == "mechanism") or
             (d["doc_type"] == "qq_window" and d.get("novelty") != "conflict") or
             (d["doc_type"] in ("qq_canonical", "glossary")))]
    # 分桶分层: 按 category 均摊
    by_cat = defaultdict(list)
    for d in pool:
        by_cat[d.get("category") or "未分类"].append(d)
    cats = sorted(by_cat, key=lambda c: -len(by_cat[c]))
    picked, i = [], 0
    while len(picked) < n_target and cats:
        c = cats[i % len(cats)]
        if by_cat[c]:
            picked.append(by_cat[c].pop(random.randrange(len(by_cat[c]))))
        else:
            cats.remove(c)
            continue
        i += 1
    print(f"pool={len(pool)} picked={len(picked)}", flush=True)

    cache = {}
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except FileNotFoundError:
        pass
    lock = threading.Lock()
    done = [0]

    def work(d):
        if d["id"] in cache:
            return
        try:
            r, _ = grok_client.call_llm(PROMPT.format(text=d["text"][:800]), retries=4)
            if not r.get("question"):
                r = {"question": None, "keywords": []}
        except Exception as e:
            r = {"question": None, "keywords": [], "error": str(e)[:100]}
        with lock:
            cache[d["id"]] = r
            done[0] += 1
            if done[0] % 20 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  {done[0]}/{len(picked)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, picked))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    out = []
    for d in picked:
        r = cache.get(d["id"]) or {}
        if not r.get("question"):
            continue
        out.append({"q": r["question"], "expect_doc_id": d["id"],
                    "expect_keywords": r.get("keywords") or [],
                    "bucket": d.get("category"), "doc_type": d["doc_type"],
                    "source": "auto_v1"})
    with open("kb/eval_questions.jsonl", "w", encoding="utf-8") as f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(json.dumps({"generated": len(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
