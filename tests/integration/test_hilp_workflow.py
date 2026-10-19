import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from cpea.application.models.confirmation import ConfirmationError, ConfirmationRequest
from tests.hilp_support import QUESTION, VIEW, clarification_drafts, runtime_for, selection


@pytest.mark.parametrize('interface', ['sql', 'web'])
def test_view_choice_precedes_term_confirmation_without_early_compilation(tmp_path, monkeypatch, interface):
    from copy import deepcopy
    from dataclasses import replace
    from types import SimpleNamespace
    from langchain_core.documents import Document
    from cpea.application.models.query import ClarificationChoice
    from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult
    from cpea.interfaces.web.ui import SessionGate, single_question_updates
    from cpea.workflows.text_to_sql import sql_generation

    calls, compiled = [], []
    runtime = runtime_for(tmp_path, executor=lambda d, s: (calls.append(s) or (['value'], [[1]])))
    first = runtime.catalog.views()[0]
    other_view = 'demo_retail.v_other_summary'
    policy = deepcopy(first.policy)
    policy['view'] = other_view
    runtime.catalog._definitions.append(replace(first, name=other_view, summary='另一種業務摘要', policy=policy))
    workflow = runtime.generation_service().workflow
    candidates = [RetrievalCandidate(document=Document(page_content='摘要', metadata={
        'document_id': view, 'source': 'test.yaml', 'filename': 'test.yaml', 'chunk_id': view}),
        retrieval_score=1.0) for view in (VIEW, other_view)]
    workflow.retriever = SimpleNamespace(retrieve=lambda query: RetrievalResult(query=query,
        candidates=list(candidates), retrieval_latency_ms=0, reranker_latency_ms=0))
    original_invoke = runtime.llm.invoke
    original_compile = sql_generation.compile_single_view

    def invoke(messages):
        if '候選證據：' in messages[-1].content:
            return SimpleNamespace(content=json.dumps({'decision': 'clarify', 'question': '要查詢哪一種摘要？'}))
        value = original_invoke(messages)
        data = json.loads(value.content)
        context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
        data['table']['view'] = context['candidates'][0]['view']
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))

    def compile_plan(*args, **kwargs):
        value = original_compile(*args, **kwargs)
        compiled.append(value)
        return value

    runtime.llm.invoke = invoke
    monkeypatch.setattr(sql_generation, 'compile_single_view', compile_plan)
    question = '請查詢含稅發票總額。'
    choice = ClarificationChoice(option_id=other_view, contract_fingerprint=runtime.catalog.fingerprint)
    try:
        if interface == 'sql':
            initial = runtime.generate(question)
            assert initial.status == 'needs_clarification' and initial.sql is None
            assert not calls and not compiled
            pending = runtime.generate(question, clarification_choice=choice)
            assert pending.status == 'needs_confirmation' and pending.sql is None
            assert not calls and not compiled and not (tmp_path / 'terms_mapping.json').exists()
            ready = runtime.confirm(selection(pending))
            assert ready.status == 'ready' and ready.selected_views == [other_view]
            assert compiled == [ready.sql] and not calls
        else:
            gate = SessionGate()
            initial = list(single_question_updates(runtime, question, gate))
            assert initial[-1].pending['question'] == '要查詢哪一種摘要？'
            assert not calls and not compiled
            pending = list(single_question_updates(runtime, '', gate, payload=choice))
            assert pending[-1].state == 'waiting_confirmation' and 'items' in pending[-1].pending
            assert not calls and not compiled and not (tmp_path / 'terms_mapping.json').exists()
            completed = list(single_question_updates(runtime, '', gate,
                payload=selection(SimpleNamespace(clarification=gate.pending))))
            assert completed[-1].state == 'completed' and other_view in gate.sql
            assert calls == [gate.sql] and compiled == [gate.sql]
        records = workflow.repository.read().mappings
        assert len(records) == 1 and records[0].view == other_view
        assert not workflow.registry.runs
    finally:
        runtime.close()


