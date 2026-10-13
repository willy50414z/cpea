from dataclasses import replace
import pytest
from tests.support import *

def test_single_view_generation_and_trace(tmp_path):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported
    assert result.sql == "SELECT TOP (2) SUM([库存数量]) AS [库存数量], [仓库名称] FROM gms2.v_inventory WHERE [品号] = N'ZX100' GROUP BY [仓库名称]"
    assert result.query_trace.selected_view == VIEW
    assert result.query_trace.rejection_stage is None
    assert result.query_trace.candidate_attempts[0].outcome == 'matched'
    assert llm.calls == 1
    assert result.query_trace.links.view_satisfied[0].fact_text == '目前'
    assert len(result.query_trace.request_facts) == 4

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


class MappingLLM(StubLLM):
    """Script model choices explicitly; these tests do not measure LLM accuracy."""
    def __init__(self, mutate=lambda draft: draft):
        super().__init__()
        self.mutate = mutate
        self.messages = []

    def with_structured_output(self, model, **kwargs):
        original = super().with_structured_output(model, **kwargs)
        def invoke(messages):
            self.messages.append(messages)
            return self.mutate(original.invoke(messages))
        return SimpleNamespace(invoke=invoke)


def test_mapping_prompt_contains_full_policy_and_samples(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    policy = catalog.views()[0].policy
    policy['samples'] = [{'品号': 'ZX100', '仓库名称': 'Synthetic West', '库存数量': 12}]
    policy['term_mappings'] = []
    policy['semantic_metadata'] = {'note': 'synthetic semantic note'}
    llm = MappingLLM()
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 1
    content = llm.messages[0][-1].content
    assert all(item in content for item in [QUESTION, 'Synthetic West', 'semantic_metadata', 'scope_rules', 'term_mappings', 'capabilities'])


@pytest.mark.parametrize('mutation,expected', [
    ('invented_value', 'ungrounded filter'), ('missing_fact', 'unlinked items'),
    ('invented_fact', 'fact absent'), ('unknown_column', 'column is not'),
    ('operator', 'operator not allowed'), ('extra_filter', 'prohibited scope'),
    ('view', 'unselected view'), ('view_satisfied_entity', 'invalid View-satisfied'),
])
def test_single_call_mapping_keeps_guards(tmp_path, mutation, expected):
    from cpea.workflows.text_to_sql.schemas import ViewSatisfiedFact
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    def mutate(draft):
        link = draft.links[0]
        if mutation == 'invented_value': link.value = 'MADEUP'
        if mutation == 'missing_fact': draft.links.pop(0)
        if mutation == 'invented_fact': draft.facts[0].text = 'absent'
        if mutation == 'unknown_column': link.column = 'absent'
        if mutation == 'operator': link.operator = 'DROP'
        if mutation == 'view': link.view = 'other.v_inventory'
        if mutation == 'extra_filter':
            draft.links.append(models.SchemaLink(fact_text='各倉庫', view=VIEW, column='仓库名称', role='filter', operator='=', value='A'))
        if mutation == 'view_satisfied_entity':
            draft.links.pop(0)
            draft.view_satisfied.append(ViewSatisfiedFact(fact_text='ZX100', reason='pretend satisfied'))
        return draft
    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert not result.supported and result.sql is None and llm.calls == 2
    assert expected in str(result.limitations)


def test_model_can_use_other_current_time_word_without_python_exclusion(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    def mutate(draft):
        draft.facts[1].text = '此刻'
        draft.view_satisfied[0].fact_text = '此刻'
        return draft
    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION.replace('目前', '此刻'))
    assert result.supported and llm.calls == 1
    assert len(result.query_plan.filters) == 1
    assert result.query_trace.links.view_satisfied[0].fact_text == '此刻'


def test_model_reports_unsupported_history_without_temporal_regex(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    def mutate(draft):
        draft.supported = False
        draft.facts[1].text = '去年'
        draft.view_satisfied = []
        draft.unresolved_facts = ['去年']
        draft.explanation = 'current snapshot cannot answer historical stock'
        return draft
    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION.replace('目前', '去年'))
    assert not result.supported and result.sql is None
    assert '去年' in result.query_trace.candidate_attempts[0].unresolved


def test_renamed_columns_require_no_business_mapping_code(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    policy = catalog.views()[0].policy
    renamed = {'品号': 'item_key', '仓库名称': 'site_label', '库存数量': 'units'}
    policy['columns'] = {renamed[k]: v for k, v in policy['columns'].items()}
    for rule in policy['scope_rules']:
        rule['required_dimension'] = 'site_label'
        rule['prohibited_filter_columns'] = ['site_label']
    policy['samples'] = [{'item_key': 'ZX100', 'site_label': 'A', 'units': 1}]
    def mutate(draft):
        for link in draft.links: link.column = renamed[link.column]
        return draft
    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 1
    assert '[item_key]' in result.sql and '[site_label]' in result.sql


def test_model_ambiguity_is_not_overridden_by_mandatory_links(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    def mutate(draft):
        draft.supported = False
        draft.links = []
        draft.unresolved_facts = ['ZX100']
        draft.ambiguity = ['samples do not establish the requested mapping']
        return draft
    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert not result.supported and not result.query_trace.candidate_attempts[0].links


def test_repair_can_succeed_without_fact_extraction_call(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    def mutate(draft):
        if llm.calls == 1: draft.links[0].value = 'MADEUP'
        return draft
    llm = MappingLLM(mutate)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever, context_packer=packer).invoke(QUESTION)
    assert result.supported and llm.calls == 2
    assert 'ungrounded filter' in llm.messages[1][-1].content
