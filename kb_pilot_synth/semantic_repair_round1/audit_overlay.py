# -*- coding: utf-8 -*-
"""审核覆盖层: 代理在「修复后 30 张随机抽检」中发现的、LLM 漏检的元话语/方法论规则。

背景: LLM 复核只做「只降不升」的单调收紧, 漏检的元话语不会被自动回收。代理逐条读
修复后正文时发现 6 张已复核卡的通则段里仍留着方法论/命名学句子, 在此以**锚句**声明的
方式补上判定 (锚句用于回填真实 idx, 避免索引口径错位; 每条锚句必须唯一命中)。

标签语义与 gate_v2 的 LLM 标签一致:
  meta_discourse -> 移入 `## 待核`(provenance 隔离, 不得当已知), 不进 affirmative
所有条目 reviewer_type=agent, source=audit_spotcheck_30, 可复现。

用法: python audit_overlay.py   # 生成/校验 audit_overlay_llm_miss.jsonl
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")

# (cluster_id, 锚句子串, 标签, 理由)
ITEMS = [
    ("帧时序与计时器-11-13", "打合约就应采用该高精度", "meta_discourse",
     "对做合约的倡导/宣教, 非机制; 该卡通则段整体是数据精度方法论"),
    ("帧时序与计时器-11-13", "不必把142.5算成142", "meta_discourse",
     "精度取舍的操作建议, 不构成游戏机制"),
    ("帧时序与计时器-11-13", "后面很多东西可以有比较好的保障", "meta_discourse",
     "对工作方法的评价, 非机制"),
    ("帧时序与计时器-11-13", "容错可以只留0.1秒", "meta_discourse",
     "留多少容错的操作建议, 非机制参数"),
    ("帧时序与计时器-11-13", "不能马虎的重要基础工作", "meta_discourse",
     "对准备工作的评价性元话语"),
    ("帧时序与计时器-11-13", "会觉得自己算出的东西并不严格", "meta_discourse",
     "讲解者经验谈(心理后果), 非机制"),
    ("帧时序与计时器-11-13", "计算效率很低", "meta_discourse",
     "讲解者经验谈(效率后果), 非机制"),

    ("帧时序与计时器-19-8", "可以通过撤减速", "meta_discourse",
     "调帧操作手法, 非机制命题"),
    ("帧时序与计时器-19-8", "也就可以找到解", "meta_discourse",
     "解谜式推测方法, 非机制命题"),
    ("帧时序与计时器-19-8", "调帧过程需要一帧一帧地调", "meta_discourse",
     "操作流程说明, 非机制命题"),

    ("寻路-10-2", "可以对任何一个怪出题", "meta_discourse",
     "自测出题方法, 非机制"),
    ("寻路-10-2", "正常的怪都可以用来出题", "meta_discourse",
     "自测出题方法, 非机制(同卡内已有多条出题建议被判 meta_discourse)"),

    ("其他-3-22", "没有经验就看不准单位在哪一格", "meta_discourse",
     "观察者经验谈, 非游戏机制"),

    ("帧时序与计时器-63-3", "完成推拉计算需要能推拉合力", "meta_discourse",
     "学习/掌握路径的能力要求清单, 非机制命题"),

    ("索敌-12-3", "相关机制在PRTS实际已有严格解释", "meta_discourse",
     "对 PRTS 的评价, 非机制; 该卡其余命名学条目保留(对术语检索有价值)"),
    ("索敌-12-3", "望文生义到这是排序数据精度上的问题", "meta_discourse",
     "命名学讨论(望文生义), 非机制"),
]


def main():
    cdir = os.path.join(FC1, "cache_items")
    cache = {}
    for fn in os.listdir(cdir):
        if fn.endswith(".json"):
            r = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
            if not r.get("error") and (r.get("result") or {}).get("_text"):
                cache[r["cluster_id"]] = r["result"]

    rows, problems = [], []
    for cid, anchor, label, reason in ITEMS:
        res = cache.get(cid)
        if not res:
            problems.append({"cluster_id": cid, "anchor": anchor, "why": "card_not_in_cache"})
            continue
        hits = [i for i, r in enumerate(res.get("rules") or []) if anchor in (r.get("text") or "")]
        if len(hits) != 1:
            problems.append({"cluster_id": cid, "anchor": anchor,
                             "why": f"anchor_matches_{len(hits)}_rules", "idx": hits})
            continue
        rows.append({"cluster_id": cid, "idx": hits[0], "label": label, "reason": reason,
                     "anchor": anchor, "reviewer_type": "agent",
                     "source": "audit_spotcheck_30"})
    if problems:
        raise SystemExit("anchor problems: " + json.dumps(problems, ensure_ascii=False))
    # 去重(同卡同 idx 只留一条)
    seen, uniq = set(), []
    for r in rows:
        k = (r["cluster_id"], r["idx"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    p = os.path.join(HERE, "audit_overlay_llm_miss.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in sorted(uniq, key=lambda x: (x["cluster_id"], x["idx"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by_card = {}
    for r in uniq:
        by_card.setdefault(r["cluster_id"], []).append(r["idx"])
    print(json.dumps({"out": p, "n_rules": len(uniq), "n_cards": len(by_card),
                      "by_card": by_card}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