def test_confirm_reuse_and_terminal_cleanup(tmp_path):
    runtime = runtime_for(tmp_path)
    pending = runtime.generate(QUESTION)
    assert pending.status == 'needs_confirmation' and pending.sql is None
    assert pending.clarification.items[0].term == '含稅發票總額'
    assert not (tmp_path / 'terms_mapping.json').exists()
    assert runtime.llm.calls == 1
    payload = selection(pending)
    result = runtime.confirm(payload)
    assert result.status == 'ready' and 'order_amount' in result.sql
    assert runtime.llm.calls == 1
    reasoning = result.term_mapping_reasoning[0]
    assert reasoning.source == 'confirmed_this_request'
    data = json.loads((tmp_path / 'terms_mapping.json').read_text(encoding='utf-8'))
    assert data['scope']['datasource_id'] == 'test-datasource'
    assert data['mappings'][0]['term'] == '含稅發票總額'
    assert not runtime.generation_service().workflow.registry.runs
    assert not runtime.generation_service().workflow.checkpointer.storage
    with pytest.raises(ConfirmationError) as error:
        runtime.confirm(payload)
    assert error.value.status_code == 409
    reused = runtime.generate(QUESTION)
    assert reused.status == 'ready'
    assert reused.term_mapping_reasoning[0].source == 'reused_confirmation'
    assert reused.term_mapping_reasoning[0].mapping_id == reasoning.mapping_id
    runtime.close()


def test_same_view_repair_then_hilp_compiles_only_after_confirmation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from cpea.workflows.text_to_sql import sql_generation

    runtime = runtime_for(tmp_path)
    contexts, compiled = [], []
    original_invoke = runtime.llm.invoke
    original_compile = sql_generation.compile_single_view

    def invoke(messages):
        contexts.append(json.loads(messages[-1].content.split('table定義: ', 1)[1]))
        value = original_invoke(messages)
        data = json.loads(value.content)
        if len(contexts) == 1:
            data['fields'] = []
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))

    def compile_plan(*args, **kwargs):
        value = original_compile(*args, **kwargs)
        compiled.append(value)
        return value

    runtime.llm.invoke = invoke
    monkeypatch.setattr(sql_generation, 'compile_single_view', compile_plan)
    try:
        pending = runtime.generate(QUESTION)
        assert pending.status == 'needs_confirmation' and not compiled
        assert runtime.llm.calls == 2
        assert [[item['view'] for item in context['candidates']] for context in contexts] == [[VIEW], [VIEW]]
        assert contexts[1]['repair']['previous_mapping']['fields'] == []
        assert 'fields mapping is empty' in contexts[1]['repair']['validation_errors']
        ready = runtime.confirm(selection(pending))
        assert ready.status == 'ready' and compiled == [ready.sql]
        assert runtime.llm.calls == 2
        assert ready.term_mapping_reasoning[0].source == 'confirmed_this_request'
    finally:
        runtime.close()


def test_semantic_coverage_failure_repairs_then_tries_next_view(tmp_path):
    from copy import deepcopy
    from dataclasses import replace
    from types import SimpleNamespace
    from langchain_core.documents import Document
    from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult

    runtime = runtime_for(tmp_path)
    first = runtime.catalog.views()[0]
    policy = deepcopy(first.policy)
    policy['view'] = second_view = 'demo_retail.v_complete_summary'
    runtime.catalog._definitions.append(replace(first, name=second_view, policy=policy))
    contexts = []

    def invoke(messages):
        context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
        contexts.append(context)
        view = context['candidates'][0]['view']
        fields = [{'text': '總額', 'column': 'order_amount'}]
        if view == second_view:
            fields.append({'text': '預估發票淨額', 'column': 'net_amount'})
        return SimpleNamespace(content=json.dumps({'table': {'view': view}, 'fields': fields, 'having': [],
                                                  'clarifications': clarification_drafts()}, ensure_ascii=False))

    candidates = [RetrievalCandidate(document=Document(page_content='摘要', metadata={
        'document_id': view, 'source': 'synthetic.yaml', 'filename': 'synthetic.yaml', 'chunk_id': view}),
                                    retrieval_score=1.0) for view in (VIEW, second_view)]
    workflow = runtime.generation_service().workflow
    workflow.retriever = SimpleNamespace(retrieve=lambda query: RetrievalResult(query=query, candidates=candidates,
        retrieval_latency_ms=0, reranker_latency_ms=0))
    runtime.llm.invoke = invoke
    try:
        pending = runtime.generate('請查詢含稅發票總額、預估發票淨額。')
        assert pending.status == 'needs_confirmation'
        assert {item.view for item in pending.clarification.items} == {second_view}
        assert [c['candidates'][0]['view'] for c in contexts] == [VIEW, VIEW, second_view]
        assert any('uncovered request text' in error for error in contexts[1]['repair']['validation_errors'])
        assert not pending.sql and not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()


