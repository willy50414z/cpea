"""Conservative, auditable evidence checks over Unicode character intervals."""
from __future__ import annotations

import re
from cpea.application.ports.term_mappings import normalize_term, view_fingerprint
from cpea.infrastructure.retrieval.schema import explicit_column_references

CLAUSES = ('fields', 'criteria', 'group', 'order', 'having')
# Only query grammar, never business qualifiers. Peel at uncovered segment edges.
GRAMMAR = ('請問', '請', '再', '從', '查詢', '查', '列出', '顯示', '提供', '依', '按照', '按',
           '計算', '分組', '排序', '的', '與', '及', '和', '以及', '各', '做', '只保留', '只顯示',
           '整理報表時照', '整理報表時', '限定', '想按', '想按照', '想依', '想查詢')
PUNCTUATION = ' \t\r\n，。；、：:;,.!?！？()（）「」\"\'`'
AGGREGATIONS = {'sum': ('合計', '總和', '加總', 'SUM'), 'avg': ('平均', 'AVG'),
                'min': ('單列最小值', '單列最低值', '最小值', '最低值', '最小', '最低', 'MIN'),
                'max': ('單列最大值', '單列最高值', '最大值', '最高值', '最大', '最高', 'MAX'),
                'count': ('計數', '筆數', 'COUNT'), 'count_distinct': ('不重複筆數', '去重後')}
OPERATORS = {'=': ('等於', '為', '='), '>': ('大於', '超過', '>'), '<': ('小於', '低於', '<'),
             '>=': ('至少', '以上', '>='), '<=': ('至多', '以下', '<='),
             '!=': ('不等於', '!='), '<>': ('不等於', '<>'), 'LIKE': ('包含', 'LIKE'), 'IN': ('IN', '屬於')}
NEGATION = re.compile(r'不含|不包含|不是|非|未包含|僅限|不等於|不代表|並非')


def description_supports(term, description, quote=None):
    """A separate negative clause must not negate an explicit positive name.

    The COMPLETE request term is still required. A qualifier absent from the
    contract, or a name mentioned only negatively, never gains trust here.
    """
    if quote is not None and (quote not in description or term not in quote):
        return False
    return any(term in clause and not NEGATION.search(clause)
               for clause in re.split(r'[，,。；;\n]', description))


def _peel(text, start, end):
    connectors = {'的', '與', '及', '和', '以及', '各'}
    edge_grammar = [t for t in GRAMMAR if t not in connectors]
    while start < end:
        if text[start] in PUNCTUATION:
            start += 1
            continue
        token = next((t for t in sorted(edge_grammar, key=len, reverse=True) if text.startswith(t, start)), None)
        if token:
            start += len(token)
        else:
            break
    while start < end:
        if text[end - 1] in PUNCTUATION:
            end -= 1
            continue
        token = next((t for t in sorted(edge_grammar, key=len, reverse=True) if text[start:end].endswith(t)), None)
        if token:
            end -= len(token)
        else:
            break
    return start, end


def _business_span(request, start, end, item, clause):
    """Remove only syntax grounded in this use's typed operation."""
    fragment = request[start:end]
    suffix = None
    if clause in ('criteria', 'having') and not isinstance(item.value, list):
        operators = OPERATORS.get(item.operator, ())
        if operators:
            pattern = '|'.join(re.escape(t) for t in sorted(operators, key=len, reverse=True))
            suffix = re.search(r'\s*(?:' + pattern + r')\s*' + re.escape(str(item.value)) + r'\s*$', fragment)
    if suffix and suffix.start() > 0:
        end = start + suffix.start()
        fragment = request[start:end]
    suffix = None
    if getattr(item, 'aggregation', None):
        tokens = AGGREGATIONS.get(item.aggregation, ())
        pattern = '|'.join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))
        suffix = re.search(r'\s*的?\s*(?:' + pattern + r')\s*$', fragment)
    if suffix and suffix.start() > 0:
        end = start + suffix.start()
    if clause in ('group', 'order'):
        start, end = _peel(request, start, end)
    while start < end and request[start].isspace():
        start += 1
    while start < end and request[end - 1].isspace():
        end -= 1
    return start, end


