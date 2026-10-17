# -*- coding: utf-8 -*-
"""grok_client.py - aitreez grok-4.6 流式 JSON 调用

非流式时网关常在 ~120s 总时长处返回 503 (模型其实已生成完)。
流式走 SSE, 只要 token 持续到达就不会被总时长上限误杀。
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

LLM_BASE = os.environ.get("GROK_BASE", "https://aitreez.com/v1")
LLM_KEY = os.environ.get("GROK_API_KEY", "").strip()
MODEL = os.environ.get("GROK_MODEL", "grok-4.6")
HTTP_TIMEOUT = int(os.environ.get("GROK_TIMEOUT", "180"))
# 可选用量台账: 设置 GROK_USAGE_LOG=<path.jsonl> 后每次成功调用追加一行
# (时间/模型/主机/token/耗时/调用脚本), 不含密钥与请求头。
USAGE_LOG = os.environ.get("GROK_USAGE_LOG", "").strip()
# 主模型连续返回空/非 JSON 时, 仅对该次调用依次换用的备选模型(逗号分隔, 可为空)。
FALLBACK_MODELS = [m.strip() for m in os.environ.get("GROK_FALLBACK_MODELS", "").split(",") if m.strip()]
EMPTY_BEFORE_FALLBACK = int(os.environ.get("GROK_EMPTY_BEFORE_FALLBACK", "3"))


def _log_usage(usage, seconds, model=None, attempt=0):
    if not USAGE_LOG:
        return
    import sys
    import threading
    from urllib.parse import urlparse
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": model or MODEL,
           "attempt": attempt,
           "host": urlparse(LLM_BASE).netloc, "script": os.path.basename(sys.argv[0]),
           "prompt_tokens": usage.get("prompt_tokens", 0),
           "completion_tokens": usage.get("completion_tokens", 0),
           "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
           "total_tokens": usage.get("total_tokens", 0), "seconds": round(seconds, 2)}
    global _LOCK
    try:
        _LOCK
    except NameError:
        _LOCK = threading.Lock()
    with _LOCK, open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _parse_sse(resp) -> tuple[str, dict]:
    pieces = []
    usage = {}
    buf = b""
    while True:
        chunk = resp.read(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            s = line.decode("utf-8", errors="replace").strip()
            if not s.startswith("data:"):
                continue
            payload = s[5:].strip()
            if payload == "[DONE]":
                return "".join(pieces), usage
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                pieces.append(content)
            # 部分网关把整段放在 message.content
            msg = choices[0].get("message") or {}
            if msg.get("content") and not content:
                pieces.append(msg["content"])
    if buf.strip():
        s = buf.decode("utf-8", errors="replace").strip()
        if s.startswith("data:") and s[5:].strip() not in ("", "[DONE]"):
            try:
                obj = json.loads(s[5:].strip())
                if obj.get("usage"):
                    usage = obj["usage"]
                choices = obj.get("choices") or []
                if choices:
                    delta = (choices[0].get("delta") or {}).get("content") or ""
                    if delta:
                        pieces.append(delta)
            except json.JSONDecodeError:
                pass
    return "".join(pieces), usage


def call_llm(prompt: str, retries=6):
    """返回 (parsed_json, usage)。usage["_model"] 为实际产出结果的模型。
    空内容/非 JSON: 指数退避重试; 主模型连续 EMPTY_BEFORE_FALLBACK 次后
    (若配置了 GROK_FALLBACK_MODELS) 仅本次调用换用备选模型。"""
    if not LLM_KEY:
        raise SystemExit("请设置环境变量 GROK_API_KEY")
    models = [MODEL] + FALLBACK_MODELS
    mi, empties = 0, 0
    total = retries + EMPTY_BEFORE_FALLBACK * len(FALLBACK_MODELS)
    last = ""
    for attempt in range(total):
        model = models[mi]
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": True,
            "stream_options": {"include_usage": True},
        }).encode()
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                LLM_BASE + "/chat/completions", data=body,
                headers={"Authorization": f"Bearer {LLM_KEY}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                content, usage = _parse_sse(resp)
            m = re.search(r"\{.*\}", content, re.S)
            if not m:
                raise json.JSONDecodeError("no json object", content[:200], 0)
            parsed = json.loads(m.group(0))
            usage = dict(usage or {}, _model=model, _attempts=attempt + 1)
            _log_usage(usage, time.monotonic() - t0, model, attempt)
            return parsed, usage
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(last)
            time.sleep(min(5 * (2 ** min(attempt, 4)), 60))
        except (json.JSONDecodeError, KeyError) as e:
            last = f"[{model}] {str(e)[:200]}"
            empties += 1
            if empties >= EMPTY_BEFORE_FALLBACK and mi + 1 < len(models):
                mi, empties = mi + 1, 0
                continue
            time.sleep(min(2 ** min(attempt, 4) * 3, 45))
        except Exception as e:
            last = str(e)[:300]
            time.sleep(min(15 * (2 ** min(attempt, 3)), 90))
    raise RuntimeError(last)
