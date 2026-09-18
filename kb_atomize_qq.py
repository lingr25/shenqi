# -*- coding: utf-8 -*-
"""kb_atomize_qq.py - 阶段D+: QQ 窗卡 → 原子命题 (deepseek-v4.1-flash)

把 qq_cards/cards.jsonl 的 789 张窗卡拆成单命题原子, schema 对齐直播原子。
产物: kb/qq_atoms.jsonl (不入 docs.jsonl, 由 kb_pack_qq_atoms.py 并入)
带断点缓存 kb/.qq_atom_cache.json。

用法: GROK_API_KEY=sk-... GROK_MODEL=deepseek-v4.1-flash python kb_atomize_qq.py --workers 32
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import grok_client

CACHE = "kb/.qq_atom_cache.json"

PROMPT = """你是明日方舟机制知识库的原子命题拆分员。下面是一张QQ群讨论窗卡片。请把其中有知识价值的结论拆成**原子命题**（每条只含一个可独立判定真假的命题）。

输出严格JSON对象（不要输出数组）：
{{"atoms": [ {{"proposition": "单句命题", "claim_type": "conclusion|observation|derivation|hypothesis|question", "applies_to": "适用对象(干员/敌人/机制名, 通用则general)", "conditions": ["前提条件"], "entities": ["涉及实体"], "parameters": [{{"name":"参数名","value":"数值","unit":"单位"}}], "speaker_credibility": "authoritative|expert|lead|member"}} ]}}

规则：
- claim_type: conclusion=明确结论; observation=实测观察; derivation=推导步骤; hypothesis=未证实猜想; question=未解决问题
- 主播(神祇/权威发言)的结论标 authoritative；专家标 expert；普通群友标 member
- 闲聊、表情、无信息量的内容不拆，没有可拆内容就输出 []
- hypothesis/question 不得包装成 conclusion
- 保留帧数/数值等参数原样

[窗卡片]
topic: {topic}
分类: {category}
问题: {question}
各方结论: {conclusions}
参数: {params}
总结: {takeaway}
实体: {entities}"""


def atomize(card):
    concl = "\n".join(f"- [{c.get('credibility','?')}] {c.get('speaker','')}: {c.get('conclusion','')}"
                      for c in (card.get("core_conclusions") or []))
    params = json.dumps(card.get("underlying_parameters") or [], ensure_ascii=False)
    prompt = PROMPT.format(
        topic=card.get("topic", ""), category=card.get("category", ""),
        question=card.get("context_question", ""), conclusions=concl,
        params=params, takeaway=card.get("summary_takeaway", ""),
        entities=" ".join(card.get("entities") or []))
    r, usage = grok_client.call_llm(prompt, retries=4)
    if isinstance(r, dict) and isinstance(r.get("atoms"), list):
        r = r["atoms"]
    elif isinstance(r, dict):
        for v in r.values():
            if isinstance(v, list):
                r = v
                break
    if not isinstance(r, list):
        raise ValueError("not a list")
    out = []
    for a in r:
        if isinstance(a, dict) and a.get("proposition") and \
           a.get("claim_type") in ("conclusion", "observation", "derivation", "hypothesis", "question"):
            out.append(a)
    return out


def main():
    workers = 32
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    cards = [json.loads(l) for l in open("qq_cards/cards.jsonl", encoding="utf-8")]
    cards = [c for c in cards if c.get("status") != "duplicate"]
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    todo = [c for c in cards if c["window_id"] not in cache]
    print(f"cards={len(cards)} todo={len(todo)}", flush=True)

    lock = threading.Lock()
    done = [0]

    def work(c):
        try:
            atoms = atomize(c)
        except Exception as e:
            atoms = {"error": str(e)[:150]}
        with lock:
            cache[c["window_id"]] = atoms
            done[0] += 1
            if done[0] % 25 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  {done[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    n_atom, n_err = 0, 0
    with open("kb/qq_atoms.jsonl", "w", encoding="utf-8") as f:
        for c in cards:
            atoms = cache.get(c["window_id"]) or []
            if isinstance(atoms, dict):
                n_err += 1
                continue
            for i, a in enumerate(atoms):
                a["atom_id"] = f"{c['window_id']}:qa{i}"
                a["window_id"] = c["window_id"]
                a["category"] = c.get("category")
                a["novelty"] = c.get("novelty")
                a["as_of"] = c.get("as_of")
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
                n_atom += 1
    print(json.dumps({"windows": len(cards), "atoms": n_atom, "errors": n_err}, ensure_ascii=False))


if __name__ == "__main__":
    main()
