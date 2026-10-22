from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from cpea.application.models.confirmation import ConfirmationRequest
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult, SchemaRetriever
from tests.hilp_support import VIEW, runtime_for
from tests.unit.test_business_clarification import RETAIL_QUESTION, option, retail_runtime
from cpea.interfaces.web.ui import SessionGate, single_question_updates
from tests.hilp_support import QUESTION, selection


def realistic_retail_runtime(root):
    runtime, mapping = retail_runtime(root)
    columns = runtime.catalog.views()[0].policy['columns']
    columns['store_city'] = columns.pop('city')
    descriptions = {
        'store_city': '訂單門市所在城市，不是會員居住城市。',
        'order_date': '訂單成立日期（曆日），不含時間。',
        'store_name': '訂單所屬門市名稱。',
        'total_quantity': '此訂單全部明細的商品銷售件數加總；單位件。',
        'order_amount': '此訂單折扣後的總銷售金額（各明細 quantity × unit_price − discount），單位 TWD。',
        'cost_amount': '此訂單全部明細的商品成本總額，單位 TWD。',
    }
    for column, description in descriptions.items():
        columns[column]['description'] = description
    for column, unit in [('order_amount', 'TWD'), ('cost_amount', 'TWD'), ('total_quantity', '件')]:
        columns[column]['unit'] = unit
    for clause in ('fields', 'group', 'order'):
        for item in mapping[clause]:
            if item['column'] == 'city':
                item['column'] = 'store_city'
    # Replay the completed real mapper's text spans and its missing choices.
    mapping['fields'] = [{'text': '訂單折扣後總金額合計', 'column': 'order_amount', 'aggregation': 'sum'},
                         {'text': 'cost_amount的單列最大值', 'column': 'cost_amount', 'aggregation': 'max'}]
    mapping['group'][0]['text'] = '依門市城市分組'
    mapping['order'][0]['text'] = '依門市城市排序'
    labels = {'order_amount': '每筆訂單折扣後的總銷售金額',
              'total_quantity': '每筆訂單全部商品的銷售件數', 'store_city': '訂單門市所在城市'}
    calls = []

    def invoke(messages):
        runtime.llm.calls += 1
        if '語意確認資料:' not in messages[-1].content:
            calls.append('match')
            return SimpleNamespace(content=json.dumps(mapping, ensure_ascii=False))
        calls.append('resolve')
        context = json.loads(messages[-1].content.split('語意確認資料: ', 1)[1])
        assert {item['term'] for item in context['required_terms']} == {
            '訂單折扣後總金額', '訂單商品總件數', '門市城市'}
        proposals = []
        for item in context['required_terms']:
            column = item['uses'][0]['column']
            assert column in item['eligible_columns']
            proposals.append({'term': item['term'], 'options': [option(column, labels[column],
                              evidence_quote=descriptions[column])]})
        return SimpleNamespace(content=json.dumps({'source_compatible': True, 'clarifications': proposals},
                                                  ensure_ascii=False))

    runtime.llm.invoke = invoke
    runtime.generation_service().workflow.retriever = SchemaRetriever(runtime.settings, catalog=runtime.catalog)
    return runtime, calls


def test_real_description_and_empty_choices_are_resolved_without_reasking_explicit_cost_or_date(tmp_path):
    runtime, calls = realistic_retail_runtime(tmp_path)
    try:
        ready = runtime.generate(RETAIL_QUESTION)
        assert ready.status == 'ready' and ready.clarification is None
        assert calls == ['match', 'resolve']
        assert {reason.term for reason in ready.term_mapping_reasoning} == {
            '訂單折扣後總金額', '訂單商品總件數', '門市城市'}
        assert all(reason.source == 'automatically_resolved' and reason.mapping_id is None
                   and reason.confirmed_at is None for reason in ready.term_mapping_reasoning)
        assert not (tmp_path / 'terms_mapping.json').exists()
        assert ready.query_plan.aggregations == {'order_amount': 'sum', 'cost_amount': 'max'}
        assert ready.query_plan.group_by == ready.query_plan.order_by == ['store_city']
        assert [(f.column, f.operator, f.value) for f in ready.query_plan.filters] == [
            ('total_quantity', '>=', 100), ('order_date', '>=', '2026-07-01'), ('store_name', 'LIKE', '中山%')]
        assert ready.query_plan.having == []
        selected = next(item for item in ready.query_trace.mapping_attempts if item.outcome == 'selected')
        assert len(selected.mapping.clarifications) == 3
        assert runtime.generate(RETAIL_QUESTION).status == 'ready'
        assert calls == ['match', 'resolve', 'match', 'resolve']
    finally:
        runtime.close()


