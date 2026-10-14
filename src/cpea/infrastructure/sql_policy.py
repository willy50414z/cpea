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


def validate_generated_sql(sql: str, allowed_views: set[str]) -> None:
    """Reject unsafe SQL without modifying the compiled statement."""
    # Ignore escaped literals and quoted column names when inspecting syntax.
    sql = re.sub(r"N?'(?:''|[^'])*'|\[(?:\]\]|[^\]])*\]", 'identifier', sql).strip()
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
    if tail and not re.match(r'^(where|group\s+by|order\s+by)\b', tail, re.IGNORECASE):
        raise SQLPolicyError('SQL 包含不允許的資料來源語法')
    references = {match.lower() for match in _VIEW_PATTERN.findall(sql)}
    unknown = references - {view.lower() for view in allowed_views}
    if unknown:
        raise SQLPolicyError(f"SQL 引用了未驗證的資料來源：{', '.join(sorted(unknown))}")
    if not references:
        raise SQLPolicyError("SQL 必須查詢已驗證的 view")
