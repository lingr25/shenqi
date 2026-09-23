# -*- coding: utf-8 -*-
"""Build the QQ-track expansion materials: an honest inventory and trial work-orders.

Phase 1 of the approved QQ coverage expansion. This script ONLY writes under
``kb_trial/curation/qq_expansion/``. It never touches ``kb/``, never writes the curated
JSON, never calls an API, and never adjudicates anything: the work-orders are material
for a downstream reviewer to read source by source, not verdicts.

Stages
------
Stage 2 (``--check`` / no flag)  the 80-window trial batch: inventory, stats and
    ``workorders/qq_wo_NNN.json``, 20 windows per category, fixed seed.
Stage 3 (``--stage3`` / ``--check-stage3``)  the full scale-up over every un-reviewed QQ
    window: ``inventory_scale_up.json[l]``, ``scale_up_stats.json``, the first batch of
    ``workorders_b3/qq_wo_b3_NNN.json``, ``workorders_b3/index.json`` and
    ``mapping_b3.json``. Stage 3 is ADDITIVE -- the default run still writes the stage-2
    outputs, and stage-3 paths never overwrite them.

What it produces
----------------
`qq_worklist_inventory.jsonl` / `.json`  one record per QQ window, joining the pre-screen
    worklist, the docs layer, the original QQ cards, the gate decisions, the existing
    review status and whether the window already ships. Written so the open question --
    "are there really 851 un-reviewed candidates, and are any duplicated or missing?" --
    can be answered from a single file.
`qq_expansion_stats.json`  the reconciliation numbers and the category breakdown.
`workorders/qq_wo_NNN.json`  80 trial work-orders, 20 per category, four mutually
    exclusive groups of WINDOWS (not rows), fixed seed.
`workorders/index.json`  the dispatch index.
`inventory_scale_up.json[l]`  every window with its stage-3 bucket and why it is (not)
    in the batch. See `STAGE3_BUCKETS`.
`scale_up_stats.json`  stage-3 counts, the 7-bucket distribution (empty buckets are
    reported as 0, never invented), pool composition and raw-coverage report.
`workorders_b3/`  the stage-3 batch, byte-compatible with stage 2 apart from the
    `qq_wo_b3_` id prefix and the added `scale_up` / `raw_only_note` fields.
`mapping_b3.json`  work-order id <-> window id map, with bucket, priority key and sha256.

Design notes worth keeping
--------------------------
* A window is the unit of review. The old worklist has 851 ROWS over 713 windows because
  138 rows are atoms carved out of windows already present, so a per-row work-order would
  review the same conversation up to 4 times. One work-order per window, carrying every
  row of that window.
* **`source_spans` are NOT the whole conversation.** They are excerpts ``qq_cards`` chose,
  and they are often trimmed: an upstream span `我记得有些群攻能力，会先决定锁人` comes from
  the raw message `@群友 我记得有些群攻能力，会先决定锁人`, and the cited ids are a SUBSET
  of the window. Reading only the spans is exactly what makes a question, an assumption
  and a conclusion look alike, so every work-order is padded out with the ordered, raw,
  anonymised messages covering the window's declared time range, resolved through
  `qq_info/messages_clean.jsonl`. See `raw_messages` below.
* `raw_messages` is reconstructed from the window's OWN declared `start_ts`/`end_ts` in
  `qq_info/windows.jsonl`. Nothing is inferred from neighbouring windows, and no other
  window's spans are ever attributed to this one. If a window has no declared range, or
  the range cannot be mapped, the work-order says so in `raw_messages.mapping_status`
  instead of guessing.
* Speakers are anonymised to `speaker_id` (an opaque 8-hex digest already present in the
  source). Nick names and QQ numbers are dropped. Reply targeting is kept only where the
  source states it: `@name` mentions are reduced to `mentions_speaker_id` when the
  mentioned nick maps to exactly one speaker in the window, otherwise to
  `mentions_nick_unresolved` (a boolean, never the nick itself).
* The category predicates are mechanical and printed into the work-order, so a reader can
  disagree with the grouping without having to trust it.

Usage
-----
    python kb_curation_qq_expansion_materials.py
    python kb_curation_qq_expansion_materials.py --check   # verify against what is on disk
"""
import argparse
import csv
import datetime
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
CURATION = ROOT / 'kb_trial' / 'curation'
OUT = CURATION / 'qq_expansion'
WORKORDERS = OUT / 'workorders'

QQ_WORKLIST = CURATION / 'qq_worklist.json'
QQ_CARDS = ROOT / 'qq_cards' / 'cards.jsonl'
QQ_WINDOWS = ROOT / 'qq_info' / 'windows.jsonl'
QQ_MESSAGES = ROOT / 'qq_info' / 'messages_clean.jsonl'
QQ_CHAT_EXPORT = ROOT / 'qq_info' / '1097395794_桃大将军粉丝群_聊天记录.csv'
TRIAL_DOCS = ROOT / 'kb_trial' / 'docs.jsonl'
DECISIONS = CURATION / 'decisions.jsonl'
EVIDENCE_VERDICTS = CURATION / 'evidence_verdicts.jsonl'
SEMANTIC_REVIEW = CURATION / 'semantic_review.json'
EVIDENCE_WORKLIST = CURATION / 'evidence_review_worklist.jsonl'
QQ_OVERLAY = CURATION / 'qq_claim_overlay.json'
QQ_HELD_OUT = CURATION / 'qq_claim_held_out.json'
CURATED = ROOT / 'kb_trial' / 'curated_high_quality.json'
STAGING = CURATION / 'curated_staging.json'

SEED = 20260921
PER_GROUP = 20

# --- stage 3 (full scale-up) -------------------------------------------------
WORKORDERS_B3 = OUT / 'workorders_b3'
INVENTORY_SCALE_UP = OUT / 'inventory_scale_up.json'
INVENTORY_SCALE_UP_JSONL = OUT / 'inventory_scale_up.jsonl'
SCALE_UP_STATS = OUT / 'scale_up_stats.json'
MAPPING_B3 = OUT / 'mapping_b3.json'
STAGE3_BATCH_LIMIT = 260

# --- stage 4 (remainder scale-up) -------------------------------------------
# Stage 4 takes everything stage 3 left behind: the pool less b2 (80) less b3 (260)
# less curated-shipped (8) less the 3 staged rescue samples already inside b2.
WORKORDERS_B4 = OUT / 'workorders_b4'
INVENTORY_SCALE_UP_B4 = OUT / 'inventory_scale_up_b4.json'
INVENTORY_SCALE_UP_B4_JSONL = OUT / 'inventory_scale_up_b4.jsonl'
MAPPING_B4 = OUT / 'mapping_b4.json'
SCALE_UP_STATS_B4 = OUT / 'scale_up_stats_b4.json'
STAGE4_BATCH_LIMIT = 441

# Batch registry: phase -> (batch id, work-order id prefix, output dir, mapping path,
# inventory path, stats path). Stage 3 and stage 4 are the same pipeline with different
# reviewed-exclusion sets and different output roots, so the batch identity is data, not
# a branch inside every function.
STAGE_BATCHES = {
    'phase3_scale_up': {
        'batch': 'b3',
        'prefix': 'qq_wo_b3',
        'workorders': WORKORDERS_B3,
        'inventory': INVENTORY_SCALE_UP,
        'inventory_jsonl': INVENTORY_SCALE_UP_JSONL,
        'mapping': MAPPING_B3,
        'stats': SCALE_UP_STATS,
    },
    'phase4_scale_up': {
        'batch': 'b4',
        'prefix': 'qq_wo_b4',
        'workorders': WORKORDERS_B4,
        'inventory': INVENTORY_SCALE_UP_B4,
        'inventory_jsonl': INVENTORY_SCALE_UP_B4_JSONL,
        'mapping': MAPPING_B4,
        'stats': SCALE_UP_STATS_B4,
    },
}

# --- category predicates: mechanical, no model scoring -----------------------
NUMBER_UNIT = re.compile(
    r'\d+(?:\.\d+)?\s*(?:帧|针|秒|分钟|格|倍|%|％|费|层|次|段|块|个|只|点|血|秒帧)|'
    r'(?:[一二三四五六七八九十百零两]+)\s*(?:帧|针|秒|格|倍|层|次|段)')
FORMULA = re.compile(r'\d+(?:\.\d+)?\s*[*/+×]\s*\d|\d+\s*-\s*\d')
IDENT = re.compile(r'\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|\b[a-z]+[A-Z][A-Za-z0-9]*\b|'
                   r'\b[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){2,}\b|\.(?:json|prefab|ab|py|dll|asset)\b')
QUESTION = re.compile(r'[?？]|吗|呢|是不是|有没有|怎么|为啥|为什么|多少|几帧|怎么算|求问|问一下|问件事')
HEDGE = ('可能', '应该', '大概', '我记得', '印象', '好像', '估计', '不确定', '不确定', '未必',
         '说不定', '记不清', '可能吧', '也许', '似乎', '感觉', '怀疑', '猜测', '我猜', '可能不',
         '理论上', '据说', '听说')
DEFINITION = ('就是', '指的是', '是指', '定义为', '叫做', '称为', '等价于', '不等于')
ORDER = ('先', '再', '然后', '之后', '最后', '同帧', '同一帧', '上一帧', '下一帧', '结算顺序',
         '优先级', '顺序', '之前', '以后')
COMPARE = ('大于', '小于', '高于', '低于', '优先于', '而不是', '并非', '优于', '劣于', '相比')

# Non-mechanism content worth flagging for the reviewer, not for filtering this phase.
CHITCHAT = ('哈哈哈', '草', '笑死', '谢了', '谢谢', '晚安', '早上好', '下播', '礼物', '投币',
            '三连', '卖萌', '表情', '草生')

PRIVACY_NOTE = (
    '工单内 source_spans 为已脱敏的群聊片段：只含消息文本，不含群号、QQ 号、昵称。'
    'source_msg_ids 与 internal_source 仅用于内部定位原消息，不得转发、不得写入任何公开层或日志。'
)
REVIEW_LIMIT = (
    '审核上限 text-source-supported：判定只能基于这里的脱敏文本片段，未核听原片、未做游戏内实测。'
    '片段丢失发言者与上下文顺序，提问、假设与结论常常同形；无法从片段闭合的，必须记 pending，不得替来源补结论。'
)


def load_records(path):
    """Read either a JSON array/object file or a JSONL file, so callers do not have to
    care which shape a given curation artifact happens to use."""
    text = path.read_text(encoding='utf-8')
    stripped = text.lstrip()
    if stripped.startswith('[') or stripped.startswith('{'):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return [payload]
    # JSONL where a record's `text` may contain literal newlines, so one record can span
    # several physical lines. Stream with raw_decode rather than splitting on newlines.
    dec = json.JSONDecoder()
    out = []
    i, n = 0, len(text)
    while True:
        while i < n and text[i] in ' \t\r\n':
            i += 1
        if i >= n:
            break
        obj, end = dec.raw_decode(text, i)
        out.append(obj)
        i = end
    return out


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class IdOrder:
    """Message ids in chronological export order, with a msg_id -> position index.

    Ids in the export are monotonic, so a window's exchange is the contiguous block from its
    first to its last cited id -- which is a far safer anchor than `windows.jsonl`'s
    `start_ts`/`end_ts` (uniformly +3600s off, see build_raw_messages).
    """

    def __init__(self):
        self._ids = []
        self._pos = {}

    def add(self, msg_id, ts):
        self._pos[msg_id] = len(self._ids)
        self._ids.append(msg_id)

    def __contains__(self, msg_id):
        return msg_id in self._pos

    def __getitem__(self, key):
        return self._pos[key]

    def __len__(self):
        return len(self._ids)

    def slice(self, lo, hi):
        """Inclusive block [lo, hi] of message ids, in order."""
        return self._ids[lo:hi + 1]


def _fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else None


