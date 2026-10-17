from dataclasses import replace
import pytest
from tests.support import *


def test_retrieval_document_uses_only_descriptions(tmp_path):
    from cpea.infrastructure.retrieval.documents import build_documents

    _, catalog, *_ = dependencies(tmp_path)
    document = build_documents(catalog)[0]
    assert "合成數量" in document.page_content
    assert "數值" not in document.page_content
    assert "库存数量" not in document.page_content
    assert "仓库名称" not in document.page_content
    assert document.metadata["document_id"] == VIEW


def test_single_view_generation_and_trace(tmp_path):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported
    assert result.sql == "SELECT TOP (2) SUM([库存数量]) AS [库存数量], [仓库名称] FROM gms2.v_inventory WHERE [品号] = N'ZX100' GROUP BY [仓库名称]"
    assert result.query_trace.selected_view == VIEW
    assert result.query_trace.rejection_stage is None
    assert result.query_trace.candidate_attempts[0].outcome == 'matched'
    assert llm.calls == 1
    assert len(result.query_trace.request_facts) == 3

@pytest.mark.parametrize('question,stage', [('請 JOIN 兩個資料表', 'schema_selection'), ('請查第一季庫存數量', 'schema_linking')])
def test_unsupported_requests(tmp_path, question, stage):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(question)
    assert not result.supported and result.sql is None
    assert result.query_trace.rejection_stage == stage

@pytest.mark.parametrize('changes', [
    {'select_columns': ['不存在']}, {'aggregations': {'库存数量': 'avg'}},
    {'filters': [models.QueryFilter(column='库存数量', operator='=', value=1)]},
    {'source_views': [VIEW, 'other.v_inventory']},
])
def test_compiler_rejects_unapproved_plan(tmp_path, changes):
    _, catalog, *_ = dependencies(tmp_path)
    values = dict(supported=True, source_views=[VIEW], select_columns=['库存数量'], aggregations={'库存数量': 'sum'})
    values.update(changes)
    with pytest.raises(Compiler.SQLPolicyError):
        Compiler.compile_single_view(models.QueryPlan(**values), catalog)

def test_scope_policy_and_grounded_filter(tmp_path):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    plan = models.QueryPlan(source_views=[VIEW], select_columns=['库存数量'], aggregations={'库存数量': 'sum'})
    errors = catalog.validate_plan_contract(plan, '各倉庫')
    assert any('維度' in item for item in errors)
    workflow = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer)
    link = models.SchemaLink(fact_text='ZX100', view=VIEW, column='品号', role='filter', operator='=', value='MADEUP')
    assert not workflow._filter_is_grounded(link, QUESTION, [])

def test_injected_execution_truncation_and_answer(tmp_path):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    calls = []
    def executor(datasource, sql):
        calls.append((datasource, sql))
        return ['仓库名称', '库存数量'], [['A', 10], ['B', 20], ['C', 30]]
    agent = Execution.SQLExecutionAgent(llm, catalog, executor=executor, settings=settings, retriever=retriever, context_packer=packer)
    result = agent.run(QUESTION, datasource='synthetic-datasource')
    assert len(calls) == result.attempts == 1
    assert calls[0][0] == 'synthetic-datasource'
    assert result.rows == [['A', 10], ['B', 20]] and result.rows_truncated
    assert result.generation.query_trace.execution_attempts == 1
    answer = Answering(llm, settings=settings, context_packer=packer).synthesize(QUESTION, result)
    assert answer.citations == ['[Source 1]']
    assert answer.rows_truncated and answer.rows == result.rows

def test_execution_failure_has_trace_without_retry(tmp_path):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    calls = []
    def executor(datasource, sql):
        calls.append(sql)
        raise RuntimeError('synthetic failure')
    agent = Execution.SQLExecutionAgent(llm, catalog, executor=executor, settings=settings, retriever=retriever, context_packer=packer)
    with pytest.raises(Execution.SQLExecutionError) as failure:
        agent.run(QUESTION, datasource='synthetic-datasource')
    assert len(calls) == 1 and llm.calls == 1
    assert failure.value.generation.query_trace.rejection_stage == 'execution'

def test_literal_escaping_and_row_bound(tmp_path):
    _, catalog, *_ = dependencies(tmp_path)
    plan = models.QueryPlan(source_views=[VIEW], select_columns=['品号'], filters=[models.QueryFilter(column='品号', operator='=', value="O'Brien")], limit=99)
    sql = Compiler.compile_single_view(plan, catalog, max_rows=2)
    assert 'TOP (2)' in sql and "N'O''Brien'" in sql

