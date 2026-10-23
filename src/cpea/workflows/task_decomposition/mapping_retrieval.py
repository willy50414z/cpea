"""Reuse schema ranking without imposing single-View column intersection."""
from __future__ import annotations

import math
import re

from cpea.infrastructure.retrieval.schema import SchemaRetriever, explicit_column_references, select_with_ties
from cpea.workflows.task_decomposition.mapping_models import ExcludedView, RetrievedView, ViewSelectionTrace

_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def select_candidate_views(request, catalog, settings, *, retriever=None, limit=None):
    limit = max(5, settings.rerank_top_k) if limit is None else limit
    if type(limit) is not int or limit < 1:
        raise ValueError('candidate view limit must be positive')
    views = catalog.views()
    definitions = {view.name: view for view in views}
    columns = explicit_column_references(request, catalog)
    # The base retriever admits only Views containing ALL explicit columns.
    # Remove those tokens only for ranking, then pin their true owners below.
    search_query = _IDENTIFIER.sub(lambda match: ' ' if match.group() in columns else match.group(), request)
    engine = retriever if retriever is not None else SchemaRetriever(settings, catalog)
    result = (engine.retrieve(search_query, limit=limit) if isinstance(engine, SchemaRetriever)
              else engine.retrieve(search_query))
    order = {view.name: index for index, view in enumerate(views)}
    scores, unique = {}, {}
    for candidate in result.candidates:
        name = candidate.document.metadata.get('document_id')
        score = candidate.retrieval_score if candidate.reranker_score is None else candidate.reranker_score
        if (name not in definitions or not math.isfinite(candidate.retrieval_score)
                or not math.isfinite(score)):
            raise ValueError('retrieval returned an unadmitted View or invalid score')
        if name not in scores or score > scores[name]:
            unique[name], scores[name] = candidate, score
    ranked = sorted(unique.values(), key=lambda c: (-scores[c.document.metadata['document_id']],
                                                   order[c.document.metadata['document_id']]))
    kept = {c.document.metadata['document_id'] for c in select_with_ties(ranked, limit)}
    reasons = {name: ['ranked'] for name in kept}
    literals = [m.span() for m in re.finditer(r"'(?:''|[^'])*'", request)]
    # Match the existing explicit-column recognizer's literal exclusions.
    for match in re.finditer(
        r'''(?:>=|<=|!=|<>|=|>|<|\bLIKE\b)\s*("[^"]*"|'(?:''|[^'])*'|[^\s，。；、且]+)'''
        r'|\bIN\s*\(([^)]*)\)', request, re.IGNORECASE,
    ):
        literals.append(match.span(1 if match.group(1) is not None else 2))

    def outside_literals(start, end):
        return not any(a <= start and end <= b for a, b in literals)

    for view in views:
        if any(outside_literals(m.start(), m.end()) for m in re.finditer(
                rf'(?<![A-Za-z0-9_.]){re.escape(view.name)}(?![A-Za-z0-9_])', request)):
            reasons.setdefault(view.name, []).append('explicit_view')
    for match in _IDENTIFIER.finditer(request):
        column = match.group()
        if column not in columns or not outside_literals(match.start(), match.end()):
            continue
        qualified = [view.name for view in views if column in view.policy['columns']
                     and re.search(rf'(?<![A-Za-z0-9_.]){re.escape(view.name)}\.$', request[:match.start()])]
        owners = qualified or [view.name for view in views if column in view.policy['columns']]
        for name in owners:
            reason = 'explicit_column:' + column
            if reason not in reasons.setdefault(name, []):
                reasons[name].append(reason)
    return ViewSelectionTrace(status='completed', query=search_query, limit=limit,
        candidates=[RetrievedView(view=view.name,
            retrieval_score=unique[view.name].retrieval_score if view.name in unique else None,
            reranker_score=unique[view.name].reranker_score if view.name in unique else None,
            reasons=reasons[view.name]) for view in views if view.name in reasons],
        excluded=[ExcludedView(view=view.name) for view in views if view.name not in reasons],
        retrieval_latency_ms=result.retrieval_latency_ms, reranker_latency_ms=result.reranker_latency_ms)
