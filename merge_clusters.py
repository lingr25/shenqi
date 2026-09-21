# -*- coding: utf-8 -*-
"""merge_clusters.py - 跨批次重复议题合并 (第二轮半)

cluster_atoms.py 按 50 张/批送 LLM, 同一议题被切到不同批次会裂成两簇。
本轮把同一 bucket 内的议题摘要再送一轮 LLM, 只做"是否为同一议题"的归并判断,
然后确定性合并 member_ids / 状态(conflict > open > agreed) / 重跑 canonical 门槛。

输出: knowledge_pilot/clusters_merged.jsonl + clusters_merged_report.md
环境变量: GROK_API_KEY (必需), GROK_BASE, GROK_MODEL
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

BATCH_SIZE = 60
WORKERS = int(os.environ.get("CLUSTER_WORKERS", os.environ.get("MERGE_WORKERS", "16")))
CACHE_PATH = OUT_DIR / ".merge_cache.json"

PROMPT = """你是《明日方舟》机制知识库的议题归并器。之前一批"原子论断卡"被分成了若干"议题簇", 但分桶时是分批处理的, 同一个议题可能被重复聚成两簇。
输入是同一机制主题下的议题簇列表(含每簇的代表命题)。

任务: 判断哪些议题簇实际在讲同一个机制问题, 应当合并。

归并红线:
1. 只有"回答同一个问题且立场/条件相容"的簇才能合并; 仅仅是主题相关(都讲索敌)不够。
2. conditions / applies_to / 精度前提不同的簇禁止合并(如 0.1 精度 vs 0.001 精度)。
3. 一个是结论簇、一个是该结论的推导过程簇, 若命题指向同一问题可合并。
4. 拿不准就不合并, 宁多勿并。

输出严格 JSON:
{"merge_groups": [["cluster_id_a", "cluster_id_b"], ...]}
每个 merge_group 列出应合并为一簇的全部 cluster_id; 不需要合并的簇不要出现。没有可合并的就返回空数组。

