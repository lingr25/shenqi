# -*- coding: utf-8 -*-
"""kb_synthesize.py - R5 簇级合成: 议题簇 → 完整机制词条

对每个有效 vod_cluster, 把成员原子命题+原话证据+QQ counterpart 卡合成为一段完整词条。
只许用输入材料中的事实, 不许脑补; hypothesis/question 必须显式标注; conflict 簇双方并列并标 vod_wins。

产物:
  默认(生产, 本任务禁止调用): kb/synthesized.jsonl (缓存 kb/.synth_cache.json)
  --pilot: 独立目录, 版本化缓存, 不写 kb/docs.jsonl 与 kb/synthesized.jsonl

用法:
  GROK_API_KEY=... GROK_MODEL=deepseek-v4.1-flash python kb_synthesize.py --pilot \\
      --ids 帧时序与计时器-3-10,索敌-0-1 --prompt-version v1 --out-dir kb_pilot_synth
"""
import json
import os
import glob
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import grok_client

_CN_DIGIT = {"零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
             "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
_CN_NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
           "十三": 13, "十四": 14, "十五": 15, "十六": 16, "十七": 17,
           "十八": 18, "十九": 19, "二十": 20, "二十一": 21, "二十二": 22,
           "二十三": 23, "二十四": 24, "二十五": 25, "二十六": 26,
           "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
           "四十": 40, "五十": 50, "六十": 60, "七十": 70, "八十": 80,
           "九十": 90, "一百": 100}

# 含「一/二/三」的常用词, 禁止当数字改写
_PROTECT_WORDS = [
    "四舍五入", "一技能", "二技能", "三技能",
    "一旦", "统一", "一起", "一定", "一般", "一样", "一直", "一些", "一切",
    "一方面", "一带", "一是", "一种", "一下", "一点", "一共", "一向", "一时",
    "一并", "一概", "一律", "一齐", "万一", "之一", "唯一", "同一", "一判",
    "一再", "一来", "一则", "一口", "一线", "一贯", "一连", "一举",
    "下一秒", "上一秒", "每一秒", "下一帧", "上一帧", "每一帧",
]

# ASR 把「帧」听成「针」的高频词形
_ZHEN_WORDS = ["出生针", "索敌针", "出怪针", "部署针", "落地针", "攻击针",
               "技能针", "冷却针", "判定针", "抬手针", "移动针", "刷新针",
               "检测针", "动画针", "索敌真", "出生真", "锁敌针"]

_CN_NUM_RE = r"[零一二两三四五六七八九十百]+(?:点[零一二两三四五六七八九]+)?"
_UNIT_RE = r"(?:帧|针|秒|格|倍)"


def _cn_num(s):
    """中文数字串→阿拉伯, 只处理无歧义形式。无法解析返回 None。"""
    if "点" in s:
        pre, _, post = s.partition("点")
        if pre and pre not in _CN_DIGIT and pre not in _CN_NUM:
            return None
        pre_n = str(_CN_NUM.get(pre, _CN_DIGIT.get(pre, "0")))
        post_n = "".join(_CN_DIGIT.get(c, "?") for c in post)
        if "?" in post_n:
            return None
        return f"{pre_n}.{post_n}"
    if "百" in s:
        a, _, b = s.partition("百")
        if a and a not in _CN_DIGIT:
            return None
        base = int(_CN_DIGIT.get(a, "1")) * 100
        if not b:
            return str(base)
        rest = _cn_num(b)
        return str(base + int(rest)) if rest is not None else None
    if s.count("十") == 1:
        a, b = s.split("十")
        if (a and a not in _CN_DIGIT) or (b and b not in _CN_DIGIT):
            return None
        tens = _CN_DIGIT.get(a, "1")
        units = _CN_DIGIT.get(b, "0")
        return str(int(tens) * 10 + int(units))
    if s in _CN_NUM:
        return str(_CN_NUM[s])
    if len(s) == 1 and s in _CN_DIGIT:
        return _CN_DIGIT[s]
    return None


def _safe_cn(s):
    """歧义长串或无法解析则原样返回。"""
    if not s:
        return s
    if s.count("十") >= 2 or ("点" not in s and len(s) >= 6):
        return s
    n = _cn_num(s)
    return n if n is not None else s


def _asr_zhen_fix(text):
    out = text.replace("一盼", "一判")
    for w in _ZHEN_WORDS:
        out = out.replace(w, w[:-1] + "帧")
    out = re.sub(r"(\d+)针", r"\1帧", out)
    # 只改「针」→「帧」，不把「六针」变成「6帧」
    out = re.sub(r"(" + _CN_NUM_RE + r")针", r"\1帧", out)
    return out


