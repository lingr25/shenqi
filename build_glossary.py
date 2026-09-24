# -*- coding: utf-8 -*-
"""Build the consolidated Arknights-mechanism glossary (root glossary.json).

Pure-local, deterministic. Merges three sources:

  1. qq_cards/glossary.jsonl      — 机制词条(50): short_def / mechanic_def /
                                    related_terms / status
  2. kb_trial/entity_index.json   — mentions 表: alias -> canonical(+type)。
                                    类型: operator/enemy/device/status/mechanic/
                                    slang/shenqi_slang, untyped 仅在 canonical
                                    含 >=2 个汉字时保留
  3. entity_corrector.py          — CORRECTION_RULES 的 (regex -> term):
                                    剔除 lookaround/反引用/通配后展开成字面值
                                    作为 term 的 asr_variants。FILE_CONTEXT_RULES
                                    是文件级消歧(语义受 scope 限制)，不全局入库。

Schema (glossary-1.0):
  entry = { term, type, aliases, asr_variants, short_def, mechanic_def,
            related_terms, sources }
  type ∈ operator|enemy|device|status|mechanic|slang|shenqi_slang|mechanism|term
  ("term" = 未归类术语, mostly ASR 消歧规则的正词)

Usage:  python build_glossary.py   # writes glossary.json
"""
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'glossary.json'
LOOKAROUND_RE = re.compile(r'\(\?<?[=!<][^()]*\)')
CJK_RE = re.compile(r'[一-鿿]')
INDEX_TYPES_KEEP = ('operator', 'enemy', 'device', 'status', 'mechanic',
                    'slang', 'shenqi_slang')


def load_glossary_terms():
    terms = {}
    path = ROOT / 'qq_cards' / 'glossary.jsonl'
    if not path.exists():
        return terms
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            g = json.loads(line)
            terms[g['term']] = {
                'short_def': g.get('short_def'),
                'mechanic_def': g.get('mechanic_def'),
                'related_terms': g.get('related_terms') or [],
                'status': g.get('status'),
            }
    return terms


def load_index():
    """alias -> canonical -> type/source."""
    idx = json.loads((ROOT / 'kb_trial' / 'entity_index.json')
                     .read_text(encoding='utf-8'))['mentions']
    canon = defaultdict(lambda: {'aliases': set(), 'sources': set(), 'types': []})
    for mention, variants in idx.items():
        for v in variants:
            c, t, src = v['canonical'], v.get('type', ''), set(v.get('source') or [])
            if c == mention:
                continue
            if t == 'untyped':
                continue  # untyped 的别名噪声大，canonical 侧在下方单独补
            e = canon[(c, t)]
            e['aliases'].add(mention)
            e['sources'] |= src
    for mention, variants in idx.items():
        for v in variants:
            c, t = v['canonical'], v.get('type', '')
            if t == 'untyped' and CJK_RE.findall(c) and len(CJK_RE.findall(c)) >= 2:
                canon[(c, 'term')]['sources'].update(v.get('source') or [])
                canon[(c, 'term')]['aliases'].add(mention) if mention != c else None
    return canon


def expand_pattern(pat):
    """(regex pattern) -> [literal variants] or None if not expandable.

    After lookaround stripping, only literals, `|`, and simple `[abc]`
    classes (no ranges) are expandable.
    """
    pat = LOOKAROUND_RE.sub('', pat)
    if re.search(r'[()\\.*?+$^]', pat):
        return None
    parts = pat.split('|')
    out = []
    for part in parts:
        combos = ['']
        for s in re.split(r'(\[[^\]]+\])', part):
            if not s:
                continue
            if s.startswith('['):
                cls = s[1:-1]
                if '-' in cls:
                    return None  # 字符区间不展开
                choices = list(dict.fromkeys(cls))
            else:
                choices = [s]
            combos = [c + ch for c in combos for ch in choices]
        out.extend(combos)
    return out or None