def test_descending_order_is_explicit_and_validated(tmp_path):
    _, catalog, *_ = dependencies(tmp_path)
    catalog.views()[0].policy['columns']['仓库名称']['capabilities'].append('order_by')
    plan = models.QueryPlan(source_views=[VIEW], select_columns=['仓库名称'],
                            order_by=['仓库名称'], order_directions={'仓库名称': 'desc'})
    assert Compiler.compile_single_view(plan, catalog).endswith('ORDER BY [仓库名称] DESC')
    with pytest.raises(Compiler.SQLPolicyError, match='order_directions'):
        Compiler.compile_single_view(plan.model_copy(update={'order_by': []}), catalog)


class MappingLLM(StubLLM):
    """Return editable raw JSON for the clause-mapping workflow."""

    def __init__(self, mutate=lambda mapping: None):
        super().__init__()
        self.mutate = mutate
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        raw = super().invoke(messages)
        if 'table定義:' not in messages[-1].content:
            return raw
        mapping = __import__('json').loads(raw.content)
        self.mutate(mapping)
        return SimpleNamespace(content=__import__('json').dumps(mapping, ensure_ascii=False))


def test_workflow_preserves_descending_order(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    catalog.views()[0].policy['columns']['仓库名称']['capabilities'].append('order_by')
    def add_order(mapping):
        mapping['order'] = [{'text': '各倉庫由高到低排序', 'column': '仓库名称', 'direction': 'desc'}]
    question = QUESTION + '請依各倉庫由高到低排序。'
    result = Workflow(MappingLLM(add_order), catalog, settings=settings,
                      retriever=retriever, context_packer=packer).invoke(question)
    assert result.supported
    assert result.query_plan.order_directions == {'仓库名称': 'desc'}
    assert result.sql.endswith('ORDER BY [仓库名称] DESC')


def test_workflow_compiles_distinct_count(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    catalog.views()[0].policy['columns']['库存数量']['aggregations'].append('count_distinct')
    def distinct_count(mapping):
        mapping['fields'][0]['aggregation'] = 'count_distinct'
    question = QUESTION + '請計算各倉庫去重後的庫存數量。'
    result = Workflow(MappingLLM(distinct_count), catalog, settings=settings,
                      retriever=retriever, context_packer=packer).invoke(question)
    assert result.supported
    assert result.query_plan.aggregations == {'库存数量': 'count_distinct'}
    assert 'COUNT(DISTINCT [库存数量])' in result.sql


def test_mapping_prompt_contains_approved_contract_without_samples(tmp_path):
    import json

    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    policy = catalog.views()[0].policy
    policy['samples'] = [{'品号': 'ZX100', '仓库名称': 'Synthetic West', '库存数量': 12}]
    policy['semantic_metadata'] = {'note': 'synthetic semantic note'}
    llm = MappingLLM()
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 1
    user_message = llm.messages[0][-1].content
    payload = json.loads(user_message.split('table定義: ', 1)[1])
    schema = payload['candidates'][0]
    assert set(schema) == {'view', 'summary', 'columns', 'temporal_scope', 'grain', 'filter_operators', 'scope_rules'}
    assert set(schema['columns']['库存数量']) == {'data_type', 'description', 'aliases', 'capabilities', 'aggregations', 'default_aggregation'}
    assert schema['columns']['库存数量']['data_type'] == 'number'
    assert schema['columns']['库存数量']['description'] == '合成數量'
    assert schema['columns']['库存数量']['aliases'] == ['庫存數量']
    assert schema['columns']['库存数量']['aggregations'] == ['sum']
    assert schema['columns']['库存数量']['default_aggregation'] == 'sum'
    assert schema['temporal_scope'] == 'current_snapshot'
    assert 'Synthetic West' not in user_message
    assert 'semantic_metadata' not in user_message


@pytest.mark.parametrize('mutation,expected', [
    ('invented_value', 'ungrounded filter'),
    ('absent_fact', 'fact absent'),
    ('unknown_column', 'column is not'),
    ('operator', 'operator not allowed'),
    ('extra_filter', 'prohibited scope'),
    ('view', 'table mapping does not match'),
    ('missing_group', '必須依維度彙總'),
])
def test_clause_mapping_keeps_guards(tmp_path, mutation, expected):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        criterion = mapping['criteria'][0]
        if mutation == 'invented_value': criterion['value'] = 'MADEUP'
        if mutation == 'absent_fact': criterion['text'] = 'absent'
        if mutation == 'unknown_column': criterion['column'] = 'absent'
        if mutation == 'operator': criterion['operator'] = 'DROP'
        if mutation == 'extra_filter':
            mapping['criteria'].append({'text': '各倉庫', 'column': '仓库名称', 'operator': '=', 'value': 'A'})
        if mutation == 'view': mapping['table']['view'] = 'other.v_inventory'
        if mutation == 'missing_group': mapping['group'] = []

    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert not result.supported and result.sql is None
    assert llm.calls == (1 if mutation == 'view' else 2)
    assert expected in str(result.limitations)


def test_accepts_model_column_names_but_grounds_them_in_request(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        mapping['fields'] = [
            {'text': '品号', 'column': '品号'},
            {'text': '库存数量', 'column': '库存数量', 'aggregation': 'sum'},
            {'text': '各倉庫', 'column': '仓库名称'},
        ]
        mapping['table'] = {'text': None, 'column': VIEW}
        mapping['criteria'][0].pop('value')

    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 1
    assert result.query_plan.select_columns == ['库存数量', '仓库名称']
    assert result.query_plan.filters[0].value == 'ZX100'
    assert {fact.text for fact in result.query_trace.request_facts} == {'ZX100', '庫存數量', '各倉庫'}


def test_multiple_view_mapping_is_rejected_without_keyword_check(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        mapping['table'] = [
            {'text': None, 'view': VIEW},
            {'text': None, 'view': 'other.v_inventory'},
        ]

    llm = MappingLLM(mutate)
    request = QUESTION.replace('請查詢', '請整合')
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(request)
    assert not result.supported and result.sql is None
    assert result.query_trace.rejection_stage == 'schema_selection'


def test_renamed_columns_follow_view_document(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    policy = catalog.views()[0].policy
    renamed = {'品号': 'item_key', '仓库名称': 'site_label', '库存数量': 'units'}
    policy['columns'] = {renamed[name]: spec for name, spec in policy['columns'].items()}
    for rule in policy['scope_rules']:
        rule['required_dimension'] = 'site_label'
        rule['prohibited_filter_columns'] = ['site_label']

    def mutate(mapping):
        for item in [*mapping['fields'], *mapping['criteria'], *mapping['group']]:
            item['column'] = renamed[item['column']]

    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 1
    assert '[item_key]' in result.sql and '[site_label]' in result.sql


def test_validation_error_repairs_same_candidate(tmp_path):
    import json

    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        if llm.calls == 1:
            mapping['fields'] = []

    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 2
    repair = json.loads(llm.messages[1][-1].content.split('table定義: ', 1)[1])['repair']
    assert repair['previous_mapping']['table']['view'] == VIEW
    assert repair['previous_mapping']['fields'] == []
    assert 'fields mapping is empty' in repair['validation_errors']
    assert [attempt.outcome for attempt in result.query_trace.mapping_attempts] == ['rejected', 'selected']


@pytest.mark.parametrize('include_second', [True, False])
def test_candidates_are_matched_one_view_at_a_time(tmp_path, include_second):
    import json
    import yaml
    from cpea.infrastructure.retrieval.documents import build_documents
    from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult
    from tests.support import Catalog, view_contract

    settings, _, packer, _, _ = dependencies(tmp_path)
    other = 'gms2.v_alternate'
    (tmp_path / 'alternate.yaml').write_text(
        yaml.safe_dump(view_contract(other), allow_unicode=True), encoding='utf-8')
    (tmp_path / 'catalog.yaml').write_text(yaml.safe_dump({'views': {
        VIEW: {'path': 'inventory.yaml'}, other: {'path': 'alternate.yaml'},
    }}, allow_unicode=True, sort_keys=False), encoding='utf-8')
    catalog = Catalog(tmp_path)
    documents = build_documents(catalog)
    candidates = [RetrievalCandidate(doc, 1.0 - index * 0.5)
                  for index, doc in enumerate(documents)]

    class Candidates:
        def retrieve(self, question):
            return RetrievalResult(question, candidates if include_second else candidates[:1], 0.0, 0.0)

    llm = MappingLLM(lambda mapping: mapping['table'].update(view=other))
    result = Workflow(llm, catalog, settings=settings, retriever=Candidates(),
                      context_packer=packer).invoke(QUESTION)
    payloads = [json.loads(messages[-1].content.split('table定義: ', 1)[1]) for messages in llm.messages]
    assert [[s['view'] for s in payload['candidates']] for payload in payloads] == (
        [[VIEW], [other]] if include_second else [[VIEW]])
    for payload in payloads:
        selected_view = payload['candidates'][0]['view']
        definitions = payload['response_schema']['$defs'].values()
        assert [definition['properties']['view']['enum'] for definition in definitions
                if 'view' in definition.get('properties', {})] == [[selected_view]]
        assert all(set(definition['properties']['column']['enum']) == set(payload['candidates'][0]['columns'])
                   for definition in definitions if 'column' in definition.get('properties', {}))
    if include_second:
        assert result.supported and llm.calls == 2
        assert result.selected_views == [other]
        assert {source.document_id for source in result.sources} == {other}
        assert [attempt.outcome for attempt in result.query_trace.candidate_attempts] == [
            'schema_mismatch', 'matched']
    else:
        assert not result.supported and result.sql is None
        assert 'table mapping does not match' in str(result.limitations)


@pytest.mark.parametrize('first_fails', [False, True])
def test_sequential_candidates_stop_on_first_compiled_sql(tmp_path, first_fails):
    import json
    import yaml
    from cpea.infrastructure.retrieval.documents import build_documents
    from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult
    from tests.support import Catalog, view_contract

    settings, _, packer, _, _ = dependencies(tmp_path)
    other = 'gms2.v_alternate'
    (tmp_path / 'alternate.yaml').write_text(
        yaml.safe_dump(view_contract(other), allow_unicode=True), encoding='utf-8')
    (tmp_path / 'catalog.yaml').write_text(yaml.safe_dump({'views': {
        VIEW: {'path': 'inventory.yaml'}, other: {'path': 'alternate.yaml'},
    }}, allow_unicode=True, sort_keys=False), encoding='utf-8')
    catalog = Catalog(tmp_path)
    candidates = [RetrievalCandidate(doc, 1.0 - index * 0.5)
                  for index, doc in enumerate(build_documents(catalog))]

    class Candidates:
        def retrieve(self, question):
            return RetrievalResult(question, candidates, 0.0, 0.0)

    def map_current_view(mapping):
        current = json.loads(llm.messages[-1][-1].content.split('table定義: ', 1)[1])['candidates'][0]['view']
        mapping['table']['view'] = current
        if first_fails and llm.calls <= 2:
            mapping['fields'][0]['aggregation'] = None

    llm = MappingLLM(map_current_view)
    result = Workflow(llm, catalog, settings=settings, retriever=Candidates(),
                      context_packer=packer).invoke(QUESTION)
    assert result.supported
    assert result.selected_views == ([other] if first_fails else [VIEW])
    assert llm.calls == (3 if first_fails else 1)
    assert [attempt.outcome for attempt in result.query_trace.candidate_attempts] == (
        ['validation_failed', 'validation_failed', 'matched'] if first_fails else ['matched'])


@pytest.mark.parametrize('sample', range(3))
def test_missing_arbitrary_identifier_filter_cannot_broaden_query(tmp_path, sample):
    from uuid import uuid4
    identifier = 'ID' + uuid4().hex[:8].upper()
    question = f'請查詢 {identifier} 目前各倉庫庫存數量'
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    llm = MappingLLM(lambda mapping: mapping.update(criteria=[]))
    result = Workflow(llm, catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke(question)
    assert not result.supported and result.sql is None
    assert identifier in str(result.limitations)


@pytest.mark.parametrize('explicit_null', [False, True])
def test_null_aggregation_keeps_raw_values_despite_catalog_default(tmp_path, explicit_null):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        field = {'text': '庫存數量', 'column': '库存数量'}
        if explicit_null:
            field['aggregation'] = None
        mapping['fields'] = [field]
        mapping['group'] = []
        mapping['ignored'] = []

    result = Workflow(MappingLLM(mutate), catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke('請列出 ZX100 的庫存數量')
    assert result.supported, result.limitations
    assert result.query_plan.aggregations == {}
    assert result.query_trace.links.links[-1].aggregation is None
    assert 'SUM(' not in result.sql
    assert '[库存数量]' in result.sql


def test_grouped_metric_without_aggregation_is_not_silently_summed(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        mapping['fields'][0]['aggregation'] = None

    result = Workflow(MappingLLM(mutate), catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke(QUESTION)
    assert not result.supported and result.sql is None
    assert result.query_trace.rejection_stage == 'sql_compilation'
    assert 'grouped query has unaggregated columns' in str(result.limitations)


def test_explicit_aggregation_must_still_pass_catalog_policy(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        mapping['fields'][0]['aggregation'] = 'avg'

    result = Workflow(MappingLLM(mutate), catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke(QUESTION)
    assert not result.supported and result.sql is None
    assert result.query_trace.rejection_stage == 'schema_linking'
    assert 'metric aggregation not allowed' in str(result.limitations)


@pytest.mark.parametrize('aggregation', ['SUM(x)', 'sum); DROP TABLE x; --'])
def test_mapping_rejects_aggregation_expressions(tmp_path, aggregation):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)

    def mutate(mapping):
        mapping['fields'][0]['aggregation'] = aggregation

    result = Workflow(MappingLLM(mutate), catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke(QUESTION)
    assert not result.supported and result.sql is None
    assert result.query_trace.rejection_stage == 'schema_linking'
