# -*- coding: utf-8 -*-
"""按 (cluster_id, rule_idx) 打印完整判定上下文, 供人工/代理逐条校准与复核。

用法: python dump_ctx.py <cluster_id>:<idx> [<cluster_id>:<idx> ...]
输出: 卡级元信息 + 规则正文/主语/条件 + 每条证据原子的 (自身命题/scope/applies_to/原话引文)
      + ctx=sub 引用解析出的真实字幕行。所有内容只读, 不落盘。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FC1 = os.path.join(os.path.dirname(HERE), "full_candidate_round1")
TS_LINE = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")
CTX = re.compile(r"^(?:ctx=)?sub:([^:]+):(\d+)$")


def load_atoms():
    atoms = {}
    for l in open(os.path.join(ROOT, "kb/docs.jsonl"), encoding="utf-8"):
        d = json.loads(l)
        if d.get("doc_type") == "vod_atom":
            atoms[d["id"].split(":", 1)[1]] = d
    return atoms


def load_cache():
    cache = {}
    cdir = os.path.join(FC1, "cache_items")
    for fn in os.listdir(cdir):
        if fn.endswith(".json"):
            r = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
            if not r.get("error") and (r.get("result") or {}).get("_text"):
                cache[r["cluster_id"]] = r
    return cache


def ts_rows(stem):
    for p in (f"transcripts_txt/{stem}.txt", f"asr_drafts/{stem}_asr.txt",
              f"asr_drafts/{stem}_asr_draft.txt"):
        fp = os.path.join(ROOT, p)
        if not os.path.exists(fp):
            continue
        rows = {}
        for line in open(fp, encoding="utf-8"):
            m = TS_LINE.match(line.rstrip())
            if m:
                sec = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                rows.setdefault(sec, m.group(4))
        return rows, p
    return {}, None


def main():
    atoms = load_atoms()
    cache = load_cache()
    for arg in sys.argv[1:]:
        cid, _, idxs = arg.rpartition(":")
        idx = int(idxs)
        rec = cache.get(cid)
        print("=" * 100)
        if not rec:
            print("NOT IN CACHE:", arg)
            continue
        res = rec["result"]
        print(f"[{cid}] idx={idx} category={rec.get('category')} issue={rec.get('issue_status')}")
        print(f"  title      : {res.get('title')}")
        print(f"  applies_to : {res.get('applies_to')}")
        print(f"  kind/scope : {res.get('kind')} / {res.get('scope')}  confidence={res.get('confidence')}")
        print(f"  conditions : {res.get('conditions')}")
        print(f"  exceptions : {res.get('exceptions')}")
        print(f"  open_qs    : {res.get('open_questions')}")
        r = (res.get("rules") or [])[idx]
        print(f"  RULE[{idx}]  text   : {r.get('text')}")
        print(f"             subject: {r.get('subject')}   when: {r.get('when')}  scope: {r.get('scope')}")
        for e in r.get("evidence_atom_ids") or []:
            e = str(e)
            m = CTX.match(e)
            if m:
                rows, path = ts_rows(m.group(1))
                sec = int(m.group(2))
                print(f"    ctx  {e}  file={path}")
                keys = sorted(rows)
                near = [k for k in keys if abs(k - sec) <= 40]
                for k in near[:8]:
                    print(f"        t={k} {rows[k][:160]}")
                if not near:
                    print("        (未找到该时间戳附近字幕行)")
            else:
                a = atoms.get(e)
                if not a:
                    print(f"    ATOM {e}  ✗ 未在 kb/docs.jsonl 找到 (旧格式/漂移)")
                else:
                    print(f"    ATOM {e}  status={a.get('status')} scope={a.get('scope')} applies_to={a.get('applies_to')} claim={a.get('claim_type')}")
                    print(f"         proposition: {(a.get('text') or '').splitlines()[0][:200]}")
                    for c in ((a.get("evidence") or {}).get("clips") or [])[:3]:
                        print(f"         quote t={c.get('t_start')}-{c.get('t_end')}: {(c.get('quote') or '')[:220]}")


if __name__ == "__main__":
    main()
