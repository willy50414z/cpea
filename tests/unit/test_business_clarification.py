import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from cpea.application.models.confirmation import ConfirmationError, ConfirmationRequest
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.interfaces.web.ui import SessionGate, business_progress, single_question_updates
from cpea.application.models.progress import WorkflowStep
from tests.hilp_support import QUESTION, VIEW, runtime_for, selection


COST_QUESTION = '顯示預估成本的單列最大值。'
RETAIL_QUESTION = ('依門市城市分組，顯示訂單折扣後總金額合計與cost_amount的單列最大值，'
                   '限定訂單商品總件數 >= 100且訂單成立日期 >= 2026-07-01且門市名稱 LIKE 中山%，依門市城市排序。')


def cost_runtime(root, *, extra=(), options=None, refine=False):
    runtime = runtime_for(root, text='預估成本')
    columns = runtime.catalog.views()[0].policy['columns']
    columns['order_amount'].update(description='每筆訂單商品成本金額', unit='TWD', aggregations=['max'])
    columns['net_amount'].update(description='每筆訂單含運成本金額', unit='TWD', aggregations=['max'])
    for column, description, field_type, unit in extra:
        columns[column] = {'type': field_type, 'description': description, 'unit': unit,
                           'capabilities': ['select'], 'aggregations': ['max']}
    if options is None:
        options = [option(column, spec['description']) for column, spec in columns.items()]
    original = runtime.llm.invoke

    def invoke(messages):
        if '語意確認資料:' in messages[-1].content:
            runtime.llm.calls += 1
            return SimpleNamespace(content=json.dumps({'source_compatible': True, 'clarifications': [
                {'term': '預估成本', 'options': options, 'needs_refinement': refine}]}, ensure_ascii=False))
        raw = original(messages)
        data = json.loads(raw.content)
        data['fields'][0]['aggregation'] = 'max'
        data['clarifications'] = [{'term': '預估成本', 'options': options, 'needs_refinement': refine}]
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))

    runtime.llm.invoke = invoke
    runtime.generation_service().workflow.retriever = SchemaRetriever(runtime.settings, catalog=runtime.catalog)
    return runtime


def option(column, label, **kwargs):
    return {'column': column, 'label': label, 'evidence_quote': label,
            'same_concept': True, 'grain_compatible': True, **kwargs}


def test_cost_choices_exclude_irrelevant_types_units_concepts_and_grains(tmp_path):
    extra = [
        ('store_name', '門市名稱', '字串', ''),
        ('region', '門市所屬區域', '字串', ''),
        ('sales_month', '業績統計月份', '日期', ''),
        ('margin', '成本占比', '數值', '%'),
        ('monthly_cost', '每月成本總額', '數值', 'TWD'),
        ('gross_profit', '當月毛利總額', '數值', 'TWD'),
    ]
    options = [option('order_amount', '每筆訂單商品成本金額')]
    # Even a model that proposes MAX on string/date columns cannot offer them.
    options += [option(c, d, grain_compatible=c != 'monthly_cost', same_concept=c != 'gross_profit')
                for c, d, _, _ in extra]
    runtime = cost_runtime(tmp_path, extra=extra, options=options)
    try:
        ready = runtime.generate(COST_QUESTION)
        assert ready.status == 'ready' and ready.clarification is None
        assert ready.query_plan.aggregations == {'order_amount': 'max'}
        assert ready.term_mapping_reasoning[0].description == '每筆訂單商品成本金額'
        assert ready.term_mapping_reasoning[0].source == 'automatically_resolved'
        assert not (tmp_path / 'terms_mapping.json').exists()
        assert runtime.llm.calls == 1
    finally:
        runtime.close()


def test_three_business_choices_plus_rephrase_fit_four_options(tmp_path):
    runtime = cost_runtime(tmp_path, extra=[('shipping_cost', '每筆訂單運送成本', '數值', 'TWD')])
    try:
        pending = runtime.generate(COST_QUESTION)
        assert pending.status == 'needs_confirmation'
        assert len(pending.clarification.items[0].options) == 4
        assert pending.clarification.items[0].options[-1].column is None
    finally:
        runtime.close()


@pytest.mark.parametrize('refine', [False, True])
def test_too_many_related_choices_require_rephrasing_without_truncation(tmp_path, refine):
    runtime = cost_runtime(tmp_path, extra=[('shipping_cost', '每筆訂單運送成本', '數值', 'TWD'),
                                          ('packing_cost', '每筆訂單包裝成本', '數值', 'TWD')], refine=refine)
    gate = SessionGate()
    try:
        frames = list(single_question_updates(runtime, COST_QUESTION, gate))
        assert frames[-1].state == 'editing'
        assert frames[-1].draft == COST_QUESTION and frames[-1].pending is None
        assert not gate.sql and not runtime.generation_service().workflow.registry.runs
        assert not (tmp_path / 'terms_mapping.json').exists()
    finally:
        runtime.close()


