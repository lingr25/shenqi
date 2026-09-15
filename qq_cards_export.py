#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qq_cards_export.py
------------------
把 candidate 权威窗导出为离线 LLM 交接包：
  qq_info/llm_batch/batch_XXX.jsonl  +  PROMPT.md

纯标准库。群聊原文零纠错；导出消息行脱敏，不含 QQ。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WINDOWS = os.path.join(ROOT_DIR, "qq_info", "windows.jsonl")
DEFAULT_MESSAGES = os.path.join(ROOT_DIR, "qq_info", "messages_clean.jsonl")
DEFAULT_OUT = os.path.join(ROOT_DIR, "qq_info", "llm_batch")

HOST_SID = "589e9b6d"
EXPERT_SID = "0f17ac97"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def clock_of(time_str: str) -> str:
    ts = (time_str or "").strip()
    if " " in ts:
        return ts.split(" ", 1)[1][:8]
    if len(ts) >= 8:
        return ts[-8:]
    return ts or "??:??:??"


def speaker_tag(msg: dict[str, Any], role_by_sid: dict[str, str]) -> str:
    sid = msg.get("speaker_id") or ""
    role = role_by_sid.get(sid)
    if role == "host" or sid == HOST_SID:
        return "[主播]"
    if role == "expert" or sid == EXPERT_SID:
        return "[专家]"
    short = (sid or "unknown")[:8]
    return f"群友_{short}"


def format_line(msg: dict[str, Any], role_by_sid: dict[str, str]) -> str:
    text = msg.get("text_stripped") or msg.get("text") or ""
    text = " ".join(text.split())
    return f"[{clock_of(msg.get('time_str') or '')}] {speaker_tag(msg, role_by_sid)} {text}"


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_messages_index(path: str) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            idx[m["msg_id"]] = m
    return idx


def window_payload(w: dict[str, Any], msg_idx: dict[str, dict[str, Any]]) -> dict[str, Any]:
    role_by_sid = {
        a.get("speaker_id"): a.get("role")
        for a in (w.get("authorities") or [])
        if a.get("speaker_id")
    }
    lines: list[str] = []
    missing = 0
    for mid in w.get("source_msg_ids") or []:
        m = msg_idx.get(mid)
        if not m:
            missing += 1
            continue
        lines.append(format_line(m, role_by_sid))
    return {
        "window_id": w["window_id"],
        "time_range": {
            "start": w.get("start_time"),
            "end": w.get("end_time"),
        },
        "evidence_lost": bool(w.get("evidence_lost")),
        "hit_terms": list(w.get("hit_terms") or []),
        "source_msg_ids": list(w.get("source_msg_ids") or []),
        "n_messages": len(lines),
        "messages": lines,
        "_missing_msgs": missing,
    }


