#!/usr/bin/env python3
"""Deixis scan over all keep claims (vod_b1, vod_b2). Prefilter regex + LLM judge (lingr-free). Read-only on repo data."""
import json, glob, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault("GROK_BASE", "https://lingr.aitreez.com/v1"); os.environ.setdefault("GROK_MODEL", "lingr-free")
os.environ.setdefault("GROK_USAGE_LOG", os.path.join(os.path.dirname(__file__), 'usage.jsonl'))
import grok_client
VE = f'{ROOT}/kb_trial/curation/vod_expansion'
PAT = re.compile(r'这个|这俩|这里|这边|这儿|这前面|这后面|这前|这后|那边|那个位置|这一[帧波只个格条]|这[波帧只格条张组]|那[俩波只]|看这|你看|如图|画面|图中|此处|该处|上面这|下面这|左边这|右边这')
items = []
for b in ('vod_b1', 'vod_b2'):
    for f in sorted(glob.glob(f'{VE}/reviews_{b}/*.json')):
        r = json.load(open(f))
        for c in r.get('claims', []):
            q = ' / '.join(e['text'] for e in c.get('evidence', []))
            if PAT.search(c['claim']) or PAT.search(q):
                items.append(dict(batch=b, id=f"{r['workorder_id']}/{c['local_id']}", stem=r['stem'], claim=c['claim'], quote=q))
PROMPT = """你是明日方舟机制知识库审核员。判断下面这条“知识卡 claim”是否依赖直播画面指涉（deixis）才能成立。
规则：若 claim 本身含无自包含指代的“这个/这里/这俩/这前面”等，或 claim 的核心事实（数值、先后、方向、对象）只能靠看画面才能确定、离开画面读者无法知道指的是哪个单位/位置/波次，则 drop。
若 claim 已自包含（主体、条件明确），引文里的“这个”只是口头禅或可由上下文明确还原的对象，则 ok。补全常识主体/数字是允许的。
只输出 JSON：{"verdict":"drop"或"ok","reason":"一句中文理由"}
claim：%s
引文：%s"""
def judge(it):
    for i in range(6):
        try:
            txt = grok_client.call_llm(PROMPT % (it['claim'], it['quote']))
            m = re.search(r'\{.*\}', txt, re.S); j = json.loads(m.group(0))
            it['verdict'] = j['verdict']; it['reason'] = j['reason']; return it
        except Exception as e:
            err = str(e)[:120]; time.sleep(20 * (i + 1))
    it['verdict'] = 'error'; it['reason'] = err; return it
with ThreadPoolExecutor(8) as ex: res = list(ex.map(judge, items))
json.dump(res, open('/workspace/deixis_keeps_20261022.json', 'w'), ensure_ascii=False, indent=1)
from collections import Counter
print(Counter((r['batch'], r['verdict']) for r in res))