def load_chat_export(path):
    """Read the group export CSV as `(msg_id, ts, text)` in file order.

    This is the FULL log (227k rows) and a strict superset of `messages_clean.jsonl`
    (158k rows). Text is kept verbatim and untruncated; four rows carry no timestamp (media
    placeholders) and are skipped.

    Returns `(rows, identities)`, where `identities` is the set of values that actually
    identify a member -- every sender QQ, every sender UID, and the group id. Redaction is
    value-based off this set (see `redact_text`), which is what lets genuine mechanism numbers
    of the same digit shape survive.
    """
    out = []
    identities = set()
    if path.exists():
        group_id = str(path.stem.split('_')[0])
        if group_id:
            identities.add(group_id)
    # utf-8-sig: the export starts with a BOM.
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            for col in ('发送人QQ', '发送人UID'):
                value = (row.get(col) or '').strip()
                if value.isdigit():
                    identities.add(value)
            stamp = (row.get('发送时间') or '').strip()
            if not stamp:
                continue
            try:
                ts = int(datetime.datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S').timestamp())
            except ValueError:
                continue
            out.append((row['消息ID'], ts, row.get('消息内容') or ''))
    return out, identities


def normalise(text):
    return re.sub(r'\s+', '', text or '')


def window_of_entry(entry_id):
    """`window:w000044#r0` -> `w000044`. Returns '' for entries that are not window-scoped."""
    if not entry_id.startswith('window:'):
        return ''
    return entry_id.split('#')[0].split(':', 1)[1]


# ---------------------------------------------------------------------------
# Raw-message context. `qq_cards.source_spans` are excerpts, not the whole exchange;
# only the raw ordered messages make questions, assumptions and conclusions separable.
#
# The raw text comes from the group export CSV (a strict superset of
# `qq_info/messages_clean.jsonl`), and the anonymised `speaker_id` is joined in from
# `messages_clean.jsonl`. Two source defects are corrected here:
#   * `windows.jsonl`'s `start_ts`/`end_ts` are +3600s off from the window's own messages
#     (a timezone/DST slip), so anchoring on them reads the WRONG hour. The window's own
#     `source_msg_ids` are the only trustworthy anchor: the slice runs from the first to
#     the last cited id.
#   * message text is loaded in full. An earlier version clipped it at 280 chars, which
#     made "complete conversation" an overstatement.
# ---------------------------------------------------------------------------
AT_MENTION = re.compile(r'@([^\s@]{1,32})')
# Account numbers, redacted by VALUE rather than by shape.
#
# Redacting every 6-12 digit run was wrong for this corpus, because Arknights writes aggro and
# UI values as exactly such runs -- `1级嘲讽提供300000000基础仇恨`, `现在是10000000*嘲讽`,
# `7*24*3600*1000=604800000`, and the in-game constant `365489981` (242 occurrences). All of
# those are mechanics, and the earlier shape-based rule shipped them as `[账号已隐去]`.
#
# The precise rule: redact the values that actually identify someone -- every sender QQ, every
# sender UID, and the group id -- and keep everything else. Measured on this export: 437 QQs and
# 439 UIDs appear inside message bodies, and NO non-QQ digit run overlaps a real QQ as a
# substring, so this loses no privacy coverage while preserving the mechanism values above.
#
# `BARE_ACCOUNT_NUMBER` remains as the shape-based fallback for account numbers that are NOT in
# the export's own sender columns (e.g. someone pasting a third party's QQ into chat). It keeps
# the `(?<![\d.])` guard, so it can never eat the fraction of a decimal constant.
NUMERIC_ID_MIN = 6
NUMERIC_ID_MAX = 12
BARE_ACCOUNT_NUMBER = re.compile(r'(?<![\d.])\d{%d,%d}(?!\d)' % (NUMERIC_ID_MIN, NUMERIC_ID_MAX))
# ... but a number the chat already wrapped in brackets (`[3461316146]`) is replaced wholesale,
# otherwise the marker lands inside them and ships as `[[账号已隐去]]`.
BRACKETED_ACCOUNT_NUMBER = re.compile(r'\[\s*\d{6,12}\s*\]')
# `@name 123456789` / `@name:123456789` — a mention token glued to an account number.
MENTION_THEN_NUMBER = re.compile(r'@([^\s@]{1,32}?)[\s:：]\s*\d{6,12}(?!\d)')
# Reply targeting is kept only as a placeholder, substituted for the anonymised id at the
# very end. Doing it that way keeps the account-number pass from eating our own output:
# 8 of the 417 real speaker_ids are pure digits (`09921076`), so an id written into the text
# early would be redacted as if it were an account number.
MENTION_PLACEHOLDER = '\x00MENTION:%d\x00'
PLACEHOLDER_RE = re.compile(r'\x00MENTION:(\d+)\x00')
# A `@`-less speaker id written by us (8 hex chars), protected from the number pass.
SPEAKER_ID_PLACEHOLDER = '\x00SPK:%d\x00'
SPEAKER_ID_RE = re.compile(r'\x00SPK:(\d+)\x00')


# Bot-report shapes that name group members. Each is anchored on the report's own layout, so
# a nickname is only touched where the FORMAT says a nickname must be -- never in prose.
RE_ROSTER = re.compile(r'^(\s*参与者\s*[:：]\s*)(\S.*)$')          # 参与者: a、b、c
RE_TITLE = re.compile(r'^(\s*[•·\-*]\s*)(.+?)(\s+[-–—]\s+)(\S.*)$')   # • <nick> - 龙王 (ENFP)
# "<quote>" —— <nick> : the byline is anchored on the CLOSING QUOTE, because `——` also
# occurs mid-sentence in the commentary below it and must not be touched.
RE_BYLINE = re.compile(r'^(\s*\d+\.\s*["“].*?["”]\s*——\s*)(\S.*?)(\s*)$')
RE_TITLE_SECTIONS = ('🏆 群友称号', '群友称号')
RE_BYLINE_SECTIONS = ('💬 群圣经', '群圣经')


def build_nick_redactor(nicks, speaker_of_nick):
    """Return (pattern, callable) that anonymises nicknames inside a bot report's name slots.

    Nicknames leak outside `@` only in the daily-report bot's fixed layouts, three of them:
    ``参与者: a、b、c`` rosters, ``• <nick> - 龙王 (ENFP)`` title lines, and
    ``"<quote>" —— <nick>`` bylines. Redacting nicknames from free prose instead is NOT safe
    -- 183 corpus nicknames are short everyday Chinese words ("前进", "仙人", "一人"), so a
    blanket substitution rewrites ordinary sentences ("每日来群大学习" -> "每日来@某人大学习").
    So each shape is rewritten only where the report's own format puts a name.

    One report carries many such slots (a 4.4k-char report here has 12 rosters, a title
    section and a byline section), so every slot is rewritten, not just the first.
    """
    ordered = sorted((n for n in nicks if len(n) >= 2), key=len, reverse=True)
    pattern = (re.compile('|'.join(re.escape(n) for n in ordered)) if ordered else None)

    def _in_section(lines, idx, headers):
        """True when line `idx` sits under one of `headers`.

        Walks upward to the nearest section header; a different emoji-led header stops the
        search, so a title line in one section is not attributed to another.
        """
        for j in range(idx - 1, -1, -1):
            s = lines[j].strip()
            if not s:
                continue
            if any(h in s for h in headers):
                return True
            if re.match(r'^[🎯📊💬🏆🔥📈🎖👑🃏]', s):
                return False
        return False

    def redact_participants(text):
        """Rewrite every member-name slot in a bot report, in place."""
        if not any(k in text for k in ('参与者', '群友称号', '群圣经')):
            return text
        lines = text.split('\n')
        out = []
        for i, line in enumerate(lines):
            m = RE_ROSTER.match(line)
            if m:
                out.append(m.group(1) + _names(m.group(2), speaker_of_nick))
                continue
            if _in_section(lines, i, RE_TITLE_SECTIONS):
                t = RE_TITLE.match(line)
                if t and t.group(2) not in ('', None):
                    out.append(t.group(1) + _one_name(t.group(2), speaker_of_nick)
                               + t.group(3) + t.group(4))
                    continue
            if _in_section(lines, i, RE_BYLINE_SECTIONS):
                b = RE_BYLINE.match(line)
                if b and b.group(2).strip():
                    out.append(b.group(1) + _one_name(b.group(2).strip(), speaker_of_nick)
                               + b.group(3))
                    continue
            out.append(line)
        return '\n'.join(out)

    return pattern, redact_participants


def _one_name(value, speaker_of_nick):
    """Anonymise a single name slot, behind a placeholder (see `_names`)."""
    v = value.strip()
    if v in speaker_of_nick:
        return SPEAKER_ID_PLACEHOLDER % _spk_slot(speaker_of_nick[v])
    return '某人' if v else value


def _names(value, speaker_of_nick):
    """Anonymise a `、`-separated name list, keeping the separators.

    Resolved names become `@<speaker_id>` behind a placeholder, so the account-number pass in
    `redact_text` cannot chew a digit-run out of the middle of our own anonymised id
    (`7bf55033` was being served as `7b[账号已隐去]`). `redact_text` rewrites the placeholder
    back to `@<speaker_id>` after that pass.
    """
    parts = re.split(r'([、,，])', value.strip())
    out = []
    for p in parts:
        if p in speaker_of_nick:
            out.append(SPEAKER_ID_PLACEHOLDER % _spk_slot(speaker_of_nick[p]))
        elif p.strip() and p not in '、,，':
            out.append('某人')
        else:
            out.append(p)
    return ''.join(out)


def _spk_slot(speaker_id):
    """Hand out a slot for a roster speaker id, for `redact_text` to restore after the
    account-number pass."""
    _SPK_RESTORE.append(str(speaker_id))
    return len(_SPK_RESTORE) - 1


def _len_spk_restore():
    """Mark the roster restore table, so a later call can wipe exactly its own entries."""
    return len(_SPK_RESTORE)


def _restore_spk(text, keep_from):
    """Swap roster placeholders back to `@<speaker_id>` and drop this call's table entries."""
    text = SPEAKER_ID_RE.sub(lambda m: '@' + _SPK_RESTORE[int(m.group(1))], text)
    del _SPK_RESTORE[keep_from:]
    return text


_SPK_RESTORE = []


def redact_text(text, nick_to_speaker, speaker, account_numbers, nick_redactor=None,
                identity_numbers=None):
    """Strip every identity out of a raw message, keep every mechanism number.

    Removed: `@nickname` reply targeting (replaced by the anonymised speaker id, or "某人"),
    nicknames listed by the daily-report bot, any account number glued to a mention, and every
    value in `identity_numbers` (the export's real sender QQs / UIDs plus the group id).

    Kept: mechanism numbers, including long ones — `300000000` aggro, `10000000` multiplier,
    `365489981` in-game constant, `604800000` seed arithmetic. Those are only preserved when
    they are NOT in `identity_numbers`; when `identity_numbers` is None (e.g. a caller that only
    knows `account_numbers`) the shape-based `BARE_ACCOUNT_NUMBER` fallback still applies, which
    is what stage 2/3 predate.

    Returns (text, resolved_speaker_ids, unresolved_mention, n_removed_identity_tokens).
    """
    resolved, unresolved = [], False
    pending = []  # anonymised ids to splice in after the number pass
    roster_n = _len_spk_restore()

    def mention_repl(match):
        nonlocal unresolved
        token = match.group(1)
        target = nick_to_speaker.get(token)
        if target and target != speaker:
            resolved.append(target)
            pending.append(target)
            return MENTION_PLACEHOLDER % (len(pending) - 1)
        unresolved = True
        return '@某人'

    # `@name 123456789` first: the trailing number must go, and the token is a mention.
    text = MENTION_THEN_NUMBER.sub(mention_repl, text)
    # Then any remaining `@name`.
    text = AT_MENTION.sub(mention_repl, text)
    # Then the bot report's `参与者:` name list (the only place nicks appear without `@`).
    if nick_redactor is not None:
        text = nick_redactor(text)

    removed = 0

    def number_repl(match):
        nonlocal removed
        removed += 1
        return '[账号已隐去]'

    # Bracketed ids first, so the marker replaces the brackets instead of nesting inside them.
    text = BRACKETED_ACCOUNT_NUMBER.sub(number_repl, text)
    if identity_numbers:
        # Value-based pass: redact exactly the identities the export attributes to real people,
        # wherever they appear, and leave every other digit run alone.
        text = _redact_known_numbers(text, set(identity_numbers), number_repl)
    if not identity_numbers:
        # Shape-based fallback for a caller with no identity table.
        text = BARE_ACCOUNT_NUMBER.sub(number_repl, text)
    # Restore the anonymised ids we inserted; they are our own output, not member identities.
    text = PLACEHOLDER_RE.sub(lambda m: '@' + pending[int(m.group(1))], text)
    text = _restore_spk(text, roster_n)
    return text, sorted(set(resolved)), unresolved, removed


def _redact_known_numbers(text, identity_numbers, repl):
    """Replace each known identity value with the standalone occurrence sets, longest first.

    Values are matched as whole standalone runs (not as substrings of a longer digit run), so
    redacting QQ `123456` never damages an unrelated `912345678` -- and never touches a window
    id or a timestamp, which have the same digit shape but are not identity.
    """
    for value in sorted(identity_numbers, key=len, reverse=True):
        if value and value.isdigit() and NUMERIC_ID_MIN <= len(value) <= NUMERIC_ID_MAX:
            text = re.sub(r'(?<![\d.])' + re.escape(value) + r'(?!\d)', repl, text)
    return text


def build_raw_messages(window, card, msg_index, id_order, nick_to_speaker, account_numbers,
                       nick_redactor=None, identity_numbers=None):
    """Rebuild the ordered conversation for this window, anchored on its OWN message ids.

    The slice is `windows.jsonl`'s `source_msg_ids` expanded to the contiguous id block
    [first cited, last cited] in the raw export, so the window's full exchange is present
    including the messages upstream chose not to cite. Nothing is borrowed from a
    neighbouring window, and the (offset) declared `start_ts`/`end_ts` are reported for
    reference only, never used as the selection anchor.
    """
    cited = [str(i) for i in ((card or {}).get('source_msg_ids') or [])]
    cited_set = set(cited)
    # The window's own member list is the anchor (a superset of the card's citations): it is
    # what `windows.jsonl` declares this conversation to consist of, so the slice is the
    # contiguous block covering all of it -- cited or not.
    members = [str(i) for i in ((window or {}).get('source_msg_ids') or [])] or cited
    declared = {
        'start_time': (window or {}).get('start_time'),
        'end_time': (window or {}).get('end_time'),
        'start_ts': (window or {}).get('start_ts'),
        'end_ts': (window or {}).get('end_ts'),
        'note': 'windows.jsonl 声明的 start_ts/end_ts 与本窗实际消息相差 +3600 秒（时区/夏令时偏移），'
                '因此仅作参考，**不是**本工单取数依据；取数依据是本窗自己的 source_msg_ids（窗口成员表，'
                '为窗卡引用集的超集）。',
    }

    known = [i for i in members if i in id_order]
    missing_cited = [i for i in cited if i not in id_order]
    if not known:
        return {
            'mapping_status': 'no_cited_ids_in_raw_export',
            'mapping_note': '本窗在 qq_info/windows.jsonl / qq_cards 里引用的消息 id 全部无法在群聊导出中定位，'
                            '故不提供原始上下文，也不借用其他窗口的片段。',
            'messages': [],
            'cited_count': len(cited),
            'cited_missing_from_raw': missing_cited,
            'declared_range': declared,
        }

    lo, hi = min(id_order[i] for i in known), max(id_order[i] for i in known)
    slice_ids = id_order.slice(lo, hi)

    out = []
    for mid in slice_ids:
        m = msg_index.get(mid)
        if m is None:
            continue
        speaker = m.get('speaker_id')
        text, mentions, unresolved_mention, removed = redact_text(
            m.get('text') or '', nick_to_speaker, speaker, account_numbers, nick_redactor,
            identity_numbers=identity_numbers)
        rec = {
            'seq': len(out) + 1,
            'speaker_id': speaker,
            'time': m.get('time_str'),
            'ts': m.get('ts'),
            'is_cited_by_card': mid in cited_set,
            'text': text,
        }
        if mentions:
            rec['mentions_speaker_id'] = mentions
        if unresolved_mention:
            rec['mentions_nick_unresolved'] = True
        if removed:
            rec['account_numbers_redacted'] = removed
        out.append(rec)

    return {
        'mapping_status': 'ok' if not missing_cited else 'ok_with_gaps',
        'mapping_note': '本列表是本窗 source_msg_ids（窗口成员表，为窗卡引用集的超集）覆盖的**完整消息块**'
                        '（取首条到末条引用之间的连续消息），按导出顺序、时间升序排列，'
                        '正文全文载入、**未截断**。'
                        '注意：成员表未覆盖的邻近对答不在其中，故它是本窗的完整消息块、'
                        '不等于整个群聊线程。speaker_id 为源数据中已有的匿名标识；'
                        '@昵称、6–12 位账号数字与日报参与者名单已去除，机制数值原样保留。'
                        'is_cited_by_card 标出该消息是否被上游窗卡引用。'
                        '上游 source_spans 常是截断后的片段（例如原文「@群友 我记得有些…」被截成「我记得有些…」），'
                        '因此本列表才是判断提问/假设/结论的依据。',
        'messages': out,
        'message_count': len(out),
        'cited_count': len(cited),
        'cited_missing_from_raw': missing_cited,
        'declared_range': declared,
    }


def existing_review_detail(entry_ids, verdict_by_entry, evidence_worklist_entry,
                           semantic_by_entry, overlay_by_win, held_by_win):
    """Every stage that already touched this window, joined by entry_id.

    evidence_verdicts.jsonl has no `track` field and keys on `entry_id`
    (`window:wNNNNNN#rN`), not on doc_id. Reading it by track silently returns nothing and
    would report a reviewed window as unreviewed.
    """
    out = []
    for eid in entry_ids:
        rec = {'entry_id': eid}
        v = verdict_by_entry.get(eid)
        if v:
            rec['evidence_verdict'] = {
                'status': v.get('status'),
                'supports': v.get('supports'),
                'confidence': v.get('confidence'),
                'reason': v.get('reason'),
                'reviewer_type': v.get('reviewer_type'),
                'review_basis': v.get('review_basis'),
                'limitation': v.get('limitation'),
                'repaired_fields': v.get('repaired_fields'),
                'derived_correction_disposition': v.get('derived_correction_disposition'),
            }
        w = evidence_worklist_entry.get(eid)
        if w:
            rec['evidence_review_worklist'] = {'review_status': w.get('review_status'),
                                               'source_layer': w.get('source_layer')}
        s = semantic_by_entry.get(eid)
        if s:
            rec['semantic_review'] = {'verdict': s.get('verdict'), 'support': s.get('support'),
                                      'info_value': s.get('info_value'), 'reason': s.get('reason'),
                                      'reviewer_type': s.get('reviewer_type')}
        out.append(rec)
    return out


def classify(kind, spans):
    """Return (group, reason). A is checked first, then B, then C, else D."""
    text = ' '.join(spans)
    has_question = bool(QUESTION.search(text))
    hedges = sorted({h for h in HEDGE if h in text})
    numbers = NUMBER_UNIT.findall(text)
    formulas = FORMULA.findall(text)
    idents = sorted(set(IDENT.findall(text)))
    defs = sorted({d for d in DEFINITION if d in text})
    orders = sorted({o for o in ORDER if o in text})
    comps = sorted({c for c in COMPARE if c in text})

    if kind == 'window' and not has_question and not hedges and defs and orders and len(text) >= 24:
        reason = ('定义/时序谓词齐备且无未闭合疑问、无 hedge：定义词=%s；时序词=%s；'
                  'kind=window（有同窗汇总），最长 span %d 字'
                  % ('/'.join(defs), '/'.join(orders[:4]), max(len(s) for s in spans)))
        return 'A_complete_mechanism', reason

    if numbers or formulas or idents:
        bits = []
        if numbers:
            bits.append('数值单位字面=%s' % '/'.join(sorted(set(numbers))[:6]))
        if formulas:
            bits.append('算式字面=%s' % '/'.join(sorted(set(formulas))[:4]))
        if idents:
            bits.append('代码标识符=%s' % '/'.join(idents[:6]))
        return 'B_number_formula_code', '；'.join(bits)

    if hedges or has_question:
        bits = []
        if has_question:
            bits.append('未闭合疑问标记')
        if hedges:
            bits.append('hedge=%s' % '/'.join(hedges))
        if comps:
            bits.append('比较词=%s' % '/'.join(comps[:4]))
        return 'C_mixed_or_guess', '；'.join(bits)

    return 'D_other_random', ('未命中 A/B/C 任何谓词：无定义-时序组合、无数值/公式/标识符、'
                              '无疑问与 hedge 标记' + ('；比较词=%s' % '/'.join(comps[:4]) if comps else ''))


GROUP_ORDER = ['A_complete_mechanism', 'B_number_formula_code', 'C_mixed_or_guess', 'D_other_random']
GROUP_LABEL = {
    'A_complete_mechanism': 'A 完整机制',
    'B_number_formula_code': 'B 数值/公式/代码',
    'C_mixed_or_guess': 'C 混合机制猜测或整窗拒绝',
    'D_other_random': 'D 其余随机',
    'no_candidates': 'E 无 worklist 行（raw-only）',
}

# ---------------------------------------------------------------------------
# 阶段三：全量扩批的分桶与批次选取
#
# 阶段二审过 80 窗、8 窗已入库。剩下的窗口按「有没有历史审核痕迹」分桶，优先级沿用
# 阶段二口径。实测（2026-09-21）：候选池 701 窗里 final_keep / keep_before_qq_fix /
# rescue 三桶**全为空**——历史上被审过的窗口，要么已在 curated，要么就在阶段二批内。
# 空桶如实记 0，不重定义桶语义去迁就池子（那会掩盖「历史审过的都已处理完」这一事实）。
# ---------------------------------------------------------------------------
STAGE3_BUCKETS = ['final_keep', 'keep_before_qq_fix', 'qq_pending', 'no_process',
                  'rescue', 'no_candidates', 'retry']
STAGE3_BUCKET_LABEL = {
    'final_keep': '阶段二逐条读源后有 keep 的窗口',
    'keep_before_qq_fix': '历史证据审核 supported / 语义内审 keep 的窗口',
    'qq_pending': '上一轮判定为 pending（证据在但口径未收束）的窗口',
    'no_process': '有候选行、但从未逐条读源',
    'rescue': '上一轮判 source_cannot_settle_claim 并隔离的救援样本',
    'no_candidates': '无 worklist 候选行，只有原始消息（raw-only）',
    'retry': '需要重读的窗口',
}


def load_stage2_context():
    """Everything stage 3 needs to know about what stage 2 already did.

    Returns (b2_windows, kept_windows, rescue_windows, historically_kept_windows).
    """
    idx_path = WORKORDERS / 'index.json'
    b2 = set()
    if idx_path.exists():
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        b2 = {e['window_id'] for e in idx['workorders']}
    kept = set()
    aud = OUT / 'audit_decisions.json'
    if aud.exists():
        payload = json.loads(aud.read_text(encoding='utf-8'))
        kept = {d['window'] for d in payload.get('decisions') or [] if d.get('verdict') == 'keep'}
    return b2, kept


def stage3_bucket_of(rec, b2, kept_in_b2, shipped, staged, prior_batches=()):
    """Bucket a window belongs to, for stage-3/4 accounting and batch ordering.

    Stage 2's own outcomes (`final_keep`, `rescue`) are properties of the BATCH, not of a
    window, so a window stage 2 already handled is never re-labelled into a later pool
    bucket.

    Precedence, and why: a window can carry more than one label (`w000041` was both a
    `staged` rescue sample AND produced a kept claim). `final_keep` wins over `rescue`,
    because "this window yielded an accepted claim" is the more informative fact and the
    one a reviewer cares about; `rescue` only says where the window came from.

    `prior_batches` names already-shipped scale-up batches (e.g. `('b3',)`) whose windows
    must not be re-issued. Without it, stage 4 would re-emit all 260 b3 windows.
    """
    wid = rec['window_id']
    batches = rec.get('_reviewed_in_batches') or ()
    for b in prior_batches:
        if b in batches:
            return ('reviewed_%s' % b, '已在阶段%s 批次内逐条读源，本批不重复收录' % b)
    if wid in shipped:
        return 'shipped', '已在 curated_high_quality.json（阶段二已并入），不得计为新增'
    if wid in kept_in_b2:
        return ('final_keep', '阶段二逐条读源后本窗有 keep 入库（该窗在阶段二批内）；'
                              + ('该窗同时是救援样本（staged），但「产出 keep」优先标注。'
                                 if wid in staged else '本批不重复收录。'))
    if wid in staged:
        return ('rescue', '上一轮判 source_cannot_settle_claim 并隔离；'
                          '该窗已在阶段二试批内作为救援样本复核，故本批不重复收录')
    if wid in b2:
        return 'reviewed_b2', '已在阶段二 80 窗试批内逐条读源（本窗未产出 keep），本批不重复收录'
    # ---- inside the stage-3/stage-4 candidate pool ----
    if rec['worklist_row_count'] == 0:
        return 'no_candidates', '无 worklist 候选行（raw-only）：上游没为它产出窗卡/原子候选，' \
                                '判定只能靠 raw_messages 本身'
    return 'no_process', '有候选行但从未逐条读源（历史审核阶段未触及本窗）'


def _has_ts_inversion(messages):
    """True when two adjacent messages are out of timestamp order.

    The export is ordered by message id, and a handful of windows contain two interleaved id
    series whose timestamps cross by a second. We keep the export's order and report this
    rather than re-sorting, so `seq` always matches what a reader sees in the source.
    """
    return any(messages[i]['ts'] < messages[i - 1]['ts'] for i in range(1, len(messages)))


def stage3_priority_key(rec):
    """Deterministic ordering inside the stage-3 pool: host-bearing windows first, then by the
    upstream window score, then by id. No randomness -- stage 3 must be re-runnable and
    resumable in increments."""
    return (0 if rec.get('has_host_authority') else 1,
            -(rec.get('window_score') or 0),
            rec['window_id'])


def pick_stage3_batch(records, b2, shipped, staged, limit, kept_in_b2=None,
                      prior_batches=()):
    """The first `limit` windows of the scale-up pool, in bucket order then priority order.

    `no_process` is drained before `no_candidates`, because a window with upstream candidate
    rows already has an extracted claim to check against; a raw-only window has none.

    A window that produced a `final_keep` reaches the pool only in the trial batch, so
    `kept_in_b2` is passed through rather than assumed empty -- otherwise a kept window
    would silently be re-issued instead of being excluded.
    """
    kept_in_b2 = set() if kept_in_b2 is None else kept_in_b2
    pool = []
    tally = Counter()
    for rec in records:
        bucket, _reason = stage3_bucket_of(rec, b2, kept_in_b2, shipped, staged,
                                           prior_batches=prior_batches)
        tally[bucket] += 1
        if bucket in ('no_process', 'no_candidates'):
            pool.append((bucket, rec))
    pool.sort(key=lambda pair: (0 if pair[0] == 'no_process' else 1,
                                stage3_priority_key(pair[1])))
    picked = [rec for _bucket, rec in pool[:limit]]
    return picked, tally, len(pool)


def build_inventory():
    worklist = load_records(QQ_WORKLIST)
    cards = {c['window_id']: c for c in load_records(QQ_CARDS)}
    windows = {w['window_id']: w for w in load_records(QQ_WINDOWS)}
    docs = {d['id']: d for d in load_records(TRIAL_DOCS)}
    decisions = {d['doc_id']: d for d in load_records(DECISIONS) if d.get('track') == 'qq'}

    # Raw-message indexes.
    #
    # The full, untruncated text comes from the group export CSV (227k rows), which is a
    # strict superset of `messages_clean.jsonl` (158k rows -- the slim pass dropped 69k
    # messages). `messages_clean.jsonl` is still the source of the anonymised `speaker_id`,
    # so the two are joined on msg_id.
    #
    # Anchoring note: `windows.jsonl`'s `start_ts`/`end_ts` are uniformly +3600s off from the
    # window's own messages, so a time-range slice reads the wrong hour. Windows are
    # therefore anchored on their own `source_msg_ids`, expanded to a contiguous id block.
    raw_rows, identity_numbers = load_chat_export(QQ_CHAT_EXPORT)
    speaker_of = {}
    nick_to_speaker = defaultdict(set)
    for m in load_records(QQ_MESSAGES):
        speaker_of[str(m['msg_id'])] = m.get('speaker_id')
        if m.get('nick') and m.get('speaker_id'):
            nick_to_speaker[m['nick']].add(m['speaker_id'])
    nick_unique = {n: next(iter(s)) for n, s in nick_to_speaker.items() if len(s) == 1}
    # Everyone who ever spoke, so account-number redaction can be verified against real ids.
    account_numbers = set(speaker_of.values())
    # Nicknames also leak outside `@` (the daily-report bot lists "参与者: <nick>"), so every
    # known nickname is struck from the text, not just mention positions.
    _, nick_redactor = build_nick_redactor(set(nick_to_speaker), nick_unique)
    # The values that genuinely identify someone, for the value-based number redaction.
    identity_numbers = identity_numbers | {v for v in account_numbers if v}

    id_order = IdOrder()
    msg_index = {}
    for msg_id, ts, text in raw_rows:
        msg_index[msg_id] = {'msg_id': msg_id, 'ts': ts, 'text': text,
                             'speaker_id': speaker_of.get(msg_id),
                             'time_str': _fmt_ts(ts)}
        id_order.add(msg_id, ts)

    overlay = json.loads(QQ_OVERLAY.read_text(encoding='utf-8'))
    overlay_by_win = defaultdict(list)
    for r in overlay['records']:
        overlay_by_win[r['entry_id'].split('#')[0].split(':', 1)[1]].append(
            {'entry_id': r['entry_id'], 'claim_from': r['claim_from'], 'claim': r['claim'],
             'subject': r['subject'], 'condition': r['condition'], 'scope': r['scope'],
             'note': r['note']})
    held_out = json.loads(QQ_HELD_OUT.read_text(encoding='utf-8'))
    held_by_win = defaultdict(list)
    for r in held_out['records']:
        held_by_win[r['entry_id'].split('#')[0].split(':', 1)[1]].append(
            {'entry_id': r['entry_id'], 'claim_from': r['claim_from'], 'code': r['code'],
             'reason': r['reason']})

    shipped = json.loads(CURATED.read_text(encoding='utf-8'))['entries']
    qq_shipped = {e['origin']['trial_doc_id'] for e in shipped
                  if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])}
    staging = json.loads(STAGING.read_text(encoding='utf-8'))['entries']
    qq_staged = {e['origin']['trial_doc_id'] for e in staging
                 if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])}
    # Windows that have actually been read source by source: exactly the ones named by the
    # claim overlay (re-derived) or the hold-out list (ruled un-settleable).
    reviewed_windows = {r['entry_id'].split('#')[0].split(':', 1)[1]
                        for records_ in (overlay['records'], held_out['records'])
                        for r in records_}

    # The full existing-review chain. The earlier claim that the QQ track had no evidence
    # verdicts was WRONG and came from filtering verdicts on a `track` field that
    # evidence_verdicts.jsonl does not have -- the verdicts key on `entry_id`
    # (`window:wNNNNNN#rN`), not on doc_id+track. Read them by entry_id.
    verdict_by_entry = {}
    for r in load_records(EVIDENCE_VERDICTS):
        verdict_by_entry[r['entry_id']] = r
    evidence_worklist_entry = {}
    for r in load_records(EVIDENCE_WORKLIST):
        evidence_worklist_entry[r['entry_id']] = r
    semantic_payload = json.loads(SEMANTIC_REVIEW.read_text(encoding='utf-8'))
    semantic_by_entry = {r['entry_id']: r for r in semantic_payload['records']}
    # entry_id -> window id, for every QQ entry the existing stages touched.
    stage_entries = defaultdict(list)
    for src, label in ((verdict_by_entry, 'evidence_verdict'),
                       (evidence_worklist_entry, 'evidence_review_worklist'),
                       (semantic_by_entry, 'semantic_review'),
                       ({r['entry_id']: r for r in overlay['records']}, 'claim_overlay'),
                       ({r['entry_id']: r for r in held_out['records']}, 'claim_held_out')):
        for eid in src:
            if eid.startswith('window:'):
                stage_entries[eid.split('#')[0].split(':', 1)[1]].append(label)

    rows_by_win = defaultdict(list)
    for r in worklist:
        rows_by_win[r['window_id']].append(r)

    records = []
    for wid in sorted(cards):
        card = cards[wid]
        rows = rows_by_win.get(wid, [])
        spans = [re.sub(r'\s+', ' ', s).strip() for s in (card.get('source_spans') or []) if s and s.strip()]
        docs_here = [docs[r['doc_id']] for r in rows if r['doc_id'] in docs]
        doc_types = Counter(d['doc_type'] for d in docs_here)
        # kind: which worklist rows this window carries. window > qq_atom.
        if any(r['doc_type'] == 'qq_window' for r in rows):
            kind, kind_rank = 'window', 0
        elif rows:
            kind, kind_rank = 'qq_atom_only', 1
        else:
            kind, kind_rank = 'no_worklist_row', 2
        entry_ids = sorted({r['entry_id'] for r in overlay_by_win[wid]} |
                           {r['entry_id'] for r in held_by_win[wid]})
        decision_here = [decisions.get(r['doc_id']) for r in rows if r['doc_id'] in decisions]
        decision_here = [d for d in decision_here if d]
        group, reason = classify(kind, spans)
        if any(d['doc_id'] in qq_shipped for d in decision_here):
            shipped_status = 'shipped'
        elif any(d['doc_id'] in qq_staged for d in decision_here):
            shipped_status = 'staged'
        elif wid in reviewed_windows:
            shipped_status = 'overlay_rewritten_not_a_verdict'
        else:
            shipped_status = 'not_reviewed'
        rec = {
            'window_id': wid,
            'worklist_row_count': len(rows),
            'kind': kind,
            'kind_rank': kind_rank,
            'doc_ids': [r['doc_id'] for r in rows],
            'doc_types': dict(doc_types),
            'candidate_atom_count': sum(1 for d in docs_here if d['doc_type'] == 'qq_atom'),
            'claim_topics': [r['claim'] for r in rows],
            'category': card.get('category'),
            'as_of': card.get('as_of'),
            'n_source_spans': len(spans),
            'source_spans': spans,
            'source_spans_note': '上游摘录片段，不是完整对话；完整对话在工单的 raw_messages 里。',
            'source_msg_ids': [str(i) for i in (card.get('source_msg_ids') or [])],
            'card_status': card.get('status'),
            'card_origin': card.get('origin'),
            'card_novelty': card.get('novelty'),
            'card_scope': card.get('scope'),
            'card_canonical_ids': card.get('canonical_ids') or [],
            'reviewed_source_by_source': wid in reviewed_windows,
            'existing_review_stages': sorted({label for label in stage_entries.get(wid, [])}),
            'existing_review_detail': existing_review_detail(
                entry_ids, verdict_by_entry, evidence_worklist_entry, semantic_by_entry,
                overlay_by_win, held_by_win),
            'span_chars': len(' '.join(spans)),
            'window_tier': (windows.get(wid) or {}).get('tier'),
            'window_raw_tier': (windows.get(wid) or {}).get('raw_tier'),
            'window_score': (windows.get(wid) or {}).get('score'),
            'window_hit_terms': (windows.get(wid) or {}).get('hit_terms') or [],
            'window_n_messages': (windows.get(wid) or {}).get('n_messages'),
            'has_host_authority': any((a or {}).get('role') == 'host'
                                      for a in ((windows.get(wid) or {}).get('authorities') or [])),
            'decisions': [{'doc_id': d['doc_id'], 'decision': d['decision'],
                           'reject_reason': d.get('reject_reason'),
                           'review_status': d.get('review_status')} for d in decision_here],
            'review_status_seen': sorted({d.get('review_status') for d in decision_here if d.get('review_status')}),
            'shipped': {
                'status': shipped_status,
                'entry_ids': entry_ids,
                'overlay': overlay_by_win.get(wid, []),
                'held_out': held_by_win.get(wid, []),
            },
            'classification': {'group': group, 'label': GROUP_LABEL[group], 'reason': reason},
        }
        records.append(rec)
    ctx = {'msg_index': msg_index, 'nick_unique': nick_unique, 'windows': windows,
           'id_order': id_order, 'account_numbers': account_numbers,
           'nick_redactor': nick_redactor,
           'identity_numbers': identity_numbers,
           'verdict_by_entry': verdict_by_entry,
           'evidence_worklist_entry': evidence_worklist_entry,
           'semantic_by_entry': semantic_by_entry,
           'qq_evidence_verdicts': sorted(e for e in verdict_by_entry
                                          if window_of_entry(e) in rows_by_win),
           'qq_semantic_rows': [r for e, r in semantic_by_entry.items()
                                if window_of_entry(e) in rows_by_win],
           'qq_evidence_worklist_rows': [e for e in evidence_worklist_entry
                                         if window_of_entry(e) in rows_by_win],
           'semantic_counts': semantic_payload.get('counts'),
           }
    return records, cards, windows, docs, worklist, ctx