def test_truncated_filter_cannot_generate_sql_by_dropping_the_condition(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        result = runtime.generate('請查詢含稅發票總額，限定商品總件數。')
        assert result.status == 'unsupported' and result.sql is None
        assert any('商品總件數' in error for error in result.limitations)
        assert runtime.llm.calls == 2
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()


def test_cancel_invalid_and_restart(tmp_path):
    runtime = runtime_for(tmp_path)
    pending = runtime.generate(QUESTION)
    bad = selection(pending).model_copy(deep=True)
    bad.decisions[0].option_id = 'invalid'
    with pytest.raises(ConfirmationError) as error:
        runtime.confirm(bad)
    assert error.value.status_code == 422
    cancelled = runtime.confirm(ConfirmationRequest(confirmation_id=pending.clarification.confirmation_id, action='cancel'))
    assert cancelled.status == 'cancelled'
    assert not (tmp_path / 'terms_mapping.json').exists()
    second = runtime.generate(QUESTION)
    other = runtime_for(tmp_path)
    with pytest.raises(ConfirmationError) as error:
        other.confirm(selection(second))
    assert error.value.status_code == 410
    runtime.close()
    other.close()


def test_null_table_candidate_and_alternative(tmp_path):
    runtime = runtime_for(tmp_path, null_table=True)
    pending = runtime.generate(QUESTION)
    assert pending.status == 'needs_confirmation'
    ready = runtime.confirm(selection(pending, 'net_amount'))
    assert ready.status == 'ready' and 'net_amount' in ready.sql
    assert ready.term_mapping_reasoning[0].column == 'net_amount'
    runtime.close()


def test_two_pending_replacement_requires_new_confirmation(tmp_path):
    runtime = runtime_for(tmp_path)
    first, second = runtime.generate(QUESTION), runtime.generate(QUESTION)
    runtime.confirm(selection(first))
    conflict = runtime.confirm(selection(second, 'net_amount'))
    assert conflict.status == 'needs_confirmation'
    assert conflict.clarification.kind == 'replace_mapping'
    ready = runtime.confirm(selection(conflict, 'net_amount'))
    assert ready.status == 'ready'
    data = json.loads((tmp_path / 'terms_mapping.json').read_text(encoding='utf-8'))
    assert [m['status'] for m in data['mappings']] == ['revoked', 'active']
    assert runtime.llm.calls == 2
    runtime.close()


def test_save_failure_never_executes(tmp_path, monkeypatch):
    calls = []
    runtime = runtime_for(tmp_path, executor=lambda d, s: (calls.append(s) or ([], [])))
    pending = runtime.execute(QUESTION)
    def fail(*args):
        raise OSError('no disk')
    monkeypatch.setattr('cpea.infrastructure.terms_mapping.os.replace', fail)
    result = runtime.confirm(selection(pending), mode='execute')
    assert result.status == 'error' and result.sql is None and not calls
    assert not runtime.generation_service().workflow.checkpointer.storage
    runtime.close()


def test_contract_change_while_waiting_invalidates_confirmation(tmp_path):
    runtime = runtime_for(tmp_path)
    pending = runtime.generate(QUESTION)
    runtime.catalog.views()[0].policy['columns']['order_amount']['description'] += '；定義已改變'
    with pytest.raises(ConfirmationError) as error:
        runtime.confirm(selection(pending))
    assert error.value.status_code == 410
    assert not runtime.generation_service().workflow.registry.runs
    runtime.close()


def test_changed_used_mapping_must_reconfirm_exact_use(tmp_path):
    from cpea.application.ports.term_mappings import TermMapping
    runtime = runtime_for(tmp_path)
    initial = runtime.generate(QUESTION)
    runtime.confirm(selection(initial))
    repository = runtime.generation_service().workflow.repository
    old = next(iter(repository.read().active().values()))
    # A waiting second term preserves the originally trusted first term.
    import json
    from types import SimpleNamespace
    original = runtime.llm.invoke
    def invoke(messages):
        raw = original(messages)
        data = json.loads(raw.content)
        data['fields'].append({'text': '淨額', 'column': 'net_amount'})
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))
    runtime.llm.invoke = invoke
    pending = runtime.generate(QUESTION.rstrip('。') + '、預估發票淨額。')
    updated = old.model_copy(update={'id': 'changed', 'column': 'net_amount'})
    repository.commit([updated], used=[], replacements={old.key: old.id})
    result = runtime.confirm(selection(pending, 'net_amount'))
    assert result.status == 'needs_confirmation'
    assert result.clarification.kind == 'replace_mapping'
    assert result.clarification.items[0].term == '含稅發票總額'
    ready = runtime.confirm(selection(result, 'order_amount'))
    assert ready.status == 'ready'
    assert ready.query_plan.select_columns == ['order_amount', 'net_amount']
    runtime.close()


