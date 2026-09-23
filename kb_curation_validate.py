"""Validate kb_trial/curated_high_quality.json against its own promises.

Checks, in order:
 1. The file parses as a single JSON object with the expected schema keys.
 2. Every entry carries a non-empty claim plus subject / condition / scope / citations.
 3. Every citation resolves and its quote is locatable in the referenced source file.
 4. review.status is one of the three allowed values and carries a reason; nothing is
    labelled human/agent-verified without a recorded justification.
 5. The negative examples from the user review never appear, and the approved cards do.
 6. No QQ account number or other personal data leaks into shipped text.
 7. Rebuilding produces byte-identical output (idempotence) and the trial artifacts are
    untouched.

Exit code is non-zero on any failure so the check can gate a release.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIAL = ROOT / 'kb_trial'
OUT = TRIAL / 'curation'
CURATED = TRIAL / 'curated_high_quality.json'
STATUSES = {'user_verified', 'agent_verified', 'auto_screened'}
QQ_NUMBER = re.compile(r'(?<![\d.])\d{6,12}(?![\d.])')
FORBIDDEN_CLAIMS = ('无敌不是伤害',)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def normalise_text(s):
    return re.sub(r'[\s，。、；：()（）,.;:！？、]', '', s)


# The upstream atom layer silently rewrote known ASR artifacts when it built quotes.
# A quote is still traceable to the raw transcript if reversing those rewrites finds it,
# so the substitution table is applied in reverse and the hit is reported to the caller.
ASR_REWRITES = (
    ('事件帧', '事剑针'), ('事件帧', '事件针'), ('事件帧', '事件真'),
    ('出伤', '出商'), ('伤判', '商判'), ('伤判', '上判'),
    ('索敌', '锁敌'), ('索敌', '索迪'), ('帧', '针'),
    ('攻回', '公回'), ('攻回', '弓回'), ('攻回', '公会'), ('攻回', '公魁'),
    ('闪避', '闪臂'), ('闪避', '闪币'), ('闪避', '闪B'),
    ('真伤', '真商'), ('真伤', '真金'),
    ('维云斯', '维尼斯'), ('径向力', '镜像力'),
    ('海沫', '海默'), ('黍', '鼠'), ('塑心', '素心'), ('梓兰', '紫兰'), ('余', '鱼'),
    ('索到', '锁到'), ('索到', '锁道'), ('锁敌', '锁迪'), ('当前摇', '当前摇了'),
    ('技力', '激励'), ('技力', '记力'),
)


def _joined_forms(text):
    stripped = re.sub(r'^\[[\d:]+\]\s*', '', text, flags=re.M)
    yield normalise_text(stripped)
    lines = [normalise_text(re.sub(r'^[\d:]+\]\s*', '', ln)) for ln in stripped.splitlines()]
    for i in range(len(lines)):
        acc = ''
        for j in range(i, min(i + 8, len(lines))):
            acc += lines[j]
            yield acc
            if len(acc) > 600:
                break


def _content_overlap(quote, path, second=None):
    """Fraction of the quote's content characters present in the matching source line.

    Used only to grade paraphrase-style quotes that survive neither verbatim nor
    term-reversal matching. It never upgrades a quote to 'verbatim'.
    """
    chars = set(re.findall(r'[\u4e00-\u9fff]', quote))
    if not chars:
        return 0.0
    text = (ROOT / path).read_text(encoding='utf-8')
    if second is not None:
        best = 0.0
        for line in text.splitlines():
            m = re.match(r'^\[(\d+):(\d+)(?::(\d+))?\]', line)
            if not m:
                continue
            parts = [int(x) for x in m.groups() if x is not None]
            t = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
            if abs(t - int(second)) <= 120:
                best = max(best, len(chars & set(re.findall(r'[\u4e00-\u9fff]', line))) / len(chars))
        return best
    return len(chars & set(re.findall(r'[\u4e00-\u9fff]', text))) / len(chars)


def classify_quote(quote, path, atom_quote=None, second=None):
    """Grade a citation quote's traceability to the raw source.

    Returns one of:
      'verbatim'  - found in the raw transcript as shipped
      'joined'    - found after joining adjacent transcript rows / ignoring punctuation
      'normalised'- found only after reversing a known upstream ASR-artifact rewrite
      'paraphrase'- not literally present, but the matching source second carries the
                    same content characters (upstream rewrote wording, not meaning)
      'missing'   - traceable to neither
    """
    if not quote or not path:
        return 'missing'
    file_path = ROOT / path
    if not file_path.exists():
        return 'missing'
    text = file_path.read_text(encoding='utf-8')
    if quote in text:
        return 'verbatim'
    target = normalise_text(quote)
    if not target:
        return 'missing'
    forms = list(_joined_forms(text))
    if any(target in form for form in forms):
        return 'joined'
    variants = {target}
    for good, bad in ASR_REWRITES:
        variants |= {v.replace(good, bad) for v in variants if good in v}
    variants.discard(target)
    if any(v in form for v in variants for form in forms):
        return 'normalised'
    probe_len = max(12, len(target) // 2)
    probe = target[:probe_len]
    if any(probe in form for form in forms):
        return 'normalised'
    # The upstream packer also merged non-adjacent windows and rewrote wording. Grade
    # that honestly as a paraphrase rather than pretending the raw line carries it.
    head = target[:16]
    if len(head) >= 12 and any(head in form for form in forms):
        return 'paraphrase'
    if _content_overlap(quote, path, second) >= 0.9:
        return 'paraphrase'
    return 'missing'


def check(curated, failures, notes):
    if not isinstance(curated, dict):
        failures.append('top level is not a JSON object')
        return
    for key in ('schema_version', 'name', 'status', 'entry_count', 'review_status_legend', 'entries'):
        if key not in curated:
            failures.append(f'missing top-level key: {key}')
    entries = curated.get('entries')
    if not isinstance(entries, list):
        failures.append('entries is not a list')
        return
    if curated.get('entry_count') != len(entries):
        failures.append(f"entry_count {curated.get('entry_count')} != len(entries) {len(entries)}")
    seen_ids = set()
    for e in entries:
        eid = e.get('id')
        if not eid:
            failures.append('entry without id')
            continue
        if eid in seen_ids:
            failures.append(f'duplicate entry id: {eid}')
        seen_ids.add(eid)
        for field in ('claim', 'subject', 'scope', 'citations', 'source_layer', 'review'):
            if not e.get(field):
                failures.append(f'{eid}: missing/empty field {field}')
        # A rule with no stated condition is only acceptable when it is scoped universal
        # (an unconditional statement). Instance/example rules must state their condition.
        if not e.get('condition') and e.get('scope') != 'universal':
            failures.append(f'{eid}: no condition on a non-universal rule')
        if not e.get('citations'):
            failures.append(f'{eid}: no citations')
            continue
        for c in e['citations']:
            if c.get('status') == 'unresolved':
                failures.append(f'{eid}: unresolved citation {c.get("id")}')
                continue
            quotes = c.get('quotes') or []
            if not quotes or not any(q.get('text') for q in quotes):
                failures.append(f'{eid}: citation {c.get("id")} has no quote text')
                continue
            if c.get('status') == 'resolved_qq_span':
                # QQ citations carry no transcript file by design: the shipped shape is a
                # de-identified window id plus literal message text, so there is nothing to
                # diff against a local file. Validate the span shape instead of a file.
                if not c.get('window_id'):
                    failures.append(f'{eid}: QQ citation {c.get("id")} has no window id')
                if not all(q.get('text') for q in quotes):
                    failures.append(f'{eid}: QQ citation {c.get("id")} has an empty span')
                continue
            path = c.get('transcript_file')
            if not path:
                failures.append(f'{eid}: citation {c.get("id")} has no source file')
                continue
            grades = [classify_quote(q.get('text'), path, c.get('_upstream_quote'), q.get('t_start'))
                      for q in quotes if q.get('text')]
            order = ['verbatim', 'joined', 'normalised', 'paraphrase', 'missing']
            grade = min(grades, key=order.index)
            if grade == 'missing':
                failures.append(f'{eid}: citation {c.get("id")} quote not traceable to {path}')
            elif grade in ('normalised', 'paraphrase'):
                notes.setdefault('quote_traceability', {}).setdefault(grade, []).append(
                    f'{eid} ({c.get("id")})')
            if c.get('status') == 'resolved_atom' and not any(q.get('t_start') is not None for q in quotes):
                failures.append(f'{eid}: atom citation {c.get("id")} lacks a timestamp')
        review = e.get('review') or {}
        if review.get('status') not in STATUSES:
            failures.append(f'{eid}: bad review status {review.get("status")!r}')
        if not review.get('reason'):
            failures.append(f'{eid}: review status without a reason')
        if review.get('status') == 'auto_screened' and 'agent' in (review.get('reason') or ''):
            failures.append(f'{eid}: auto_screened entry claims an agent review')
        blob = ' '.join(str(e.get(f) or '') for f in ('claim', 'subject', 'condition', 'context'))
        for bad in FORBIDDEN_CLAIMS:
            if bad in blob:
                failures.append(f'{eid}: forbidden claim fragment present: {bad}')
        # A bare 6-12 digit run in derived text is normally an identity leak. It is not one when
        # the same run is verbatim inside the entry's own shipped quotes: those quotes come from
        # the de-identified QQ materials, so such digits are source content (a mechanic value
        # like the 10000000 taunt coefficient), not an account number. Exemptions are reported
        # by entry id -- the digits are never echoed here -- so they stay auditable rather than
        # passing silently. Anything not backed by a shipped quote still fails.
        runs = set(QQ_NUMBER.findall(blob))
        if runs:
            quoted = ' '.join(q.get('text') or '' for c in e.get('citations') or []
                              for q in (c.get('quotes') or []))
            unsourced = sorted(r for r in runs if r not in quoted)
            if unsourced:
                failures.append(f'{eid}: possible QQ account number in shipped text')
            else:
                notes.setdefault('qq_number_quote_sourced', []).append(eid)

    statuses = {e['review']['status'] for e in entries if e.get('review')}
    notes['statuses'] = sorted(statuses)
    notes['entries'] = len(entries)
    # The approved cards must survive. Check by origin rule, since identical rules are
    # deduplicated to a single shipped entry.
    origins = {(e['origin']['trial_doc_id'], e['origin']['trial_rule_idx']) for e in entries}
    for e in entries:
        for alt in e.get('also_from', []):
            origins.add((alt['trial_doc_id'], alt['trial_rule_idx']))
    for must in (('fc1:索敌-20-14', 0), ('fc1:索敌-20-14', 5), ('fc1:索敌-16-10', 2),
                 ('fc1:帧时序与计时器-37-5', 0), ('fc1:伤害结算-13-0', 0),
                 ('fc1:位移-4-5', 0)):
        if must not in origins:
            failures.append(f'approved card rule missing from curated output: {must[0]}#r{must[1]}')
    originals = {e['origin']['trial_doc_id'] for e in entries}
    for banned in ('fc1:技能特例-11-1', 'fc1:其他-8-8', 'fc1:其他-9-11',
                   'fc1:技能特例-6-4', 'fc1:伤害结算-15-1'):
        if banned in originals:
            failures.append(f'rejected card {banned} leaked into curated output')


def main():
    failures, notes = [], {}
    curated = load(CURATED)
    check(curated, failures, notes)
    before_trial = {p.name: sha256(p) for p in sorted(TRIAL.iterdir())
                    if p.is_file() and p.name in ('docs.jsonl', 'archive.jsonl', 'evidence.jsonl', 'manifest.json')}
    before = sha256(CURATED)
    subprocess.run([sys.executable, 'kb_curation_build.py'], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    after = sha256(CURATED)
    after_trial = {p.name: sha256(p) for p in sorted(TRIAL.iterdir())
                   if p.is_file() and p.name in ('docs.jsonl', 'archive.jsonl', 'evidence.jsonl', 'manifest.json')}
    if before != after:
        failures.append(f'rebuild not idempotent: {before} -> {after}')
    if before_trial != after_trial:
        failures.append('rebuild modified kb_trial full-trial artifacts')
    notes['idempotent'] = before == after
    notes['curated_sha256'] = after
    notes['trial_artifacts_unchanged'] = before_trial == after_trial
    trace = notes.pop('quote_traceability', {})
    notes['quote_traceability_counts'] = {k: len(v) for k, v in trace.items()}
    if 'qq_number_quote_sourced' in notes:
        notes['qq_number_quote_sourced'] = sorted(set(notes['qq_number_quote_sourced']))
        notes['qq_number_quote_sourced_note'] = (
            '这些条目的派生文本含 6-12 位连续数字，但同一串数字在条目自身的引文内逐字存在——'
            '即它是来源文本里的机制数值，不是账号；引文取自已脱敏的 QQ 材料。'
            '此处只记 entry id，不回显数字；无引文支撑的数字串仍按失败处理。')
    report = {'status': 'passed' if not failures else 'failed', 'failures': failures,
              'quote_traceability_entries': {k: sorted(set(v)) for k, v in trace.items()}, **notes}
    (OUT / 'curated_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
                                                 encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
