# -*- coding: utf-8 -*-
"""
atomize_claims.py — 将章节知识卡拆成原子命题 (草稿层)

步骤:
  1. 规则过滤方法论/闲聊/无机制内容 → noise jsonl
  2. LLM 将每张父卡拆成原子命题, 证据必须是父卡 quote 的子串
  3. 程序校验 quote; 汉字数字另存 value_norm; 针→帧
  4. 写入 {stem}.atoms.jsonl

课型路由 (写入原子卡, 供后续聚类使用, 本脚本不合成「正确卡」):
  lecture + 寻路/平整化 → lesson_kind=algorithm, 要求 derivation_step
  lecture + 帧时序/技力  → lesson_kind=derivation
  combat                 → lesson_kind=observation_default
  其余                   → lesson_kind=general
"""

import argparse
import json
import re
import sys
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pilot_extract_claims as base

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "knowledge_pilot"

NOISE_CATEGORIES = {"学习方法", "机制方法论"}
MECH_HINT = re.compile(
    r"帧|索敌|寻路|平整|仇恨|技力|冷却|部署|前摇|后摇|避障|阻挡|位移|"
    r"攻速|费用|判定|过滤器|同帧|出伤|沉睡|眩晕"
)
CN_NUM = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

RETRIEVAL_WEIGHT = {
    "conclusion": 1.0,
    "correction": 1.0,
    "observation": 0.6,
    "derivation": 0.6,
    "hypothesis": 0.2,
    "question": 0.1,
}

CONTRACT = """你把一张父级机制知识卡拆成原子命题。输入含父卡结论、参数、证据原文。

契约:
1. 每条原子卡恰好一个 proposition、一个 claim_type。claim_type 只能是 question/hypothesis/derivation/observation/conclusion/correction。
2. 一条结论若同时含定论和猜测, 必须拆开, 猜测标 hypothesis。
3. evidence.quote 必须是「父卡证据」里真实出现的连续子串, 尽量短, 只覆盖本条命题。不要跨到别的结论的原话。
4. parameters 只保留本条用到的; 没有则 []。unit 用 帧/秒/格/百分比/无, 原文写「针」则 unit=帧。
5. conditions: 本条成立的前提(如前十费、同帧部署、代理而非手操)。没有则 []。
6. applies_to: 仅该干员/技能则写具体名, 否则 "general"。
7. visual_required: 依赖「这个格/如图/看这里」则为 true。
8. derivation_step: 若是算法/公式中的第 N 步(从1开始), 填整数; 否则 null。
9. 禁止用训练知识补全数字或机制; 闲聊、学习方法、攻略哲学不要产出原子卡。
10. 若整张父卡没有机制命题, 返回 {"drop_parent": true, "drop_reason": "...", "atoms": []}。

只输出 JSON:
{"drop_parent": false, "drop_reason": "",
 "atoms": [{"proposition": "...", "claim_type": "...",
   "conditions": [], "applies_to": "general", "visual_required": false,
   "derivation_step": null,
   "parameters": [{"name": "...", "value": "...", "unit": "...", "source_span": "..."}],
   "evidence": [{"start": 秒, "end": 秒, "quote": "..."}]}]}"""


def lesson_kind(card: dict) -> str:
    cat = card.get("category") or ""
    kind = (card.get("chapter") or {}).get("kind") or ""
    if kind == "combat":
        return "observation_default"
    if re.search(r"寻路|平整|避障", cat):
        return "algorithm"
    if re.search(r"帧时序|技力|冷却|计时", cat):
        return "derivation"
    if re.search(r"技能特例", cat) and card.get("entities"):
        return "special_case"
    return "general"


def is_noise(card: dict) -> str | None:
    cat = card.get("category") or ""
    kind = (card.get("chapter") or {}).get("kind") or ""
    blob = json.dumps(card, ensure_ascii=False)
    if cat in NOISE_CATEGORIES:
        return "noise_category"
    if kind == "warmup":
        return "warmup"
    if kind == "other" and not MECH_HINT.search(blob):
        return "other_no_mechanism"
    if not card.get("core_conclusions"):
        return "no_conclusion"
    return None


def cn_to_int(s: str):
    s = (s or "").strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return s
    if s in CN_NUM:
        return str(CN_NUM[s])
    m = re.fullmatch(r"十([一二三四五六七八九])?", s)
    if m:
        return str(10 + CN_NUM.get(m.group(1) or "", 0))
    m = re.fullmatch(r"([一二三四五六七八九])十([一二三四五六七八九])?", s)
    if m:
        return str(CN_NUM[m.group(1)] * 10 + CN_NUM.get(m.group(2) or "", 0))
    m = re.fullmatch(r"([一二三四五六七八九])百([零一二三四五六七八九十]+)?", s)
    if m:
        rest = cn_to_int(m.group(2) or "0")
        try:
            return str(CN_NUM[m.group(1)] * 100 + int(rest))
        except Exception:
            return None
    return None


def norm_unit(u: str) -> str:
    u = (u or "").strip()
    if u in ("针", "针数"):
        return "帧"
    if u in ("unknown", "无", ""):
        return "无"
    return u


def parent_evidence_blob(card: dict) -> str:
    parts = [ev.get("quote") or "" for ev in card.get("evidence") or []]
    parts += [p.get("source_span") or "" for p in card.get("underlying_parameters") or []]
    return "\n".join(parts)