def norm_cn_numbers(text):
    """ASR 针→帧; 保护一旦/下一秒等; 只转比式与 Cn 公式。不把六十九帧改成 69。"""
    if not text:
        return text
    out = _asr_zhen_fix(text)
    holders = []

    def stash(word):
        def repl(_m, w=word):
            holders.append(w)
            return f"\x00W{len(holders)-1}\x00"
        return repl

    for w in _PROTECT_WORDS:
        if w in out:
            out = re.sub(re.escape(w), stash(w), out)

    def repl_ratio(m):
        return f"{_safe_cn(m.group(1))}比{_safe_cn(m.group(2))}"

    def repl_n(m):
        return _safe_cn(m.group(1)) + "n"

    # 不把「六十九帧/下一秒」改成阿拉伯数字；只转比式与 Cn 公式
    out = re.sub(rf"({_CN_NUM_RE})比({_CN_NUM_RE})", repl_ratio, out)
    out = re.sub(rf"({_CN_NUM_RE})n", repl_n, out)

    def unstash(m):
        return holders[int(m.group(1))]

    out = re.sub(r"\x00W(\d+)\x00", unstash, out)
    return out


def load_source_atoms(correct_quotes=False):
    """加载 enriched atoms。命题可套纠错; 原话默认不改写。"""
    import re as _re
    from entity_corrector import CORRECTION_RULES
    atoms = {}
    for f in glob.glob("knowledge_pilot/*.atoms.enriched.jsonl"):
        for l in open(f, encoding="utf-8"):
            a = json.loads(l)
            for p, r in CORRECTION_RULES:
                a["proposition"] = _re.sub(p, r, a.get("proposition", ""))
                if correct_quotes:
                    for ev in a.get("evidence") or []:
                        if ev.get("quote"):
                            ev["quote"] = _re.sub(p, r, ev["quote"])
            atoms[a["atom_id"]] = a
    return atoms


CACHE = "kb/.synth_cache.json"

PROMPT_V1 = """你是明日方舟机制百科的撰写员。下面是同一个机制议题下的若干条提炼命题与原话证据。请合成一段完整、自洽的机制词条。

输出严格JSON：
{{"title": "词条标题(含主语)",
 "applies_to": "适用对象(干员/敌人/机制名；主语在材料中不可考则填「未点名」，禁止用「通用」凑数)",
 "rules": [{{"text": "一条规则", "subject": "该条主语", "when": ["生效条件"], "evidence_atom_ids": ["atom_id"], "scope": "universal|instance"}}],
 "conditions": ["词条级前提"],
 "exceptions": ["例外/边界"],
 "open_questions": ["尚未解决/待验证"],
 "scope": "universal|instance",
 "confidence": "high|mid|low"}}

铁律：
- 只许使用【命题与证据】中的事实，严禁补充游戏常识。证据不够就让 rules 为空（abstain），不要为了像词条而编造
- 数值/帧数必须逐字符从原文复制，禁止改写或翻译数字（2.75帧、0.05格、六十九 均可原样保留）
- 无法解析的中文数字串禁止放入 rules，写入 open_questions 并注明「数值待听原音」
- 每条 rule 必须带 evidence_atom_ids，且 id 必须来自输入的 [id=...]；写不出证据的条目不要进 rules
- subject 必须能在该条所引 atom 的对象字段或原话中找到；材料没点名就填「未点名」，禁止猜测干员名
- 局部观测（某次部署实验、某关、某演示）scope=instance，禁止升格为跨对象通则
- 无实质结论（如「车来了」）丢弃。hypothesis/question 只能进 open_questions
- 材料间矛盾时在 rules 里并列并注明「(存争议)」
- applies_to 为「通用」仅当材料明确跨对象适用
- scope: universal=可复用规则; instance=单次实验/关卡观测（标题写明场景）
- confidence 只评估**已写入 rules 的命题**：主播对机制作了明确、完整、直接的讲述即可 high（即使只有一条原话、只有一个来源）。mid=讲述不完整或需跨句拼凑推导。low=材料含糊、主语不清、或 rules 为空。有数字≠high。缺多个来源不是扣分理由。open_questions 的存在不影响 confidence

[议题标题] {title}
[议题问题] {question}
[档案备注] {note}

[命题与证据]
{atoms}

{qq_block}
{sub_block}"""


