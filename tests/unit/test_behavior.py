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
    assert llm.calls == 2

@pytest.mark.parametrize('question,stage', [('請 JOIN 兩個資料表', 'schema_selection'), ('請查第一季庫存數量', 'request_ambiguity')])
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
    assert workflow._temporal_mismatch(VIEW, '2025年歷史庫存') is not None

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
    assert len(calls) == 1 and llm.calls == 2
    assert failure.value.generation.query_trace.rejection_stage == 'execution'

def test_literal_escaping_and_row_bound(tmp_path):
    _, catalog, *_ = dependencies(tmp_path)
    plan = models.QueryPlan(source_views=[VIEW], select_columns=['品号'], filters=[models.QueryFilter(column='品号', operator='=', value="O'Brien")], limit=99)
    sql = Compiler.compile_single_view(plan, catalog, max_rows=2)
    assert 'TOP (2)' in sql and "N'O''Brien'" in sql
