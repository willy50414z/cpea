"""Grounded business choices; identifiers remain in the server-side draft."""
from __future__ import annotations

import re

from cpea.application.ports.term_mappings import normalize_term


MAX_BUSINESS_OPTIONS = 3

RESOLUTION_PROMPT = '''你負責為已通過查詢結構檢查的問題整理業務語意選項。僅回覆 JSON Schema，不輸出 SQL、推理或額外文字。
伺服器已列出需確認的完整詞彙 required_terms。每個詞彙恰好一筆 clarifications，term 必須逐字等於提供的詞彙；不要增刪修飾詞、聚合或條件。不可更改查詢子句、來源或已明確指定的欄位。
先核對整題與契約 grain；若來源無法保留原始統計對象或所有條件，source_compatible=false，不以相似欄位或人工確認放行。特別是訂單總件數不能換成商品明細件數或門市月銷量。
options 只能來自同一契約及該詞彙 eligible_columns，只保留相同業務概念、型別、單位與粒度的候選。成本不能換成毛利或營收，城市不能換成會員居住地；公式提及某概念不代表欄位就是該概念。same_concept、grain_compatible 只有符合時才為 true。
evidence_quote 逐字引用該欄位 description 支持業務含義的片段；可有不同字面但同義的表達，不要求原文詞彙逐字出現在描述中。label 用簡短繁體中文表達必要業務差異，最多 60 字，不含資料庫識別碼、SQL、公式或技術資訊。
一至三個相關選項，不湊數；有唯一相關候選也必須提供，供伺服器驗證後直接採用。多個欄位只是相同詞義重複時不要製造假歧義。超過三個可區分的相關含義，needs_refinement=true，不任取前三個；確實無相關候選才 options=[]。不要因主映射漏給選項或原文不是逐字別名，就要求使用者重寫清楚的問題。'''


def requires_resolution(mapping, term, catalog, view):
    """Omitted or malformed model choices are a system task, not user ambiguity."""
    proposals = [item for item in getattr(mapping, 'clarifications', [])
                 if normalize_term(item.term) == normalize_term(term)]
    if len(proposals) != 1:
        return True
    proposal = proposals[0]
    if proposal.needs_refinement:
        return False
    if semantic_choices(mapping, term, catalog, view):
        return False
    return any(option.same_concept and option.grain_compatible for option in proposal.options)


def incompatible_term(mapping, term):
    """Explicitly unrelated choices cannot establish a viable source."""
    proposals = [item for item in getattr(mapping, 'clarifications', [])
                 if normalize_term(item.term) == normalize_term(term)]
    if len(proposals) != 1:
        return False
    proposal = proposals[0]
    if not proposal.options:
        return not proposal.needs_refinement
    return all(not option.same_concept or not option.grain_compatible for option in proposal.options)


def business_label(label, catalog):
    """Reject technical labels rather than attempting to redact them in place."""
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 60:
        return None
    label = label.strip()
    if any(char in label for char in '\n\r`<>'):
        return None
    identifiers = {view.name for view in catalog.views()}
    identifiers.update(column for view in catalog.views() for column in catalog.columns(view.name)
                       if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', column))
    if any(re.search(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])',
                     label, re.IGNORECASE) for name in identifiers):
        return None
    # A qualified identifier can refer to a source outside this catalogue too.
    if re.search(r'[A-Za-z_]\w*\.[A-Za-z_]\w*|[A-Za-z]\w*_[A-Za-z_]\w*', label):
        return None
    if re.search(r'\b(?:SELECT|FROM|JOIN|WHERE|GROUP\s+BY|ORDER\s+BY)\b|\b(?:SUM|MAX|MIN|AVG|COUNT)\s*\(',
                 label, re.IGNORECASE):
        return None
    return label


def semantic_choices(mapping, term, catalog, view):
    """Require explicit semantic proposals with verbatim contract evidence.

    Semantic relevance and grain are assessed by the requirement mapper, not
    inferred from shared characters or the fact that MAX accepts a column.
    Missing evidence never falls back to every column in a source.
    """
    proposals = [item for item in getattr(mapping, 'clarifications', [])
                 if normalize_term(item.term) == normalize_term(term)]
    if len(proposals) != 1 or proposals[0].needs_refinement:
        return []
    choices = []
    for option in proposals[0].options:
        if (not option.same_concept or not option.grain_compatible
                or option.column not in catalog.columns(view)):
            continue
        spec = catalog.field_contract(view, option.column)
        evidence = str(spec.get('description', ''))
        if not option.evidence_quote.strip() or option.evidence_quote not in evidence:
            continue
        label = business_label(option.label, catalog)
        if label is None:
            continue
        choices.append((option.column, label))
    # Repeated labels hide distinctions; repeated columns are not alternatives.
    if (len({c for c, _ in choices}) != len(choices)
            or len({label for _, label in choices}) != len(choices)):
        return []
    return choices
