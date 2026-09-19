# -*- coding: utf-8 -*-
"""kb_mine_asr.py - ASR 错词系统化挖掘

流程: 高频未知 n-gram 候选(本地) → LLM 批量判定(ok/error/slang + 纠正词) → kb/asr_mine.jsonl
判为 error 且有 correction 的进入候选规则清单 kb/asr_rules_proposal.md (人工过目后入 entity_corrector.py)。

用法: GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash python kb_mine_asr.py [--workers 16]
"""
import json
import os
import re
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import grok_client

CACHE = "kb/.asr_mine_cache.json"
BOILER = {"参数", "条件", "实体", "主题", "适用对象", "档案备注", "问题", "结论", "假设",
          "观察", "推导", "均为", "包含", "议题", "簇", "合并"}

PROMPT = """你是明日方舟(Arknights)中文社区的语音识别纠错专家。下面是从直播ASR文本中挖出的高频词，它们不在已知实体词典里。请判断每个词：

输出严格JSON：
{{"results": [{{"term": "词", "verdict": "ok|error|slang", "correction": "纠正词或空", "note": "一句话"}}]}}

- ok: 正常的通用词/机制词/关卡或敌人名，无需处理
- error: 疑似ASR同音/近音错词，correction 给出正确写法（如 赛雷亚→塞雷娅, 翼德→异德, 锁敌→索敌）
- slang: 社区黑话/昵称，可保留但建议在 correction 里给出正式名（如 杰哥→?）
- 拿不准的给 ok，宁缺毋滥。只有上下文明显说不通时才给 error。
- 重要：词典可能不含最新干员。若某词上下文自洽地作为干员/敌人名出现（如带技能、天赋描述），给 ok 或 slang，严禁凭旧知识把它"纠正"成发音相近的老干员（真实事故：新干员"珊比"曾被错改成"山"）。
- 特别注意明日方舟专有名词：危机合约赛季名（如 涤墨作战/弧光行动）、集成战略关卡名（ISW-NO xxx）、敌人名。ASR 常把赛季名写错（真实案例：迪莫→涤墨作战）。

输入（term \\t 出现次数 \\t 上下文样例）：
{batch}"""


def mine_candidates():
    idx = json.load(open("kb/entity_index.json", encoding="utf-8"))["mentions"]
    known = set(idx.keys())
    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    cand = Counter()
    ctx = defaultdict(list)
    for d in docs:
        if d.get("status") == "noise" or d["doc_type"] not in ("vod_cluster", "vod_atom"):
            continue
        t = d["text"]
        for m in re.finditer(r"[一-鿿]{2,4}", t):
            g = m.group(0)
            if g in known or g in BOILER:
                continue
            if any(g in k for k in known if len(k) >= 2):
                continue
            if any(k in g for k in known if len(k) >= 2):
                continue  # 候选含已知实体(如"珊比三技"), 是切分伪影不是错词
            cand[g] += 1
            if len(ctx[g]) < 2:
                ctx[g].append(t[max(0, m.start() - 12):m.end() + 12].replace("\n", " "))
    return [(g, c, ctx[g][0]) for g, c in cand.most_common() if c >= 8][:500]


def main():
    workers = 16
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    cands = mine_candidates()
    print(f"candidates={len(cands)}", flush=True)
    batches = [cands[i:i + 40] for i in range(0, len(cands), 40)]
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))

    lock = threading.Lock()

    def work(bi, batch):
        if str(bi) in cache:
            return
        lines = "\n".join(f"{g}\t{c}\t{s}" for g, c, s in batch)
        try:
            r, _ = grok_client.call_llm(PROMPT.format(batch=lines), retries=4)
            res = r.get("results")
            if not isinstance(res, list):
                raise ValueError("no results")
        except Exception as e:
            res = {"error": str(e)[:150]}
        with lock:
            cache[str(bi)] = res
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"  batch {bi} done", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda x: work(*x), enumerate(batches)))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    stat = Counter()
    errors, slangs = [], []
    with open("kb/asr_mine.jsonl", "w", encoding="utf-8") as f:
        for bi in sorted(cache, key=int):
            res = cache[bi]
            if isinstance(res, dict):
                continue
            for it in res:
                if not isinstance(it, dict) or "term" not in it:
                    continue
                stat[it.get("verdict", "?")] += 1
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                if it.get("verdict") == "error" and it.get("correction"):
                    errors.append(it)
                elif it.get("verdict") == "slang":
                    slangs.append(it)

    lines = ["# ASR 错词候选规则（待人工过目）", "",
             "确认后把规则并入 entity_corrector.py 并回填 docs.jsonl。", ""]
    for it in errors:
        lines.append(f"- [ ] `{it['term']}` → `{it['correction']}`  — {it.get('note','')}")
    lines += ["", "## slang（建议收录别名，不改文本）", ""]
    for it in slangs:
        lines.append(f"- {it['term']} → {it.get('correction','')}  — {it.get('note','')}")
    open("kb/asr_rules_proposal.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({"verdicts": dict(stat), "errors": len(errors), "slangs": len(slangs)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