def atom_id(stem: str, parent_idx: int, atom_idx: int, prop: str) -> str:
    h = hashlib.sha1(prop.encode("utf-8")).hexdigest()[:8]
    return f"{stem}:p{parent_idx}:a{atom_idx}:{h}"


def call_split(card: dict):
    payload = {
        "topic": card.get("topic"),
        "category": card.get("category"),
        "entities": card.get("entities"),
        "context_question": card.get("context_question"),
        "core_conclusions": card.get("core_conclusions"),
        "underlying_parameters": card.get("underlying_parameters"),
        "evidence": card.get("evidence"),
        "chapter": card.get("chapter"),
    }
    return base.call_llm(
        CONTRACT + "\n\n=== 父卡 ===\n" + json.dumps(payload, ensure_ascii=False)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stem", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    src = OUT_DIR / f"{args.stem}.chapter_claims.jsonl"
    parents = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        parents = parents[: args.limit]
    print(f"{args.stem}: {len(parents)} 张父卡", flush=True)

    noise_path = OUT_DIR / f"{args.stem}.noise.jsonl"
    atoms_path = OUT_DIR / f"{args.stem}.atoms.jsonl"
    # 本试点覆盖写, 避免半截结果
    if atoms_path.exists():
        atoms_path.unlink()
    if noise_path.exists():
        noise_path.unlink()

    kept = []
    n_noise = 0
    with open(noise_path, "a", encoding="utf-8") as fn:
        for i, card in enumerate(parents):
            why = is_noise(card)
            if why:
                rec = {"parent_idx": i, "reason": why, "topic": card.get("topic")}
                fn.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_noise += 1
            else:
                kept.append((i, card))
    print(f"规则过滤噪声 {n_noise}, 待拆 {len(kept)}", flush=True)

    def process(item):
        i, card = item
        try:
            result, usage = call_split(card)
        except Exception as e:
            return i, card, None, str(e)
        return i, card, result, usage

    n_ok = n_unbound = n_drop = n_fail = 0
    with open(atoms_path, "a", encoding="utf-8") as fa:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for i, card, result, extra in ex.map(process, kept):
                if result is None:
                    print(f"FAIL p{i}: {extra}", flush=True)
                    n_fail += 1
                    continue
                if result.get("drop_parent"):
                    with open(noise_path, "a", encoding="utf-8") as fn:
                        fn.write(json.dumps(
                            {"parent_idx": i, "reason": "llm_drop",
                             "detail": result.get("drop_reason"),
                             "topic": card.get("topic")},
                            ensure_ascii=False) + "\n")
                    n_drop += 1
                    print(f"DROP p{i}: {result.get('drop_reason','')[:40]}", flush=True)
                    continue
                blob = parent_evidence_blob(card)
                lk = lesson_kind(card)
                atoms = result.get("atoms") or []
                wrote = 0
                for j, raw in enumerate(atoms):
                    prop = (raw.get("proposition") or "").strip()
                    ctype = raw.get("claim_type") or "conclusion"
                    if not prop:
                        continue
                    evs = []
                    unbound = False
                    for ev in raw.get("evidence") or []:
                        q = ev.get("quote") or ""
                        fake = {"evidence": [ev], "underlying_parameters": []}
                        if not q or not base.validate(fake, blob):
                            unbound = True
                        else:
                            evs.append({"start": ev.get("start"), "end": ev.get("end"),
                                        "quote": q})
                    params = []
                    for p in raw.get("parameters") or []:
                        val = str(p.get("value") or "")
                        params.append({
                            "name": p.get("name"),
                            "value_raw": val,
                            "value_norm": cn_to_int(val),
                            "unit": norm_unit(p.get("unit")),
                            "source_span": p.get("source_span"),
                        })
                    atom = {
                        "atom_id": atom_id(args.stem, i, j, prop),
                        "parent_idx": i,
                        "parent_topic": card.get("topic"),
                        "proposition": prop,
                        "claim_type": ctype,
                        "retrieval_weight": RETRIEVAL_WEIGHT.get(ctype, 0.3),
                        "claim_status": "draft",
                        "conditions": raw.get("conditions") or [],
                        "applies_to": raw.get("applies_to") or "general",
                        "visual_required": bool(raw.get("visual_required")),
                        "derivation_step": raw.get("derivation_step"),
                        "lesson_kind": lk,
                        "category": card.get("category"),
                        "entities": card.get("entities") or [],
                        "parameters": params,
                        "evidence": evs,
                        "quote_check": "unbound" if (unbound or not evs) else "pass",
                        "source_id": card.get("source_id"),
                        "track": card.get("track"),
                        "timeline": card.get("timeline"),
                        "chapter": card.get("chapter"),
                        "window": card.get("window"),
                        "status": "draft",
                    }
                    fa.write(json.dumps(atom, ensure_ascii=False) + "\n")
                    fa.flush()
                    wrote += 1
                    if atom["quote_check"] == "pass":
                        n_ok += 1
                    else:
                        n_unbound += 1
                print(f"p{i} 《{str(card.get('topic'))[:28]}》 → {wrote} 原子", flush=True)
    print(f"完成: pass={n_ok} unbound={n_unbound} llm_drop={n_drop} fail={n_fail} noise={n_noise}",
          flush=True)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
