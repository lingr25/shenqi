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
    if not LLM_KEY:
        raise SystemExit("请设置环境变量 GROK_API_KEY")
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "stream": True,
    }).encode()
    for attempt in range(retries):
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
            return json.loads(m.group(0)), usage
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (400, 429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(min(5 * (2 ** attempt), 60))
                continue
            raise RuntimeError(f"HTTP {e.code}: {detail}")
        except (json.JSONDecodeError, KeyError) as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 30))
                continue
            raise RuntimeError(str(e)[:200])
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(15 * (2 ** attempt), 90))
                continue
            raise RuntimeError(str(e)[:300])
