# -*- coding: utf-8 -*-
"""试验库 vs 生产：冻结题。不写生产。"""
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
RET = os.path.join(ROOT, "kb_pilot_synth", "retest_round2")
sys.path.insert(0, ROOT)
sys.path.insert(0, RET)
os.chdir(ROOT)
import grok_client
import run_retest as R


def main():
    qs = R.load_jsonl(os.path.join(RET, "questions.jsonl"))
    held = R.load_jsonl(os.path.join(HERE, "heldout_q.jsonl"))
    frozen = json.load(open(os.path.join(HERE, "heldout_frozen.json"), encoding="utf-8"))
    h = hashlib.sha256(open(os.path.join(HERE, "heldout_q.jsonl"), "rb").read()).hexdigest()
    if h != frozen["sha256"]:
        raise SystemExit("heldout hash mismatch")
    questions = qs + held
    print("n_q", len(questions), "model", grok_client.MODEL, "key", bool(grok_client.LLM_KEY))
    old = R.load_prod_docs()
    trial = []
    with open(os.path.join(HERE, "trial_docs.jsonl"), encoding="utf-8") as f:
        for line in f:
            trial.append(json.loads(line))
    idx_old = R.Index(old)
    idx_new = R.Index(trial)
    print("docs old", len(old), "trial", len(trial))
    t0 = time.time()
    old_rows, old_tm = R.run_side("old", idx_old, questions)
    new_rows, new_tm = R.run_side("new", idx_new, questions)
    def dump(name, rows):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    dump("eval_answers_old.jsonl", old_rows)
    dump("eval_answers_new.jsonl", new_rows)
    usage = {
        "model": grok_client.MODEL, "k": R.K, "max_ctx_chars": R.MAX_CTX_CHARS,
        "heldout_sha256": h, "n_questions": len(questions),
        "old": old_tm, "new": new_tm, "wall_sec": round(time.time() - t0, 2),
        "corpus": {"old": len(old), "trial": len(trial)},
    }
    json.dump(usage, open(os.path.join(HERE, "eval_usage.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"old_tok": old_tm["usage"]["total_tokens"], "new_tok": new_tm["usage"]["total_tokens"],
                      "calls": old_tm["usage"]["calls"] + new_tm["usage"]["calls"],
                      "wall": usage["wall_sec"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
