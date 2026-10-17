# -*- coding: utf-8 -*-
"""汇总本阶段(第三轮定向语义修复)的真实 LLM 用量。

来源:
  - events_semantic.jsonl : repair_semantic.py 每卡一行账本 (status ok/error, tokens, t_llm_sec)
  - usage_semantic.json   : 只反映最后一次运行, 仅作交叉校核
  - trial_v2_usage.json   : trial_rag_v2.py 两侧评测的 fresh 计数与 token 聚合
  - answers_cache_v2.json : 评测答案缓存 (本轮新建, 全部为 fresh)

口径说明:
  - error 行(HTTP 429)在网关侧被拒, 未产生可计费的 completion usage, 账本 tokens=null;
    这些尝试的 token 不可恢复, 因此本表报的是**下界**。
  - 纯本地步骤(compute_scope/triage/gate_v2/validate/freeze)零 LLM 调用, 不产生 token。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_jsonl(p):
    if not os.path.isfile(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    ev = load_jsonl(os.path.join(HERE, "events_semantic.jsonl"))
    ok = [e for e in ev if e["status"] == "ok"]
    err = [e for e in ev if e["status"] != "ok"]
    sem_tokens = sum(int(e.get("tokens") or 0) for e in ok)
    sem_sec = round(sum(float(e.get("t_llm_sec") or 0) for e in ok), 1)

    usage_sem = json.load(open(os.path.join(HERE, "usage_semantic.json"), encoding="utf-8"))
    trial = json.load(open(os.path.join(HERE, "trial_v2_usage.json"), encoding="utf-8"))
    cache = json.load(open(os.path.join(HERE, "answers_cache_v2.json"), encoding="utf-8"))
    # 缓存按 (side|qid|corpus_sha) 分键; build1 与 build2 的 corpus_sha 不同, 故 build1 行仍在缓存里
    n_b1_new = sum(1 for k, v in cache.items()
                   if k.startswith("new_gated_v2|") and not v.get("error")
                   and v.get("corpus_sha") != trial["new"]["corpus_sha"])
    n_b2_new = sum(1 for k, v in cache.items()
                   if k.startswith("new_gated_v2|") and not v.get("error")
                   and v.get("corpus_sha") == trial["new"]["corpus_sha"])
    n_b1_old = sum(1 for k, v in cache.items()
                   if k.startswith("old_gated_v1|") and not v.get("error"))
    cache_err = sum(1 for v in cache.values() if v.get("error"))
    vc = json.load(open(os.path.join(HERE, "variance_check.json"), encoding="utf-8"))
    variance_usages = {}
    for v in vc["rows"].values():
        for r in v["runs"]:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                variance_usages[k] = variance_usages.get(k, 0) + int((r.get("usage") or {}).get(k) or 0)
    variance_calls = sum(len(v["runs"]) for v in vc["rows"].values())
    # 评测用量: build1 旧侧(build1 语料未变, 缓存行即 build1) + build1 新侧(缓存里 corpus_sha 不同的那批)
    #   + build2 新侧(当前 corpus_sha) ; 2 行 429 补齐复用 build1 新侧缓存键, 故已含在内
    b1_old_tok = int(trial["usage"]["old"].get("total_tokens") or 0)
    b1_new_tok = sum(int((v.get("usage") or {}).get("total_tokens") or 0)
                     for k, v in cache.items()
                     if k.startswith("new_gated_v2|") and not v.get("error")
                     and v.get("corpus_sha") != trial["new"]["corpus_sha"])
    b2_new_tok = int(trial["usage"]["new"].get("total_tokens") or 0)
    eval_tokens = b1_old_tok + b1_new_tok + b2_new_tok
    eval_sec = round(120.98 + 9.96 + float(trial.get("wall_sec") or 0), 2)

    out = {
        "reviewer_type": "agent",
        "stage": "semantic_repair_round1",
        "model": usage_sem.get("model"),
        "prompt_version": usage_sem.get("prompt_version"),
        "ledger": {
            "semantic_repair": {
                "calls_ok": len(ok),
                "calls_error": len(err),
                "calls_total_attempted": len(ev),
                "totals_tokens_ok_rows": sem_tokens,
                "sum_t_llm_sec_ok_rows": sem_sec,
                "error_kind": "HTTP 429 (网关限流), 20 条; 其 token 用量不可恢复",
                "units_labeled": usage_sem.get("n_labels"),
                "cards_in_scope": usage_sem.get("n_cards_in_scope"),
                "rules_in_scope": usage_sem.get("n_rules_in_scope"),
                "runs": 3,
                "note": "3 遍: --apply(100 ok/20 err, 119412 tok) + 重试(20 ok, 22582 tok) + "
                        "修引用后补跑(5 新调用, 6230 tok); 145 条账本行合计",
            },
            "heldout_eval_v2": {
                "questions": 30,
                "sides": 2,
                "build1": {"calls_ok_old_side": n_b1_old, "calls_ok_new_side": n_b1_new,
                           "calls_error": 2,
                           "tokens_old_side": b1_old_tok, "tokens_new_side": b1_new_tok,
                           "tokens": b1_old_tok + b1_new_tok, "wall_sec": 130.94,
                           "note": "build1 语料: 首轮 60 次调用中 2 次 HTTP 429(X07/N12 新面, 脚本落盘为 "
                                   "abstain+空答), 再用缓存只重跑这 2 行补齐; 该 2 行 token 已并入新侧"},
                "build2": {"calls_ok": n_b2_new, "calls_error": 0, "tokens": b2_new_tok,
                           "wall_sec": float(trial.get("wall_sec") or 0),
                           "note": "加入审核覆盖层(16 条)后重跑新侧 30 题; 旧侧 30 行因语料未变而全部缓存命中"},
                "calls_ok_total": n_b1_old + n_b1_new + n_b2_new + 2,
                "calls_error_total": 2,
                "totals_tokens": eval_tokens,
                "wall_sec_total": eval_sec,
                "model": trial.get("model"),
            },
            "variance_recheck": {
                "questions": 3,
                "reps": 3,
                "calls_ok": variance_calls,
                "calls_error": 0,
                "totals_tokens": int((variance_usages.get("total_tokens") or 0)),
                "note": "variance_check.py: X07/N12/R03 在完全相同输入下各重跑 3 次, 用于分离采样方差",
            },
            "local_only_zero_llm": [
                "compute_scope.py", "triage_e1.py", "gate_v2.py",
                "validate_gates_v2.py", "freeze_v2.py", "dump_ctx.py",
                "spotcheck_v2.py", "spotcheck_worksheet.py", "label_application_check.py",
                "audit_overlay.py",
            ],
        },
        "grand_total_calls_ok": len(ok) + n_b1_old + n_b1_new + n_b2_new + 2 + variance_calls,
        "grand_total_calls_error_attempts": len(err) + 2,
        "grand_total_tokens_lower_bound": sem_tokens + eval_tokens + variance_usages.get("total_tokens", 0),
        "usage_semantic_json_crosscheck": {
            "calls": usage_sem.get("calls"),
            "cache_hit": usage_sem.get("cache_hit"),
            "total_tokens": usage_sem.get("total_tokens"),
            "note": "仅最后一次运行的增量, 不等于本阶段用量; 见 events_semantic.jsonl 聚合",
        },
        "not_counted": [
            "22 条 429 失败尝试的请求 token (网关未返回 usage, 不可恢复): semantic 20 条 + 评测 2 条",
            "重试期间因 cache 命中而未发生的重复调用 (本就不消耗 token; 评测第 2 次 run 命中 58 行)",
            "第二轮(full_candidate_round1)的全部用量, 不在本阶段口径内",
            "本地步骤(scope/triage/gate/validate/freeze/spotcheck/dump_ctx/fix_citations)零 LLM 调用",
        ],
    }
    # ---- 第三轮收尾 (X07 根因修复 + 覆盖判据收紧 + 同源配额评估) ----
    closing = {}
    for tag, label in (("v3", "build3 对照(v1语料 vs build3语料, 配额 all)"),
                       ("v4", "build4 对照(配额 layer_only)"),
                       ("v5", "配额消融(QUOTA_MODE=off, 只跑新面 ctx 改变的 20 题)")):
        p = os.path.join(HERE, "trial_%s_usage.json" % tag)
        if not os.path.isfile(p):
            continue
        t = json.load(open(p, encoding="utf-8"))
        # 只统计**本轮真实发生的调用**的 token: 复用行带着上一代的 usage, 不能计入
        tok = 0
        for s in ("old", "new"):
            fp = os.path.join(HERE, "answers_%s_%s.jsonl" % (tag, s))
            if not os.path.isfile(fp):
                continue
            for line in open(fp, encoding="utf-8"):
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("reused_from"):
                    continue
                tok += int((r.get("usage") or {}).get("total_tokens") or 0)
        closing[tag] = {"label": label, "quota_mode": t.get("quota_mode"),
                        "calls_ok": int(t.get("n_llm_calls_this_run") or 0), "calls_error": 0,
                        "tokens": tok, "wall_sec": t.get("wall_sec"),
                        "old_fresh": t["old"]["n_fresh"], "new_fresh": t["new"]["n_fresh"],
                        "n_docs": {"old": t["old"]["n_docs"], "new": t["new"]["n_docs"]}}
    ap = os.path.join(HERE, "attribution_noquota.json")
    if os.path.isfile(ap):
        a = json.load(open(ap, encoding="utf-8"))
        closing["attribution_noquota"] = {
            "label": "X07 归因: build3 关配额重跑 X07×3/F04/F06/N09",
            "quota_mode": "off", "calls_ok": a["n_calls"], "calls_error": 0,
            "tokens": a["tokens"], "why": a["why"]}
    out["ledger"]["closing_round_build3"] = closing
    cl_calls = sum(v["calls_ok"] for v in closing.values())
    cl_tokens = sum(int(v.get("tokens") or 0) for v in closing.values())
    out["closing_round_calls_ok"] = cl_calls
    out["closing_round_tokens"] = cl_tokens
    out["grand_total_calls_ok"] += cl_calls
    out["grand_total_tokens_lower_bound"] += cl_tokens
    out["not_counted"].append(
        "关配额/单变体消融脚本按 **ctx 指纹** 缓存, ctx 未变的题直接复用上一代答案行, 因此这些数字"
        "只统计真的发生的调用, 不是 30 题×2 面的全量重跑")
    json.dump(out, open(os.path.join(HERE, "usage_ledger_v2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in ("grand_total_calls_ok", "grand_total_calls_error_attempts",
                                         "grand_total_tokens_lower_bound", "closing_round_calls_ok",
                                         "closing_round_tokens")}, ensure_ascii=False))
    print(json.dumps(out["ledger"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
