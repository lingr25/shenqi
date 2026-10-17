# -*- coding: utf-8 -*-
"""用量账本: 只报可核对的数, 明确写出「不含/不可恢复」的部分。

原则:
  - 主/重试段快照(run_summary_*.json)与 events.jsonl 是两套口径, 不得相加当总计费。
  - events.jsonl 是逐 cluster 事件账本: ok 事件带 tokens, 失败尝试记 0 tokens,
    失败尝试的真实消耗不可恢复 -> 只能报「≥」。
  - 其他 pilot 轮的用量(usage_all.json 等)单独列出, 不计入本轮。
"""
import collections
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.dirname(HERE)


def j(p, default=None):
    p = p if os.path.isabs(p) else os.path.join(HERE, p)
    if not os.path.isfile(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def events(p):
    n = collections.Counter()
    tok = collections.Counter()
    zero = 0
    ts = []
    hour = collections.Counter()
    if not os.path.isfile(p):
        return None
    for l in open(p, encoding="utf-8"):
        d = json.loads(l)
        s = d.get("status") or "?"
        t = int(d.get("tokens") or 0)
        n[s] += 1
        tok[s] += t
        if t == 0:
            zero += 1
        if d.get("ts"):
            ts.append(d["ts"])
            hour[datetime.datetime.fromtimestamp(d["ts"]).strftime("%m-%d %H")] += 1
    return {"n_by_status": dict(n), "tokens_by_status": dict(tok),
            "n_zero_token_events": zero,
            "tokens_ok_only": tok.get("ok", 0),
            "span": [datetime.datetime.fromtimestamp(min(ts)).strftime("%m-%d %H:%M:%S"),
                     datetime.datetime.fromtimestamp(max(ts)).strftime("%m-%d %H:%M:%S")] if ts else None,
            "events_by_hour": dict(sorted(hour.items()))}


def main():
    ev = events(os.path.join(HERE, "events.jsonl"))
    ev_main = events(os.path.join(HERE, "events_snapshot_at_main_done.jsonl"))
    main_s = j("run_summary_main.json", {}).get("usage", {})
    retry_s = j("run_summary_retry.json", {}).get("usage", {})
    usage_now = j("usage.json", {})
    partial = j("usage_after_main_overwritten_by_retry.json", {})
    trial = j("trial_usage.json", {})
    trial40 = (j("usage_total.json", {}) or {}).get("trial_eval_40", {})
    all_pilot = j(os.path.join(PILOT, "usage_all.json"), {}) or {}
    retest = j(os.path.join(PILOT, "retest_round2/usage.json"), {}) or {}
    cross = j(os.path.join(PILOT, "cross_eval_round1/usage.json"), {}) or {}
    b100 = j(os.path.join(PILOT, "batch100_round2/usage.json"), {}) or {}

    def t(u):
        return int((u or {}).get("total_tokens") or 0)

    old_t = t((retest.get("old") or {}).get("usage")) + t((retest.get("new") or {}).get("usage"))
    old_c = int(((retest.get("old") or {}).get("usage") or {}).get("calls") or 0) \
        + int(((retest.get("new") or {}).get("usage") or {}).get("calls") or 0)
    cross_t = t((cross.get("old") or {}).get("usage")) + t((cross.get("new") or {}).get("usage"))
    cross_c = int(((cross.get("old") or {}).get("usage") or {}).get("calls") or 0) \
        + int(((cross.get("new") or {}).get("usage") or {}).get("calls") or 0)
    gated = j("trial_gated_usage.json", {}) or {}
    # 真实付费次数从 answers 落盘行反推(每行若带 usage.total_tokens 即为一次真实调用);
    # 首轮崩溃前完成的 old 侧 + 第二轮 new 侧, 第三轮全部命中缓存。不能只看末轮 n_fresh。
    def paid(name):
        n = 0
        fp = os.path.join(HERE, name)
        if not os.path.isfile(fp):
            return 0
        for l in open(fp, encoding="utf-8"):
            if not l.strip():
                continue
            row = json.loads(l)
            if int((row.get("usage") or {}).get("total_tokens") or 0) > 0:
                n += 1
        return n
    g_old_fresh = paid("answers_old_gatedrun.jsonl")
    g_new_fresh = paid("answers_new_gated.jsonl")
    trial_t = t((trial.get("old") or {}).get("usage")) + t((trial.get("new") or {}).get("usage"))
    trial_c = int(((trial.get("old") or {}).get("usage") or {}).get("calls") or 0) \
        + int(((trial.get("new") or {}).get("usage") or {}).get("calls") or 0)

    inround = {
        "eval_trial_rag_gated_first_run": {
            "fresh_calls_total": int(g_old_fresh) + int(g_new_fresh),
            "old_fresh_calls": g_old_fresh, "new_fresh_calls": g_new_fresh,
            "tokens_fresh_total": t((gated.get("old") or {}).get("usage"))
            + t((gated.get("new") or {}).get("usage")),
            "note": ("首次 gated 运行 7 old + 7 new 为真实调用; 第二次运行语料等同(corpus_sha 未变)"
                     "全部命中 answers_cache.json, 0 次新调用"),
        },
        "generation_events_ledger": ev,
        "generation_events_ledger_at_main_done": ev_main,
        "run_summary_main_usage": main_s,
        "run_summary_retry_usage": retry_s,
        "usage_json_now_overwritten_by_retry": usage_now,
        "usage_partial_midretry_snapshot": partial,
        "eval_run_trial_eval_40calls": trial40,
        "eval_trial_rag_this_round": {
            "calls": trial_c, "total_tokens": trial_t,
            "retrieve_only": trial.get("retrieve_only"),
            "old_tokens": t((trial.get("old") or {}).get("usage")),
            "new_tokens": t((trial.get("new") or {}).get("usage")),
        },
    }
    prior = {
        "v1_v2_v3_pilot": all_pilot.get("totals"),
        "batch100_round2": {"api_calls": b100.get("api_calls"),
                            "note": b100.get("note")},
        "retest_round2_26calls": {"calls": old_c, "total_tokens": old_t},
        "cross_eval_round1_40calls": {"calls": cross_c, "total_tokens": cross_t},
        "evidence_round1": {"api_calls": 0, "note": "纯本地证据整理, 无 usage 文件"},
    }
    verifiable_inround = (ev or {}).get("tokens_ok_only", 0)
    prior_tok = sum(int((prior[k] or {}).get("total_tokens") or 0)
                    for k in ("v1_v2_v3_pilot", "retest_round2_26calls", "cross_eval_round1_40calls"))
    gtok = inround["eval_trial_rag_gated_first_run"]["tokens_fresh_total"]
    eval_tok = int(trial40.get("old_tokens") or 0) + int(trial40.get("new_tokens") or 0) + trial_t + gtok
    out = {
        "reviewer_type": "agent",
        "endpoint": "https://aitreez.com/v1", "model": "deepseek-v4.1-flash",
        "in_round_full_candidate_round1": inround,
        "prior_pilot_rounds_separate": prior,
        "verifiable_totals": {
            "in_round_generation_tokens_ge": verifiable_inround,
            "in_round_eval_tokens": eval_tok,
            "prior_rounds_tokens": prior_tok,
            "repo_wide_tokens_ge": verifiable_inround + eval_tok + prior_tok,
            "why_ge": ("events.jsonl 把 108 次失败尝试(429/SSL)记为 0 tokens, 其真实消耗不可恢复; "
                       "events 早于主运行开始(12-worker 波次), 故不能与主/重试快照相加当总计费。"),
        },
        "not_counted": [
            "108 次失败尝试的真实 tokens (events 记 0, 无 usage 回包)",
            "本轮之前的冒烟测试调用 (无落盘记录)",
            "run_summary_main 的 cache_hit 121 条: 主运行计数器未计其 tokens, 但 events 账本计入了 -> 两口径差 301,036",
            "endpoint 侧其他会话/其它仓库的调用 (本地无记录)",
        ],
        "claim_policy": ("报告只能写「可核对下界 ≥ N tokens」, 不得写「总计费完整口径」; "
                         "主/重试段快照与他轮用量分列, 不相加。"),
    }
    json.dump(out, open(os.path.join(HERE, "usage_ledger.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"verifiable_totals": out["verifiable_totals"],
                      "gated_fresh_calls": inround["eval_trial_rag_gated_first_run"]["fresh_calls_total"],
                      "gated_tokens": gtok}, ensure_ascii=False))
    print(json.dumps({"events_n": (ev or {}).get("n_by_status"),
                      "events_tokens": (ev or {}).get("tokens_by_status"),
                      "span": (ev or {}).get("span")}, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
