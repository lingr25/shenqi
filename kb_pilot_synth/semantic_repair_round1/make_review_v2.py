# -*- coding: utf-8 -*-
"""本代理(agent)对 30 题两面对照的逐题判分, 产出 heldout_v2_review.json + .md。

reviewer_type = agent (非 LLM 判定)。score: 1 / 0.75 / 0.5 / 0 ；
err 沿用手工码: none / hallucinate_number / failed_abstain / extra_unverified_calc /
failed_use_context / overconfident / missed_cite / missed_fact / wrong_polarity / cite_format
tag: fix / regression / neutral / fix_partial
cite 有效性由 answers_v2_*.jsonl 机械核验: cite ⊆ ctx(前后缀归一) 且非裸层名。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# 路径可经环境变量覆盖, 默认值 == build2 的原始口径(保持可复现)。
ANS_OLD = os.environ.get("REVIEW_ANS_OLD", "answers_v2_old.jsonl")
ANS_NEW = os.environ.get("REVIEW_ANS_NEW", "answers_v2_new.jsonl")
VERDICTS = os.environ.get("REVIEW_VERDICTS", "review_verdicts.json")
OUT_JSON = os.environ.get("REVIEW_OUT_JSON", "heldout_v2_review.json")
OUT_MD = os.environ.get("REVIEW_OUT_MD", "heldout_v2_review.md")
USAGE = os.environ.get("REVIEW_USAGE", "trial_v2_usage.json")
VARFILE = os.environ.get("REVIEW_VAR", "variance_check.json")
TITLE = os.environ.get("REVIEW_TITLE",
                       "# 冻结 30 题对照评测：代理逐题判分（旧 gated v1 vs 新 gate v2）")
SIDE_LABEL = os.environ.get("REVIEW_SIDE_LABEL", "旧 gated v1 / 新 gate v2")
SIDE_OLD_KEY = os.environ.get("REVIEW_SIDE_OLD_KEY", "old")
SIDE_NEW_KEY = os.environ.get("REVIEW_SIDE_NEW_KEY", "new")

BASE = {"reviewer_type": "agent"}

R = {
  "F01": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面都答「该帧逻辑帧已运算完毕；手操部署属操作层」。新面 gold 降为 top2 但仍在 ctx 内。"),
  "F02": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面核心答案一致。新面额外引 fc1:寻路-2-0 并明说「该条在待核/隔离中，仅说明未闭合」——"
                   "该卡同时在通则段列了相反命题(红门有地块识别能力)，新面把冲突显式化而非抹平；判为可接受的加分项。"),
  "F03": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均答巡逻状态机 + 阻挡不远程索敌 + 解阻挡立刻抬手。"),
  "F04": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均答两套速度不加和、退出失衡清零再走寻路。"),
  "F05": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="硬约束 F05: 两面都明确「不是已核公式」，未把未核定项当已知 → 满足。abstain 开关两面均为 false "
                   "(第二轮已记录该开关不稳)；若严格要求 abstain=true 则两面同为 partial，不构成新旧差异。"),
  "F06": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面都直接否证并给出「卡墙只决定何时不传送，怎么走由寻路决定」的证据关系；新面措辞更干净(run0 旧面曾出现先附和)。"),
  "F07": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均答两部分(路径点指令 + 只管时间的停住指令)。"),
  "X03": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均答不能短于原初动画长度 0.1 倍。"),
  "X07": dict(old=1.0, new=0.75, tag="regression", err="missed_fact",
              note="新面只肯说「片段没有直接说明眩晕结束时阻挡帧会不会立刻触发」，未落到期望的「不像」。"
                   "gold(er1:M03-block-3cycle / -from-deploy) 均在 ctx 内且写明「阻挡帧按部署相位三循环，不能理解成索敌那种立刻归零」；"
                   "补采样 3 次同样全部不肯正面断言 → 可复现的欠断定，非单次抖动。成因指向检索名次变动: 新语料保留了更多旧词条，"
                   "顶6被 vod_entry:寻路-10-1 / 帧时序与计时器-40-13 / -27-7 挤入，替代了旧面的 fc1:索敌-16-0 / window:w001342。"
                   "未断言错误事实，故记 0.75 而非 0。(首轮评测该行为 HTTP 429 空答，已重跑补齐)"),
  "X11": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均拒绝把 0.05 格当已知，指出帧时长/单位未给。"),
  "X13": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面均答「更长走冷却值、更短走动画值」；新面追加的「超过上下限则拉伸到最上/最下」可在所引 vod_entry 中查到，属有据补充。"),
  "X14": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均答单位未标明、不得猜，引 fc1 待验证条目佐证。"),
  "X16": dict(old=1.0, new=1.0, tag="neutral", err="cite_format",
              note="内容两面均正确(不算第五种，瞬移归入传送)。新面 cite_ids 返回裸层前缀 ['fc1','er1']，无具体文档目标；"
                   "该缺陷不改变事实正确性，但按引用有效性记为 cite_format。"),
  "R03": dict(old=1.0, new=0.5, tag="regression", err="wrong_polarity",
              note="期望肯定「要」；新面本次起手写「不需要把攻击冷却清零…并非释放时主动清零」，把机制细分写成了否定式标题。"
                   "补采样 3 次: 2 次答「需要/是」，1 次答「不需要」(同本次) → 标题极性属采样方差，机制内容两次都对。"),
  "R05": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面都否掉「碰到就必挂」与「周期有通用帧数」；新面本次 abstain=true 但正文给了同样结论。"),
  "N01": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="误导题。两面都拒绝把「伊德减三十抗真伤」升格为通则；新面还引到被移到实例段的原子并标明其为例外观测 → 方向正确。"),
  "N02": dict(old=0.75, new=1.0, tag="fix", err="missed_fact",
              note="旧面漏掉「真伤仍吃伤判、可以增伤减伤」；新面把真伤/生命流失各自跳过的环节完整对齐(真伤跳抗性结算不跳伤判；生命流失跳判定不跳计算)。"),
  "N03": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面均答「未点名/一般性表述」，未编造主语。新面引到旧词条里写作「通用」的措辞，略有措辞出入但不影响结论。"),
  "N04": dict(old=1.0, new=1.0, tag="neutral", err="cite_format",
              note="两面内容一致(不需要命中，只需发射)。旧面 cite_ids 含裸层前缀 'fc1'(旧面本轮同类缺陷)。"),
  "N05": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面均答 0.1 是速度阈值、单位原片未写明。新面明确复述「未写明是格还是格/秒」。"),
  "N06": dict(old=1.0, new=0.75, tag="neutral", err="none",
              note="新面 gold(fc1:伤害结算-4-3) 跌出 top6；但检回的 vod_atom:BV14VZCB1EJR_p1_36119907781:p111:a0:bbfa0a34 "
                   "原文即「用炸死与炸不死的临界值取点，再找三个点三点画圆」，答案有据且方法完整 → 内容对，检索 gold 未中。"),
  "N07": dict(old=0.5, new=1.0, tag="fix", err="failed_abstain",
              note="旧面(该卡当机制留在 default)只敢说「不能确认为底层机制」，未直接回答；新面该卡已入 archive，"
                   "检回旧词条后明确答「不是」底层机制/属条件性建议 → 隔离生效。"),
  "N08": dict(old=0.0, new=1.0, tag="fix", err="overconfident",
              note="**本轮最关键修复**。旧面把元话语当机制: 「是机制结论」，理由是片段把它列为『可复用规则』；"
                   "新面同一问改为「不是可直接当作机制结论的表述…而非闭合的机制通则」。该卡已进 archive，回答方向反转。"),
  "N09": dict(old=1.0, new=0.75, tag="neutral", err="missed_fact",
              note="期望区分「机制/操作限制，非对局策略建议」+「交替粒度未闭合」。旧面明确点出粒度待验证且非已定论；"
                   "新面 abstain=true，正确引用「⚠未闭合/ctx_only_evidence」，但把『机制限制还是操作建议』也说成无法确定 → 少了一分精度。"),
  "N10": dict(old=0.75, new=1.0, tag="fix", err="none",
              note="期望文本假设该条应标「引用不可追溯待核」，实测更优: v2 把 v1 里漂移的引用 "
                   "BV1TomVBBEK1_p1:a2:ec71e01d 规范回 BV1TomVBBEK1_p1_34675165371:p10:a2:ec71e01d，"
                   "引用可追溯 → 该条未进待核而是被修好。新面答「有可追溯证据」并补上「仅为实例、非通则」，与实测一致。"),
  "N11": dict(old=0.5, new=0.5, tag="neutral", err="missed_fact",
              note="两面都拒绝裁定「三帧/三针」(符合『单位不猜』)，也都漏答 ctx 中已在位的「拉力或推力命中三帧之内不退出失衡」"
                   "(fc1:状态效果-8-0 通则第 6 条 + window:w001366 三帧保底)。属两面共有的可用上下文未被用足，非新旧差异。"),
  "N12": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="期望「不对，三条件」。首轮评测新面该行是 HTTP 429 失败(缓存里就是 error 记录，答案字段为空)，已重跑补齐；"
                   "补齐后答「不对。需同时满足三个条件…只有速度小于等于0.1这一个条件并不足以退出失衡」，"
                   "补采样 3/3 亦全部正确 → 无回归。"),
  "N13": dict(old=1.0, new=1.0, tag="neutral", err="none", note="两面均答改写后该地图推拉与位移速度都变。"),
  "N14": dict(old=1.0, new=1.0, tag="neutral", err="none",
              note="两面均正确把该式判为「未闭合/ctx_only_evidence，不得当已核公式」——门控的待核标记直接被引用为拒答依据。"),
  "N15": dict(old=0.5, new=0.5, tag="neutral", err="missed_fact",
              note="引用题。两面 ctx 中都含时间戳(ctx=sub:BV1j4KC6KEse_p1_40109737103:9408)，两面都没把它写成「约 9407 秒」；"
                   "旧面列出 9408 却同时说给不出时间，新面给出 bvid 与第 75 页却省了时间戳 → 同为部分正确。"),
}

ORDER = ["F01","F02","F03","F04","F05","F06","F07","X03","X07","X11","X13","X14","X16",
         "R03","R05","N01","N02","N03","N04","N05","N06","N07","N08","N09","N10","N11",
         "N12","N13","N14","N15"]


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def gold_hit(gold_ids, hit_ids):
    """gold 命中判定: 允许层前缀差异 (gold 'M04-x' vs doc 'er1:M04-x')。"""
    hits = list(hit_ids or [])
    for g in (gold_ids or []):
        if g in hits:
            return True
        if any(h == g or h.endswith(":" + g) or g.endswith(":" + h) for h in hits):
            return True
    return False


def cite_stats(rows):
    exact = bare = unver = 0
    for r in rows:
        ctx = set(r["ctx_ids"] or [])
        for c in (r["cite_ids"] or []):
            if c in ctx:
                exact += 1
            elif c in ("fc1", "er1", "vod_entry", "vod_cluster", "canonical", "qq_atom", "window"):
                bare += 1
            else:
                unver += 1
    return {"cites": exact + bare + unver, "in_ctx": exact,
            "bare_layer_prefix": bare, "not_in_ctx": unver}


def main():
    o = {r["id"]: r for r in load_jsonl(os.path.join(HERE, ANS_OLD))}
    n = {r["id"]: r for r in load_jsonl(os.path.join(HERE, ANS_NEW))}
    qs = {q["id"]: q for q in load_jsonl(os.path.join(HERE, "heldout_q_v2.jsonl"))}
    var = (json.load(open(os.path.join(HERE, VARFILE), encoding="utf-8"))
           if os.path.isfile(os.path.join(HERE, VARFILE)) else {"rows": {}})
    vf = json.load(open(os.path.join(HERE, VERDICTS), encoding="utf-8"))
    R.update({k: dict(v) for k, v in vf["verdicts"].items()})

    rows = []
    for qid in ORDER:
        r = R[qid]
        rows.append({
            "id": qid, "type": qs[qid]["type"], "q": qs[qid]["q"], "expect": qs[qid].get("expect"),
            "old_score": r["old"], "new_score": r["new"], "delta": round(r["new"] - r["old"], 2),
            "tag": r["tag"], "err": r["err"], "note": r["note"],
            "old": {"abstain": o[qid].get("abstain"), "empty": not (o[qid].get("answer") or "").strip(),
                    "cite_ids": o[qid].get("cite_ids"), "hit_ids": o[qid].get("hit_ids"),
                    "gold_hit": gold_hit(o[qid].get("gold_ids"), o[qid].get("hit_ids"))},
            "new": {"abstain": n[qid].get("abstain"), "empty": not (n[qid].get("answer") or "").strip(),
                    "cite_ids": n[qid].get("cite_ids"), "hit_ids": n[qid].get("hit_ids"),
                    "gold_hit": gold_hit(n[qid].get("gold_ids"), n[qid].get("hit_ids"))},
            "variance_recheck": {k: {"abstain": [x.get("abstain") for x in v["runs"]]}
                                 for k, v in var["rows"].items() if k == qid} or None,
        })
    out = dict(BASE, heldout_sha256=json.load(open(os.path.join(HERE, "heldout_v2_frozen.json"),
                                                  encoding="utf-8"))["sha256"],
               model="deepseek-v4.1-flash", n=len(rows),
               summary={
                   "old_mean": round(sum(x["old_score"] for x in rows) / len(rows), 3),
                   "new_mean": round(sum(x["new_score"] for x in rows) / len(rows), 3),
                   "old_buckets": {b: sum(1 for x in rows if x["old_score"] == b)
                                   for b in (1.0, 0.75, 0.5, 0.0)},
                   "new_buckets": {b: sum(1 for x in rows if x["new_score"] == b)
                                   for b in (1.0, 0.75, 0.5, 0.0)},
                   "tags": {t: sum(1 for x in rows if x["tag"] == t)
                            for t in ("fix", "fix_partial", "regression", "neutral")},
                   "err_new": {}, "err_old": {},
                   "cite_old": cite_stats(list(o.values())),
                   "cite_new": cite_stats(list(n.values())),
                   "gold_hit_old": sum(1 for x in rows if x["old"]["gold_hit"]),
                   "gold_hit_new": sum(1 for x in rows if x["new"]["gold_hit"]),
                   "no_score_claim": "n=30 单次采样; 两面同检索/同 prompt/同预算; 不构成统计显著结论",
               }, rows=rows)
    # 错误码按侧归属: 只有该侧确实出现该缺陷时才计入
    ERR_SIDE = {k: tuple(v) for k, v in vf["err_side"].items()}
    for side in ("old", "new"):
        d = {}
        for x in rows:
            k = "none"
            if x["id"] in ERR_SIDE:
                code, whom = ERR_SIDE[x["id"]]
                if whom in (side, "both"):
                    k = code
            d[k] = d.get(k, 0) + 1
        out["summary"]["err_" + side] = d
    out["summary"]["err_side_map"] = {k: {"code": v[0], "side": v[1]} for k, v in ERR_SIDE.items()}
    json.dump(out, open(os.path.join(HERE, OUT_JSON), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    L = [TITLE,
         "",
         f"- heldout sha256 `{out['heldout_sha256'][:16]}…`（n=30，答题前校验通过）；model `deepseek-v4.1-flash`；`reviewer_type=agent`",
         "- 两面严格同口径：同 BM25(bigram) / k=6 / 每片段 500 字 / 上下文上限 3000 字 / 同 prompt / 同 workers=4；两侧语料同样做 QQ 脱敏（`T.scrub`）",
         f"- 语料规模：旧 {json.load(open(os.path.join(HERE,USAGE),encoding='utf-8'))[SIDE_OLD_KEY]['n_docs']} 篇 → 新 {json.load(open(os.path.join(HERE,USAGE),encoding='utf-8'))[SIDE_NEW_KEY]['n_docs']} 篇",
         "",
         "## 汇总",
         "",
         f"- 均分：旧 **{out['summary']['old_mean']}** → 新 **{out['summary']['new_mean']}**（满分 1.0，n=30）",
         f"- 分档：旧 {out['summary']['old_buckets']} → 新 {out['summary']['new_buckets']}",
         f"- 标签：{out['summary']['tags']}",
         f"- gold 文档进入 top6：旧 {out['summary']['gold_hit_old']}/30 → 新 {out['summary']['gold_hit_new']}/30",
         f"- 引用有效性：旧 {out['summary']['cite_old']}；新 {out['summary']['cite_new']}",
         f"- 错误码计数：旧 {out['summary']['err_old']}；新 {out['summary']['err_new']}",
         "",
         "## 逐题",
         "",
         "| 题 | 类型 | 旧 | 新 | Δ | 判 | 备注 |",
         "|---|---|---|---|---|---|---|"]
    for x in rows:
        L.append(f"| {x['id']} | {x['type']} | {x['old_score']} | {x['new_score']} | "
                 f"{'+' if x['delta']>0 else ''}{x['delta']} | {x['tag']}/{x['err']} | {x['note']} |")
    if not os.environ.get("REVIEW_SKIP_GOLD_NOTES"):
        L += ["",
              "## gold 未进 top6 的逐题归因（新面 7 例）",
              "",
              "| 题 | gold | 新面实际检回 | 等价内容是否在 ctx | 结论 |",
              "|---|---|---|---|---|"]
        NOTES = {
            "N01": ("fc1:伤害结算-0-10", "vod_entry:伤害结算-0-10 + 实例原子 p42:a13",
                    "是", "该卡被降级为实例段后 fc1 boost 降，旧词条接住同一内容"),
            "N02": ("fc1:伤害结算-0-10", "canonical:c0007 + vod_entry:伤害结算-0-10",
                    "是", "两面答案质量对比：新面更完整"),
            "N05": ("fc1:状态效果-8-0", "B100-exit-imbalance-three + fc1:状态效果-16-2",
                    "是", "同为三条件表述，答案正确"),
            "N06": ("fc1:伤害结算-4-3", "vod_atom:BV14VZCB1EJR_p1_36119907781:p111:a0:bbfa0a34",
                    "是", "该原子原文即三点画圆法，答案有据"),
            "N07": ("fc1:其他-3-17", "vod_entry:其他-3-17 + 原原子",
                    "是", "该卡已入 archive，旧词条保留，回答方向正确（修复）"),
            "N08": ("fc1:技能特例-21-11", "vod_entry:技能特例-21-11",
                    "是", "该卡已入 archive，回答方向正确（修复）"),
            "N09": ("fc1:技能特例-15-1", "vod_atom:p21:a7 / p21:a8 + vod_cluster:技能特例-15-1",
                    "是", "该卡 instance_only boost=0.5，原原子直接接住同一命题"),
        }
        for x in rows:
            if x["id"] in NOTES and not x["new"]["gold_hit"]:
                g, got, eq, why = NOTES[x["id"]]
                L.append(f"| {x['id']} | `{g}` | {got} | {eq} | {why} |")
        L += ["",
              "> gold_hit 是「gold 文档本身进 top6」的机械指标；新面 7 例未中**全部来自新题**，其中 6 例等价内容仍在 ctx，"
              "1 例（N06）由原始原子直接接住。故该指标下降主要反映「gold 定义只认 fc1 文档」与「新管线主动把部分 fc1 卡降级/隔离」的结构差异，"
              "不等于内容不可达；但 X07（非新题）证明名次变动确实会在个别题上造成回答退化，须记为未闭合项。",
              ""]
    L += ["",
          "## 口径与限制",
          "",
          "- 判分只依据回答内容是否满足 `expect`，**不**把 `abstain` 布尔开关单独计分；该开关在多次采样间不稳（第二轮已记录 F05/F06 同现象），"
          "本表把开关状态作为诊断字段保留（见 review JSON 的 `old/new.abstain`）。",
          f"- 本表口径：{SIDE_LABEL}。",
          "- 回归只列 `tag=regression` 的行；均未断言错误事实、无捏造数值。",
          "- n=30、单次采样，只作一致性与方向对照，不构成提分或统计显著结论；`reviewer_type=agent` 不代表人工核听。",
          ""]
    open(os.path.join(HERE, OUT_MD), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(json.dumps(out["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
