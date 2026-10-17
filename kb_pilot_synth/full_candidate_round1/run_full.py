# -*- coding: utf-8 -*-
"""全量候选合成（隔离目录）。不写 kb/docs.jsonl / kb/synthesized.jsonl。"""
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import grok_client
import kb_synthesize as S

PV = "v4"
MAX_WORKERS = 12
SMOKE_IDS = [
    "帧时序与计时器-24-0",
    "伤害结算-1-1",
    "伤害结算-2-4",
]


def safe_name(cid):
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", cid)[:180]


def fingerprint(prompt, model, pv):
    """prompt 已含簇文+原子命题+原话+字幕邻近，再加 pv/model。"""
    h = hashlib.sha256()
    h.update(pv.encode())
    h.update(b"\0")
    h.update((model or "").encode())
    h.update(b"\0")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


def source_hash(c, members):
    """显式源内容指纹：簇正文+成员 atom_id/命题/原话。不含 prompt 模板。"""
    h = hashlib.sha256()
    h.update((c.get("id") or "").encode())
    h.update(b"\0")
    h.update((c.get("text") or "").encode("utf-8"))
    h.update(b"\0")
    for m in members:
        h.update((m.get("atom_id") or "").encode())
        h.update(b"\0")
        h.update((m.get("proposition") or "").encode("utf-8"))
        h.update(b"\0")
        for ev in m.get("evidence") or []:
            h.update((ev.get("quote") or "").encode("utf-8"))
            h.update(b"\0")
    return h.hexdigest()


def item_path(cache_dir, cid):
    return os.path.join(cache_dir, safe_name(cid) + ".json")