PROMPT_V2 = """你是明日方舟机制百科的撰写员。只用【命题与证据】里的事实合成词条，禁止游戏常识补全。证据不够就 rules=[]（abstain）。

输出严格JSON：
{{"title": "词条标题(含主语与关键条件)",
 "applies_to": "适用对象；原话或议题标题已出现的对象可用；都没有则「未点名」；禁止猜干员名、禁止用「通用」凑数",
 "rules": [{{"text": "合并后的规则", "subject": "该条主语", "when": ["生效条件，没有则[]"], "evidence_atom_ids": ["atom_id"], "scope": "universal|instance"}}],
 "conditions": ["词条级前提（机制条件，不要写实验流程备注）"],
 "exceptions": ["例外/边界"],
 "open_questions": ["材料里真正未决的问题或 hypothesis"],
 "scope": "universal|instance",
 "confidence": "high|mid|low"}}

合成要求：
1. 合并同义重复和同一推导链，典型 2–6 条 rules，禁止一条 atom 抄成一条 rule。
2. 每条 rule 必须能被 evidence_atom_ids 的原话支撑。
3. 数字按原话抄：原文写「零帧/一针/六针/两格/六十九」就保持这种写法，不要改成 0帧/1帧/2格。原话已是阿拉伯数字则保持阿拉伯数字。
4. 「针」在机制语境就是「帧」的听写，写入规则可用「帧」但数字本身不要改；禁止把「一针/六针/出生针」标成「数值待听原音」。只有「零二十四十四」这类无法解析的串才待听原音。
5. instance 仅当材料给出明确实验条件（如零帧部署一帧撤退、空费帧演示、集海默课题、具体两格/0.4 的演算例）。不要因为「来自一场直播」就标 instance。
6. hypothesis/question 只进 open_questions。无信息条目丢弃。
7. open_questions 不要写程序性套话（「细节未说明」「本轮未提供QQ」）。材料没当成问题的不要编问题。
8. confidence 评估已成立 rules：主播明确完整直接讲述 → high（单条、单来源也可以）。mid=需跨句拼凑。low=含糊或 rules 空。有数字≠high。缺多个来源不扣分。open_questions 不扣分。
9. 本输入可能不含QQ。不要把「隔离QQ/未提供QQ」写进 conditions 或 rules。

[议题标题] {title}
[议题问题] {question}
[档案备注] {note}

[命题与证据]
{atoms}

{qq_block}
{sub_block}"""


PROMPT_V3 = """你是明日方舟机制百科的撰写员。只用【命题与证据】和可选的【原字幕邻近】补证。禁止游戏常识。证据不够就删那一条 rule，保留能站住的部分，不要为了整洁把有用规则清空。

输出严格JSON：
{{"title": "词条标题(含主语与关键条件)",
 "applies_to": "适用对象；原话/议题标题已出现的可用；无法确认则「未点名」；禁止猜干员名、禁止用「通用」凑数",
 "rules": [{{"text": "一条自包含规则(含必要前提)", "subject": "该条主语", "when": ["该条生效条件"], "evidence_atom_ids": ["atom_id或ctx id"], "scope": "universal|instance|example"}}],
 "conditions": ["词条级机制前提"],
 "exceptions": ["例外/边界"],
 "open_questions": ["材料里真正未决的问题或 hypothesis"],
 "scope": "universal|instance|example",
 "confidence": "high|mid|low"}}

scope：
- universal=跨对象可复用机制，when 必须写清前提
- instance=某次实验/部署/关卡观测（零帧部署一帧撤退、空费帧演示、集海默）
- example=带具体数值的演算例题或演示（如 1.95格、0.4、149→150）。example/instance 禁止标成 universal
词条级 scope 取最窄（有 example 用 example；纯实验用 instance）。

要求：
1. 合并同义，但不同观测不要揉成一条。指代不清就保持原句（「它现在变成了零到五十九」不要改成「车辆位置范围」）。
2. 每条 when 自包含。数字与原话等价即可（零帧=0帧、一针=1帧不算错误）；【原话】行保持原文。
3. 「针」=「帧」听写，不要标成待听原音。只有「零二十四十四」这类才待听原音。
4. hypothesis/question 只进 open_questions。无信息条目丢弃。
5. 【原字幕邻近】只给已有讲解补证，必须引用 ctx= 编号；不能把字幕里一闪而过、无法确认的对象写进 applies_to。
6. 演算例题 scope=example。取整若主播说成一般原则可 universal，when 写明「刚好整数/非整数」。
7. confidence：明确完整直接讲述→high（单条也可以）。mid=需拼凑。low=含糊或 rules 空。open_questions 不扣分。缺多个来源不扣分。
8. 不要把实验备注写进 conditions。

[议题标题] {title}
[议题问题] {question}
[档案备注] {note}

[命题与证据]
{atoms}

{qq_block}
{sub_block}"""

