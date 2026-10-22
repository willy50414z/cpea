"""Contracts at the boundary between model drafts and source selection."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult
from cpea.workflows.text_to_sql.schemas import SQLClauseMappingV10
from cpea.workflows.text_to_sql.semantics import assess
from tests.hilp_support import VIEW, runtime_for
from tests.unit.test_semantic_resolution import realistic_retail_runtime
from tests.unit.test_business_clarification import RETAIL_QUESTION


def test_group_dimensions_are_preserved_in_the_selected_mapping(tmp_path):
    runtime, calls = realistic_retail_runtime(tmp_path)
    try:
        result = runtime.generate(RETAIL_QUESTION)
        assert result.status == 'ready'
        selected = next(a.mapping for a in result.query_trace.mapping_attempts if a.outcome == 'selected')
        assert [(f.column, f.aggregation) for f in selected.fields] == [
            ('order_amount', 'sum'), ('cost_amount', 'max'), ('store_city', None)]
        assert 'total_quantity' not in [f.column for f in selected.fields]
        assert calls == ['match', 'resolve']
    finally:
        runtime.close()


@pytest.mark.parametrize('name', ['已完成訂單筆數', '歷來最大值', '按月合計', '分組最大值', '依約合計'])
@pytest.mark.parametrize('prefix', ['', '列出'])
def test_statistical_words_in_approved_names_do_not_require_an_operation(tmp_path, name, prefix):
    runtime = runtime_for(tmp_path)
    try:
        runtime.catalog.views()[0].policy['columns']['order_amount']['aliases'] = [name]
        mapping = SQLClauseMappingV10.model_validate({'table': {'view': VIEW}, 'having': [],
            'fields': [{'text': prefix + name, 'column': 'order_amount'}]})
        assert not assess(f'列出{name}。', mapping, runtime.catalog, VIEW,
                          runtime.generation_service().workflow.repository.read())[2]
    finally:
        runtime.close()


def test_mixed_metrics_bind_operations_to_their_own_phrases(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        mapping = SQLClauseMappingV10.model_validate({'table': {'view': VIEW}, 'having': [], 'fields': [
            {'text': '訂單金額', 'column': 'order_amount', 'aggregation': 'sum'},
            {'text': '未稅訂單金額', 'column': 'net_amount', 'aggregation': 'max'}]})
        question = '顯示訂單金額合計與未稅訂單金額的單列最大值。'
        assert not assess(question, mapping, runtime.catalog, VIEW,
                          runtime.generation_service().workflow.repository.read())[2]
    finally:
        runtime.close()


def test_explicit_aggregate_mismatch_uses_same_view_mapping_repair(tmp_path):
    runtime = runtime_for(tmp_path, text='訂單金額')
    runtime.catalog.views()[0].policy['columns']['order_amount']['aggregations'] = ['count', 'max']
    contexts = []

    def invoke(messages):
        context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
        contexts.append(context)
        return SimpleNamespace(content=json.dumps({'table': {'view': VIEW}, 'having': [], 'fields': [
            {'text': '訂單金額', 'column': 'order_amount',
             'aggregation': 'max' if context.get('repair') else 'count'}]}, ensure_ascii=False))

    runtime.llm.invoke = invoke
    try:
        result = runtime.generate('顯示訂單金額的單列最大值。')
        assert result.status == 'ready' and result.query_plan.aggregations == {'order_amount': 'max'}
        assert len(contexts) == 2
        assert 'explicit aggregation mismatch' in str(contexts[1]['repair']['validation_errors'])
        assert 'MAX(' in result.sql and 'COUNT(' not in result.sql
    finally:
        runtime.close()


@pytest.mark.parametrize('punctuation', ['。', ':', '；'])
@pytest.mark.parametrize('prefix', ['', '顯示'])
def test_mapped_phrase_punctuation_cannot_hide_an_explicit_operation(tmp_path, punctuation, prefix):
    runtime = runtime_for(tmp_path)
    try:
        mapping = SQLClauseMappingV10.model_validate({'table': {'view': VIEW}, 'having': [], 'fields': [
            {'text': prefix + '訂單金額的單列最大值' + punctuation,
             'column': 'order_amount', 'aggregation': 'count'}]})
        errors = assess('顯示訂單金額的單列最大值' + punctuation, mapping, runtime.catalog, VIEW,
                        runtime.generation_service().workflow.repository.read())[2]
        assert any('aggregation' in error for error in errors)
    finally:
        runtime.close()


@pytest.mark.parametrize('aggregation,text', [
    ('count', '訂單金額'), ('sum', '訂單金額的單列最大值'), (None, '訂單金額'),
])
@pytest.mark.parametrize('punctuation', ['。', ':', ';', '）', '」', '\n'])
def test_explicit_maximum_cannot_be_reinterpreted_as_a_business_term(tmp_path, aggregation, text, punctuation):
    runtime = runtime_for(tmp_path)
    try:
        mapping = SQLClauseMappingV10.model_validate({'table': {'view': VIEW}, 'having': [],
            'fields': [{'text': text, 'column': 'order_amount', 'aggregation': aggregation}]})
        errors = assess('顯示訂單金額的單列最大值' + punctuation, mapping, runtime.catalog, VIEW,
                        runtime.generation_service().workflow.repository.read())[2]
        assert any('aggregation' in error for error in errors)
    finally:
        runtime.close()


@pytest.mark.parametrize('aggregation,question', [
    ('max', '顯示訂單金額的單列最大值。'), (None, '列出訂單金額。'),
])
def test_valid_aggregate_and_unaggregated_business_names_remain_valid(tmp_path, aggregation, question):
    runtime = runtime_for(tmp_path)
    try:
        mapping = SQLClauseMappingV10.model_validate({'table': {'view': VIEW}, 'having': [],
            'fields': [{'text': '訂單金額', 'column': 'order_amount', 'aggregation': aggregation}]})
        assert not assess(question, mapping, runtime.catalog, VIEW,
                          runtime.generation_service().workflow.repository.read())[2]
    finally:
        runtime.close()


@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_invalid_semantic_label_gets_one_bounded_repair_without_remapping(tmp_path, repair_succeeds):
    runtime = runtime_for(tmp_path, text='預估金額')
    original = runtime.llm.invoke
    calls = []

    def invoke(messages):
        if '語意確認資料:' not in messages[-1].content:
            calls.append('match')
            data = json.loads(original(messages).content)
            data['clarifications'] = []
            return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))
        calls.append('resolve')
        context = json.loads(messages[-1].content.split('語意確認資料: ', 1)[1])
        if calls.count('resolve') == 2:
            assert context['repair']['validation_errors']
            assert context['repair']['previous_resolution']
        label = '訂單金額' if repair_succeeds and calls.count('resolve') == 2 else 'order_amount'
        return SimpleNamespace(content=json.dumps({'source_compatible': True, 'clarifications': [
            {'term': item['term'], 'options': [{'column': 'order_amount', 'label': label,
                'evidence_quote': '訂單金額', 'same_concept': True, 'grain_compatible': True}]}
            for item in context['required_terms']]}, ensure_ascii=False))

    runtime.llm.invoke = invoke
    try:
        result = runtime.generate('查詢預估金額。')
        assert calls == ['match', 'resolve', 'resolve']
        assert result.status == ('ready' if repair_succeeds else 'error')
        if not repair_succeeds:
            assert result.code == 'clarification_generation_failed' and result.sql is None
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()


@pytest.mark.parametrize('negative_options', [True, False])
def test_incompatible_required_term_cannot_create_view_ambiguity(tmp_path, negative_options):
    runtime = runtime_for(tmp_path, text='預估金額')
    original = runtime.catalog.views()[0]
    wrong_view = 'demo_retail.v_other_source'
    policy = deepcopy(original.policy)
    policy['view'] = wrong_view
    runtime.catalog._definitions.insert(0, replace(original, name=wrong_view, policy=policy))
    candidates = [RetrievalCandidate(document=Document(page_content='業務資料', metadata={
        'document_id': v, 'source': 'synthetic', 'filename': v, 'chunk_id': v}), retrieval_score=1.0)
        for v in (wrong_view, VIEW)]
    workflow = runtime.generation_service().workflow
    workflow.retriever = SimpleNamespace(retrieve=lambda query: RetrievalResult(query=query,
        candidates=candidates, retrieval_latency_ms=0, reranker_latency_ms=0))
    compared = []

    def invoke(messages):
        content = messages[-1].content
        if 'table定義: ' not in content:
            compared.append(content)
            return SimpleNamespace(content=json.dumps({'decision': 'clarify', 'question': '請選口徑',
                'options': [{'id': v, 'label': '可行來源', 'description': '業務資料'} for v in (wrong_view, VIEW)]}))
        context = json.loads(content.split('table定義: ', 1)[1])
        view = context['candidates'][0]['view']
        good = view == VIEW
        options = [{'column': 'order_amount', 'label': '訂單金額', 'evidence_quote': '訂單金額',
                    'same_concept': good, 'grain_compatible': True}] if good or negative_options else []
        return SimpleNamespace(content=json.dumps({'fields': [{'text': '預估金額', 'column': 'order_amount'}],
            'table': {'view': view}, 'having': [], 'clarifications': [
                {'term': '預估金額', 'options': options, 'needs_refinement': not good and negative_options}]}, ensure_ascii=False))

    runtime.llm.invoke = invoke
    try:
        result = runtime.generate('查詢預估金額。')
        assert result.status == 'ready' and result.selected_views == [VIEW]
        assert not compared
        assert not any(a.outcome == 'matched' for a in result.query_trace.candidate_attempts if a.view == wrong_view)
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()
