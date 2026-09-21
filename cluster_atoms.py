# -*- coding: utf-8 -*-
"""cluster_atoms.py - 议题聚类(第二轮): 原子卡 -> 议题档案

只做档案(agreed / conflicts / open), 禁止 LLM 把结论当真理:
- 条件不同禁止合并; 干员特例禁止并入 general
- hypothesis/correction 未关闭 -> open, 不出 canonical
- combat observation 不与 lecture conclusion 自动合并
- canonical 草案(proposed_canonical)仅当: 同 applies_to + 同条件 + >=2 独立证据 + status=agreed
  且永远标 claim_status=draft

用法: python cluster_atoms.py [--bucket 索敌] [--only-stem STEM]
环境变量: GROK_API_KEY (必需), GROK_BASE, GROK_MODEL
输出: knowledge_pilot/clusters.jsonl + clusters_report.md
"""
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from grok_client import LLM_KEY, call_llm

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "knowledge_pilot"

BATCH_SIZE = 50
WORKERS = int(os.environ.get("CLUSTER_WORKERS", "16"))
CACHE_PATH = Path(__file__).parent / "knowledge_pilot" / ".cluster_cache.json"

# 粗粒度受控分桶: 按优先级匹配第一个命中的桶
BUCKET_RULES = [
    ("索敌", ["索敌", "仇恨", "阻挡"]),
    ("寻路", ["寻路"]),
    ("帧时序与计时器", ["帧时序", "技力", "冷却", "光环", "再部署", "计时", "取整", "浮点"]),
    ("位移", ["位移"]),
    ("伤害结算", ["伤害", "费用"]),
    ("状态效果", ["状态效果", "隐匿"]),
    ("技能特例", ["技能特例"]),
]


def bucket_of(category: str) -> str:
    for name, keys in BUCKET_RULES:
        if any(k in category for k in keys):
            return name
    return "其他"


PROMPT = """你是《明日方舟》底层机制知识库的议题聚类器。输入是同一机制主题下的一批"原子论断卡"(JSON 数组)。
这些卡来自主播"神祇读神奇"的录播转写, 全部只是 draft, 你不能用游戏知识判断谁对谁错。

任务: 把回答同一个机制问题的卡聚成"议题"(issue), 并如实标注议题状态。

合并红线(必须遵守):
1. conditions 不同的卡禁止合并进同一议题的同一立场; 条件不同导致结论不同 -> 拆成不同议题或在议题内分行标注条件。
2. applies_to 是具体干员/技能的特例卡, 禁止并入 applies_to=general 的通用议题。
3. claim_type=hypothesis/question 的卡不得被当成结论合并; 有未关闭的 hypothesis/correction -> status=open。
4. claim_type=observation(实战观察)不得与 conclusion(讲解定论)自动视为一致, 除非命题文字几乎相同。
5. 同一推导链(derivation_step 连续、parent_idx 相同)应归入同一议题。

议题状态:
- agreed: 议题内所有 conclusion/observation 命题一致, 无冲突。
- conflict: 议题内存在互相矛盾的命题(如实列出双方 atom_id), 你不裁决对错。
- open: 只有 hypothesis/question, 或证据不足。

输出严格 JSON:
{"issues": [{"title": "议题名", "question": "该议题回答的问题",
  "member_ids": ["原子id..."],
  "status": "agreed|conflict|open",
  "note": "分歧点/条件差异/为什么 open, 没有则空字符串",
  "proposed_canonical": "仅当 status=agreed 且 applies_to 与 conditions 完全一致时, 用一句中文草拟共识命题; 否则空字符串"}]}
member_ids 必须逐字来自输入的 id 字段, 每个输入 id 至多出现在一个议题里。无法归类的 id 不要输出。

输入原子卡:
"""


def compact_atom(a: dict) -> dict:
    return {
        "id": a["atom_id"],
        "type": a["claim_type"],
        "prop": a["proposition"],
        "cond": a.get("conditions") or [],
        "applies_to": a.get("applies_to", "unknown"),
        "parent_idx": a.get("parent_idx"),
        "step": a.get("derivation_step"),
        "params": [{k: p.get(k) for k in ("name", "value_raw", "unit")} for p in a.get("parameters", [])],
        "src": a["source_id"],
    }


