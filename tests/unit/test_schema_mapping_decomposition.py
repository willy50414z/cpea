import json

import pytest

from tests.decomposition_support import FakeLLM, catalog_at, settings
from tests.schema_mapping_support import REQUEST, StagedLLM, StaticViewRetriever, extraction, mapped_draft, mapping, review, span


def setup(tmp_path, *, monthly=False, payloads=None, token_counter=None, observer=None, retriever=None, view_limit=None):
    from cpea.application.services.schema_mapping_decomposition import SchemaMappingDecompositionService
    catalog = catalog_at(tmp_path)
    responses = (payloads if payloads is not None else
                 [extraction(), *[mapping(v.name, monthly=monthly) for v in catalog.views()],
                  review(monthly=monthly), mapped_draft(monthly=monthly)])
    llm = StagedLLM(responses)
    service = SchemaMappingDecompositionService(llm, catalog, settings=settings(),
        token_counter=token_counter, observer=observer, view_limit=view_limit,
        retriever=retriever if retriever is not None else StaticViewRetriever([v.name for v in catalog.views()]))
    return service, llm, catalog


@pytest.mark.parametrize('monthly', [False, True])
def test_independent_service_maps_every_view_then_reviews_and_prepares_requests(tmp_path, monthly):
    from cpea.application.models.decomposition import DecompositionResponse
    events = []
    service, llm, catalog = setup(tmp_path, monthly=monthly, observer=events.append)
    result = service.plan(REQUEST)
    assert isinstance(result, DecompositionResponse)
    assert result.status == 'ready' and len(result.prepared_requests) == 2
    assert result.prepared_requests[1].view == ('demo.monthly' if monthly else 'demo.sales')
    assert len(llm.calls) == len(catalog.views()) + 3
    assert [event['stage'] for event in events] == ['extract', *['map_view'] * 4, 'review', 'plan_draft']
    assert all(event['usage']['input_tokens'] == 10 for event in events)
    assert all(s.status == 'completed' for s in result.trace.stages)
    assert result.trace.extraction.requirements[2].span.text == '目前庫存件數'
    assert len(result.trace.mappings) == 4 and result.trace.review.status == 'ready'
    assert result.trace.bindings[-1].requirement_id == 'period'
    assert result.contract_fingerprint == catalog.fingerprint and result.context_tokens > 0
    for index, view in enumerate(catalog.views(), 1):
        payload = json.loads(llm.calls[index][1].content)
        assert payload['request'] == REQUEST and payload['view'] == {'view': view.name, **view.policy}
    review_payload = json.loads(llm.calls[-2][1].content)
    assert review_payload['request'] == REQUEST and len(review_payload['mappings']) == 4
    draft_payload = json.loads(llm.calls[-1][1].content)
    assert draft_payload['review']['selected_candidate_ids'] == review(monthly=monthly)['selected_candidate_ids']
    assert {v['view'] for v in draft_payload['views']} == {'demo.stock', 'demo.monthly' if monthly else 'demo.sales'}


@pytest.mark.parametrize('index', range(7))
@pytest.mark.parametrize('failure', ['provider', 'parse'])
def test_any_stage_failure_stops_without_retry_and_keeps_partial_trace(tmp_path, index, failure):
    catalog = catalog_at(tmp_path)
    payloads = [extraction(), *[mapping(v.name) for v in catalog.views()], review(), mapped_draft()]
    payloads[index] = RuntimeError('429 private-secret endpoint') if failure == 'provider' else {'bogus': True}
    events = []
    service, llm, _ = setup(tmp_path, payloads=payloads, observer=events.append)
    result = service.plan(REQUEST)
    assert result.status == 'error' and not result.prepared_requests
    assert result.code == ('provider_error' if failure == 'provider' else 'invalid_model_response')
    assert len(llm.calls) == index + 1 and len(events) == index + 1
    assert result.trace.stages[-1].status == 'error'
    assert len(result.trace.mappings) == min(max(index - 1, 0), 4)
    assert (result.trace.extraction is not None) == (index > 0)
    assert 'private-secret' not in result.model_dump_json()


