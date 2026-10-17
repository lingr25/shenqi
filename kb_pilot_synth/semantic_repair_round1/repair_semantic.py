# -*- coding: utf-8 -*-
"""定向语义复核/补证: 只跑「进入 gated_default 肯定段且被本地三分为可疑」的交集。

范围(见 scope_intersection.json / e1_triage.jsonl):
  - union(rule_scope_narrow | atom_scope_all_narrow) = 270 规则单元 / 117 卡
  - E2_advice_only_rules 3 卡
其余 1786 个单元本地无可判定问题, **不调用**(无变的不调用)。

授权: 只用 GROK_MODEL 指定的免费模型; secret 仅经 shell env, 不打印不落盘。
缓存: 一条一文件 `cache_semantic/<sha256(prompt+model+pv)>.json`, 完整 prompt 落盘, 可复现;
      已有 cache 命中即不重复调用; `full_candidate_round1/cache_items/` 全程不改。

产物:
  - cache_semantic/*.json      逐条缓存(prompt/model/pv/result/usage)
  - events_semantic.jsonl      逐卡事件账本(ts/cluster/status/tokens/elapsed)
  - semantic_repaired.jsonl    overlay: cluster_id -> {llm_labels, usage, prompt_hash}
  - semantic_repair_log.jsonl  逐规则判定明细
  - usage_semantic.json        本阶段 calls/tokens/墙钟
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
sys.path.insert(0, ROOT)

PV = "semantic-v1"
MAX_WORKERS = 4
TS_LINE = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")
CTX = re.compile(r"^(?:ctx=)?sub:([^:]+):(\d+)$")
SHORT_ATOM = re.compile(r"^(BV[0-9A-Za-z]+_p\d+):a(\d+):([0-9a-f]{8})$")

PROMPT = """你是明日方舟底层机制知识库的**结构复核员**。下面给出一张知识卡的元信息, 以及若干条**待复核规则**。
每条规则后附它的证据原子命题与**原字幕原话**(原话可能是语音识别结果, 有同音错字, 属正常)。

请逐条判定, 只输出 JSON, 不要输出别的文字。

判定标签(每条规则单选一个):
- keep_rule      : 规则本身是有实质内容的机制/实验结论, 且适用对象可由证据追溯 -> 保留为通则
- narrow_scope   : 内容成立, 但只是某个具体对象 / 某次实验的特例, 不得当通则 -> 降为实例
- mark_unclosed  : 关键数值 / 单位 / 条件在原字幕里未闭合 -> 移入待核, 不得当已知
- meta_discourse : 是讲解者的元话语、研究方法论或对局操作建议, 不是游戏机制命题 -> 移入待核
- bad_citation   : 给出的证据引用与规则文本对不上, 或无法在语料里追溯到 -> 移入待核

硬约束(违反即无效):
1. 不得发明数值或单位; 不得把「帧」写成「针」或反之 —— 原字幕怎么写就怎么保留。
2. 每条判定必须给出 `decision_evidence`, 内容是**上面给出的**原子 id 或 ctx id, 不得自造 id。
3. 若证据不足以支持通则, 只能选 narrow_scope / mark_unclosed / meta_discourse / bad_citation, 不得选 keep_rule。
4. 不要改写、不要输出规则正文的替换版本; 只做判定。
5. 只有面向对局的策略/操作建议才算 meta_discourse; 机制本身的限制条件不算。

输出格式(严格 JSON):
{{"decisions":[{{"idx":<规则序号整数>,"label":"<五选一>","decision_evidence":["<id>"],"reason":"<=60字"}}]}}

=== 知识卡 ===
标题: {title}
适用对象: {applies_to}
卡级范围(scope): {scope}   kind: {kind}