PROMPT_V4 = """你是明日方舟机制百科的撰写员。只用【命题与证据】和可选的【原字幕邻近】。禁止游戏常识补全。证据不够就删那一条，保留能站住的部分。

输出严格JSON：
{{"title": "词条标题(含主语与关键条件)",
 "applies_to": "适用对象；原话/议题标题已出现的可用；无法确认则「未点名」；禁止猜干员名、禁止用「通用」凑数",
 "kind": "mechanism|experiment|reject|pending",
 "context_incomplete": false,
 "rules": [{{"text": "一条自包含规则(含必要前提)", "subject": "该条主语", "when": ["该条生效条件"], "evidence_atom_ids": ["atom_id或ctx id"], "scope": "universal|instance|example"}}],
 "conditions": ["词条级机制前提"],
 "exceptions": ["例外/边界"],
 "open_questions": ["材料里真正未决的问题或 hypothesis"],
 "scope": "universal|instance|example",
 "confidence": "high|mid|low"}}

kind：mechanism=可独立陈述的机制（主语+条件闭合）；experiment=当场部署/关卡/读数；pending=单位/数字/主语未闭合；reject=无信息或无法成卡。不要为产量把 pending 写成 mechanism。
context_incomplete=true 仅当材料明显被截断、跨文件对不齐、或字幕邻近不足——标出来，禁止编造补全。

scope：
- universal=跨对象可复用机制，when 必须写清前提
- instance=某次实验/部署/关卡观测
- example=带具体数值的演算例题
example/instance 禁止标成 universal。词条级 scope 取最窄。

要求：
1. 合并同义，不同观测不要揉成一条。指代不清就保持原句。
2. 每条 when 自包含。数字按原话；零帧=0帧、一针=1帧不算错误。【原话】行保持原文，不要改写引文。
3. 「针」=「帧」听写。缺单位的数字不要猜秒或帧；不要把「可能是帧」写成事实。
4. 禁止把下列未闭合内容写成 mechanism：1/10=3/30=0.05 当一帧可达半径；「补整之后加一」当公式；剩余冷却 0.5 的单位。这些进 pending 或 open_questions。
5. 禁止改专有名词：珊比、酒神、遥、桃金娘、塞雷娅、杰西卡、伊内丝。不要「纠正」成词典里别的名字。
6. hypothesis/question 只进 open_questions。无信息条目丢弃。open_questions 不扣 confidence。
7. 【原字幕邻近】只给已有讲解补证，必须引用 ctx= 编号；不能把一闪而过的对象写进 applies_to。
8. conflict 议题：双方并列，不要自动 vod_wins 删掉一边。
9. 不要用 QQ 给录播补主语（本输入可能无QQ）。
10. confidence：明确完整直接讲述→high。mid=需拼凑。low=含糊或 rules 空。缺多个来源不扣分。

[议题标题] {title}
[议题问题] {question}
[档案备注] {note}

[命题与证据]
{atoms}

{qq_block}
{sub_block}"""


PROMPTS = {"v1": PROMPT_V1, "v2": PROMPT_V2, "v3": PROMPT_V3, "v4": PROMPT_V4}


def fmt_atoms(members, max_members=None, quote_limit=500, max_chars=None):
    """命题可做安全数字规范化; 原话保持原文(不做纠错、不做中文数字改写)。"""
    lines = []
    use = members if max_members is None else members[:max_members]
    for m in use:
        aid = m.get("atom_id") or "?"
        prop = norm_cn_numbers(m.get("proposition") or "")
        head = f"- [id={aid}] [{m.get('claim_type','?')}] {prop}"
        if m.get("applies_to") and m["applies_to"] != "general":
            head += f" (对象:{m['applies_to']})"
        else:
            head += " (对象:未点名或general)"
        if m.get("conditions"):
            conds = []
            for c in m["conditions"]:
                if isinstance(c, dict):
                    conds.append(norm_cn_numbers(f"{c.get('name','')}={c.get('value','')}"))
                else:
                    conds.append(norm_cn_numbers(str(c)))
            head += " (条件:" + ";".join(conds) + ")"
        if m.get("parameters"):
            parts = []
            for p in m["parameters"]:
                if not isinstance(p, dict):
                    continue
                raw = str(p.get("value_raw") or "")
                parts.append(f"{p.get('name','')}={raw}{p.get('unit') or ''}")
            if parts:
                head += " (参数:" + ";".join(parts) + ")"
        lines.append(head)
        for ev in (m.get("evidence") or []):
            q = ev.get("quote") or ""
            if not q:
                continue
            if quote_limit and len(q) > quote_limit:
                q = q[:quote_limit] + "…"
            lines.append(f"  原话[{ev.get('start','?')}s]: {q}")
    text = "\n".join(lines)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n…(截断)"
    return text


_TS_LINE = re.compile(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)$")


def _load_ts_rows(stem):
    for p in (f"transcripts_txt/{stem}.txt",
              f"asr_drafts/{stem}_asr.txt",
              f"asr_drafts/{stem}_asr_draft.txt"):
        if not os.path.exists(p):
            continue
        rows = []
        for line in open(p, encoding="utf-8"):
            m = _TS_LINE.match(line.rstrip())
            if not m:
                continue
            h = int(m.group(1) or 0)
            sec = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            rows.append((sec, m.group(4), p))
        return rows
    return []


