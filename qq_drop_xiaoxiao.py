#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已产物中剔除小晓 bot 消息，不重切簇。

bot 的 QQ 号不入库，由 qq_info/identities.json 的 xiaoxiao_qq 注入。"""

from __future__ import annotations

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
from local_ids import XIAOXIAO_QQ as QQ
SID = "e3d07517"
INFO = os.path.join(ROOT, "qq_info")
CARDS = os.path.join(ROOT, "qq_cards", "cards.jsonl")


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def dump_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_bot(m: dict) -> bool:
    return m.get("qq") == QQ or m.get("speaker_id") == SID


def main() -> None:
    msgs_path = os.path.join(INFO, "messages_clean.jsonl")
    wins_path = os.path.join(INFO, "windows.jsonl")
    msgs = load_jsonl(msgs_path)
    bot_ids = {m["msg_id"] for m in msgs if is_bot(m)}
    kept = [m for m in msgs if not is_bot(m)]
    print(f"messages_clean {len(msgs)} -> {len(kept)} dropped {len(msgs) - len(kept)}")
    dump_jsonl(msgs_path, kept)

    wins = load_jsonl(wins_path)
    touched = 0
    emptied = 0
    for w in wins:
        ids = w.get("source_msg_ids") or []
        new = [i for i in ids if i not in bot_ids]
        if len(new) != len(ids):
            touched += 1
            w["source_msg_ids"] = new
            w["slim_n"] = len(new)
            w["n_messages"] = len(new)
            if not new:
                emptied += 1
    print(f"windows stripped {touched} emptied {emptied} total {len(wins)}")
    dump_jsonl(wins_path, wins)

    cards = load_jsonl(CARDS)
    c_touch = 0
    for c in cards:
        ids = c.get("source_msg_ids") or []
        new = [i for i in ids if i not in bot_ids]
        if len(new) != len(ids):
            c_touch += 1
            c["source_msg_ids"] = new
    print(f"cards stripped {c_touch}")
    dump_jsonl(CARDS, cards)

    sm_path = os.path.join(INFO, "speaker_map.json")
    sm = json.load(open(sm_path, encoding="utf-8"))
    speakers = sm.get("speakers") or {}
    if QQ in speakers:
        del speakers[QQ]
        sm["n_speakers"] = len(speakers)
        json.dump(sm, open(sm_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("speaker_map removed", QQ)


if __name__ == "__main__":
    main()