class StageCounter:
    name = 'stage-counter'

    def __init__(self, fail_index):
        self.index, self.fail_index = 0, fail_index

    def count_messages(self, messages):
        self.index += 1
        return 100000 if self.index == self.fail_index + 1 else 11


@pytest.mark.parametrize('index', range(7))
def test_context_budget_is_checked_before_each_call_without_truncation(tmp_path, index):
    service, llm, _ = setup(tmp_path, token_counter=StageCounter(index))
    result = service.plan(REQUEST)
    assert result.code == 'context_budget_exceeded' and not result.prepared_requests
    assert len(llm.calls) == index and result.context_tokens == 100000
    assert result.trace.stages[-1].code == 'context_budget_exceeded'


@pytest.mark.parametrize('index', range(7))
def test_counter_failure_is_sanitized_with_failed_stage_and_partial_trace(tmp_path, index):
    class FailingCounter(StageCounter):
        def count_messages(self, messages):
            if self.index == self.fail_index:
                raise RuntimeError('private-secret endpoint unavailable')
            return super().count_messages(messages)

    service, llm, _ = setup(tmp_path, token_counter=FailingCounter(index))
    result = service.plan(REQUEST)
    assert result.status == 'error' and result.code == 'token_count_error'
    assert len(llm.calls) == index and not result.prepared_requests
    assert len(result.trace.stages) == index + 1 and result.trace.stages[-1].status == 'error'
    assert (result.trace.extraction is not None) == (index > 0)
    assert 'private-secret' not in result.model_dump_json()


@pytest.mark.parametrize('mutation,code,calls', [
    ('extraction_gap', 'invalid_requirement_extraction', 1),
    ('mapping_gap', 'invalid_view_mapping', 2),
    ('review_omission', 'invalid_mapping_review', 6),
    ('draft_expansion', 'invalid_plan', 7),
])
def test_invalid_stage_outputs_never_dispatch(tmp_path, mutation, code, calls):
    catalog = catalog_at(tmp_path)
    values = [extraction(), *[mapping(v.name) for v in catalog.views()], review(), mapped_draft()]
    if mutation == 'extraction_gap': values[0]['requirements'].pop(2)
    if mutation == 'mapping_gap': values[1]['results'].pop()
    if mutation == 'review_omission': values[-2]['missing_requirements'] = [span('暫不計算採購量')]
    if mutation == 'draft_expansion': values[-1]['draft']['tasks'][0]['required_columns'].append('snapshot_date')
    service, llm, _ = setup(tmp_path, payloads=values)
    result = service.plan(REQUEST)
    assert result.code == code and not result.prepared_requests and result.validation_errors
    assert len(llm.calls) == calls
    if mutation == 'review_omission': assert result.trace.review.missing_requirements[0].text == '暫不計算採購量'


def test_nonready_review_preserves_reason_and_skips_draft(tmp_path):
    catalog = catalog_at(tmp_path)
    checked = review()
    checked.update(status='needs_clarification', reasons=['需要確認目前的盤點時間口徑。'])
    values = [extraction(), *[mapping(v.name) for v in catalog.views()], checked]
    service, llm, _ = setup(tmp_path, payloads=values)
    result = service.plan(REQUEST)
    assert result.status == 'needs_clarification' and not result.prepared_requests
    assert len(llm.calls) == 6 and result.trace.review.reasons


def test_invocations_are_stateless_and_legacy_planner_still_calls_once(tmp_path):
    service, llm, catalog = setup(tmp_path)
    llm.payloads.extend(llm.payloads.copy())
    first, second = service.plan(REQUEST), service.plan(REQUEST)
    assert first.status == second.status == 'ready'
    assert len(first.trace.stages) == len(second.trace.stages) == 7
    assert first.trace is not second.trace
    from cpea.application.services.task_decomposition import TaskDecompositionService
    legacy = FakeLLM()
    assert TaskDecompositionService(legacy, catalog, settings=settings()).plan(REQUEST).status == 'ready'
    assert len(legacy.calls) == 1