@pytest.mark.parametrize('options, status, calls', [
    ([], 'unsupported', 1),
    ([option('order_amount', '每筆訂單商品成本金額', evidence_quote='捏造的證據')], 'error', 3),
    ([option('order_amount', '每筆訂單商品成本金額', evidence_quote=' ')], 'error', 3),
    ([option('missing_column', '不存在的成本')], 'error', 3),
    ([option('order_amount', '每筆訂單商品成本金額', same_concept=False)], 'unsupported', 1),
    ([option('order_amount', '每筆訂單商品成本金額', grain_compatible=False)], 'unsupported', 1),
    ([option('order_amount', f'{VIEW}.order_amount', evidence_quote='每筆訂單商品成本金額')], 'error', 3),
    ([option('order_amount', 'MAX(成本)', evidence_quote='每筆訂單商品成本金額')], 'error', 3),
    ([option('order_amount', '成本金額', evidence_quote='每筆訂單商品成本金額'),
      option('net_amount', '成本金額', evidence_quote='每筆訂單含運成本金額')], 'error', 3),
])
def test_no_valid_proposals_never_fall_back_to_all_columns(tmp_path, options, status, calls):
    # One MATCH, one resolution, and at most one semantic validation repair.
    runtime = cost_runtime(tmp_path, options=options)
    try:
        result = runtime.generate(COST_QUESTION)
        assert result.status == status
        assert result.code == ('clarification_rephrase' if status == 'unsupported' else 'clarification_generation_failed')
        assert result.clarification is None and result.sql is None
        assert runtime.llm.calls == calls and not runtime.generation_service().workflow.registry.runs
    finally:
        runtime.close()


def test_missing_semantic_proposals_are_resolved_once_without_remapping(tmp_path):
    runtime = runtime_for(tmp_path)
    original = runtime.llm.invoke

    def invoke(messages):
        data = json.loads(original(messages).content)
        if 'table定義:' in messages[-1].content:
            data.pop('clarifications')
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))

    runtime.llm.invoke = invoke
    try:
        result = runtime.generate(QUESTION)
        assert result.status == 'needs_confirmation' and result.sql is None
        assert runtime.llm.calls == 2
        assert result.clarification.items[0].term == '含稅發票總額'
        ready = runtime.confirm(selection(result))
        assert ready.status == 'ready' and runtime.llm.calls == 2
    finally:
        runtime.close()


def test_choosing_rephrase_restores_question_and_consumes_confirmation(tmp_path):
    runtime = runtime_for(tmp_path, executor=lambda *args: pytest.fail('must not execute'))
    gate = SessionGate()
    try:
        initial = list(single_question_updates(runtime, QUESTION, gate))[-1]
        public = initial.pending
        assert 'view' not in public['items'][0]
        assert all('column' not in o for o in public['items'][0]['options'])
        assert VIEW not in json.dumps(public) and 'order_amount' not in json.dumps(public)
        confirmation_id = gate.pending.confirmation_id
        payload = ConfirmationRequest(confirmation_id=confirmation_id, action='rephrase')
        editing = list(single_question_updates(runtime, '', gate, payload=payload))[-1]
        assert editing.state == 'editing' and editing.draft == QUESTION and not editing.pending
        assert not editing.sql and not (tmp_path / 'terms_mapping.json').exists()
        assert not runtime.generation_service().workflow.registry.runs
        with pytest.raises(ConfirmationError):
            runtime.resume_generation(payload, mode='web', owner=gate.owner)
        again = list(single_question_updates(runtime, QUESTION, gate))[-1]
        assert again.state == 'waiting_confirmation'
        assert gate.pending.confirmation_id != confirmation_id
    finally:
        runtime.close()


def test_business_progress_never_forwards_arbitrary_workflow_info():
    steps = [WorkflowStep('match candidate view', {'view': VIEW}),
             WorkflowStep('unrecognized step', 'top-secret schema'),
             WorkflowStep('validate SQL', 'SELECT order_amount FROM ' + VIEW)]
    assert business_progress(steps) == ['正在比對問題與資料內容。', '正在檢查查詢條件。']


def test_browser_summary_results_and_pending_state_have_no_schema_identifiers(tmp_path):
    runtime = runtime_for(tmp_path, executor=lambda *args: (['order_amount'], [[123]]))
    gate = SessionGate()
    try:
        initial = list(single_question_updates(runtime, QUESTION, gate))
        payload = selection(SimpleNamespace(clarification=gate.pending))
        final = list(single_question_updates(runtime, '', gate, payload=payload))[-1]
        browser_content = json.dumps([*(f.messages[-1] for f in initial), initial[-1].pending,
                                      final.messages[-1], final.reasoning, final.rows], ensure_ascii=False)
        assert VIEW not in browser_content and 'order_amount' not in browser_content
        assert final.rows == {'headers': ['訂單金額'], 'data': [[123]]}
        assert all(not f.sql for f in initial)
        assert final.sql == gate.sql
        assert 'order_amount' in gate.sql
    finally:
        runtime.close()