def fmt_sub_ctx(members, pad=40, max_lines=18, max_chars=2800):
    """有界原字幕邻近：按 atom 时间±pad 秒，限行/限字，带 file+t+ctx id。"""
    by_stem = {}
    for m in members:
        stem = m.get("source_id") or (m.get("atom_id") or "").split(":")[0]
        if not stem:
            continue
        for ev in m.get("evidence") or []:
            t = ev.get("start")
            if t is None:
                continue
            by_stem.setdefault(stem, set()).add(int(float(t)))
    if not by_stem:
        return ""
    out = ["[原字幕邻近(补证, 与atom分开; 仅下列有界片段)]"]
    scored = []
    for stem, times in by_stem.items():
        rows = _load_ts_rows(stem)
        if not rows:
            out.append(f"- (未找到字幕 stem={stem})")
            continue
        for sec, text, path in rows:
            dist = min(abs(sec - t) for t in times)
            raw = (text or "").strip()
            if dist > pad or not raw or raw in (".", "。", "OK.", "对。"):
                continue
            if "进入直播间" in raw and len(raw) < 80:
                continue
            scored.append((dist, sec, text, path, stem))
    scored.sort(key=lambda x: (x[0], x[1]))
    picked = sorted(scored[:max_lines], key=lambda x: x[1])
    for _dist, sec, text, path, stem in picked:
        out.append(f"- [ctx=sub:{stem}:{sec} file={path} t={sec}] {text}")
    text = "\n".join(out)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…(字幕上下文截断)"
    return text


def _rule_text(x):
    if isinstance(x, dict):
        return (x.get("text") or "").strip()
    return str(x).strip()


def render(r, cluster, members):
    lines = [f"# {r['title']}", f"适用对象: {r.get('applies_to') or ''}"]
    scope = r.get("scope")
    if scope == "instance":
        lines.append("范围: 单关/单次实验观测")
    elif scope == "example":
        lines.append("范围: 演算例题/带数值的演示")
    elif scope == "universal":
        lines.append("范围: 可复用规则")
    if r.get("rules"):
        lines.append("## 规则")
        for x in r["rules"]:
            t = _rule_text(x)
            if not t:
                continue
            extra = ""
            if isinstance(x, dict):
                ids = x.get("evidence_atom_ids") or []
                subj = x.get("subject") or ""
                when = x.get("when") or []
                sc = x.get("scope") or ""
                bits = []
                if subj:
                    bits.append(f"主语:{subj}")
                if when:
                    bits.append("条件:" + ";".join(str(w) for w in when))
                if sc:
                    bits.append(f"scope:{sc}")
                if ids:
                    bits.append("证据:" + ",".join(ids))
                if bits:
                    extra = "  (" + " | ".join(bits) + ")"
            lines.append(f"- {t}{extra}")
    if r.get("conditions"):
        lines.append("## 条件")
        lines += [f"- {x}" for x in r["conditions"]]
    if r.get("exceptions"):
        lines.append("## 例外")
        lines += [f"- {x}" for x in r["exceptions"]]
    if r.get("open_questions"):
        lines.append("## 待验证")
        lines += [f"- {x}" for x in r["open_questions"]]
    if cluster.get("issue_status") == "conflict":
        lines.append("⚠ 本议题存在争议, 以上规则含存争议内容")
    return "\n".join(lines)


def _normalize_llm_result(r):
    if not isinstance(r, dict):
        raise ValueError("bad synth json: not object")
    if not r.get("title"):
        raise ValueError("bad synth json: no title")
    rules = r.get("rules")
    if rules is None:
        r["rules"] = []
    elif not isinstance(rules, list):
        raise ValueError("bad synth json: rules not list")
    else:
        normed = []
        for x in rules:
            if isinstance(x, str) and x.strip():
                normed.append({"text": x.strip(), "subject": "", "when": [],
                               "evidence_atom_ids": [], "scope": r.get("scope") or ""})
            elif isinstance(x, dict) and _rule_text(x):
                ids = x.get("evidence_atom_ids") or x.get("evidence_ids") or []
                if isinstance(ids, str):
                    ids = [ids]
                when = x.get("when") or x.get("conditions") or []
                if isinstance(when, str):
                    when = [when]
                normed.append({
                    "text": _rule_text(x),
                    "subject": x.get("subject") or "",
                    "when": when,
                    "evidence_atom_ids": ids,
                    "scope": x.get("scope") or r.get("scope") or "",
                })
        r["rules"] = normed
    if r.get("confidence") not in ("high", "mid", "low"):
        r["confidence"] = "low"
    if r.get("kind") not in ("mechanism", "experiment", "reject", "pending"):
        if not r.get("rules"):
            r["kind"] = "reject"
        elif r.get("scope") in ("instance", "example"):
            r["kind"] = "experiment"
        else:
            r["kind"] = "mechanism"
    r["context_incomplete"] = bool(r.get("context_incomplete"))
    valid = ("universal", "instance", "example")
    if r.get("scope") not in valid:
        scopes = {x.get("scope") for x in r["rules"] if isinstance(x, dict) and x.get("scope") in valid}
        extra = scopes - {"universal"}
        if scopes == {"instance"}:
            r["scope"] = "instance"
        elif extra:
            r["scope"] = "example" if "example" in extra else "instance"
        else:
            r["scope"] = "universal"
    return r