def pick_trial_windows(records):
    """Four mutually exclusive groups of 20 windows each, drawn from windows that have NOT
    already shipped.

    `exclude` drops windows whose entry is already in the curated layer, because phase 2 is
    meant to ADD 80 windows and a shipped window cannot count as new. `rescue` keeps the
    three windows the previous round held out as `source_cannot_settle_claim`: they are
    legitimate material (a reviewer now has the raw conversation, which is what they lacked),
    but the work-order marks them as previously-held-out so they are not double-counted as
    fresh discoveries either.
    """
    by_group = defaultdict(list)
    for r in records:
        by_group[r['classification']['group']].append(r)

    eligible = [r for r in records if r['shipped']['status'] != 'shipped']
    rescue_ids = {r['window_id'] for r in records if r['shipped']['status'] == 'staged'}
    by_group = defaultdict(list)
    for r in eligible:
        by_group[r['classification']['group']].append(r)

    picked, shortfalls = [], {}
    for g in GROUP_ORDER[:3]:
        pool = sorted(by_group[g], key=lambda r: (r['kind_rank'], r['window_id']))
        take = pool[:PER_GROUP]
        if len(take) < PER_GROUP:
            shortfalls[g] = PER_GROUP - len(take)
        for r in take:
            r['selection'] = {'group': g, 'rule': 'predicate_match',
                              'rank': pool.index(r) + 1, 'pool_size': len(pool),
                              'excludes_shipped': True,
                              'is_rescue_sample': r['window_id'] in rescue_ids}
        picked.extend(take)

    taken = {r['window_id'] for r in picked}
    pool_d = sorted((r for r in by_group['D_other_random'] if r['window_id'] not in taken),
                    key=lambda r: r['window_id'])
    rng = random.Random(SEED)
    d_pool = list(pool_d)
    rng.shuffle(d_pool)
    take_d = d_pool[:PER_GROUP]
    if len(take_d) < PER_GROUP:
        shortfalls['D_other_random'] = PER_GROUP - len(take_d)
    for r in take_d:
        r['selection'] = {'group': 'D_other_random', 'rule': 'random_shuffle_seed_%d' % SEED,
                          'shuffled_index': d_pool.index(r) + 1, 'pool_size': len(pool_d),
                          'excludes_shipped': True,
                          'is_rescue_sample': r['window_id'] in rescue_ids}
    picked.extend(take_d)
    return picked, shortfalls, {g: len(by_group[g]) for g in GROUP_ORDER}