def load_corrector_rules():
    """Parse CORRECTION_RULES from entity_corrector.py without importing it."""
    src = (ROOT / 'entity_corrector.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Name)
                        and target.id == 'CORRECTION_RULES'):
                    pairs = []
                    for elt in node.value.elts:
                        if (isinstance(elt, ast.Tuple) and len(elt.elts) == 2
                                and all(isinstance(e, ast.Constant)
                                        and isinstance(e.value, str)
                                        for e in elt.elts)):
                            pairs.append((elt.elts[0].value, elt.elts[1].value))
                    return pairs
    return []


def load_asr_variants():
    target_vars = defaultdict(set)
    for pat, term in load_corrector_rules():
        if '\\' in term:
            # 反引用规则(如 (重装|打|抽)山比 -> \1珊比)是上下文改写,不是别名
            continue
        for v in expand_pattern(pat) or []:
            if v and v != term and len(v) <= 16:
                target_vars[term].add(v)
    return target_vars


def main():
    g_terms = load_glossary_terms()
    canon = load_index()
    asr = load_asr_variants()

    entries = {}
    all_types = defaultdict(set)

    def ensure(term, typ, sources):
        key = (term, typ)
        if key not in entries:
            entries[key] = {
                'term': term, 'type': typ,
                'aliases': set(), 'asr_variants': set(),
                'short_def': None, 'mechanic_def': None,
                'related_terms': [], 'sources': set(),
            }
        entries[key]['sources'] |= set(sources)
        return entries[key]

    for (c, t), e in canon.items():
        ent = ensure(c, t, e['sources'])
        ent['aliases'] |= {a for a in e['aliases'] if a != c}
        all_types[c].add(t)

    for term, g in g_terms.items():
        cands = all_types.get(term)
        if cands:
            for t in cands:
                ent = ensure(term, t, g.get('status') and ['glossary'] or [])
                ent['short_def'] = g['short_def']
                ent['mechanic_def'] = g['mechanic_def']
                ent['related_terms'] = g['related_terms']
        else:
            ent = ensure(term, 'mechanism', ['glossary'])
            ent['short_def'] = g['short_def']
            ent['mechanic_def'] = g['mechanic_def']
            ent['related_terms'] = g['related_terms']

    for term, vars_ in asr.items():
        cands = all_types.get(term)
        if cands:
            for t in cands:
                ensure(term, t, ['corrector'])['asr_variants'] |= vars_
        else:
            ensure(term, 'term', ['corrector'])['asr_variants'] |= vars_

    out_entries = []
    for ent in entries.values():
        e = {k: (sorted(v) if isinstance(v, set) else v) for k, v in ent.items()}
        for k in ('short_def', 'mechanic_def'):
            if not e[k]:
                e[k] = None
        if not e['aliases']:
            e.pop('aliases')
        if not e['asr_variants']:
            e.pop('asr_variants')
        if not e['related_terms']:
            e.pop('related_terms')
        if not e['sources']:
            e.pop('sources')
        else:
            e['sources'] = sorted(e['sources'])
        out_entries.append(e)
    out_entries.sort(key=lambda e: (e['type'], e['term']))

    from collections import Counter
    tc = Counter(e['type'] for e in out_entries)
    doc = {
        'name': 'shenqi_glossary',
        'schema_version': 'glossary-1.0',
        'generated_by': 'build_glossary.py',
        'sources': ['qq_cards/glossary.jsonl', 'kb_trial/entity_index.json',
                    'entity_corrector.py CORRECTION_RULES'],
        'entry_count': len(out_entries),
        'type_counts': dict(tc),
        'usage': ('RAG 同义词扩展/消歧清单: term 为官方或社区正词, aliases 为'
                  '社区黑话与英文别名, asr_variants 为转写讹写(仅本语料有效); '
                  '同一 alias 可能命中多个 term, 检索端按并列处理。'),
        'entries': out_entries,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n',
                   encoding='utf-8')
    print('wrote glossary.json:', len(out_entries), 'entries')
    print('type counts:', dict(tc))


if __name__ == '__main__':
    main()