def retail_runtime(root):
    runtime = runtime_for(root)
    definition = runtime.catalog.views()[0]
    specs = {
        'order_id': ('訂單識別碼', 'string', 'dimension'),
        'city': ('門市城市', 'string', 'dimension'),
        'order_amount': ('訂單折扣後總金額', 'number', 'metric'),
        'cost_amount': ('訂單商品成本金額', 'number', 'metric'),
        'total_quantity': ('訂單商品總件數', 'number', 'metric'),
        'order_date': ('訂單成立日期', 'date', 'dimension'),
        'store_name': ('門市名稱', 'string', 'dimension'),
    }
    policy = {'version': 3, 'view': VIEW, 'summary': '每張訂單的門市、金額、成本、商品件數與成立日期',
              'grain': {'description': '每列為一張訂單', 'keys': ['order_id']},
              'columns': {name: {'description': desc, 'type': typ, 'role': role}
                          for name, (desc, typ, role) in specs.items()}}
    runtime.catalog._definitions[0] = replace(definition, policy=policy, summary=policy['summary'])
    monthly_policy = {'version': 3, 'view': 'demo_retail.v_store_monthly_kpi', 'summary': '門市每月業績',
                      'grain': {'description': '每列為一家門市一個月的業績', 'keys': ['store_id', 'sales_month']},
                      'columns': {
                          'store_id': {'description': '門市識別碼', 'type': 'string', 'role': 'dimension'},
                          'sales_month': {'description': '業績統計月份', 'type': 'date', 'role': 'dimension'},
                          'city': {'description': '門市城市', 'type': 'string', 'role': 'dimension'},
                          'gross_profit': {'description': '當月毛利總額（營收減商品成本）', 'type': 'number', 'role': 'metric'},
                      }}
    runtime.catalog._definitions.append(replace(definition, name=monthly_policy['view'], policy=monthly_policy,
                                               summary=monthly_policy['summary']))
    mapping = {'table': {'view': VIEW}, 'having': [], 'clarifications': [],
               'fields': [{'text': '門市城市', 'column': 'city'},
                          {'text': '訂單折扣後總金額', 'column': 'order_amount', 'aggregation': 'sum'},
                          {'text': 'cost_amount', 'column': 'cost_amount', 'aggregation': 'max'}],
               'criteria': [{'text': '訂單商品總件數 >= 100', 'column': 'total_quantity', 'operator': '>=', 'value': 100},
                            {'text': '訂單成立日期 >= 2026-07-01', 'column': 'order_date', 'operator': '>=', 'value': '2026-07-01'},
                            {'text': '門市名稱 LIKE 中山%', 'column': 'store_name', 'operator': 'LIKE', 'value': '中山%'}],
               'group': [{'text': '門市城市', 'column': 'city'}],
               'order': [{'text': '門市城市', 'column': 'city'}]}

    def invoke(messages):
        runtime.llm.calls += 1
        context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
        assert context['candidates'][0]['view'] == VIEW
        return SimpleNamespace(content=json.dumps(mapping, ensure_ascii=False))

    runtime.llm.invoke = invoke
    runtime.generation_service().workflow.retriever = SchemaRetriever(runtime.settings, catalog=runtime.catalog)
    return runtime, mapping


def test_original_retail_question_preserves_all_operations_without_reasking_cost(tmp_path):
    runtime, _ = retail_runtime(tmp_path)
    try:
        result = runtime.generate(RETAIL_QUESTION)
        assert result.status == 'ready' and result.clarification is None
        assert result.query_plan.aggregations == {'order_amount': 'sum', 'cost_amount': 'max'}
        assert result.query_plan.group_by == result.query_plan.order_by == ['city']
        assert [f.column for f in result.query_plan.filters] == ['total_quantity', 'order_date', 'store_name']
        assert result.query_plan.having == []
        assert "[total_quantity] >= 100" in result.sql
        assert "[order_date] >= N'2026-07-01'" in result.sql
        assert "[store_name] LIKE N'中山%'" in result.sql
        assert 'SUM([order_amount])' in result.sql and 'MAX([cost_amount])' in result.sql
        assert runtime.llm.calls == 1
    finally:
        runtime.close()


def test_nonexistent_explicit_cost_identifier_cannot_be_substituted_with_gross_profit(tmp_path):
    runtime = runtime_for(tmp_path, text='cost_amount')
    try:
        result = runtime.generate('顯示cost_amount。')
        assert result.status == 'unsupported' and not result.clarification and not result.sql
        assert any('explicit identifier' in error for error in result.limitations)
    finally:
        runtime.close()