=== 待复核规则 ===
{rules_block}
"""


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_cache_items():
    cache = {}
    cdir = os.path.join(FC1, "cache_items")
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json"):
            continue
        r = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
        if r.get("error") or not (r.get("result") or {}).get("_text"):
            continue
        cache[r["cluster_id"]] = r
    return cache


def load_atoms():
    atoms = {}
    for l in open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        if d.get("doc_type") == "vod_atom":
            atoms[d["id"].split(":", 1)[1]] = d
    return atoms


def ts_rows(stem):
    for p in (f"transcripts_txt/{stem}.txt", f"asr_drafts/{stem}_asr.txt",
              f"asr_drafts/{stem}_asr_draft.txt"):
        fp = os.path.join(ROOT, p)
        if os.path.exists(fp):
            rows = {}
            for line in open(fp, encoding="utf-8"):
                m = TS_LINE.match(line.rstrip())
                if m:
                    sec = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                    rows.setdefault(sec, m.group(4))
            return rows, p
    return {}, None


def build_rules_block(res, idxs, atoms, tscache):
    out = []
    for i in idxs:
        r = res["rules"][i] or {}
        out.append(f"[idx={i}] 规则: {r.get('text')}")
        out.append(f"        主语:{r.get('subject') or '(空)'} | 条件:{r.get('when')} | 规则自身scope:{r.get('scope')}")
        for e in (r.get("evidence_atom_ids") or []):
            e = str(e)
            m = CTX.match(e)
            if m:
                stem, sec = m.group(1), int(m.group(2))
                row, path = tscache.setdefault(stem, ts_rows(stem))
                keys = [k for k in sorted(row) if abs(k - sec) <= 40][:5]
                out.append(f"        证据 ctx {e} (file={path}) 原字幕:")
                for k in keys:
                    out.append(f"          t={k} {row[k][:200]}")
                if not keys:
                    out.append("          (该时间戳附近找不到字幕行)")
            else:
                a = atoms.get(e)
                if not a:
                    out.append(f"        证据原子 {e}: **语料中找不到该 id**")
                    continue
                prop = (a.get("text") or "").splitlines()[0][:220]
                out.append(f"        证据原子 {e}: scope={a.get('scope')} applies_to={a.get('applies_to')} "
                           f"claim_type={a.get('claim_type')}")
                out.append(f"          原子命题: {prop}")
                for c in ((a.get("evidence") or {}).get("clips") or [])[:2]:
                    out.append(f"          原话 t={c.get('t_start')}-{c.get('t_end')}: "
                               f"{(c.get('quote') or '')[:260]}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    workers = max(1, min(MAX_WORKERS, args.workers))

    tri = [json.loads(l) for l in open(os.path.join(HERE, "e1_triage.jsonl"), encoding="utf-8")]
    target = collections.defaultdict(set)
    for r in tri:
        t = r["triage"]
        if "atom_scope_all_narrow" in t or "untraceable_atom" in t:
            target[r["cluster_id"]].add(r["rule_idx"])
    # rule 自身 scope 是 instance/example 的也要复核(取原文标签, 用于报告与元话语识别)
    cache = load_cache_items()
    units = [json.loads(l) for l in open(os.path.join(HERE, "scope_units.jsonl"), encoding="utf-8")]
    for u in units:
        if not (u["in_gated_default"] and u["still_affirmative"]):
            continue
        rr = (cache[u["cluster_id"]]["result"]["rules"][u["rule_idx"]] or {})
        if rr.get("scope") in ("instance", "example"):
            target[u["cluster_id"]].add(u["rule_idx"])
    # E2 三卡: 全部规则进复核 (判据与 diagnose.py 的 E2 保持一致)
    ADVICE = ("应该", "建议", "不要", "必须", "基本功", "很重要", "重要", "浪费",
              "没意义", "意义", "价值", "性价比", "划算", "不值得", "值不值",
              "最好", "尽量", "必须自己", "必须自己算", "要能")
    for cid, rec in cache.items():
        res = rec["result"]
        if res.get("kind") != "mechanism" or res.get("scope") != "universal":
            continue
        rules = [x for x in (res.get("rules") or []) if isinstance(x, dict)]
        texts = [x.get("text") or "" for x in rules]
        if texts and all(any(m in t for m in ADVICE) for t in texts):
            for i in range(len(rules)):
                target[cid].add(i)

    ids = sorted(target)
    if args.limit:
        ids = ids[: args.limit]
    os.makedirs(os.path.join(HERE, "cache_semantic"), exist_ok=True)
    atoms = load_atoms()
    hash_index = collections.defaultdict(list)
    for k in atoms:
        h = k.rsplit(":", 1)[-1]
        if re.fullmatch(r"[0-9a-f]{8}", h):
            hash_index[h].append(k)
    trans_stems = set()
    for d in ("transcripts_txt", "asr_drafts"):
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                if fn.endswith(".txt"):
                    trans_stems.add(re.sub(r"(_asr|_asr_draft)?\.txt$", "", fn))
    import gate_v2 as GV2
    tscache = {}
    n_fixed = collections.Counter()
    for cid, rec in cache.items():
        res = dict(rec["result"])
        res["rules"] = [dict(x) if isinstance(x, dict) else x
                        for x in (rec["result"].get("rules") or [])]
        a, b, c = GV2.fix_citations(res, trans_stems, atoms, hash_index)
        n_fixed["normalized"] += a
        n_fixed["recovered"] += b
        n_fixed["unresolvable"] += c
        rec = dict(rec)
        rec["result"] = res
        cache[cid] = rec
    print("citation pre-normalization:", dict(n_fixed), flush=True)
    model = os.environ.get("GROK_MODEL", "")
    stats = {"calls": 0, "cache_hit": 0, "errors": 0, "prompt_tokens": 0,
             "completion_tokens": 0, "total_tokens": 0}
    lock = threading.Lock()
    t0 = time.time()
    events = os.path.join(HERE, "events_semantic.jsonl")
    logpath = os.path.join(HERE, "semantic_repair_log.jsonl")
    outpath = os.path.join(HERE, "semantic_repaired.jsonl")

    def process(cid):
        rec = cache[cid]
        res = rec["result"]
        idxs = sorted(target[cid])
        block = build_rules_block(res, idxs, atoms, tscache)
        prompt = PROMPT.format(title=res.get("title"), applies_to=res.get("applies_to"),
                               scope=res.get("scope"), kind=res.get("kind"), rules_block=block)
        key = sha256(prompt + "\0" + model + "\0" + PV)
        cpath = os.path.join(HERE, "cache_semantic", key + ".json")
        if os.path.isfile(cpath):
            try:
                old = json.load(open(cpath, encoding="utf-8"))
                if old.get("result") and not old.get("error"):
                    with lock:
                        stats["cache_hit"] += 1
                    return cid, "hit", old
            except Exception:
                pass
        if not args.apply:
            return cid, "dry", {"dry_run": True, "prompt_chars": len(prompt), "key": key}
        import grok_client
        t1 = time.time()
        try:
            raw, usage = grok_client.call_llm(prompt, retries=3)
            out = {"cluster_id": cid, "key": key, "prompt_version": PV, "model": model,
                   "prompt": prompt, "prompt_chars": len(prompt),
                   "idx_in_scope": idxs, "result": raw, "usage": usage or {},
                   "t_llm_sec": round(time.time() - t1, 3), "error": None,
                   "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            status = "ok"
            with lock:
                stats["calls"] += 1
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    stats[k] += int((usage or {}).get(k) or 0)
        except Exception as e:
            out = {"cluster_id": cid, "key": key, "prompt_version": PV, "model": model,
                   "prompt": prompt, "prompt_chars": len(prompt),
                   "idx_in_scope": idxs, "error": str(e)[:400],
                   "t_llm_sec": round(time.time() - t1, 3),
                   "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            status = "error"
            with lock:
                stats["errors"] += 1
        tmp = cpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(tmp, cpath)
        with open(events, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "cluster_id": cid, "status": status,
                                "tokens": (out.get("usage") or {}).get("total_tokens"),
                                "error": out.get("error"),
                                "t_llm_sec": out.get("t_llm_sec")}, ensure_ascii=False) + "\n")
        return cid, status, out

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (cid, status, out) in enumerate(ex.map(process, ids), 1):
            results[cid] = (status, out)
            if n % 10 == 0 or status != "hit":
                print(f"  {n}/{len(ids)} {cid} {status}", flush=True)

    # ---- 汇总 ----
    LBL = ("keep_rule", "narrow_scope", "mark_unclosed", "meta_discourse", "bad_citation")
    cbad = collections.Counter()
    n_rules = n_labels = 0
    if args.apply:
        with open(outpath, "w", encoding="utf-8") as fo, open(logpath, "w", encoding="utf-8") as fl:
            for cid in ids:
                status, out = results[cid]
                if status not in ("ok", "hit"):
                    cbad["cache_error"] += 1
                    continue
                dec = ((out.get("result") or {}).get("decisions") or [])
                labels = []
                allowed = set(out.get("idx_in_scope") or [])
                for d in dec:
                    if not isinstance(d, dict):
                        cbad["bad_decision_object"] += 1
                        continue
                    i = d.get("idx")
                    lab = d.get("label")
                    if i not in allowed:
                        cbad["idx_not_in_scope"] += 1
                        continue
                    if lab not in LBL:
                        cbad["unknown_label"] += 1
                        continue
                    ev = [str(x) for x in (d.get("decision_evidence") or [])]
                    if not ev:
                        cbad["missing_decision_evidence"] += 1
                    labels.append({"idx": i, "label": lab, "evidence": ev,
                                   "reason": (d.get("reason") or "")[:200]})
                    n_labels += 1
                got = {x["idx"] for x in labels}
                for i in sorted(allowed - got):
                    cbad["idx_unanswered"] += 1
                n_rules += len(allowed)
                fo.write(json.dumps({"cluster_id": cid, "source": "cache_semantic",
                                     "prompt_hash": out["key"], "model": out.get("model"),
                                     "prompt_version": PV, "llm_labels": labels,
                                     "usage": out.get("usage") or {},
                                     "reviewer_type": "agent"}, ensure_ascii=False) + "\n")
                fl.write(json.dumps({"cluster_id": cid, "labels": labels,
                                     "idx_in_scope": sorted(allowed),
                                     "reviewer_type": "agent"}, ensure_ascii=False) + "\n")
    stats["elapsed_sec"] = round(time.time() - t0, 1)
    stats["n_cards_in_scope"] = len(ids)
    stats["n_rules_in_scope"] = n_rules if args.apply else sum(len(v) for v in target.values())
    stats["n_labels"] = n_labels
    stats["label_problems"] = dict(cbad.most_common())
    stats["model"] = model
    stats["prompt_version"] = PV
    stats["cache_items_untouched"] = True
    stats["reviewer_type"] = "agent"
    json.dump(stats, open(os.path.join(HERE, "usage_semantic.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