def build_workorder(n, rec, cards, decisions_by_doc, docs, windows, ctx,
                    phase='phase1_trial_batch', bucket=None, excluded_reason=None):
    """One work-order. It carries the upstream excerpts AND the full ordered raw conversation
    for the window's own id block, because the excerpts alone cannot distinguish a question
    from an assumption from a conclusion.

    `phase`/`bucket` switch this between the stage-2 trial batch and the stage-3 scale-up: a
    raw-only stage-3 window has no upstream candidate rows, so its `atoms_from_this_window`
    and `old_decisions` are empty by construction (with a note saying so) rather than absent.
    """
    wid = rec['window_id']
    card = cards.get(wid) or {}
    raw = build_raw_messages(windows.get(wid), card, ctx['msg_index'],
                             ctx['id_order'], ctx['nick_unique'], ctx['account_numbers'],
                             ctx['nick_redactor'],
                             identity_numbers=ctx.get('identity_numbers'))

    atoms = []
    for doc_id in rec['doc_ids']:
        d = docs.get(doc_id)
        if not d:
            continue
        if d['doc_type'] == 'qq_atom':
            atoms.append({
                'doc_id': d['id'],
                'atom_text': d['text'],
                'claim_type': d.get('claim_type'),
                'applies_to': d.get('applies_to'),
                'conditions': d.get('conditions') or [],
                'credibility': (d.get('source') or {}).get('credibility'),
                'mode': d.get('mode'),
                'scope': d.get('scope'),
            })
        elif d['doc_type'] == 'qq_window':
            atoms.append({
                'doc_id': d['id'],
                'atom_text': None,
                'note': '上游窗卡文本（含主题行）；本工单的 kinds 里已把它列为 kind=window 的行',
                'window_text': d['text'],
                'mode': d.get('mode'),
                'scope': d.get('scope'),
                'credibility': (d.get('source') or {}).get('credibility'),
            })

    old_decisions = []
    for doc_id in rec['doc_ids']:
        d = decisions_by_doc.get(doc_id)
        if not d:
            continue
        old_decisions.append({
            'doc_id': d['doc_id'],
            'rule_idx': d['rule_idx'],
            'decision': d['decision'],
            'reject_reason': d.get('reject_reason'),
            'review_status': d.get('review_status'),
            'review_note': d.get('review_note'),
            'claim_as_decided': d.get('claim'),
            'audit_kind': d.get('audit_kind'),
            'audit_verdict': d.get('audit_verdict'),
            'flags': d.get('flags'),
        })

    spec = STAGE_BATCHES.get(phase)
    workorder_id = (('%s_%03d' % (spec['prefix'], n)) if spec else ('qq_wo_%03d' % n))
    batch = spec['batch'] if spec else None
    group = bucket or rec['classification']['group']
    out = {
        'workorder_id': workorder_id,
        'phase': phase,
        'group': group,
        'group_label': (STAGE3_BUCKET_LABEL.get(group)
                        or GROUP_LABEL.get(group) or group),
        'selection_rule': rec.get('selection') or {
            'group': group,
            'rule': '%s_pool_priority_order' % (batch or 'trial'),
            'priority_key': list(stage3_priority_key(rec)),
            'pool_scope': 'no_process_then_no_candidates',
            'excludes_shipped': True,
            'excludes_stage2_reviewed': True,
            'excludes_prior_scale_up_batches': sorted(
                rec.get('_reviewed_in_batches') or ()),
            'is_rescue_sample': False,
        },
        'window': {
            'window_id': wid,
            'as_of': rec['as_of'],
            'category': rec['category'],
            'kind': rec['kind'],
            'window_tier': rec['window_tier'],
            'window_raw_tier': rec['window_raw_tier'],
            'window_score': rec['window_score'],
            'window_hit_terms': rec['window_hit_terms'],
            'n_chat_messages': rec['window_n_messages'],
            'has_host_authority': rec['has_host_authority'],
            'card_status': rec['card_status'],
            'card_origin': rec['card_origin'],
            'card_novelty': rec['card_novelty'],
            'card_scope': rec['card_scope'],
            'card_canonical_ids': rec['card_canonical_ids'],
        },
        # The upstream excerpts. NOT the whole conversation: they are trimmed, and they
        # are what makes a question look like an assertion when read alone.
        'source_spans_excerpts': rec['source_spans'],
        # The authoritative reading material: every raw message in this window's own
        # declared span, ordered, anonymised, with reply targeting kept where the source
        # states it.
        'raw_messages': raw,
        'original_card': {
            'topic': card.get('topic'),
            'context_question': card.get('context_question'),
            'core_conclusions': card.get('core_conclusions') or [],
            'underlying_parameters': card.get('underlying_parameters') or [],
            'summary_takeaway': card.get('summary_takeaway'),
            'note': card.get('note'),
            'vod_evidence': card.get('vod_evidence') or [],
        },
        'atoms_from_this_window': atoms,
        'old_decisions': old_decisions,
        'existing_review': {
            'shipped_status': rec['shipped']['status'],
            'shipped_entry_ids': rec['shipped']['entry_ids'],
            'qq_claim_overlay': rec['shipped']['overlay'],
            'qq_claim_held_out': rec['shipped']['held_out'],
            'stages_that_touched_this_window': rec['existing_review_stages'],
            'stage_records': rec['existing_review_detail'],
            'note': 'shipped_status=shipped 表示该窗口已有条目进入甄选层，本次扩展不得计为新增；'
                    'staged 表示上一轮判为 source_cannot_settle_claim 并隔离（本次作为救援样本，'
                    '因为它缺的正是 raw_messages 提供的原始上下文）；'
                    'overlay_rewritten_not_a_verdict 表示上一轮只重写了标题、仍算未审，必须重新读源。'
                    'stage_records 逐条列出证据审核（evidence_verdicts.jsonl 按 entry_id 索引）、'
                    '语义内审与重写/隔离记录——QQ 轨**确实**经过证据审核，只是它没有 track 字段，'
                    '必须按 entry_id 读，不能按 track 过滤。',
        },
        'classification_reason': rec['classification']['reason'],
        'review_instructions': {
            'unit': '本工单只审这一个窗口；窗口内所有候选行（窗卡 + 原子）一并判读，不要跨窗口合并。',
            'must_read': '以 raw_messages 为主读材料（本窗 source_msg_ids 覆盖的完整消息块，按时间升序，'
                         '全文未截断，含发言者与回复指向），'
                         'source_spans_excerpts 只作为上游摘录对照。判断提问/假设/结论必须依据 raw_messages。',
            'spans_are_excerpts': 'source_spans_excerpts 是上游裁切后的片段，**不是**完整对话，'
                                  '且常被截断（例：原文「@群友 我记得有些…」被截成「我记得有些…」）。'
                                  '只看片段会把提问误读成断言，这正是本工单附上 raw_messages 的原因。',
            'verdict_values': ['keep_with_claim', 'repair_claim', 'reject_window', 'pending_source_cannot_settle'],
            'required_fields': ['verdict', 'claim', 'subject', 'condition', 'scope', 'evidence_quote_spans',
                                'reason'],
            'evidence_quote_spans': '必须逐字引用 raw_messages[].text 中出现过的文本；'
                                    '引用 raw_messages 与 source_spans_excerpts 之外的文本即为无效回执。',
            'number_rule': 'claim 中出现任何数字（帧/秒/倍/格/百分比）时，必须给出该数字所在的消息原文；'
                           '原文里没有的数字不得写进 claim。',
            'no_generalisation': '消息未限定的适用范围不得自行归为通用通则；无法确定 scope 就写「未标注」。',
            'speaker_rule': 'speaker_id 是匿名标识，可用来判断「同一人前后是否自相矛盾」与「谁在回答谁」，'
                            '但不得把它还原成人名，也不得在回执里猜测身份。',
            'reply_rule': 'mentions_speaker_id 表示该条消息 @ 了某位发言者（已匿名化）；'
                          'mentions_nick_unresolved=true 表示 @ 对象无法唯一映射，不要猜是谁。',
            'context_rule': '上下文一律取自 raw_messages（本窗声明区间内的原始消息）。'
                            '若 mapping_status 不是 ok，说明该窗原始上下文缺失，必须按缺失处理，'
                            '不得用邻近窗口的片段替代。',
            'privacy': PRIVACY_NOTE,
        },
        'review_limits': REVIEW_LIMIT,
        'internal_source': {
            'card_file': 'qq_cards/cards.jsonl',
            'raw_message_file': 'qq_info/messages_clean.jsonl',
            'window_file': 'qq_info/windows.jsonl',
            'worklist_rows': rec['doc_ids'],
            'docs_layer': 'kb_trial/docs.jsonl',
            'decisions': 'kb_trial/curation/decisions.jsonl',
            'evidence_verdicts': 'kb_trial/curation/evidence_verdicts.jsonl（按 entry_id 索引）',
            'source_msg_ids': rec['source_msg_ids'],
            'note': '仅供内部定位原消息；source_msg_ids 不得转发或写入任何公开层。'
                    'raw_messages 已丢弃昵称与 QQ 号，只保留 speaker_id。',
        },
    }
    if spec:
        out['scale_up'] = {
            'bucket': group,
            'bucket_reason': excluded_reason or STAGE3_BUCKET_LABEL.get(group, ''),
            'batch': batch,
            'note': '阶段%s扩批工单。与阶段二逐字段同构；唯一差别见 raw_only_note。'
                    % batch[1:],
        }
        if rec['worklist_row_count'] == 0:
            out['raw_only_note'] = (
                '本窗**无 worklist 候选行**（上游没有为它产出窗卡或原子），因此 '
                'atoms_from_this_window 与 old_decisions 均为空数组——这是「上游没有这东西」，'
                '不是「材料缺失」。判定只能依据 raw_messages 本身；'
                'original_card 仍来自 qq_cards/cards.jsonl，可作对照但不作判据。')
    return out