def parse_args(argv):
    args = {
        "workers": 16,
        "pilot": False,
        "ids": None,
        "ids_file": None,
        "limit": None,
        "out_dir": None,
        "cache": None,
        "prompt_version": "v1",
        "retry_errors": True,
        "max_members": 12,
        "max_atom_chars": 3000,
        "quote_limit": 100,
        "self_test": False,
        "dry_run": False,
        "correct_quotes": False,
        "no_qq": False,
        "retries": 2,
        "sub_ctx": False,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--workers":
            args["workers"] = int(argv[i + 1]); i += 2; continue
        if a == "--pilot":
            args["pilot"] = True
            args["retry_errors"] = True
            args["max_members"] = None
            args["max_atom_chars"] = None
            args["quote_limit"] = 500
            args["workers"] = min(args["workers"], 4)
            args["no_qq"] = True
            args["retries"] = 2
            i += 1; continue
        if a == "--ids":
            args["ids"] = [x.strip() for x in argv[i + 1].split(",") if x.strip()]; i += 2; continue
        if a == "--ids-file":
            args["ids_file"] = argv[i + 1]; i += 2; continue
        if a == "--limit":
            args["limit"] = int(argv[i + 1]); i += 2; continue
        if a == "--out-dir":
            args["out_dir"] = argv[i + 1]; i += 2; continue
        if a == "--cache":
            args["cache"] = argv[i + 1]; i += 2; continue
        if a == "--prompt-version":
            args["prompt_version"] = argv[i + 1]; i += 2; continue
        if a == "--retry-errors":
            args["retry_errors"] = True; i += 1; continue
        if a == "--self-test":
            args["self_test"] = True; i += 1; continue
        if a == "--dry-run":
            args["dry_run"] = True; i += 1; continue
        if a == "--correct-quotes":
            args["correct_quotes"] = True; i += 1; continue
        if a == "--no-qq":
            args["no_qq"] = True; i += 1; continue
        if a == "--with-qq":
            args["no_qq"] = False; i += 1; continue
        if a == "--sub-ctx":
            args["sub_ctx"] = True; i += 1; continue
        if a == "--no-sub-ctx":
            args["sub_ctx"] = False; i += 1; continue
        if a == "--retries":
            args["retries"] = int(argv[i + 1]); i += 2; continue
        i += 1
    return args


def self_test_norm():
    cases = {
        "一旦触发": "一旦触发",
        "统一结算": "统一结算",
        "一起部署": "一起部署",
        "一定范围内": "一定范围内",
        "一般情况": "一般情况",
        "一直抬手": "一直抬手",
        "一技能": "一技能",
        "酒神三技能": "酒神三技能",
        "四舍五入": "四舍五入",
        "六十一到七十帧": "六十一到七十帧",
        "六十九帧": "六十九帧",
        "九十九和二十九": "九十九和二十九",
        "三帧一索": "三帧一索",
        "两帧移动": "两帧移动",
        "零二十四十四": "零二十四十四",
        "十一比十五": "11比15",
        "八比三十": "8比30",
        "一盼": "一判",
        "一判": "一判",
        "出生针": "出生帧",
        "索敌针": "索敌帧",
        "六针": "六帧",
        "七针命中": "七帧命中",
        "下一秒": "下一秒",
        "0.05格": "0.05格",
        "2.75帧": "2.75帧",
        "桃金娘": "桃金娘",
        "第一辆车": "第一辆车",
        "二n加一": "2n加一",
        "开局五秒": "开局五秒",
    }
    failed = []
    for src, exp in cases.items():
        got = norm_cn_numbers(src)
        if got != exp:
            failed.append((src, exp, got))
    if failed:
        for src, exp, got in failed:
            print(f"FAIL {src!r} expected {exp!r} got {got!r}")
        raise SystemExit(f"self-test failed: {len(failed)}")
    print(f"self-test ok: {len(cases)} cases")


def _cluster_id_of(c):
    return (c.get("links") or {}).get("cluster_id") or c["id"].replace("vod_cluster:", "")


def _load_id_list(args):
    ids = list(args["ids"] or [])
    if args["ids_file"]:
        with open(args["ids_file"], encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                ids.append(line.split()[0])
    # 去重保序
    seen = set()
    out = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args["self_test"]:
        self_test_norm()
        return

    if not args["dry_run"] and not grok_client.LLM_KEY:
        raise SystemExit(
            "未设置 GROK_API_KEY。请仅在当前 shell 注入后重跑，不要写入仓库文件。\n"
            "  export GROK_API_KEY='…'\n"
            "  export GROK_MODEL=deepseek-v4.1-flash\n"
            "  python kb_synthesize.py --pilot --prompt-version v1 "
            "--ids-file kb_pilot_synth/ids_train.txt --workers 2"
        )

    pv = args["prompt_version"]
    if pv not in PROMPTS or not PROMPTS[pv]:
        raise SystemExit(f"unknown or unset prompt version {pv}, have {list(PROMPTS)}")
    prompt_tmpl = PROMPTS[pv]

    if args["pilot"]:
        out_dir = args["out_dir"] or "kb_pilot_synth"
        os.makedirs(out_dir, exist_ok=True)
        cache_path = args["cache"] or os.path.join(out_dir, f".synth_cache_{pv}.json")
        synth_path = os.path.join(out_dir, f"synthesized_{pv}.jsonl")
        usage_path = os.path.join(out_dir, f"usage_{pv}.json")
        workers = min(args["workers"], 4)
        max_members = args["max_members"]
        max_atom_chars = args["max_atom_chars"]
        quote_limit = args["quote_limit"]
        print(f"[pilot] out_dir={out_dir} cache={cache_path} prompt={pv} "
              f"workers={workers} no_qq={args['no_qq']} sub_ctx={args['sub_ctx']} "
              f"retries={args['retries']} model={grok_client.MODEL} base={grok_client.LLM_BASE} "
              f"(will NOT write kb/synthesized.jsonl or kb/docs.jsonl)",
              flush=True)
    else:
        out_dir = None
        cache_path = args["cache"] or CACHE
        synth_path = "kb/synthesized.jsonl"
        usage_path = None
        workers = args["workers"]
        max_members = 12 if args["max_members"] is None else args["max_members"]
        max_atom_chars = 3000 if args["max_atom_chars"] is None else args["max_atom_chars"]
        quote_limit = 100 if args["quote_limit"] == 500 and not args["pilot"] else args["quote_limit"]
        # 非 pilot 且未显式改 quote_limit 时保持历史 100; parse_args 默认 100
        quote_limit = args["quote_limit"]

    docs = [json.loads(l) for l in open("kb/docs.jsonl", encoding="utf-8")]
    atoms = load_source_atoms(correct_quotes=args["correct_quotes"])
    noise_ids = {d.get("atom_id") for d in docs
                 if d["doc_type"] == "vod_atom" and d.get("status") == "noise"}
    atoms = {k: v for k, v in atoms.items() if k not in noise_ids}
    by_id = {d["id"]: d for d in docs}
    clusters = [d for d in docs if d["doc_type"] == "vod_cluster" and d.get("status") != "noise"]

    want = _load_id_list(args)
    if want:
        by_cid = {}
        for c in clusters:
            by_cid[_cluster_id_of(c)] = c
            by_cid[c["id"]] = c
        missing = [x for x in want if x not in by_cid]
        if missing:
            print(f"missing cluster ids: {missing}", flush=True)
        clusters = [by_cid[x] for x in want if x in by_cid]
    if args["limit"] is not None:
        clusters = clusters[: args["limit"]]
    print(f"clusters to synthesize: {len(clusters)}", flush=True)

    cache = {}
    if os.path.exists(cache_path):
        cache = json.load(open(cache_path, encoding="utf-8"))

    def is_cached_ok(cid):
        rec = cache.get(cid)
        if not rec:
            return False
        if not isinstance(rec, dict):
            return False
        if rec.get("dry_run"):
            return False
        if args["retry_errors"] and rec.get("error"):
            return False
        if rec.get("error"):
            return True  # 历史错误默认跳过; --retry-errors 才会重打
        return bool(rec.get("_text") or rec.get("title"))

    todo = [c for c in clusters if not is_cached_ok(c["id"])]
    print(f"todo (uncached or error-retry): {len(todo)}", flush=True)

    lock = threading.Lock()
    done = [0]
    usage_tot = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                 "calls": 0, "errors": 0, "prompt_chars": 0}

    def add_usage(u, prompt_chars=0):
        usage_tot["calls"] += 1
        usage_tot["prompt_chars"] += prompt_chars
        if not u:
            return
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                usage_tot[k] += int(u.get(k) or 0)
            except (TypeError, ValueError):
                pass

    def work(c):
        mids = [m for m in (c["links"].get("member_atom_ids") or []) if m in atoms]
        members = [atoms[m] for m in mids]
        qq_block = ""
        if not args["no_qq"]:
            cps = [by_id[q] for q in (c["links"].get("counterpart_ids") or []) if q in by_id]
            if cps:
                qq_block = (
                    "[QQ群讨论(补充线索, 禁止用QQ给录播补主语; 与录播冲突时以录播为准)]\n"
                    + "\n".join(f"- {q['text'][:400]}" for q in cps[:3])
                )
        else:
            qq_block = ""
        title = (c.get("text") or "").split("\n")[0]
        body = (c.get("text") or "")
        question = ""
        note = ""
        for line in body.split("\n"):
            if line.startswith("问题:"):
                question = line[3:].strip()
            if line.startswith("档案备注:"):
                note = line[5:].strip()
        atom_text = fmt_atoms(members, max_members=max_members,
                              quote_limit=quote_limit, max_chars=max_atom_chars)
        sub_block = fmt_sub_ctx(members) if args["sub_ctx"] else ""
        prompt = prompt_tmpl.format(
            title=title, question=question, note=note,
            atoms=atom_text, qq_block=qq_block, sub_block=sub_block)
        if args["dry_run"]:
            pdir = os.path.join(out_dir or "kb_pilot_synth", f"prompts_{pv}")
            os.makedirs(pdir, exist_ok=True)
            fn = _cluster_id_of(c).replace(":", "_") + ".txt"
            with open(os.path.join(pdir, fn), "w", encoding="utf-8") as pf:
                pf.write(prompt)
            with lock:
                usage_tot["prompt_chars"] += len(prompt)
                usage_tot["calls"] += 1
                done[0] += 1
                print(f"  dry-run {_cluster_id_of(c)} chars={len(prompt)} members={len(members)}",
                      flush=True)
            return
        try:
            raw, usage = grok_client.call_llm(prompt, retries=args["retries"])
            r = _normalize_llm_result(raw)
            r["_text"] = render(r, c, members)
            r["_prompt_version"] = pv
            r["_usage"] = usage or {}
            r["_prompt_chars"] = len(prompt)
            with lock:
                add_usage(usage, len(prompt))
        except Exception as e:
            r = {"error": str(e)[:300], "_prompt_version": pv, "_prompt_chars": len(prompt)}
            with lock:
                usage_tot["errors"] += 1
                usage_tot["prompt_chars"] += len(prompt)
        with lock:
            cache[c["id"]] = r
            done[0] += 1
            _save_json(cache_path, cache)
            if usage_path:
                _save_json(usage_path, usage_tot)
            print(f"  {done[0]}/{len(todo)} {_cluster_id_of(c)} "
                  f"{'ERR' if 'error' in r else r.get('confidence','?')}",
                  flush=True)

    t0 = time.time()
    if todo:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(work, todo))
    if not args["dry_run"]:
        _save_json(cache_path, cache)
    if usage_path:
        usage_tot["elapsed_sec"] = round(time.time() - t0, 1)
        _save_json(usage_path, usage_tot)

    if args["dry_run"]:
        summary = {"dry_run": True, "clusters": len(clusters), "prompt_version": pv,
                   "usage": usage_tot, "prompts_dir": os.path.join(out_dir or "kb_pilot_synth", f"prompts_{pv}")}
        print(json.dumps(summary, ensure_ascii=False))
        return

    n_ok = n_err = 0
    existing = {}
    if args["pilot"] and os.path.exists(synth_path):
        for line in open(synth_path, encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("doc_id"):
                existing[rec["doc_id"]] = rec
    with open(synth_path, "w", encoding="utf-8") as f:
        for c in clusters:
            r = cache.get(c["id"]) or {}
            if "error" in r or not r.get("_text"):
                n_err += 1
                continue
            rec = {
                "cluster_id": _cluster_id_of(c),
                "doc_id": c["id"],
                "title": r["title"],
                "applies_to": r.get("applies_to"),
                "confidence": r.get("confidence"),
                "scope": r.get("scope"),
                "issue_status": c.get("issue_status"),
                "audit_kind": c.get("audit_kind"),
                "text": r["_text"],
                "rules": r.get("rules") or [],
                "conditions": r.get("conditions") or [],
                "exceptions": r.get("exceptions") or [],
                "open_questions": r.get("open_questions") or [],
                "member_count": len(c["links"].get("member_atom_ids") or []),
                "counterpart_ids": c["links"].get("counterpart_ids") or [],
                "prompt_version": r.get("_prompt_version") or pv,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_ok += 1
            existing.pop(c["id"], None)
        for rec in existing.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    summary = {"synthesized": n_ok, "errors": n_err, "cache": cache_path,
               "out": synth_path, "prompt_version": pv, "pilot": bool(args["pilot"]),
               "usage": usage_tot}
    print(json.dumps(summary, ensure_ascii=False))
    if args["pilot"] and out_dir:
        with open(os.path.join(out_dir, f"run_summary_{pv}.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