def atomic_write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def append_event(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_clusters():
    docs = []
    with open("kb/docs.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            docs.append(d)
    atoms = S.load_source_atoms(correct_quotes=False)
    noise_ids = {d.get("atom_id") for d in docs
                 if d.get("doc_type") == "vod_atom" and d.get("status") == "noise"}
    atoms = {k: v for k, v in atoms.items() if k not in noise_ids}
    by_id = {d["id"]: d for d in docs}
    clusters = [d for d in docs if d.get("doc_type") == "vod_cluster" and d.get("status") != "noise"]
    return clusters, atoms, by_id


def build_prompt(c, atoms, by_id, no_qq=True, sub_ctx=True):
    mids = [m for m in (c["links"].get("member_atom_ids") or []) if m in atoms]
    members = [atoms[m] for m in mids]
    qq_block = ""
    if not no_qq:
        cps = [by_id[q] for q in (c["links"].get("counterpart_ids") or []) if q in by_id]
        if cps:
            qq_block = (
                "[QQ群讨论(补充线索, 禁止用QQ给录播补主语; 与录播冲突时以录播为准)]\n"
                + "\n".join(f"- {q['text'][:400]}" for q in cps[:3])
            )
    title = (c.get("text") or "").split("\n")[0]
    body = c.get("text") or ""
    question = note = ""
    for line in body.split("\n"):
        if line.startswith("问题:"):
            question = line[3:].strip()
        if line.startswith("档案备注:"):
            note = line[5:].strip()
    atom_text = S.fmt_atoms(members, max_members=None, quote_limit=500, max_chars=None)
    sub_block = S.fmt_sub_ctx(members) if sub_ctx else ""
    if sub_block.endswith("…(字幕上下文截断)") or "未找到字幕" in sub_block:
        incomplete_hint = True
    else:
        incomplete_hint = False
    prompt = S.PROMPTS[PV].format(
        title=title, question=question, note=note,
        atoms=atom_text, qq_block=qq_block, sub_block=sub_block)
    stems = sorted({(m.get("source_id") or (m.get("atom_id") or "").split(":")[0]) for m in members if m})
    return prompt, members, incomplete_hint, stems


def parse_args(argv):
    smoke = "--smoke" in argv
    dry = "--dry-run" in argv
    workers = 8
    limit = None
    ids = list(SMOKE_IDS) if smoke else None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--workers":
            workers = min(MAX_WORKERS, int(argv[i + 1])); i += 2; continue
        if a == "--limit":
            limit = int(argv[i + 1]); i += 2; continue
        if a == "--ids":
            ids = [x.strip() for x in argv[i + 1].split(",") if x.strip()]; i += 2; continue
        i += 1
    return {"smoke": smoke, "dry": dry, "workers": workers, "limit": limit, "ids": ids}


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cache_dir = os.path.join(HERE, "cache_items")
    events_path = os.path.join(HERE, "events.jsonl")
    usage_path = os.path.join(HERE, "usage.json")
    synth_path = os.path.join(HERE, "synthesized_v4.jsonl")
    os.makedirs(cache_dir, exist_ok=True)

    print("model", grok_client.MODEL, "base", grok_client.LLM_BASE,
          "key", bool(grok_client.LLM_KEY), "pv", PV,
          "workers", args["workers"], "smoke", args["smoke"], "dry", args["dry"],
          flush=True)
    if not args["dry"] and not grok_client.LLM_KEY:
        raise SystemExit("GROK_API_KEY missing")

    clusters, atoms, by_id = load_clusters()
    if args["ids"]:
        by_cid = {S._cluster_id_of(c): c for c in clusters}
        clusters = [by_cid[i] for i in args["ids"] if i in by_cid]
    if args["limit"] is not None:
        clusters = clusters[: args["limit"]]
    print("clusters", len(clusters), "atoms", len(atoms), flush=True)

    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                 "calls": 0, "errors": 0, "cache_hit": 0, "ok": 0, "requests": 0}
    lock = threading.Lock()
    t0 = time.time()

    def bump(u=None, **kw):
        if u:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                try:
                    usage_tot[k] += int(u.get(k) or 0)
                except (TypeError, ValueError):
                    pass
        for k, v in kw.items():
            usage_tot[k] = usage_tot.get(k, 0) + v

    def process(c):
        cid = S._cluster_id_of(c)
        mids = [m for m in (c["links"].get("member_atom_ids") or []) if m in atoms]
        members0 = [atoms[m] for m in mids]
        sh = source_hash(c, members0)
        path = item_path(cache_dir, cid)
        if os.path.isfile(path):
            try:
                old = json.load(open(path, encoding="utf-8"))
            except Exception:
                old = {}
            if (not old.get("error") and old.get("result")
                    and old.get("prompt_version") == PV
                    and old.get("model") == grok_client.MODEL
                    and old.get("source_hash") == sh):
                with lock:
                    bump(cache_hit=1)
                return cid, "hit", old
        prompt, members, incomplete_hint, stems = build_prompt(c, atoms, by_id)
        fp = fingerprint(prompt, grok_client.MODEL, PV)
        if os.path.isfile(path):
            try:
                old = json.load(open(path, encoding="utf-8"))
            except Exception:
                old = {}
            if old.get("fingerprint") == fp and not old.get("error") and old.get("result"):
                old["source_hash"] = sh
                atomic_write(path, old)
                with lock:
                    bump(cache_hit=1)
                return cid, "hit", old
        if args["dry"]:
            rec = {"cluster_id": cid, "fingerprint": fp, "dry_run": True,
                   "prompt_chars": len(prompt), "n_members": len(members), "stems": stems}
            atomic_write(path, rec)
            with lock:
                bump(ok=1)
            return cid, "dry", rec

        t1 = time.time()
        with lock:
            bump(requests=1)
        try:
            raw, usage = grok_client.call_llm(prompt, retries=6)
            r = S._normalize_llm_result(raw)
            if incomplete_hint:
                r["context_incomplete"] = True
            r["_text"] = S.render(r, c, members)
            rec = {
                "cluster_id": cid,
                "doc_id": c["id"],
                "fingerprint": fp,
                "source_hash": sh,
                "prompt_version": PV,
                "model": grok_client.MODEL,
                "issue_status": c.get("issue_status"),
                "category": c.get("category"),
                "n_members": len(members),
                "stems": stems,
                "prompt_chars": len(prompt),
                "result": {k: r.get(k) for k in (
                    "title", "applies_to", "kind", "context_incomplete", "rules",
                    "conditions", "exceptions", "open_questions", "scope",
                    "confidence", "_text")},
                "usage": usage or {},
                "t_llm_sec": round(time.time() - t1, 3),
                "error": None,
            }
            status = "ok"
            with lock:
                bump(usage, calls=1, ok=1)
        except Exception as e:
            rec = {
                "cluster_id": cid, "doc_id": c["id"], "fingerprint": fp,
                "source_hash": sh,
                "prompt_version": PV, "model": grok_client.MODEL,
                "error": str(e)[:400], "prompt_chars": len(prompt),
                "t_llm_sec": round(time.time() - t1, 3),
            }
            status = "error"
            with lock:
                bump(calls=1, errors=1)
        atomic_write(path, rec)
        with lock:
            append_event(events_path, {
                "ts": time.time(), "cluster_id": cid, "status": status,
                "tokens": (rec.get("usage") or {}).get("total_tokens"),
                "error": rec.get("error"), "t_llm_sec": rec.get("t_llm_sec"),
            })
            atomic_write(usage_path, {**usage_tot, "elapsed_sec": round(time.time() - t0, 1)})
        return cid, status, rec

    n = len(clusters)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args["workers"])) as ex:
        for cid, status, rec in ex.map(process, clusters):
            done += 1
            if done % 20 == 0 or status != "hit" or args["smoke"]:
                print(f"  {done}/{n} {cid} {status}", flush=True)

    # pack jsonl from cache
    n_ok = n_err = n_hit = 0
    with open(synth_path, "w", encoding="utf-8") as f:
        for c in clusters:
            cid = S._cluster_id_of(c)
            path = item_path(cache_dir, cid)
            if not os.path.isfile(path):
                n_err += 1
                continue
            rec = json.load(open(path, encoding="utf-8"))
            if rec.get("error") or not (rec.get("result") or {}).get("_text"):
                n_err += 1
                continue
            r = rec["result"]
            out = {
                "cluster_id": cid,
                "doc_id": c["id"],
                "title": r.get("title"),
                "applies_to": r.get("applies_to"),
                "kind": r.get("kind"),
                "context_incomplete": r.get("context_incomplete"),
                "confidence": r.get("confidence"),
                "scope": r.get("scope"),
                "issue_status": c.get("issue_status"),
                "category": c.get("category"),
                "text": r.get("_text"),
                "rules": r.get("rules") or [],
                "conditions": r.get("conditions") or [],
                "exceptions": r.get("exceptions") or [],
                "open_questions": r.get("open_questions") or [],
                "member_count": rec.get("n_members"),
                "stems": rec.get("stems") or [],
                "prompt_version": PV,
                "fingerprint": rec.get("fingerprint"),
                "reviewer_type": "agent",
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
            n_ok += 1
            if rec.get("t_llm_sec") is None and not rec.get("error"):
                n_hit += 1
    usage_tot["elapsed_sec"] = round(time.time() - t0, 1)
    usage_tot["synthesized"] = n_ok
    usage_tot["write_errors"] = n_err
    atomic_write(usage_path, usage_tot)
    summary = {"synthesized": n_ok, "errors": n_err, "usage": usage_tot,
               "out": synth_path, "prompt_version": PV, "model": grok_client.MODEL,
               "n_clusters": n, "pilot_isolation": True}
    json.dump(summary, open(os.path.join(HERE, "run_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: summary[k] for k in ("synthesized", "errors", "n_clusters") if k in summary}
                     | {"calls": usage_tot.get("calls"), "tokens": usage_tot.get("total_tokens"),
                        "elapsed": usage_tot.get("elapsed_sec"), "cache_hit": usage_tot.get("cache_hit")},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
