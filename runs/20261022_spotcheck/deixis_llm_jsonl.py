#!/usr/bin/env python3
"""Resumable LLM deixis judge: appends each result to /workspace/deixis_llm_results.jsonl; skips done ids."""
import json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')); sys.path.insert(0, ROOT)
os.environ.setdefault("GROK_BASE", "https://lingr.aitreez.com/v1"); os.environ.setdefault("GROK_MODEL", "lingr-speed")
os.environ.setdefault("GROK_FALLBACK_MODELS", "lingr-free,lingr-pro"); os.environ.setdefault("GROK_TIMEOUT", "60")
os.environ.setdefault("GROK_USAGE_LOG", os.path.join(os.path.dirname(__file__), 'usage.jsonl'))
import grok_client
PROMPT = open(os.path.join(os.path.dirname(__file__), 'deixis_scan.py')).read().split('PROMPT = """')[1].split('"""')[0]
OUT = '/workspace/deixis_llm_results.jsonl'
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            x = json.loads(l)
            if x['verdict'] != 'error': done.add(x['id'])
        except Exception: pass
todo = [d for d in json.load(open('/workspace/deixis_keeps_20261022.json')) if d['judged'] == 'heuristic_default' and d['id'] not in done]
print('todo', len(todo), flush=True); lock = threading.Lock()
def judge(d):
    v, why = 'error', ''
    for i in range(3):
        try:
            t = grok_client.call_llm(PROMPT % (d['claim'], d['quote']), retries=2)
            t = t[0] if isinstance(t, tuple) else t
            j = t if isinstance(t, dict) else json.loads(re.search(r'\{[^{}]*\}', t, re.S).group(0))
            if j.get('verdict') in ('drop', 'ok'): v, why = j['verdict'], j.get('reason', ''); break
        except Exception as e: why = str(e)[:150]
    with lock:
        open(OUT, 'a').write(json.dumps({'id': d['id'], 'verdict': v, 'reason': why}, ensure_ascii=False) + '\n')
with ThreadPoolExecutor(6) as ex: list(ex.map(judge, todo))
print('finished', flush=True)