输入议题簇:
"""


def main():
    clusters = [json.loads(l) for l in (OUT_DIR / "clusters.jsonl").read_text(encoding="utf-8").splitlines()]
    atoms = {}
    for f in OUT_DIR.glob("*.atoms.jsonl"):
        for l in f.read_text(encoding="utf-8").splitlines():
            a = json.loads(l)
            atoms[a["atom_id"]] = a

    # 每簇摘要: 标题 + 问题 + 状态 + 权重最高的 3 条代表命题
    summaries = {}
    for c in clusters:
        mem = [atoms[i] for i in c["member_ids"] if i in atoms]
        mem.sort(key=lambda a: -a.get("retrieval_weight", 0))
        reps = [m["proposition"][:120] for m in mem[:3]]
        summaries[c["cluster_id"]] = {
            "id": c["cluster_id"], "title": c["title"], "question": c["question"],
            "status": c["status"], "n": c["member_count"], "reps": reps,
        }

    buckets = defaultdict(list)
    for c in clusters:
        buckets[c["bucket"]].append(c["cluster_id"])

    tasks = []
    for bname, ids in sorted(buckets.items()):
        for i in range(0, len(ids), BATCH_SIZE):
            tasks.append((bname, i // BATCH_SIZE, [summaries[x] for x in ids[i:i + BATCH_SIZE]]))
    print(f"{len(clusters)} 簇, {len(tasks)} 个归并批次")

    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    def run_task(t):
        bname, bidx, sums = t
        key = f"{bname}#{bidx}"
        if key in cache:
            return key, cache[key], None
        prompt = PROMPT + json.dumps(sums, ensure_ascii=False)
        try:
            out, _ = call_llm(prompt)
            return key, out.get("merge_groups", []), None
        except Exception as e:
            return key, None, str(e)

    merge_groups = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for key, groups, err in ex.map(run_task, tasks):
            if err:
                print(f"[FAIL] {key}: {err[:150]}", flush=True)
                continue
            if key not in cache:
                cache[key] = groups
                CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            merge_groups.extend(groups)
            print(f"[done] {key}: {len(groups)} 组", flush=True)

    # 确定性合并: union-find
    parent = {c["cluster_id"]: c["cluster_id"] for c in clusters}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    valid_ids = set(parent)
    n_bad = 0
    for g in merge_groups:
        g = [x for x in g if x in valid_ids]
        if len(g) < 2:
            if g:
                n_bad += 1
            continue
        root = find(g[0])
        for x in g[1:]:
            parent[find(x)] = root

    by_root = defaultdict(list)
    for c in clusters:
        by_root[find(c["cluster_id"])].append(c)

    STATUS_RANK = {"conflict": 2, "open": 1, "agreed": 0}
    merged = []
    for root, cs in sorted(by_root.items()):
        member_ids = []
        seen = set()
        for c in cs:
            for mid in c["member_ids"]:
                if mid not in seen:
                    member_ids.append(mid)
                    seen.add(mid)
        status = max((c["status"] for c in cs), key=lambda s: STATUS_RANK.get(s, 1))
        members = [atoms[i] for i in member_ids if i in atoms]
        # 重跑 canonical 门槛
        canon = next((c["proposed_canonical"] for c in cs if c.get("proposed_canonical")), "")
        applies = {m.get("applies_to") for m in members}
        conds = {json.dumps(m.get("conditions") or [], ensure_ascii=False, sort_keys=True)
                 for m in members}
        windows = {(m["source_id"], m.get("window", {}).get("start")) for m in members}
        has_open_type = any(m["claim_type"] in ("hypothesis", "question") for m in members)
        if canon and (status != "agreed" or len(applies) > 1 or len(conds) > 1
                      or len(windows) < 2 or has_open_type):
            canon = ""
        merged.append({
            "cluster_id": root,
            "bucket": cs[0]["bucket"],
            "title": cs[0]["title"] + (f" [合并{len(cs)}簇]" if len(cs) > 1 else ""),
            "question": cs[0]["question"],
            "status": status,
            "note": " | ".join(c["note"] for c in cs if c.get("note")),
            "member_ids": member_ids,
            "member_count": len(member_ids),
            "sources": sorted({m["source_id"] for m in members}),
            "claim_types": sorted({m["claim_type"] for m in members}),
            "merged_from": [c["cluster_id"] for c in cs] if len(cs) > 1 else [],
            "proposed_canonical": canon,
            "canonical_status": "draft" if canon else None,
        })

    out = OUT_DIR / "clusters_merged.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for c in merged:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    n_merged = sum(1 for c in merged if c["merged_from"])
    by_status = defaultdict(int)
    for c in merged:
        by_status[c["status"]] += 1
    lines = [
        "# 议题归并报告 (clusters_merged)",
        "",
        f"- 归并前: {len(clusters)} 簇 -> 归并后: {len(merged)} 簇 (合并发生 {n_merged} 处, LLM 无效建议 {n_bad})",
        f"- 状态: agreed={by_status['agreed']}, conflict={by_status['conflict']}, open={by_status['open']}",
        f"- canonical 草案: {sum(1 for c in merged if c['proposed_canonical'])} 条 (仍 draft)",
        "",
        "## 发生的合并",
    ]
    for c in merged:
        if c["merged_from"]:
            lines.append(f"- {c['cluster_id']} <= {' + '.join(c['merged_from'])}: {c['title']} ({c['member_count']}卡)")
    lines += ["", "## 冲突议题"]
    for c in merged:
        if c["status"] == "conflict":
            lines.append(f"- [{c['bucket']}] {c['title']} ({c['member_count']}卡) — {c['note'][:200]}")
    (OUT_DIR / "clusters_merged_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(clusters)} -> {len(merged)} 簇, 合并 {n_merged} 处")


if __name__ == "__main__":
    main()