@pytest.mark.parametrize('input_request', ['', ' ', None, 'x' * 4001])
def test_invalid_request_makes_no_model_calls(tmp_path, input_request):
    service, llm, _ = setup(tmp_path)
    result = service.plan(input_request)
    assert result.code == 'invalid_request' and not llm.calls


def test_empty_catalog_is_unsupported_without_model_call(tmp_path):
    service, llm, _ = setup(tmp_path)
    service.workflow.catalog = type('EmptyCatalog', (), {'fingerprint': 'empty', 'views': lambda self: []})()
    result = service.plan(REQUEST)
    assert result.status == 'unsupported' and result.code == 'empty_catalog' and not llm.calls


def test_unmapped_required_data_stops_after_all_view_comparisons(tmp_path):
    catalog = catalog_at(tmp_path)
    values = [extraction(), *[mapping(v.name) for v in catalog.views()]]
    for value in values[1:]:
        for row in value['results']:
            if row['requirement_id'] == 'sales': row.update(status='unmatched', candidates=[])
    service, llm, _ = setup(tmp_path, payloads=values)
    result = service.plan(REQUEST)
    assert result.status == 'unsupported' and result.code == 'unmapped_required_requirement'
    assert len(llm.calls) == 5 and len(result.trace.mappings) == 4 and not result.prepared_requests


def test_nonready_draft_keeps_trace_without_preparing_requests(tmp_path):
    catalog = catalog_at(tmp_path)
    values = [extraction(), *[mapping(v.name) for v in catalog.views()], review(),
              {'draft': {'status': 'needs_clarification', 'clarifications': ['需確認缺值政策。']}, 'bindings': []}]
    service, llm, _ = setup(tmp_path, payloads=values)
    result = service.plan(REQUEST)
    assert result.status == 'needs_clarification' and result.draft.clarifications
    assert result.trace.review.status == 'ready' and len(llm.calls) == 7 and not result.prepared_requests


def test_front_filter_reduces_model_calls_and_preserves_exclusion_trace(tmp_path):
    catalog = catalog_at(tmp_path)
    candidates = [v for v in catalog.views() if v.name in {'demo.stock', 'demo.sales'}]
    values = [extraction(), *[mapping(v.name) for v in candidates], review(), mapped_draft()]
    retriever = StaticViewRetriever([v.name for v in candidates])
    service, llm, _ = setup(tmp_path, payloads=values, retriever=retriever)
    result = service.plan(REQUEST)
    assert result.status == 'ready' and len(llm.calls) == 5
    assert [m.view for m in result.trace.mappings] == ['demo.sales', 'demo.stock']
    assert {v.view for v in result.trace.retrieval.excluded} == {'demo.kpi', 'demo.monthly'}
    assert result.trace.retrieval.status == 'completed' and retriever.calls == [REQUEST]
    assert len(json.loads(llm.calls[-2][1].content)['mappings']) == 2


@pytest.mark.parametrize('names,error,code', [
    ([], None, 'empty_retrieval'),
    ([], RuntimeError('private-secret embedding endpoint'), 'retrieval_error'),
    (['demo.secret'], None, 'retrieval_error'),
])
def test_retrieval_failure_is_clean_before_any_model_call(tmp_path, names, error, code):
    retriever = StaticViewRetriever(names, error=error)
    service, llm, _ = setup(tmp_path, retriever=retriever)
    result = service.plan(REQUEST)
    assert result.code == code and not result.prepared_requests and not llm.calls
    assert len(retriever.calls) == 1
    assert result.trace.retrieval.status == ('completed' if code == 'empty_retrieval' else 'error')
    assert 'private-secret' not in result.model_dump_json()