def assess(request, mapping, catalog, view, snapshot, *, all_uses=None):
    """Return uses requiring confirmation, trusted records, and hard errors.

    Cover fields and typed syntax first, then peel grammar from remaining edges.
    Uncovered text touching a business span expands that span, so shortened
    evidence cannot discard qualifiers, even if the model puts them in ignored.
    """
    covered = [False] * len(request)
    uses, errors, reused = [], [], []
    fingerprint = view_fingerprint(catalog, view)
    active = snapshot.active()
    required = explicit_column_references(request, catalog)
    mapped = {item.column for clause in CLAUSES for item in getattr(mapping, clause, [])}
    for column in sorted(required):
        if column not in catalog.columns(view):
            errors.append('explicit column is outside selected View: ' + column)
        elif column not in mapped:
            errors.append('explicit column is not mapped: ' + column)
    explicit = {(t.clause, t.index): t for t in getattr(mapping, 'terms', [])}
    if len(explicit) != len(getattr(mapping, 'terms', [])):
        errors.append('duplicate term use')
    def cover(start, end):
        for i in range(start, end):
            covered[i] = True
    def occurrences(text):
        return [(m.start(), m.end()) for m in re.finditer(re.escape(text), request)] if text else []
    for span in getattr(mapping, 'syntax_spans', []):
        a, b = span.start, span.end
        if not 0 <= a < b <= len(request):
            errors.append('syntax span outside request')
            continue
        fragment = request[a:b]
        items = getattr(mapping, span.clause, []) if span.clause != 'table' else [mapping.table]
        if span.index >= len(items) or items[span.index] is None:
            errors.append('unknown syntax use')
            continue
        item = items[span.index]
        if span.kind == 'source':
            valid = span.clause == 'table' and fragment == view
        elif span.kind == 'aggregation':
            valid = fragment in AGGREGATIONS.get(getattr(item, 'aggregation', None), ())
        elif span.kind == 'operator':
            valid = fragment in OPERATORS.get(getattr(item, 'operator', None), ())
        else:
            values = getattr(item, 'value', [])
            values = values if isinstance(values, list) else [values]
            valid = fragment in [str(v) for v in values]
        if not valid:
            errors.append('syntax span does not match typed mapping')
        else:
            cover(a, b)
    for start, end in occurrences(view):
        cover(start, end)
    for clause in CLAUSES:
        for index, item in enumerate(getattr(mapping, clause, [])):
            referenced = explicit_column_references(item.text, catalog) & required
            if referenced - {item.column}:
                errors.append('explicit column cannot map to another column: ' + item.text)
            evidence = explicit.get((clause, index))
            values = getattr(item, 'value', [])
            values = values if isinstance(values, list) else [values]
            for value in values:
                if value is not None:
                    for a, b in occurrences(str(value)):
                        cover(a, b)
            for token in AGGREGATIONS.get(getattr(item, 'aggregation', None), ()):
                for a, b in occurrences(token):
                    cover(a, b)
            for token in OPERATORS.get(getattr(item, 'operator', None), ()):
                for a, b in occurrences(token):
                    cover(a, b)
            if clause == 'order':
                for token in (('遞減', '降冪', '由大到小', '由高到低') if item.direction == 'desc' else ('遞增', '升冪', '由小到大', '由低到高')):
                    for a, b in occurrences(token):
                        cover(a, b)
            if evidence:
                a, b = evidence.start, evidence.end
                if not (0 <= a < b <= len(request)) or request[a:b] != evidence.term:
                    errors.append('term span does not match original request')
                    continue
                candidates = list(dict.fromkeys([item.column, *evidence.candidates]))
            else:
                spec = catalog.field_contract(view, item.column)
                names = [item.column, *spec.get('aliases', [])]
                spans = occurrences(item.text)
                if not spans:
                    # Existing clause mapper can emit identifiers for selected
                    # filter/group columns. Resolve to their grounded aliases.
                    alias = next((n for n in names if n in request), None)
                    if alias:
                        spans = occurrences(alias)
                    elif clause == 'fields' and item.column in {c.column for c in mapping.criteria} | {g.column for g in mapping.group}:
                        continue
                    else:
                        errors.append('mapped text absent from request')
                        continue
                a, b = spans[0]
                candidates = [item.column]
                if clause in ('criteria', 'having') and request[a:b] in [str(v) for v in values]:
                    continue
                # Strip query wrappers only when what remains is an exact
                # approved name. Never remove grammar inside a business term.
                x, y = _peel(request, a, b)
                for name in sorted(names, key=len, reverse=True):
                    if request[x:y] == name:
                        a, b = x, y
                        break
                    if name in request[a:b]:
                        pos = request.find(name, a, b)
                        before, after = request[a:pos], request[pos + len(name):b]
                        syntax = [t for t in GRAMMAR] + list(AGGREGATIONS.get(getattr(item, 'aggregation', None), ()))
                        if clause == 'order':
                            syntax += ['由高到低', '由大到小', '降冪', '遞減'] if item.direction == 'desc' else ['由低到高', '由小到大', '升冪', '遞增']
                        pattern = '(?:' + '|'.join(re.escape(t) for t in sorted(syntax, key=len, reverse=True)) + '|[\\s，。])*'
                        if re.fullmatch(pattern, before) and re.fullmatch(pattern, after):
                            a, b = pos, pos + len(name)
                            break
            a, b = _business_span(request, a, b, item, clause)
            if a >= b:
                continue
            if any(c not in catalog.columns(view) for c in candidates):
                errors.append('candidate outside selected View')
                continue
            uses.append({'clause': clause, 'index': index, 'start': a, 'end': b,
                         'term': request[a:b], 'column': item.column, 'candidates': candidates,
                         'evidence_quote': evidence.evidence_quote if evidence else None})
            for x, y in occurrences(request[a:b]):
                cover(x, y)
                if item.column in {g.column for g in mapping.group} and x > 0 and request[x - 1] == '各':
                    cover(x - 1, x)
    if any(key[0] not in CLAUSES or key[1] >= len(getattr(mapping, key[0], [])) for key in explicit):
        errors.append('unknown term use')
    # Temporal scope can only cover its own explicit, approved statement.
    definition = next(d for d in catalog.views() if d.name == view)
    if definition.policy.get('temporal_scope') == 'current_snapshot':
        for a, b in occurrences('目前'):
            cover(a, b)
    for match in re.finditer(r'[^，。；、\n]+', request):
        a, b = _peel(request, match.start(), match.end())
        gaps = []
        i = a
        while i < b:
            if covered[i]:
                i += 1
                continue
            start = i
            while i < b and not covered[i]:
                i += 1
            x, y = _peel(request, start, i)
            if mapping.group and mapping.having and request[x:y] == '的群組':
                continue
            if (request[start:i].strip(PUNCTUATION) in {'的', '與', '及', '和', '以及', '且'}
                    and start > 0 and i < len(request) and covered[start - 1] and covered[i]):
                continue
            if x < y:
                gaps.append((x, y))
        for x, y in gaps:
            adjacent = [u for u in uses if u['end'] == x or u['start'] == y]
            if adjacent:
                for use in adjacent:
                    use['start'], use['end'] = min(x, use['start']), max(y, use['end'])
                    use['term'] = request[use['start']:use['end']]
            else:
                errors.append('uncovered request text: ' + request[x:y])
    if all_uses is not None:
        all_uses.extend(uses)
    uncertain = []
    for use in uses:
        term, column = use['term'], use['column']
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+', term) and term != column:
            errors.append('explicit identifier cannot map to another column: ' + term)
            continue
        spec = catalog.field_contract(view, column)
        description = str(spec.get('description', ''))
        names = [column, *spec.get('aliases', [])]
        record = active.get((normalize_term(term), view))
        if record and record.view_contract_fingerprint == fingerprint and record.column == column:
            reused.append(record)
            continue
        # Explicit identifiers and complete approved names can pass; quoted
        # description evidence must affirm the COMPLETE term in its own clause.
        quote = use['evidence_quote']
        negation = NEGATION.search(description)
        if normalize_term(term) == normalize_term(column) or (normalize_term(term) in {normalize_term(n) for n in names} and not negation):
            continue
        if description_supports(term, description, quote):
            continue
        uncertain.append(use)
    return uncertain, list({m.id: m for m in reused}.values()), errors
