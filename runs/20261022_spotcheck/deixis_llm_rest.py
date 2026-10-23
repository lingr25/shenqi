#!/usr/bin/env python3
"""LLM-judge the heuristic_default items in /workspace/deixis_keeps_20261022.json (incremental save)."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')); sys.path.insert(0, ROOT)
os.environ.setdefault("GROK_BASE", "https://lingr.aitreez.com/v1"); os.environ.setdefault("GROK_MODEL", "lingr-speed")
os.environ.setdefault("GROK_USAGE_LOG", os.path.join(os.path.dirname(__file__), 'usage.jsonl'))
import grok_client
src = open(os.path.join(os.path.dirname(__file__), 'deixis_scan.py')).read()
PROMPT = src.split('PROMPT = """')[1].split('"""')[0]
P = '/workspace/deixis_keeps_20261022.json'; data = json.load(open(P))
todo = [d for d in data if d['judged'] == 'heuristic_default']
def judge(d):
    for i in range(5):
        try:
            t = grok_client.call_llm(PROMPT % (d['claim'], d['quote']))
            j = json.loads(re.search(r'\{.*\}', t, re.S).group(0))
            d['llm_verdict'] = j['verdict']; d['llm_reason'] = j['reason']; return
        except Exception as e:
            if '401' in str(e): raise
            time.sleep(15 * (i + 1))
    d['llm_verdict'] = 'error'
with ThreadPoolExecutor(8) as ex: list(ex.map(judge, todo))
json.dump(data, open('/tmp/deixis_llm.json', 'w'), ensure_ascii=False, indent=1)
from collections import Counter; print(Counter((d['batch'], d.get('llm_verdict')) for d in todo))