def test_llm_contract_name_can_use_verified_original_business_span(tmp_path):
    start = QUESTION.index('含稅發票總額')
    terms = [{'clause': 'fields', 'index': 0, 'start': start, 'end': start + len('含稅發票總額'),
              'term': '含稅發票總額', 'candidates': ['order_amount'], 'evidence_quote': None}]
    runtime = runtime_for(tmp_path, text='訂單金額', terms=terms)
    pending = runtime.generate(QUESTION)
    assert pending.status == 'needs_confirmation' and runtime.llm.calls == 1
    assert pending.clarification.items[0].term == '含稅發票總額'
    runtime.close()


def test_reused_mapping_can_admit_source_missing_from_retrieval(tmp_path):
    from types import SimpleNamespace
    from cpea.infrastructure.retrieval.schema import RetrievalResult
    runtime = runtime_for(tmp_path)
    runtime.confirm(selection(runtime.generate(QUESTION)))
    workflow = runtime.generation_service().workflow
    workflow.retriever = SimpleNamespace(retrieve=lambda query: RetrievalResult(query=query, candidates=[],
        retrieval_latency_ms=0, reranker_latency_ms=0))
    result = runtime.generate('請查詢含稅發票總額。')
    assert result.status == 'ready'
    assert result.selected_views == [VIEW] and result.term_mapping_reasoning[0].source == 'reused_confirmation'
    runtime.close()


def test_ambiguous_sources_require_explicit_view_and_unrelated_view_change_is_safe(tmp_path):
    from dataclasses import replace
    from copy import deepcopy
    from cpea.application.ports.term_mappings import view_fingerprint
    runtime = runtime_for(tmp_path)
    runtime.confirm(selection(runtime.generate(QUESTION)))
    first = runtime.catalog.views()[0]
    second_policy = deepcopy(first.policy)
    second_policy['view'] = 'demo_retail.v_other_summary'
    second = replace(first, name=second_policy['view'], policy=second_policy)
    runtime.catalog._definitions.append(second)
    repository = runtime.generation_service().workflow.repository
    original = next(iter(repository.read().active().values()))
    other = original.model_copy(update={'id': 'other-source', 'view': second.name,
        'view_contract_fingerprint': view_fingerprint(runtime.catalog, second.name)})
    repository.commit([other], used=[], replacements={})
    calls = runtime.llm.calls
    ambiguous = runtime.generate('請查詢含稅發票總額。')
    assert ambiguous.status == 'unsupported' and ambiguous.code == 'ambiguous_source'
    assert ambiguous.clarification is None and runtime.llm.calls == calls
    second.policy['columns']['order_amount']['description'] = '其他來源更新'
    exact = runtime.generate(QUESTION)
    assert exact.status == 'ready' and exact.term_mapping_reasoning[0].mapping_id == original.id
    runtime.close()