def main():
    only_bucket = None
    only_stem = None
    args = sys.argv[1:]
    if "--bucket" in args:
        only_bucket = args[args.index("--bucket") + 1]
    if "--only-stem" in args:
        only_stem = args[args.index("--only-stem") + 1]

    atoms = []
    for f in sorted(OUT_DIR.glob("*.atoms.jsonl")):
        if only_stem and only_stem not in f.name:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            a = json.loads(line)
            a["_bucket"] = bucket_of(a.get("category", ""))
            atoms.append(a)
    if only_bucket:
        atoms = [a for a in atoms if a["_bucket"] == only_bucket]
    print(f"载入原子卡 {len(atoms)} 张")

    buckets = defaultdict(list)
    for a in atoms:
        buckets[a["_bucket"]].append(a)

    # 生成批次任务
    tasks = []  # (bucket, batch_idx, [compact atoms])
    for bname, items in sorted(buckets.items()):
        for i in range(0, len(items), BATCH_SIZE):
            tasks.append((bname, i // BATCH_SIZE, [compact_atom(a) for a in items[i:i + BATCH_SIZE]]))
    print(f"分桶: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(buckets.items())))
    print(f"共 {len(tasks)} 个 LLM 批次")

    results = {}  # (bucket, batch_idx) -> issues
    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0}

    # 断点续跑: 已完成批次从缓存读取
    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    pending = []
    for t in tasks:
        key = f"{t[0]}#{t[1]}"
        if key in cache:
            results[(t[0], t[1])] = cache[key]["issues"]
            print(f"[cache] {key}: {len(cache[key]['issues'])} 议题")
        else:
            pending.append(t)
    print(f"待跑 {len(pending)} 批 (缓存命中 {len(tasks) - len(pending)})")

    def run_task(t):
        bname, bidx, comp = t
        prompt = PROMPT + json.dumps(comp, ensure_ascii=False)
        try:
            out, usage = call_llm(prompt)
            return bname, bidx, out.get("issues", []), usage, None
        except Exception as e:
            return bname, bidx, [], {}, str(e)

    def save_cache():
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    failed = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for bname, bidx, issues, usage, err in ex.map(run_task, pending):
            if err:
                failed.append((bname, bidx, err))
                print(f"[FAIL] {bname}#{bidx}: {err[:150]}", flush=True)
                continue
            results[(bname, bidx)] = issues
            cache[f"{bname}#{bidx}"] = {"issues": issues}
            save_cache()
            for k in usage_tot:
                usage_tot[k] += usage.get(k, 0) or 0
            print(f"[done] {bname}#{bidx}: {len(issues)} 议题", flush=True)
    if failed:
        print(f"警告: {len(failed)} 个批次失败, 其原子将计入 orphan; 重跑脚本可续跑")

    # 校验 + 落盘
    atom_by_id = {a["atom_id"]: a for a in atoms}
    clusters = []
    assigned = set()
    n_bad_id = 0
    for (bname, bidx), issues in sorted(results.items()):
        for j, iss in enumerate(issues):
            valid_ids = []
            for mid in iss.get("member_ids", []):
                if mid in atom_by_id and mid not in assigned:
                    valid_ids.append(mid)
                    assigned.add(mid)
                else:
                    n_bad_id += 1
            if not valid_ids:
                continue
            members = [atom_by_id[i] for i in valid_ids]
            status = iss.get("status", "open")
            # canonical 门槛: agreed + 同 applies_to + 同 conditions + >=2 独立证据(不同时间窗)
            canon = iss.get("proposed_canonical") or ""
            applies = {m.get("applies_to") for m in members}
            conds = {json.dumps(m.get("conditions") or [], ensure_ascii=False, sort_keys=True)
                     for m in members}
            windows = {(m["source_id"], m.get("window", {}).get("start")) for m in members}
            has_open_type = any(m["claim_type"] in ("hypothesis", "question") for m in members)
            if canon and (status != "agreed" or len(applies) > 1 or len(conds) > 1
                          or len(windows) < 2 or has_open_type):
                canon = ""  # 不达标, 丢弃草案
            clusters.append({
                "cluster_id": f"{bname}-{bidx}-{j}",
                "bucket": bname,
                "title": iss.get("title", ""),
                "question": iss.get("question", ""),
                "status": status,
                "note": iss.get("note", ""),
                "member_ids": valid_ids,
                "member_count": len(valid_ids),
                "sources": sorted({m["source_id"] for m in members}),
                "claim_types": sorted({m["claim_type"] for m in members}),
                "proposed_canonical": canon,
                "canonical_status": "draft" if canon else None,
            })

    orphans = [a for a in atoms if a["atom_id"] not in assigned]
    out_path = OUT_DIR / "clusters.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for c in clusters:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # 报告
    by_status = defaultdict(int)
    for c in clusters:
        by_status[c["status"]] += 1
    lines = [
        "# 议题聚类档案 (clusters)",
        "",
        f"- 原子卡总数: {len(atoms)}",
        f"- 议题数: {len(clusters)} (agreed={by_status['agreed']}, conflict={by_status['conflict']}, open={by_status['open']})",
        f"- 入议题原子: {len(assigned)}, 未入议题(orphan): {len(orphans)}, LLM 幻觉 id 丢弃: {n_bad_id}",
        f"- token 用量: prompt={usage_tot['prompt_tokens']}, completion={usage_tot['completion_tokens']}",
        "",
        "## 分桶",
    ]
    for k, v in sorted(buckets.items()):
        n_c = sum(1 for c in clusters if c["bucket"] == k)
        lines.append(f"- {k}: 原子 {len(v)}, 议题 {n_c}")
    lines += ["", "## 冲突议题 (需人工裁决, LLM 不裁)"]
    for c in clusters:
        if c["status"] == "conflict":
            lines.append(f"- [{c['bucket']}] {c['title']} ({c['member_count']}卡) — {c['note']}")
    lines += ["", "## proposed_canonical (仍 draft, 过了门槛)"]
    for c in clusters:
        if c["proposed_canonical"]:
            lines.append(f"- [{c['bucket']}] {c['title']}: {c['proposed_canonical']}")
    (OUT_DIR / "clusters_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"议题 {len(clusters)}, orphan {len(orphans)}, 幻觉id {n_bad_id}")
    print(f"写出 {out_path} 与 clusters_report.md")


if __name__ == "__main__":
    main()
