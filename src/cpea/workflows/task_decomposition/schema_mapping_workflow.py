"""Independent, stateless evidence mapping; never generates or executes SQL."""
from __future__ import annotations

import json
from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage

from cpea.application.models.schema_mapping_decomposition import (
    MappingStage, MappingTrace, SchemaMappingDecompositionResponse)
from cpea.infrastructure.llm.context_budget import build_token_counter
from cpea.infrastructure.llm.factory import bind_response_schema
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.mapping import (
    DATA_KINDS, approved_uses, validate_extraction, validate_mapped_draft,
    validate_review, validate_view_mapping)
from cpea.workflows.task_decomposition.mapping_models import (
    MappedDraft, MappingReview, RequirementExtraction, ViewMapping, ViewSelectionTrace)
from cpea.workflows.task_decomposition.mapping_prompts import PROMPTS
from cpea.workflows.task_decomposition.mapping_retrieval import select_candidate_views
from cpea.workflows.task_decomposition.validation import prepare_requests


class _PlanningStop(Exception):
    def __init__(self, code, errors=None):
        self.code, self.errors = code, errors or []
        super().__init__(code)


class SchemaMappingDecompositionWorkflow:
    def __init__(self, llm, catalog, *, settings, token_counter=None, observer=None, retriever=None, view_limit=None):
        self.llm, self.catalog, self.settings = llm, catalog, settings
        self.token_counter = token_counter or build_token_counter(settings)
        self.observer = observer
        self.retriever, self.view_limit = retriever, view_limit

    def _result(self, trace, status, **kwargs):
        return SchemaMappingDecompositionResponse(
            status=status, trace=trace, contract_fingerprint=self.catalog.fingerprint,
            context_tokens=max((s.context_tokens for s in trace.stages), default=0),
            token_counter=self.token_counter.name, **kwargs)

    def _call(self, stage, payload, model, trace, *, view=None):
        context = {'stage': stage, 'request': trace.request, **payload,
                   'response_schema': model.model_json_schema()}
        messages = [SystemMessage(content=PROMPTS[stage]),
                    HumanMessage(content=json.dumps(context, ensure_ascii=False))]
        record = MappingStage(stage=stage, view=view)
        trace.stages.append(record)
        try:
            tokens = self.token_counter.count_messages([('system', messages[0].content), ('user', messages[1].content)])
        except Exception:
            record.status, record.code = 'error', 'token_count_error'
            raise _PlanningStop(record.code) from None
        record.context_tokens = tokens
        budget = self.settings.context_window - self.settings.output_token_reserve - self.settings.context_safety_tokens
        if tokens > budget:
            record.status, record.code = 'error', 'context_budget_exceeded'
            raise _PlanningStop(record.code)
        event = {'event': 'model_call', 'stage': stage, 'view': view, 'context_tokens': tokens,
                 'messages': [{'role': message.type, 'content': message.content} for message in messages]}
        started = perf_counter()
        try:
            llm = bind_response_schema(self.llm, model)
            if self.settings.llm_provider == 'azure' and hasattr(llm, 'bind'):
                llm = llm.bind(response_format={'type': 'json_object'})
            raw = llm.invoke(messages)
        except Exception as exc:
            event.update(error_type=type(exc).__name__, error=str(exc), elapsed_ms=(perf_counter() - started) * 1000)
            if self.observer:
                self.observer(event)
            record.status, record.code = 'error', 'provider_error'
            raise _PlanningStop(record.code) from None
        event.update(response=getattr(raw, 'content', raw), usage=getattr(raw, 'usage_metadata', None),
                     elapsed_ms=(perf_counter() - started) * 1000)
        if self.observer:
            self.observer(event)
        try:
            return parse_model(raw, model)
        except (ValueError, TypeError):
            record.status, record.code = 'error', 'invalid_model_response'
            raise _PlanningStop(record.code) from None

    @staticmethod
    def _check(errors, code, trace):
        if errors:
            trace.stages[-1].status, trace.stages[-1].code = 'error', code
            raise _PlanningStop(code, errors)

    def invoke(self, request):
        trace = MappingTrace(request=request if isinstance(request, str) else '')
        if not isinstance(request, str) or not request.strip() or len(request) > 4000:
            return self._result(trace, 'error', code='invalid_request')
        views = self.catalog.views()
        if not views:
            return self._result(trace, 'unsupported', code='empty_catalog')
        trace.retrieval = ViewSelectionTrace()
        try:
            trace.retrieval = select_candidate_views(request, self.catalog, self.settings,
                                                     retriever=self.retriever, limit=self.view_limit)
        except Exception:
            trace.retrieval.status, trace.retrieval.code = 'error', 'retrieval_error'
            return self._result(trace, 'error', code='retrieval_error')
        admitted = {candidate.view for candidate in trace.retrieval.candidates}
        views = [view for view in views if view.name in admitted]
        if not views:
            return self._result(trace, 'unsupported', code='empty_retrieval')
        draft = None
        try:
            extracted = self._call('extract', {}, RequirementExtraction, trace)
            trace.extraction = extracted
            self._check(validate_extraction(request, extracted), 'invalid_requirement_extraction', trace)
            for view in views:
                compared = self._call('map_view', {'extraction': extracted.model_dump(),
                    'view': {'view': view.name, **view.policy}}, ViewMapping, trace, view=view.name)
                trace.mappings.append(compared)
                self._check(validate_view_mapping(compared, extracted, view), 'invalid_view_mapping', trace)
            available = {result.requirement_id for mapping in trace.mappings for result in mapping.results
                         if result.candidates}
            missing = [r.id for r in extracted.requirements
                       if r.required and r.kind in DATA_KINDS and r.id not in available]
            if missing:
                return self._result(trace, 'unsupported', code='unmapped_required_requirement',
                                    validation_errors=[f'{rid}: no admitted candidate' for rid in missing])
            candidate_views = {m.view for m in trace.mappings if any(r.candidates for r in m.results)}
            reviewed = self._call('review', {'extraction': extracted.model_dump(),
                'mappings': [m.model_dump() for m in trace.mappings],
                'views': [{'view': v.name, **v.policy} for v in views if v.name in candidate_views]},
                MappingReview, trace)
            trace.review = reviewed
            self._check(validate_review(request, extracted, trace.mappings, reviewed, views),
                        'invalid_mapping_review', trace)
            if reviewed.status != 'ready':
                return self._result(trace, reviewed.status)
            selected_views = {view for view, _, _ in approved_uses(trace.mappings, reviewed)}
            mapped = self._call('plan_draft', {'extraction': extracted.model_dump(),
                'mappings': [m.model_dump() for m in trace.mappings], 'review': reviewed.model_dump(),
                'views': [{'view': v.name, **v.policy} for v in views if v.name in selected_views]}, MappedDraft, trace)
            draft, trace.bindings = mapped.draft, mapped.bindings
            if draft.status != 'ready':
                return self._result(trace, draft.status, draft=draft)
            self._check(validate_mapped_draft(extracted, trace.mappings, reviewed, mapped, self.catalog),
                        'invalid_plan', trace)
            try:
                prepared = prepare_requests(draft, self.catalog)
            except ValueError:
                self._check(['validated plan could not be prepared'], 'invalid_prepared_request', trace)
            return self._result(trace, 'ready', draft=draft, prepared_requests=prepared)
        except _PlanningStop as stopped:
            return self._result(trace, 'error', code=stopped.code, draft=draft, validation_errors=stopped.errors)