@pytest.mark.parametrize('has_valid_source', [True, False])
def test_incompatible_grain_exhausts_this_source_and_tries_remaining_candidates(tmp_path, has_valid_source):
    runtime = runtime_for(tmp_path)
    original = runtime.catalog.views()[0]
    wrong_view = 'demo_retail.v_detail_rows'
    policy = deepcopy(original.policy)
    policy.update(view=wrong_view, grain='每項訂單商品明細一列')
    runtime.catalog._definitions.insert(0, replace(original, name=wrong_view, policy=policy))
    views = [wrong_view, VIEW] if has_valid_source else [wrong_view]
    candidates = [RetrievalCandidate(document=Document(page_content='訂單金額', metadata={
        'document_id': view, 'source': 'synthetic', 'filename': 'synthetic', 'chunk_id': view}), retrieval_score=1.0)
        for view in views]
    workflow = runtime.generation_service().workflow
    workflow.retriever = SimpleNamespace(retrieve=lambda query: RetrievalResult(query=query, candidates=candidates,
        retrieval_latency_ms=0, reranker_latency_ms=0))
    calls = []

    def invoke(messages):
        if '語意確認資料:' in messages[-1].content:
            context = json.loads(messages[-1].content.split('語意確認資料: ', 1)[1])
            view = context['contract']['view']
            calls.append(('resolve', view))
            data = {'source_compatible': view == VIEW, 'clarifications': []}
            if view == VIEW:
                data['clarifications'] = [{'term': item['term'], 'options': [option('order_amount', '訂單金額')]}
                                         for item in context['required_terms']]
        else:
            context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
            view = context['candidates'][0]['view']
            calls.append(('match', view))
            data = {'fields': [{'text': '含稅發票總額', 'column': 'order_amount'}], 'having': [],
                    'table': {'view': view}, 'clarifications': []}
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))

    runtime.llm.invoke = invoke
    try:
        result = runtime.generate('查詢含稅發票總額。')
        assert calls[:2] == [('match', wrong_view), ('resolve', wrong_view)]
        assert not (tmp_path / 'terms_mapping.json').exists()
        if has_valid_source:
            assert result.status == 'ready' and result.sql
            assert calls[2:] == [('match', VIEW), ('resolve', VIEW)]
            assert result.query_plan.source_views == [VIEW]
        else:
            assert result.status == 'unsupported' and len(calls) == 2
            assert result.query_trace.selected_view is None
            assert result.query_trace.mapping_attempts[0].outcome == 'rejected'
        assert not workflow.registry.runs
    finally:
        runtime.close()


def test_single_meanings_continue_to_execution_once_and_show_sql_and_full_summary(tmp_path):
    runtime, calls = realistic_retail_runtime(tmp_path)
    executions = []
    runtime.executor = lambda datasource, sql: (executions.append(sql) or (
        ['store_city', 'order_amount', 'cost_amount'], [['台北市', 12000, 600]]))
    gate = SessionGate('retail')
    try:
        frames = list(single_question_updates(runtime, RETAIL_QUESTION, gate))
        assert frames[-1].state == 'completed'
        assert 'waiting_confirmation' not in [frame.state for frame in frames]
        assert calls == ['match', 'resolve'] and executions == [frames[-1].sql]
        assert frames[-1].sql and frames[-1].pending is None
        assert frames[-1].reasoning.count('自動採用：') == 3
        assert frames[-1].reasoning in frames[-1].messages[-1]['content']
        assert frames[-1].rows['data'] == [['台北市', 12000, 600]]
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()