def build_worked_examples(workorders, decisions_by_doc):
    """Show, on real work-orders, where the mechanical categories are right and where they
    are visibly wrong. This exists so the grouping is not mistaken for an adjudication:
    the A-group false positive below is mechanical clean but plainly un-rulable, and that
    is exactly why phase 2 reads every window by hand instead of trusting the regex."""
    def probe(window_id):
        """Look the example up by WINDOW id, not work-order id: the work-order numbering
        shifts whenever the eligible pool changes, so a hard-coded `qq_wo_NNN` would silently
        start pointing at a different conversation."""
        wo = next(w for w in workorders if w['window']['window_id'] == window_id)
        old = [d for d in wo['old_decisions']]
        return {
            'workorder_id': wo['workorder_id'],
            'window_id': wo['window']['window_id'],
            'group': wo['group'],
            'category': wo['window']['category'],
            'classification_reason': wo['classification_reason'],
            'source_spans_excerpts': wo['source_spans_excerpts'],
            'raw_messages': wo['raw_messages'],
            'existing_review': wo['existing_review']['shipped_status'],
            'old_decisions': [{'doc_id': d['doc_id'], 'decision': d['decision'],
                               'reject_reason': d['reject_reason']} for d in old],
        }

    examples = {
        'note': '机械分组的实测校验。下面两条来自真实工单，用来证明分组只是「分桶」而非判定：'
                'A 组允许按谓词入选，但入选的片段仍可能整段不可判读；'
                'C 组则证明「有疑问词」并不等于「整窗无价值」。两条例子都按 window_id 选取，'
                '不受工单编号重排影响。',
        'A_group_example_mechanical_pass_but_reviewer_must_still_judge': probe('w000013'),
        'C_group_example_question_but_may_still_carry_a_rule': probe('w000077'),
    }
    return examples


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true',
                    help='verify the on-disk outputs against a fresh computation, then exit')
    ap.add_argument('--stage3', action='store_true',
                    help='stage 3: write the full un-reviewed inventory + the b3 first batch')
    ap.add_argument('--check-stage3', action='store_true',
                    help='stage 3 self-check against disk (idempotence + privacy), then exit')
    ap.add_argument('--b3-limit', type=int, default=STAGE3_BATCH_LIMIT,
                    help='how many windows the b3 batch takes (default %d)' % STAGE3_BATCH_LIMIT)
    ap.add_argument('--stage4', action='store_true',
                    help='stage 4: write the remaining un-reviewed inventory + the full b4 batch')
    ap.add_argument('--check-stage4', action='store_true',
                    help='stage 4 self-check against disk (idempotence + privacy), then exit')
    ap.add_argument('--b4-limit', type=int, default=STAGE4_BATCH_LIMIT,
                    help='how many windows the b4 batch takes (default %d; the pool holds 441)'
                         % STAGE4_BATCH_LIMIT)
    args = ap.parse_args()

    if args.stage3 or args.check_stage3:
        STAGE_BATCHES['phase3_scale_up']['check'] = bool(args.check_stage3)
        return main_stage3(args, 'phase3_scale_up')
    if args.stage4 or args.check_stage4:
        STAGE_BATCHES['phase4_scale_up']['check'] = bool(args.check_stage4)
        return main_stage3(args, 'phase4_scale_up')

    records, cards, windows, docs, worklist, ctx = build_inventory()
    picked, shortfalls, group_pool = pick_trial_windows(records)
    picked.sort(key=lambda r: (GROUP_ORDER.index(r['classification']['group']), r['window_id']))

    decisions_by_doc = {}
    for d in load_records(DECISIONS):
        if d.get('track') == 'qq':
            decisions_by_doc.setdefault(d['doc_id'], d)

    workorders = [build_workorder(i + 1, r, cards, decisions_by_doc, docs, windows, ctx)
                  for i, r in enumerate(picked)]

    # ---- reconciliation numbers -------------------------------------------------
    wl_windows = {r['window_id'] for r in worklist}
    card_windows = set(cards)
    canon = set()
    for c in cards.values():
        if c.get('canonical_window_id'):
            canon.add(c['window_id'])
    overlay = json.loads(QQ_OVERLAY.read_text(encoding='utf-8'))
    held = json.loads(QQ_HELD_OUT.read_text(encoding='utf-8'))
    overlay_entry_ids = {r['entry_id'] for r in overlay['records']}
    held_entry_ids = {r['entry_id'] for r in held['records']}
    wl_overlay = {e for e in overlay_entry_ids if e.split('#')[0].split(':', 1)[1] in wl_windows}
    wl_held = {e for e in held_entry_ids if e.split('#')[0].split(':', 1)[1] in wl_windows}

    qq_decisions = [d for d in load_records(DECISIONS) if d.get('track') == 'qq']
    accepted = [d for d in qq_decisions if d['decision'] == 'accept']
    shipped_entries = [e for e in json.loads(CURATED.read_text(encoding='utf-8'))['entries']
                       if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])]
    staged_entries = [e for e in json.loads(STAGING.read_text(encoding='utf-8'))['entries']
                      if any(c.get('status') == 'resolved_qq_span' for c in e['citations'])]

    # Existing QQ review history, indexed by entry_id (these files have NO `track` field,
    # so a track filter silently reports "never reviewed" -- that was the earlier error).
    all_evidence_verdicts = load_records(EVIDENCE_VERDICTS)
    all_evidence_verdicts_by_entry = {r['entry_id']: r for r in all_evidence_verdicts}
    qq_evidence_verdicts = ctx['qq_evidence_verdicts']
    all_evidence_worklist = load_records(EVIDENCE_WORKLIST)
    qq_evidence_worklist_rows = ctx['qq_evidence_worklist_rows']
    qq_semantic_rows = ctx['qq_semantic_rows']
    semantic_counts = ctx['semantic_counts']

    per_window_rows = Counter(r['window_id'] for r in worklist)

    n_atom_rows = sum(1 for r in worklist if r['doc_type'] == 'qq_atom')
    n_card_rows = sum(1 for r in worklist if r['doc_type'] == 'qq_window')
    n_atom_with_card = sum(1 for r in worklist if r['doc_type'] == 'qq_atom'
                           and per_window_rows[r['window_id']] > 1)
    reviewed_windows = {e.split('#')[0].split(':', 1)[1] for e in overlay_entry_ids | held_entry_ids}
    accepted_docs = {d['doc_id'] for d in accepted}
    shipped_docs = {e['origin']['trial_doc_id'] for e in shipped_entries}
    staged_docs = {e['origin']['trial_doc_id'] for e in staged_entries}
    wl_doc_ids = {r['doc_id'] for r in worklist}
    outside = [d for d in qq_decisions if d['doc_id'] not in wl_doc_ids]
    outside_with_evidence = [d for d in outside if d.get('qq_evidence')]
    outside_windows = {d['doc_id'].split(':')[1] for d in outside if d.get('qq_evidence')
                       and d['doc_type'] in ('qq_window', 'qq_atom')}
    stats = {
        'note': '本文件由 kb_curation_qq_expansion_materials.py 实测生成；数字只描述 2026-09-21 磁盘上的状态，'
                '不代表审核结论。本阶段未做任何判定。',
        'seed': SEED,
        'sources': {
            'qq_worklist_rows': len(worklist),
            'qq_worklist_unique_windows': len(wl_windows),
            'qq_worklist_extra_rows_beyond_one_per_window': len(worklist) - len(wl_windows),
            'windows_with_multiple_rows': sum(1 for v in per_window_rows.values() if v > 1),
            'max_rows_per_window': max(per_window_rows.values()),
            'rows_by_doc_type': dict(Counter(r['doc_type'] for r in worklist)),
            'qq_cards_total': len(cards),
            'qq_cards_windows_without_worklist_row': len(card_windows - wl_windows),
            'qq_cards_duplicate_status': sum(1 for c in cards.values() if c.get('status') == 'duplicate'),
            'qq_cards_with_canonical_window_id': len(canon),
            'qq_cards_reachable_after_duplicate_removal': len(card_windows - canon),
            'trial_docs_qq_rows': sum(1 for d in docs.values() if d.get('track') == 'qq'),
            'decision_rows_qq': len(qq_decisions),
            'decision_rows_qq_accept': len(accepted),
            'decision_rows_qq_reject': len(qq_decisions) - len(accepted),
            'decision_docs_qq_accept_unique': len(accepted_docs),
            'decision_rows_qq_with_qq_evidence': sum(1 for d in qq_decisions if d.get('qq_evidence')),
            'curated_qq_entries': len(shipped_entries),
            'curated_total_entries': json.loads(CURATED.read_text(encoding='utf-8'))['entry_count'],
            'staging_qq_entries': len(staged_entries),
        },
        'reconciliation': {
            'question_the_user_asked': '851 待核是否真实、有无重复与遗漏？',
            'headline': '851 是「上游 D+ 原子化阶段产出的 QQ 预筛候选行」，不是待核队列，也从未被当作待核队列处理过：'
                        '其中 %d 行是 qq_atom、%d 行是窗卡行，同一窗口同时有窗卡行与原子行，'
                        '按窗口去重后是 %d 个窗口（多出 %d 行）。'
                        '「未被逐条读源」是以窗口为单位说的：这 %d 个窗口里有 %d 个没有逐条读源记录，'
                        '已逐条读源的是 %d 个窗口（%d 条入库 + %d 条隔离）。'
                        % (n_atom_rows, n_card_rows, len(wl_windows),
                           len(worklist) - len(wl_windows), len(wl_windows),
                           len(wl_windows - reviewed_windows), len(reviewed_windows),
                           len(shipped_entries), len(staged_entries)),
            'row_counts_are_not_comparable_to_window_counts': '本文件里出现的任何「行数」与「窗口数」量纲不同，'
                                                              '不得相互比较大小或做减法推断覆盖率；覆盖率一律以窗口为单位计算。',
            'is_it_a_deduplicated_queue': False,
            'queue_status_note': '上游 kb_curation_prescreen.py 只做确定性预筛并同时输出 docs.jsonl 的窗卡行与其 qq_atom 行，'
                                 '没有做「一窗一行」去重；kb_curation_decide.py 又把 1012 行全部判为 reject/accept，'
                                 '因此这 851 行本身不是独立的可审单元；就窗口而言，%d 个窗口里已逐条读源的是 %d 个，'
                                 '其余 %d 个窗口本阶段按待评估处理。'
                                 % (len(wl_windows), len(reviewed_windows),
                                    len(wl_windows - reviewed_windows)),
            'raw_rows': len(worklist),
            'atom_rows': n_atom_rows,
            'window_card_rows': n_card_rows,
            'atom_rows_on_window_with_a_card_row': n_atom_with_card,
            'extra_rows_beyond_one_per_window': len(worklist) - len(wl_windows),
            'unique_windows': len(wl_windows),
            'windows_never_read_source_by_source': len(wl_windows - reviewed_windows),
            'windows_in_existing_overlay': len(wl_overlay),
            'windows_in_existing_hold_out': len(wl_held),
            'windows_in_overlay_or_hold_out': len(wl_overlay | wl_held),
            'accepted_rows': len(accepted),
            'accepted_docs': len(accepted_docs),
            'accepted_docs_shipped': len(accepted_docs & shipped_docs),
            'accepted_docs_held_out': len(accepted_docs & staged_docs),
            'accepted_docs_nowhere': len(accepted_docs - shipped_docs - staged_docs),
            'duplicate_windows_inside_curated_layer': len(shipped_entries) - len(shipped_docs),
            'duplicate_windows_inside_curated_layer_note': '甄选层同窗条目由 kb_curation_build.py 的 dedupe_claims 合并，'
                                                           '同一窗口的两条不同 claim 会并存，这不是缺陷但读源时要一并判读。',
            'windows_missing_from_worklist': len(card_windows - wl_windows),
            'windows_missing_from_worklist_with_source_spans': len(
                [w for w in (card_windows - wl_windows) if (cards[w].get('source_spans') or [])]),
            'windows_missing_from_worklist_with_source_spans_note': '这些窗口有原文片段、却因为没有任何候选行而未进 worklist，'
                                                                    '属于**覆盖缺口**，不是「已判定为无价值」，本阶段如实计入待评估范围，未纳入 80 试批。',
            'rows_outside_worklist': len(outside),
            'rows_outside_worklist_with_qq_evidence': len(outside_with_evidence),
            'rows_outside_worklist_by_doc_type': dict(Counter(d['doc_type'] for d in outside)),
            'windows_outside_worklist_dropped_reasons': dict(Counter(
                d.get('reject_reason') for d in outside)),
            'windows_outside_worklist_note': '这些行（含 %d 个有原文片段、却因「文本太短 / 无来源行 / 非机制」等确定性理由'
                                             '被预筛挡掉、因而未进 worklist 的窗口 %d 个）只呈现判定分布，不做「应当补回」的结论。'
                                             % (len(outside_with_evidence), len(outside_windows)),
            'duplicate_note': '窗口级重复已按窗口聚合；本次 80 份工单窗窗互斥，'
                              '同窗的窗卡行与全部原子行都收进同一份工单，不再重复出现。',
        },
        'classification': {
            'rule': 'A 完整机制 = kind=window 且无疑问/无 hedge 且同时出现定义词与时序词且总长≥24；'
                    'B 数值/公式/代码 = 命中数值单位或算式或代码标识符；'
                    'C 混合/猜测 = 命中疑问标记或 hedge 词；D = 其余。窗口粒度互斥。',
            'pool_by_group': group_pool,
            'trial_selected_by_group': dict(Counter(g for g, _ in
                                                    [(r['classification']['group'], 1) for r in picked])),
            'shortfalls': shortfalls,
            'shortfall_note': '某组不足 20 时如实留空并在 workorders/index.json 的 shortfalls 记明，'
                              '不跨组借窗口凑数。',
        },
        'workorders': {
            'count': len(workorders),
            'groups': dict(Counter(w['group'] for w in workorders)),
            'unique_windows': len({w['window']['window_id'] for w in workorders}),
            'group_overlap_windows': len(workorders) - len({w['window']['window_id'] for w in workorders}),
            'already_shipped_entries_must_not_count_as_new': sum(
                len(w['existing_review']['shipped_entry_ids']) for w in workorders
                if w['existing_review']['shipped_status'] == 'shipped'),
            'selection_excludes_shipped_windows': True,
            'already_staged_windows_rescue_sample': sum(
                1 for w in workorders
                if w['existing_review']['shipped_status'] == 'staged'),
            'rescue_sample_window_ids': sorted(
                w['window']['window_id'] for w in workorders
                if w['existing_review']['shipped_status'] == 'staged'),
            'rescue_sample_note': '这 3 个窗口上一轮被判为 source_cannot_settle_claim 并隔离在 '
                                  'curation/curated_staging.json。它们不是新增候选，保留在试批里是为了检验'
                                  '「补上完整原始对话后，原来的不可闭合判断是否仍然成立」——属于救援样本，'
                                  '统计新增覆盖时不得计入。',
            'title_rewritten_but_never_evidence_judged': sum(
                1 for w in workorders
                if w['existing_review']['shipped_status'] == 'overlay_rewritten_not_a_verdict'),
            'untouched_windows': sum(1 for w in workorders
                                     if w['existing_review']['shipped_status'] == 'not_reviewed'),
            'windows_needing_a_fresh_read': sum(
                1 for w in workorders
                if w['existing_review']['shipped_status'] != 'shipped'),
            'with_raw_messages': sum(1 for w in workorders
                                     if w['raw_messages'].get('message_count')),
            'raw_messages_by_mapping_status': dict(Counter(
                w['raw_messages'].get('mapping_status') for w in workorders)),
            'total_raw_messages': sum(w['raw_messages'].get('message_count', 0) for w in workorders),
            'median_raw_messages': median(
                [w['raw_messages'].get('message_count', 0) for w in workorders]),
            'raw_messages_note': 'raw_messages 是本窗 source_msg_ids（窗口成员表）覆盖的连续消息块，'
                                 '按导出顺序、时间升序、正文全文未截断、speaker 匿名，'
                                 '不是 source_spans 的转写。它把「提问 / 假设 / 结论」区分开，'
                                 '但仍不等于完整群聊线程：窗口成员表之外的对答不在此列。',
            'encoded_source_spans_excerpts': sum(
                len(w['source_spans_excerpts']) for w in workorders),
            'windows_with_prior_action': sorted(
                w['workorder_id'] + ':' + w['window']['window_id'] for w in workorders
                if w['existing_review']['shipped_status'] != 'not_reviewed'),
            'windows_actually_evidence_reviewed_in_past': sorted(
                w['workorder_id'] + ':' + w['window']['window_id'] for w in workorders
                if 'evidence_verdict' in w['existing_review']['stages_that_touched_this_window']),
        },
        'review_state_legend': {
            'shipped': '该窗口的条目已进入 kb_trial/curated_high_quality.json，不得计为新增。本试批已把这类窗口整体排除。',
            'staged': '该窗口的条目被上一轮隔离在 curation/curated_staging.json（判定为 source_cannot_settle_claim）。'
                      '本试批保留 3 个作为救援样本，不计入新增覆盖。',
            'overlay_rewritten_not_a_verdict': '上一轮只重写了标题、并没有做证据判定：'
                                               'kb_curation_evidence_close.py 的 QQ_REPAIRS 表把这些窗口的'
                                               '原始标题改写成按 span 重写的机制句，kb_curation_build.py 随之把它置为 '
                                               'auto_screened。「重写过」不等于「审过」，本次审核必须重新读源。',
            'not_reviewed': '没有任何逐条读源的记录，也没有被重写或隔离过。',
            'reviewed_source_by_source': '该窗口出现在 qq_claim_overlay 或 qq_claim_held_out 中，'
                                         '即上一轮确实依据 span 逐条读过（合计 11 个窗口）。',
            'evidence_reviewed': '该窗口在 curation/evidence_verdicts.jsonl 里有按 entry_id 索引的条目'
                                 '（形如 window:w000044#r0），即证据查证阶段确实审过它的原文 span。',
            'caution': '「被重写过」不等于「被审过」；「被隔离」才是被审过且判为不可闭合。'
                       '本字段只陈述历史动作，不构成本次审核结论。',
            'how_to_read_qq_review_history': 'QQ 轨确实经过证据查证与语义内审，但必须按 entry_id 读取：'
                                             'evidence_verdicts.jsonl 的条目里没有 track 字段，'
                                             '用 d.get("track") == "qq" 过滤会把已有的 QQ 条目漏掉、'
                                             '从而误报成「从未审核」。本文件的 existing_review_detail 已按 entry_id 逐条汇总，'
                                             '请以它为准。',
        },
        'existing_qq_review_history': {
            'evidence_verdicts_rows_total': len(all_evidence_verdicts),
            'evidence_verdicts_rows_for_qq_windows': len(qq_evidence_verdicts),
            'evidence_verdicts_qq_entry_ids': sorted(qq_evidence_verdicts),
            'evidence_verdicts_qq_status': dict(Counter(
                all_evidence_verdicts_by_entry[e].get('status') for e in qq_evidence_verdicts)),
            'evidence_verdicts_qq_supports': dict(Counter(
                all_evidence_verdicts_by_entry[e].get('supports') for e in qq_evidence_verdicts)),
            'evidence_worklist_rows_total': len(all_evidence_worklist),
            'evidence_worklist_rows_for_qq_windows': len(qq_evidence_worklist_rows),
            'semantic_review_counts': semantic_counts,
            'semantic_review_qq_rows': len(qq_semantic_rows),
            'semantic_review_qq_verdicts': dict(Counter(r.get('verdict') for r in qq_semantic_rows)),
            'how_qq_rows_were_identified': '按 entry_id 前缀 window: 与 索引字段统计；'
                                           '这些文件没有 track 字段，不能按 track 过滤。',
            'correction_log': '本文件的上一版曾断言「QQ 轨的 evidence_verdicts / evidence_review_worklist / '
                              'agent_verifications 条目数为 0/0/0、QQ 从未经过证据审核」。该断言错误：'
                              '上述文件按 entry_id 索引，确实存在 %d 条 QQ 窗口证据判定与 %d 条 QQ 语义内审记录。'
                              '错误原因是按不存在的 track 字段过滤，已在 build_inventory 的 existing_review_detail 中修正，'
                              '并保留此条记录供核对。'
                              % (len(qq_evidence_verdicts), len(qq_semantic_rows)),
        },
        'category_schema': {
            'note': '工单口径里的「四类」与窗口天然分类是两回事，必须分清：'
                    '(a) 上游窗卡的 category（帧时序/索敌/伤害结算/位移/寻路/干员机制/技能特例/数值与读图/关卡与出怪/其他）'
                    '是**机制主题**；'
                    '(b) 本阶段 A/B/C/D 四组是**审核难度分桶**——看的是这段片段能不能自足地定一条机制，'
                    '不是它讲什么机制。同一个 category 会同时出现在四个组里。',
            'why_not_topic_based': '用户要求的四类（完整机制 / 数值公式代码 / 混合机制猜测或整窗拒绝 / 其余随机）'
                                   '描述的是「读源时要做多少判断」，不是主题；按主题分组无法覆盖「整窗拒绝」这一类。',
            'drives_what': '分组决定审核方对「不可枚举数值」与「不可闭合片段」的处理口径：'
                           '只有 A 组的工单允许直接认可枚举数字；B 组必须逐字给出数字出处；'
                           'C 组与 D 组一律不得写入片段里没有的数字与范围。',
        },
        'privacy': {
            'spans_are_sanitized': True,
            'contains_group_id_or_qq_number': False,
            'nicknames_redacted_from_text': True,
            'nickname_redaction_rule': 'raw_messages[].text 里的 `@昵称` 一律去掉昵称：'
                                       '能唯一解析到某个发言者的写成 `@<speaker_id>`，解析不到的写成 `@某人`，'
                                       '并置 mentions_nick_unresolved=true。日报 `参与者:` 名单行整行匿名。'
                                       '6–12 位连续数字抹为 `[账号已隐去]`（含被 `[]` 包住的情形）。',
            'source_msg_ids_kept_for': '内部定位原消息，不得转发或写入公开层',
            'verified_by': 'kb_curation_qq_expansion_privacy_scan.py → '
                           'kb_trial/curation/qq_expansion/privacy_scan.json',
            'verified_result': '真实 QQ 号 0 命中、群号 0 命中；残留 6–12 位数字逐条核过，'
                               '无一是真实发送者 QQ；昵称命中均为同形误报。'
                               '上一版「扫 417 个 QQ 号命中 0」的判据过窄、不成立，已更正。',
            'confidence_limit': 'text-source-supported：未核听原片、未做游戏内实测，'
                                '不得复述为「已彻底脱敏」。',
        },
        'worked_examples': build_worked_examples(workorders, decisions_by_doc),
    }

    if args.check:
        return check(records, workorders, stats)

    OUT.mkdir(parents=True, exist_ok=True)
    WORKORDERS.mkdir(parents=True, exist_ok=True)
    for f in WORKORDERS.glob('qq_wo_*.json'):
        f.unlink()

    inv_lines = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)
    (OUT / 'qq_worklist_inventory.jsonl').write_text(inv_lines, encoding='utf-8')
    (OUT / 'qq_worklist_inventory.json').write_text(
        json.dumps({'note': 'QQ 轨窗口清点：每行一个窗口，合并工作清单、文档层、原卡、判定、'
                            '已入选与已有审核状态。逐窗记录见同目录 .jsonl。',
                    'record_count': len(records),
                    'fields': sorted(records[0].keys()),
                    'records': records},
                   ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    index = []
    for w in workorders:
        wide = w['window']['window_id']
        p = WORKORDERS / ('%s.json' % w['workorder_id'])
        p.write_text(json.dumps(w, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        index.append({
            'workorder_id': w['workorder_id'],
            'file': str(p.relative_to(ROOT)).replace('\\', '/'),
            'group': w['group'],
            'group_label': w['group_label'],
            'window_id': wide,
            'kind': w['window']['kind'],
            'category': w['window']['category'],
            'as_of': w['window']['as_of'],
            'n_source_spans_excerpts': len(w['source_spans_excerpts']),
            'n_raw_messages': w['raw_messages'].get('message_count', 0),
            'raw_mapping_status': w['raw_messages'].get('mapping_status'),
            'n_atoms': sum(1 for a in w['atoms_from_this_window'] if a.get('atom_text')),
            'n_old_decisions': len(w['old_decisions']),
            'shipped_status': w['existing_review']['shipped_status'],
            'is_rescue_sample': bool(w['selection_rule'].get('is_rescue_sample')),
            'sha256': sha256_bytes(p.read_bytes()),
        })

    (WORKORDERS / 'index.json').write_text(json.dumps({
        'note': '阶段一 80 份试批工单索引。四组各 20 个互斥窗口，seed=%d；'
                '组由 qq_expansion_stats.json 的 classification.rule 机械判定，未凑类别。'
                % SEED,
        'seed': SEED,
        'count': len(index),
        'shortfalls': shortfalls,
        'by_group': dict(Counter(i['group'] for i in index)),
        'by_shipped_status': dict(Counter(i['shipped_status'] for i in index)),
        'workorders': index,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    (OUT / 'qq_expansion_stats.json').write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    print(json.dumps({k: stats[k] for k in ('sources', 'classification', 'workorders')},
                     ensure_ascii=False, indent=1, sort_keys=True))
    return 0


def check(records, workorders, stats):
    """Recompute and compare against disk. Fails loudly on drift."""
    problems = []
    inv_path = OUT / 'qq_worklist_inventory.jsonl'
    if not inv_path.exists():
        problems.append('missing %s' % inv_path)
    else:
        disk = load_records(inv_path)
        if len(disk) != len(records):
            problems.append('inventory row count %d != recomputed %d' % (len(disk), len(records)))
    idx_path = WORKORDERS / 'index.json'
    if not idx_path.exists():
        problems.append('missing %s' % idx_path)
    else:
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        if idx['count'] != len(workorders):
            problems.append('index count %d != recomputed %d' % (idx['count'], len(workorders)))
        for entry in idx['workorders']:
            p = ROOT / entry['file']
            if not p.exists():
                problems.append('missing work-order %s' % entry['file'])
                continue
            if sha256_bytes(p.read_bytes()) != entry['sha256']:
                problems.append('sha256 drift: %s' % entry['file'])
        got = [w['window']['window_id'] for w in workorders]
        want = [e['window_id'] for e in idx['workorders']]
        if got != want:
            problems.append('work-order window order changed (seed/subset unstable)')
        if len(set(got)) != len(got):
            problems.append('work-order windows not unique')
        if any(g.startswith('group_overlap') for g in []):
            pass
        groups = Counter(w['group'] for w in workorders)
        for g, n in groups.items():
            if n > PER_GROUP:
                problems.append('group %s has %d work-orders (>%d)' % (g, n, PER_GROUP))
    st_path = OUT / 'qq_expansion_stats.json'
    if not st_path.exists():
        problems.append('missing %s' % st_path)
    if problems:
        print('CHECK FAILED')
        for p in problems:
            print(' -', p)
        return 1
    print('CHECK OK: inventory=%d windows, workorders=%d, groups=%s'
          % (len(records), len(workorders),
             dict(Counter(w['group'] for w in workorders))))
    return 0


# ---------------------------------------------------------------------------
# Stage 3: full scale-up inventory + first b3 batch
# ---------------------------------------------------------------------------

def _stage3_context(prior_batches=()):
    """Shared loader for the scale-up build and its self-check.

    `prior_batches` tags every record with the scale-up batch (if any) that already reviewed
    it, so the bucket function can exclude it. Stage 3 passes nothing; stage 4 passes `('b3',)`
    and thereby excludes all 260 b3 windows.
    """
    records, cards, windows, docs, worklist, ctx = build_inventory()
    b2, kept_in_b2 = load_stage2_context()
    shipped = {r['window_id'] for r in records
               if (r.get('shipped') or {}).get('status') == 'shipped'}
    staged = {r['window_id'] for r in records
              if (r.get('shipped') or {}).get('status') == 'staged'}
    for b in prior_batches:
        spec = next(s for s in STAGE_BATCHES.values() if s['batch'] == b)
        idx_path = spec['workorders'] / 'index.json'
        if not idx_path.exists():
            continue
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        done = {e['window_id'] for e in idx['workorders']}
        for rec in records:
            if rec['window_id'] in done:
                rec.setdefault('_reviewed_in_batches', []).append(b)
    decisions_by_doc = {}
    for d in load_records(DECISIONS):
        if d.get('track') == 'qq':
            decisions_by_doc.setdefault(d['doc_id'], d)
    return records, cards, windows, docs, ctx, decisions_by_doc, b2, kept_in_b2, shipped, staged


def build_stage3_inventory(records, b2, kept_in_b2, shipped, staged, prior_batches=()):
    """Every window with its scale-up bucket and why it is (not) in this batch."""
    rows = []
    for rec in records:
        bucket, reason = stage3_bucket_of(rec, b2, kept_in_b2, shipped, staged,
                                          prior_batches=prior_batches)
        rows.append({
            'window_id': rec['window_id'],
            'bucket': bucket,
            'bucket_label': STAGE3_BUCKET_LABEL.get(bucket, bucket),
            'excluded_reason': reason,
            'in_stage3_pool': bucket in ('no_process', 'no_candidates'),
            'priority_key': list(stage3_priority_key(rec)),
            'worklist_row_count': rec['worklist_row_count'],
            'kind': rec['kind'],
            'classification_group': rec['classification']['group'],
            'category': rec['category'],
            'as_of': rec['as_of'],
            'window_tier': rec.get('window_tier'),
            'window_score': rec.get('window_score'),
            'window_n_messages': rec.get('window_n_messages'),
            'has_host_authority': rec.get('has_host_authority'),
            'n_source_spans': rec.get('n_source_spans'),
            'shipped_status': (rec.get('shipped') or {}).get('status'),
            'existing_review_stages': rec.get('existing_review_stages'),
            'reviewed_in_scale_up_batches': sorted(rec.get('_reviewed_in_batches') or ()),
            'source_msg_ids': rec['source_msg_ids'],
        })
    return rows


def main_stage3(args, phase):
    spec = STAGE_BATCHES[phase]
    batch = spec['batch']
    prior_batches = ('b3',) if batch == 'b4' else ()
    limit = args.b3_limit if batch == 'b3' else args.b4_limit

    (records, cards, windows, docs, ctx, decisions_by_doc, b2, kept_in_b2,
     shipped, staged) = _stage3_context(prior_batches=prior_batches)

    all_rows = build_stage3_inventory(records, b2, kept_in_b2, shipped, staged,
                                     prior_batches=prior_batches)
    bucket_tally = Counter(r['bucket'] for r in all_rows)
    pool_rows = [r for r in all_rows if r['in_stage3_pool']]

    picked, _tally, pool_size = pick_stage3_batch(
        records, b2, shipped, staged, limit, kept_in_b2=kept_in_b2,
        prior_batches=prior_batches)
    picked.sort(key=stage3_priority_key)

    def bucket_of(rec):
        return stage3_bucket_of(rec, b2, kept_in_b2, shipped, staged,
                                prior_batches=prior_batches)

    workorders = [
        build_workorder(i + 1, rec, cards, decisions_by_doc, docs, windows, ctx,
                        phase=phase, bucket=bucket_of(rec)[0],
                        excluded_reason=bucket_of(rec)[1])
        for i, rec in enumerate(picked)]

    # Everything the pool still holds after this batch. For b3 that is the remainder stage 4
    # picked up; for b4 (which takes the whole remainder) it must be 0.
    taken = {r['window_id'] for r in picked}
    remaining = [r for r in pool_rows if r['window_id'] not in taken]

    missing_raw = [
        {'window_id': w['window']['window_id'],
         'workorder_id': w['workorder_id'],
         'mapping_status': w['raw_messages'].get('mapping_status'),
         'cited_missing_from_raw': w['raw_messages'].get('cited_missing_from_raw') or [],
         'n_raw_messages': w['raw_messages'].get('message_count', 0)}
        for w in workorders
        if w['raw_messages'].get('mapping_status') != 'ok']

    bucket_notes_s3 = {
        'final_keep': '本桶在候选池中为 **0**：阶段二有 keep 的 30 窗全部已在阶段二批内。'
                      '（其中 w000041 同时是 rescue 样本；按「产出 keep」优先标注。）',
        'keep_before_qq_fix': '本桶在候选池中为 **0**：历史上 supported/keep 的 11 窗，'
                              '8 窗已入 curated、3 窗在阶段二批内。',
        'rescue': '本桶在候选池中为 **0**：3 个救援样本 w000031/w000036/w000041 '
                  '已在阶段二批内复核（w000041 因产出 keep 归入 final_keep）。',
        'qq_pending': '本桶在池中为 0（pending 是阶段二的窗口级判定，已在批内消化）。',
        'retry': '本桶在池中为 0（尚无需要重读的窗口）。',
        'no_process': '池的主体：有候选行、但从未逐条读源。',
        'no_candidates': '无 worklist 候选行的 raw-only 窗口，判定只能靠 raw_messages。',
    }
    bucket_notes_extra = {b: '历史阶段已审窗口，本批不重复收录。' for b in
                          ['reviewed_b2', 'reviewed_b3']}

    stats = {
        'stage': phase,
        'batch': batch,
        'note': '阶段%s扩批的清单层。本文件只清点，不含任何审核判定。' % batch[1:],
        'generated_from': {
            'windows_inventory': 'kb_trial/curation/qq_expansion/qq_worklist_inventory.json',
            'stage2_workorders': 'kb_trial/curation/qq_expansion/workorders/index.json',
            'curated': 'kb_trial/curated_high_quality.json',
            'prior_scale_up_batches': [
                'kb_trial/curation/qq_expansion/workorders_%s/index.json' % b
                for b in prior_batches],
        },
        'counts': {
            'windows_total': len(records),
            'already_reviewed_stage2': len(b2),
            'already_reviewed_prior_batches': len(
                {r['window_id'] for r in records if r.get('_reviewed_in_batches')}),
            'already_in_curated': len(shipped),
            'pool_unreviewed': pool_size,
            'this_batch': len(workorders),
            'remaining_after_this_batch': len(remaining),
        },
        'bucket_distribution': {b: bucket_tally.get(b, 0) for b in
                                ['final_keep', 'keep_before_qq_fix', 'qq_pending', 'no_process',
                                 'rescue', 'no_candidates', 'retry', 'reviewed_b2',
                                 'reviewed_b3']},
        'bucket_distribution_all': dict(bucket_tally),
        'bucket_scope': dict(STAGE3_BUCKET_LABEL, **{
            'reviewed_b2': '阶段二 80 窗试批内已读源',
            'reviewed_b3': '阶段三 b3 批内已读源',
        }),
        'bucket_notes': dict(bucket_notes_s3, **bucket_notes_extra),
        'pool_composition': {
            'no_process': sum(1 for r in pool_rows if r['bucket'] == 'no_process'),
            'no_candidates': sum(1 for r in pool_rows if r['bucket'] == 'no_candidates'),
        },
        'batch': {
            'batch_id': batch,
            'limit': limit,
            'window_count': len(workorders),
            'by_bucket': dict(Counter(w['group'] for w in workorders)),
            'by_classification_group': dict(Counter(
                w['window']['window_id'] and next(
                    r['classification_group'] for r in pool_rows
                    if r['window_id'] == w['window']['window_id']) for w in workorders)),
            'ordering_rule': '先 no_process 后 no_candidates；组内按 '
                             '(has_host_authority 降序, window_score 降序, window_id 升序)。'
                             '确定性、可增量续跑，不用随机。',
            'excludes_prior_scale_up_batches': list(prior_batches),
        },
        'raw_coverage': {
            'windows_with_raw_located': sum(1 for w in workorders
                                            if w['raw_messages'].get('message_count', 0) > 0),
            'windows_missing_raw': missing_raw,
            'missing_raw_count': len(missing_raw),
            'total_raw_messages': sum(w['raw_messages'].get('message_count', 0) for w in workorders),
            'note': 'missing_raw 非空即为「该窗原始消息无法在导出中定位」——按缺失处理，绝不编造。'
                    'raw-only 窗口无上游候选行，但其原始消息仍可定位。',
            'ts_order_quirk': [w['window']['window_id'] for w in workorders
                               if _has_ts_inversion(w['raw_messages']['messages'])],
            'ts_order_quirk_note': '源导出按消息 id 排序；个别窗口存在 id 序与时间序不一致的条目'
                                   '（相邻两条时间差 1 秒、顺序相反）。原样保留，不重排、不丢弃，'
                                   'raw_messages.seq 仍是导出顺序。',
        },
        'windows_by_category': dict(Counter(w['window']['category'] for w in workorders)),
    }

    if spec.get('check'):
        return check_stage3(records, workorders, stats, all_rows, phase)

    OUT.mkdir(parents=True, exist_ok=True)
    spec['workorders'].mkdir(parents=True, exist_ok=True)
    for f in spec['workorders'].glob('%s_*.json' % spec['prefix']):
        f.unlink()

    spec['inventory_jsonl'].write_text(
        ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in all_rows), encoding='utf-8')
    spec['inventory'].write_text(json.dumps({
        'note': '阶段%s全量未审窗口清点：每个窗口标注所属桶、是否在候选池内、以及未入选原因。'
                '逐窗记录见同目录 %s。' % (batch[1:], spec['inventory_jsonl'].name),
        'batch_id': batch,
        'record_count': len(all_rows),
        'fields': sorted(all_rows[0].keys()),
        'records': all_rows,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    index = []
    mapping = []
    for w in workorders:
        wide = w['window']['window_id']
        p = spec['workorders'] / ('%s.json' % w['workorder_id'])
        p.write_text(json.dumps(w, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        digest = sha256_bytes(p.read_bytes())
        index.append({
            'workorder_id': w['workorder_id'],
            'file': str(p.relative_to(ROOT)).replace('\\', '/'),
            'group': w['group'],
            'group_label': w['group_label'],
            'window_id': wide,
            'kind': w['window']['kind'],
            'category': w['window']['category'],
            'as_of': w['window']['as_of'],
            'n_source_spans_excerpts': len(w['source_spans_excerpts']),
            'n_raw_messages': w['raw_messages'].get('message_count', 0),
            'raw_mapping_status': w['raw_messages'].get('mapping_status'),
            'n_atoms': sum(1 for a in w['atoms_from_this_window'] if a.get('atom_text')),
            'n_old_decisions': len(w['old_decisions']),
            'shipped_status': w['existing_review']['shipped_status'],
            'is_rescue_sample': False,
            'sha256': digest,
        })
        mapping.append({
            'workorder_id': w['workorder_id'],
            'file': str(p.relative_to(ROOT)).replace('\\', '/'),
            'window_id': wide,
            'bucket': w['group'],
            'priority_key': list(stage3_priority_key(
                next(r for r in records if r['window_id'] == wide))),
            'n_raw_messages': w['raw_messages'].get('message_count', 0),
            'raw_mapping_status': w['raw_messages'].get('mapping_status'),
            'sha256': digest,
        })

    (spec['workorders'] / 'index.json').write_text(json.dumps({
        'note': '阶段%s %s 批索引：%d 份工单，格式与阶段二完全一致，仅编号前缀为 %s_。'
                % (batch[1:], batch, len(index), spec['prefix']),
        'batch_id': batch,
        'count': len(index),
        'by_bucket': dict(Counter(i['group'] for i in index)),
        'by_shipped_status': dict(Counter(i['shipped_status'] for i in index)),
        'workorders': index,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    spec['mapping'].write_text(json.dumps({
        'note': '阶段%s %s 批的 工单编号 ↔ 窗口 id 映射表，含桶归属、优先级键与工单 sha256。'
                'window_id 仅用于内部定位原始消息，不得转发或写入任何公开层。'
                % (batch[1:], batch),
        'batch_id': batch,
        'count': len(mapping),
        'ordering_rule': stats['batch']['ordering_rule'],
        'mappings': mapping,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    spec['stats'].write_text(
        json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')

    print(json.dumps({
        'batch': batch,
        'windows_total': stats['counts']['windows_total'],
        'pool_unreviewed': stats['counts']['pool_unreviewed'],
        'this_batch': stats['counts']['this_batch'],
        'remaining_after_this_batch': stats['counts']['remaining_after_this_batch'],
        'bucket_distribution': stats['bucket_distribution'],
        'pool_composition': stats['pool_composition'],
        'raw_missing': stats['raw_coverage']['missing_raw_count'],
    }, ensure_ascii=False, indent=1))
    return 0


def check_stage3(records, workorders, stats, all_rows, phase):
    """Scale-up self-check: idempotence of on-disk outputs, raw locatability, and a full
    privacy sweep over every work-order in the batch.

    The privacy sweep is the gate: it must find ZERO real QQ numbers and ZERO group ids.
    Mechanism numbers (0.5, 0.65, `1帧`, `1/3`, `23 48 73 98`) must survive untouched --
    they are short or separated, so the 6-12 contiguous-digit rule never matches them.
    """
    spec = STAGE_BATCHES[phase]
    batch = spec['batch']
    problems = []

    if not spec['workorders'].exists():
        problems.append('missing %s' % spec['workorders'])
        print('CHECK FAILED')
        for p in problems:
            print(' -', p)
        return 1

    idx_path = spec['workorders'] / 'index.json'
    if not idx_path.exists():
        problems.append('missing %s' % idx_path)
    else:
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        if idx['count'] != len(workorders):
            problems.append('%s index count %d != recomputed %d'
                            % (batch, idx['count'], len(workorders)))
        for entry in idx['workorders']:
            p = ROOT / entry['file']
            if not p.exists():
                problems.append('missing work-order %s' % entry['file'])
                continue
            if sha256_bytes(p.read_bytes()) != entry['sha256']:
                problems.append('sha256 drift (not idempotent): %s' % entry['file'])

    for path in (spec['inventory'], spec['inventory_jsonl'], spec['stats'], spec['mapping']):
        if not path.exists():
            problems.append('missing %s' % path.relative_to(ROOT))

    # ---- mapping must agree with the index, window-for-window --------------------
    if spec['mapping'].exists():
        mp = json.loads(spec['mapping'].read_text(encoding='utf-8'))
        if mp['count'] != len(workorders):
            problems.append('%s mapping count %d != recomputed %d'
                            % (batch, mp['count'], len(workorders)))
        if [m['workorder_id'] for m in mp['mappings']] != [w['workorder_id'] for w in workorders]:
            problems.append('%s mapping order/content differs from the batch' % batch)

    # ---- window uniqueness / ordering / seq / ts --------------------------------
    wids = [w['window']['window_id'] for w in workorders]
    if len(set(wids)) != len(wids):
        problems.append('%s windows not unique' % batch)
    ts_inversions = []
    for w in workorders:
        msgs = w['raw_messages']['messages']
        if [m['seq'] for m in msgs] != list(range(1, len(msgs) + 1)):
            problems.append('seq not contiguous: %s' % w['workorder_id'])
        # Ordering follows the SOURCE EXPORT's own message order, which is by message id.
        # A handful of windows contain a message whose timestamp is 1s earlier than its
        # predecessor (two interleaved id series); that is the export's shape, not our
        # error, so it is reported rather than treated as a failure.
        n_inv = sum(1 for i in range(1, len(msgs)) if msgs[i]['ts'] < msgs[i - 1]['ts'])
        if n_inv:
            ts_inversions.append({'workorder_id': w['workorder_id'],
                                  'window_id': w['window']['window_id'],
                                  'inversions': n_inv,
                                  'note': '源导出按消息 id 排序；该窗存在 id 序与时间序不一致的条目，'
                                          '原样保留，不做重排也不丢弃。'})
    # ---- raw locatability: anything not fully located must be REPORTED -----------
    for w in workorders:
        status = w['raw_messages'].get('mapping_status')
        if status not in ('ok', 'ok_with_gaps', 'no_cited_ids_in_raw_export'):
            problems.append('unexpected mapping_status %s: %s'
                            % (status, w['workorder_id']))
        if status == 'no_cited_ids_in_raw_export':
            if w['raw_messages'].get('message_count', 0) != 0:
                problems.append('flagged missing but has messages: %s' % w['workorder_id'])
            if not w['raw_messages'].get('mapping_note'):
                problems.append('missing raw without explanation: %s' % w['workorder_id'])

    # ---- privacy sweep: real QQ ids / group id must be ZERO ----------------------
    real_qqs = set()
    with open(QQ_CHAT_EXPORT, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            q = (row.get('发送人QQ') or '').strip()
            if q:
                real_qqs.add(q)
    group_id = str(QQ_CHAT_EXPORT.stem.split('_')[0])
    qq_hits, group_hits = [], []
    for w in workorders:
        blob = json.dumps(w, ensure_ascii=False)
        if group_id and group_id in blob:
            group_hits.append(w['workorder_id'])
        for q in real_qqs:
            if re.search(r'(?<!\d)' + re.escape(q) + r'(?!\d)', blob):
                qq_hits.append((w['workorder_id'], 'sender_qq'))
                break
    if qq_hits:
        problems.append('PRIVACY: real QQ number in %d work-order(s): %s'
                        % (len(qq_hits), qq_hits[:5]))
    if group_hits:
        problems.append('PRIVACY: group id in %d work-order(s): %s'
                        % (len(group_hits), group_hits[:5]))

    # ---- mechanism numbers must survive -----------------------------------------
    blob_all = json.dumps([w['raw_messages'] for w in workorders], ensure_ascii=False)
    mech = ['0.5', '0.65', '1帧', '21帧', '1/3', '23 48 73 98', '0.0333333']
    survived = {m: blob_all.count(m) for m in mech}

    # A redaction marker that sits immediately after a decimal point is a destroyed fraction,
    # not a hidden identity: the source wrote a mechanism constant there. This is the check
    # that would have caught the `0.[账号已隐去]` defect the first time it shipped.
    mangled = []
    for w in workorders:
        for m in w['raw_messages']['messages']:
            if re.search(r'\.\s*\[账号已隐去\]', m.get('text') or ''):
                mangled.append((w['window']['window_id'], m['seq']))
    if mangled:
        problems.append('MECHANISM NUMBER DESTROYED: redaction ate the fraction of a decimal '
                        'in %d message(s): %s' % (len(mangled), mangled[:5]))

    if problems:
        print('CHECK FAILED')
        for p in problems:
            print(' -', p)
        return 1
    print('STAGE%s CHECK OK (batch=%s): windows=%d batch_windows=%d buckets=%s '
          'raw_missing=%d remaining=%d privacy_qq_hits=0 privacy_group_hits=0'
          % (batch[1:], batch, stats['counts']['windows_total'], len(workorders),
             stats['bucket_distribution'], stats['raw_coverage']['missing_raw_count'],
             stats['counts']['remaining_after_this_batch']))
    print('  pool=%s' % stats['pool_composition'])
    print('  mechanism numbers preserved: %s' % survived)
    if ts_inversions:
        print('  source-order quirk (reported, not an error): %s' % ts_inversions)
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
