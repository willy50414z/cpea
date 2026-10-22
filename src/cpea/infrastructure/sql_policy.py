"""Final passive safety checks for compiled SQL."""

from __future__ import annotations

import re


class SQLPolicyError(ValueError):
    pass


_VIEW_PATTERN = re.compile(r"\b(?:from|join)\s+([\w.]+)", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|merge|exec(?:ute)?|create|grant|revoke|into|union|intersect|except|join|apply|openrowset|opendatasource|openquery)\b",
    re.IGNORECASE,
)


def validate_generated_sql(sql: str, allowed_views: set[str], *, dialect: str = 'mssql') -> None:
    """Reject unsafe SQL without modifying the compiled statement."""
    # Keep quoted source names for the allowlist while hiding their contents
    # from keyword checks. Token names must not collide with raw SQL names.
    identifiers = {}
    prefix = '__cpea_quoted_'
    while prefix in sql:
        prefix += '_'
    def mask(match):
        value = match.group()
        if value.startswith(('"', '[')):
            key = f'{prefix}{len(identifiers)}'
            identifiers[key] = (value[1:-1].replace('""', '"') if value[0] == '"'
                                else value[1:-1].replace(']]', ']'))
            return key
        return 'literal'
    sql = re.sub(r'''N?'(?:''|[^'])*'|\[(?:\]\]|[^\]])*\]|"(?:""|[^"])*"''', mask, sql).strip()
    if not sql:
        raise SQLPolicyError("SQL 不可為空")
    if not re.match(r"^select\b", sql, re.IGNORECASE):
        raise SQLPolicyError("只允許產出 SELECT 查詢")
    if _FORBIDDEN.search(sql):
        raise SQLPolicyError("SQL 包含不允許的資料異動或管理指令")
    if ';' in sql.rstrip(';') or '--' in sql or '/*' in sql:
        raise SQLPolicyError('SQL 必須為單一查詢')
    matches = list(_VIEW_PATTERN.finditer(sql))
    if len(matches) != 1 or len(re.findall(r'\bselect\b', sql, re.IGNORECASE)) != 1:
        raise SQLPolicyError('SQL 必須查詢單一核准 View')
    tail = sql[matches[0].end():].strip().rstrip(';').strip()
    if tail and not re.match(r'^(where|group\s+by|having|order\s+by|limit)\b', tail, re.IGNORECASE):
        raise SQLPolicyError('SQL 包含不允許的資料來源語法')
    references = {tuple(identifiers.get(part, part.lower()) for part in match.split('.'))
                  for match in _VIEW_PATTERN.findall(sql)}
    if dialect == 'mssql':
        references = {tuple(part.lower() for part in view) for view in references}
    allowed = {tuple((view.lower() if dialect == 'mssql' else view).split('.')) for view in allowed_views}
    unknown = references - allowed
    if unknown:
        raise SQLPolicyError(f"SQL 引用了未驗證的資料來源：{', '.join('.'.join(view) for view in sorted(unknown))}")
    if not references:
        raise SQLPolicyError("SQL 必須查詢已驗證的 view")