def test_mixed_single_and_ambiguous_terms_only_confirm_and_save_ambiguous_term(tmp_path):
    runtime = runtime_for(tmp_path)
    original = runtime.llm.invoke
    def invoke(messages):
        value = json.loads(original(messages).content)
        value['fields'].append({'text': '預估發票淨額', 'column': 'net_amount'})
        value['clarifications'][0]['options'] = value['clarifications'][0]['options'][:1]
        return SimpleNamespace(content=json.dumps(value, ensure_ascii=False))
    runtime.llm.invoke = invoke
    try:
        pending = runtime.generate(QUESTION.rstrip('。') + '、預估發票淨額。')
        assert pending.status == 'needs_confirmation'
        assert [item.term for item in pending.clarification.items] == ['預估發票淨額']
        ready = runtime.confirm(selection(pending, column='net_amount'))
        assert ready.status == 'ready'
        assert {(reason.term, reason.source) for reason in ready.term_mapping_reasoning} == {
            ('含稅發票總額', 'automatically_resolved'), ('預估發票淨額', 'confirmed_this_request')}
        stored = json.loads((tmp_path / 'terms_mapping.json').read_text(encoding='utf-8'))
        assert [record['term'] for record in stored['mappings']] == ['預估發票淨額']
    finally:
        runtime.close()


def test_single_candidate_cannot_silently_replace_an_existing_user_choice(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        runtime.confirm(selection(runtime.generate(QUESTION), column='net_amount'))
        original = runtime.llm.invoke
        def invoke(messages):
            value = json.loads(original(messages).content)
            value['clarifications'][0]['options'] = value['clarifications'][0]['options'][:1]
            return SimpleNamespace(content=json.dumps(value, ensure_ascii=False))
        runtime.llm.invoke = invoke
        result = runtime.generate(QUESTION)
        assert result.status == 'needs_confirmation' and result.sql is None
        assert [option.column for option in result.clarification.items[0].options] == ['order_amount', None]
        stored = json.loads((tmp_path / 'terms_mapping.json').read_text(encoding='utf-8'))
        assert [record['column'] for record in stored['mappings'] if record['status'] == 'active'] == ['net_amount']
    finally:
        runtime.close()


def test_automatic_city_substitution_updates_group_and_order_together(tmp_path):
    runtime, _ = realistic_retail_runtime(tmp_path)
    columns = runtime.catalog.views()[0].policy['columns']
    columns['branch_city'] = deepcopy(columns['store_city'])
    original = runtime.llm.invoke
    def invoke(messages):
        value = json.loads(original(messages).content)
        if '語意確認資料:' in messages[-1].content:
            for proposal in value['clarifications']:
                for candidate in proposal['options']:
                    if candidate['column'] == 'store_city':
                        candidate['column'] = 'branch_city'
        return SimpleNamespace(content=json.dumps(value, ensure_ascii=False))
    runtime.llm.invoke = invoke
    try:
        result = runtime.generate(RETAIL_QUESTION)
        assert result.status == 'ready'
        assert result.query_plan.group_by == result.query_plan.order_by == ['branch_city']
        assert '[store_city]' not in result.sql and '[branch_city]' in result.sql
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()


def test_multiple_single_choices_must_pass_combined_plan_validation(tmp_path):
    runtime = runtime_for(tmp_path)
    columns = runtime.catalog.views()[0].policy['columns']
    for spec in columns.values():
        spec['aggregations'] = ['sum', 'max']
    columns['common_amount'] = {**deepcopy(columns['order_amount']), 'description': '交易金額'}
    def invoke(messages):
        return SimpleNamespace(content=json.dumps({
            'fields': [{'text': '含稅發票總額', 'column': 'order_amount', 'aggregation': 'sum'},
                       {'text': '預估發票淨額', 'column': 'net_amount', 'aggregation': 'max'}],
            'table': {'view': VIEW}, 'having': [],
            'clarifications': [{'term': term, 'options': [option('common_amount', '交易金額')]}
                               for term in ('含稅發票總額', '預估發票淨額')]}, ensure_ascii=False))
    runtime.llm.invoke = invoke
    try:
        result = runtime.generate(f'請從 {VIEW} 查詢含稅發票總額合計、預估發票淨額的單列最大值。')
        assert result.status == 'unsupported' and result.sql is None and result.clarification is None
        assert any('conflicting aggregation' in error for error in result.limitations)
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()