PROMPT_MD = r'''# 群聊机制知识卡片提炼 — Prompt 模板

离线交接包。一窗一调用；不要把本文件或 batch JSONL 提交到公开 Git。

---

## 批次使用说明

1. 从 `batch_001.jsonl` 起逐行读取，每行是一个窗的完整载荷 JSON。
2. **一窗一调用**：把该行 JSON 填入下方 user 模板的 `{WINDOW_PAYLOAD}`。
3. 模型只输出 **一个 JSON 对象**（不要 Markdown 围栏、不要解说）。
4. 将输出追加写入 `cards_batch_XXX.jsonl`（与输入 batch 编号对应，每行一个 JSON，`window_id` 必须与输入一致）。
5. 闲聊/无机制结论时输出 skip 对象，不要硬编卡片。

---

## System

你是明日方舟机制讨论的提炼员。输入是一段已脱敏的群聊窗：

- `[主播]` = 机制权威主播「神祇读神奇」，其测算与定性视为权威真值。
- `[专家]` = 核心机制群友（拆包/实测），可信但次于主播。
- `群友_XXXX` = 普通群友；发言可作线索，不能当成权威。

只根据窗内原文提炼。禁止用外部攻略、Wiki、训练记忆补全任何数字、单位、组件名或路径。窗里没说的就不要写。

当载荷 `evidence_lost` 为 true：相关图片/媒体已丢失，只引用仍在的文字；此时 `core_conclusions[].credibility` 不得超过 `expert`（即使发言人是主播，也因证据残缺降一档）。

---

## 输出 JSON

### A. 可提炼时（一张卡）

严格输出一个 JSON 对象，字段如下：

| 字段 | 类型 | 说明 |
|---|---|---|
| `topic` | string | 机制主题，短标题 |
| `category` | string | 枚举：`索敌` / `帧时序` / `位移` / `寻路` / `伤害结算` / `拆包数据` / `其他` |
| `entities` | string[] | 中英对照，如 `"索敌间隔（Attack Interval / Search Interval）"` |
| `context_question` | string | 窗内在争论/求解什么 |
| `core_conclusions` | object[] | 见下 |
| `underlying_parameters` | object[] | 见下；没有过硬数字就 `[]` |
| `summary_takeaway` | string | 一两句可入库摘要 |
| `window_id` | string | 与输入完全一致 |
| `as_of` | string | 用载荷 `time_range.end` |
| `status` | string | 固定 `"draft"` |
| `novelty` | string | 固定 `"unknown"` |
| `source_msg_ids` | string[] | 必须 ⊆ 输入 `source_msg_ids`，只列支撑结论的消息 |
| `source_spans` | string[] | 原文摘录，每条必须是某条窗内消息正文的子串 |

`core_conclusions[]`：

- `speaker`: 只能是 `"主播"` / `"专家"` / `"群友"`（不要写 speaker_id 或真名）
- `credibility`: 只能是 `"authoritative"` / `"expert"` / `"lead"`
  - 主播且 evidence_lost=false → `authoritative`
  - 专家，或主播但 evidence_lost=true → `expert`
  - 普通群友且被主播/专家明确认可的推论 → `lead`；未被认可不要单独成条，或 cred=`lead` 并写明未确认
- `conclusion`: 只复述窗内信息

`underlying_parameters[]`：

- `name`: 参数名
- `value`: **必须逐字出现在 `source_spans` 之一里**（允许两端空白差异）；找不到就把整个 `underlying_parameters` 留 `[]`，禁止估数字
- `unit`: 如 `帧` / `秒` / `格`；没有则 `""`
- `source_span`: 含该 value 的原文摘录（同样必须是窗内正文子串）

### B. 应跳过时

```json
{"skip": true, "window_id": "w000000", "reason": "纯闲聊，无机制结论"}
```

`window_id` 仍必填。

硬约束再强调：

1. 结论与参数只能来自窗内消息。
2. `underlying_parameters[].value` 找不到原文 → 该字段整段改 `[]`，不要编。
3. 禁止输出 QQ 号、真实昵称、群号。
4. 不要输出 JSON 以外的文字。

---

## Few-shot

### User（示例载荷）

```json
{
  "window_id": "w000307",
  "time_range": {"start": "2026-05-25 16:43:58", "end": "2026-05-25 16:48:47"},
  "evidence_lost": false,
  "hit_terms": ["攻击间隔", "索敌", "帧"],
  "source_msg_ids": [
    "7643764081512327704", "7643764081512327698", "7643764081512327693",
    "7643764081512327688", "7643764081512327677", "7643764081512327666",
    "7643764081512327660", "7643764081512327654", "7643764081512327648",
    "7643764081512327642", "7643764081512327636", "7643764081512327625",
    "7643764081512327619", "7643764081512327614", "7643764145933907243"
  ],
  "n_messages": 15,
  "messages": [
    "[16:43:58] [专家] 哦不对不能拿多连击说",
    "[16:44:22] 群友_bb42f5fd 之前那期视频不是说",
    "[16:44:37] 群友_bb42f5fd 持续攻击的话攻击间隔就是索敌间隔",
    "[16:44:43] [主播] 是啊",
    "[16:45:09] [主播] 攻击间隔的数值",
    "[16:45:14] [主播] 是由索敌间隔决定的",
    "[16:45:25] [主播] 不管他索敌是什么逻辑决定的间隔",
    "[16:45:40] [主播] 就算你攻击冷却早早转好了",
    "[16:45:42] [主播] 没意义",
    "[16:45:57] [主播] 动画没结束不能索敌，索敌冷却没转好不能索敌",
    "[16:47:39] [主播] 你是被后面那句而非3帧循环误导了？",
    "[16:48:04] [主播] 那个说的是3帧归0之后动画没结束也不能抬手",
    "[16:48:17] 群友_bb42f5fd 还真是",
    "[16:48:18] [主播] 所以不是每3一次",
    "[16:48:47] [主播] 不是每3一次不等于没了3限制"
  ]
}
```

### Assistant（正确输出）

```json
{
  "topic": "攻击间隔由索敌间隔决定，动画未结束不能抬手",
  "category": "索敌",
  "entities": [
    "攻击间隔（Attack Interval）",
    "索敌间隔（Search Interval）",
    "索敌冷却（Search Cooldown）"
  ],
  "context_question": "持续攻击时攻击间隔是否等于索敌间隔？3帧循环是否意味着每3帧都能抬手？",
  "core_conclusions": [
    {
      "speaker": "群友",
      "credibility": "lead",
      "conclusion": "提出持续攻击时攻击间隔就是索敌间隔，获主播当场确认。"
    },
    {
      "speaker": "主播",
      "credibility": "authoritative",
      "conclusion": "攻击间隔的数值由索敌间隔决定；攻击冷却转好但动画未结束或索敌冷却未好转，仍不能索敌。所谓3帧循环是3帧归零后若动画没结束也不能抬手，因此不是每3帧一次，但这不等于3帧限制消失。"
    }
  ],
  "underlying_parameters": [
    {
      "name": "误读的循环周期",
      "value": "3帧",
      "unit": "帧",
      "source_span": "那个说的是3帧归0之后动画没结束也不能抬手"
    }
  ],
  "summary_takeaway": "面板攻击间隔由索敌间隔决定；动画未结束或索敌冷却未转好都不能索敌。3帧归零不等于每3帧一次抬手。",
  "window_id": "w000307",
  "as_of": "2026-05-25 16:48:47",
  "status": "draft",
  "novelty": "unknown",
  "source_msg_ids": [
    "7643764081512327693",
    "7643764081512327688",
    "7643764081512327666",
    "7643764081512327642",
    "7643764081512327625",
    "7643764081512327614",
    "7643764145933907243"
  ],
  "source_spans": [
    "持续攻击的话攻击间隔就是索敌间隔",
    "是由索敌间隔决定的",
    "动画没结束不能索敌，索敌冷却没转好不能索敌",
    "那个说的是3帧归0之后动画没结束也不能抬手",
    "所以不是每3一次",
    "不是每3一次不等于没了3限制"
  ]
}
```

说明：参数 value `"3帧"` 逐字出现在对应 `source_span` 里。若某数字窗内从未出现，应把 `underlying_parameters` 设为 `[]`。

---

## User 模板（复制后替换占位符）

请根据下面的群聊窗提炼一张机制知识卡片。只输出一个 JSON 对象。

{WINDOW_PAYLOAD}
'''


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="导出群聊窗 LLM 交接包")
    p.add_argument("--windows", default=DEFAULT_WINDOWS)
    p.add_argument("--messages", default=DEFAULT_MESSAGES)
    p.add_argument("--tier", default="candidate")
    p.add_argument("--top", type=int, default=0, help="最多导出 N 窗，0=全部")
    p.add_argument("--batch-size", type=int, default=25)
    p.add_argument("--out-dir", default=DEFAULT_OUT)
    args = p.parse_args(argv)

    log(f"读 windows: {args.windows}")
    windows = load_jsonl(args.windows)
    selected = [w for w in windows if w.get("tier") == args.tier]
    selected.sort(
        key=lambda w: (
            not bool(w.get("fast_track")),
            -int(w.get("score") or 0),
            w.get("window_id") or "",
        )
    )
    if args.top and args.top > 0:
        selected = selected[: args.top]
    log(f"tier={args.tier} 选中 {len(selected)} / {len(windows)}")

    log(f"读 messages: {args.messages}")
    msg_idx = load_messages_index(args.messages)
    log(f"消息索引 {len(msg_idx)}")

    os.makedirs(args.out_dir, exist_ok=True)
    batch_size = max(1, args.batch_size)
    n_batches = (len(selected) + batch_size - 1) // batch_size if selected else 0
    missing_total = 0
    for b in range(n_batches):
        chunk = selected[b * batch_size : (b + 1) * batch_size]
        path = os.path.join(args.out_dir, f"batch_{b + 1:03d}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for w in chunk:
                payload = window_payload(w, msg_idx)
                missing_total += int(payload.pop("_missing_msgs", 0))
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        log(f"  {os.path.basename(path)}  {len(chunk)} 窗")

    prompt_path = os.path.join(args.out_dir, "PROMPT.md")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(PROMPT_MD.lstrip("\n"))

    print(
        f"exported windows={len(selected)} batches={n_batches} "
        f"batch_size={batch_size} missing_msgs={missing_total} out={args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
