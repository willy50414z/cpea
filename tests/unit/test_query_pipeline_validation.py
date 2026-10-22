from dataclasses import replace

import pytest

from cpea.application.models.query_pipeline import TaskSQLInput
from cpea.config.database import DatabaseSettings
from cpea.workflows.query_pipeline.validation import preflight_tasks, validate_task_sql
from tests.decomposition_support import catalog_at, settings
from tests.query_pipeline_support import generation, planning


@pytest.fixture
def context(tmp_path):
    catalog = catalog_at(tmp_path)
    plan = planning(catalog)
    task = plan.draft.tasks[1]
    return catalog, plan, TaskSQLInput(original_request='九月銷量', task=task, contract_fingerprint=catalog.fingerprint)


@pytest.mark.parametrize('change', [
    {'conditional_metrics': [dict(column='quantity', aggregation='sum', conditions=[])]},
    {'metadata_collections': ['order_date']}, {'depends_on': ['stock']}, {'unbound_inputs': ['ids']},
    {'filters': [dict(column='quantity', operator='=', value=True)]},
    {'filters': [dict(column='quantity', operator='IS NULL', value=None)]},
    {'filters': [dict(column='quantity', operator='=', value=float('inf'))]},
    {'filters': [dict(column='quantity', operator='NOT IN', value=[1])]},
])
def test_batch_preflight_rejects_unsupported_capability(context, change):
    catalog, plan, _ = context
    from cpea.application.models.decomposition import PlanningTask
    plan.draft.tasks[1] = PlanningTask.model_validate(plan.draft.tasks[1].model_dump() | change)
    assert 'unsupported_task_capability' in {i.code for i in preflight_tasks(plan, catalog=catalog)}


@pytest.mark.parametrize('change', ['status', 'fingerprint', 'duplicate', 'prepared', 'missing'])
def test_stale_catalog_and_nonready_planning_do_not_dispatch(context, change):
    catalog, plan, _ = context
    if change == 'status': plan.status = 'unsupported'
    if change == 'fingerprint': plan.contract_fingerprint = 'old'
    if change == 'duplicate': plan.draft.tasks.append(plan.draft.tasks[0])
    if change == 'prepared': plan.prepared_requests[0].payload['request'] = '替代文字'
    if change == 'missing': plan.prepared_requests = []
    assert preflight_tasks(plan, catalog=catalog)


@pytest.mark.parametrize('change', [
    {'source_views': ['demo.stock']}, {'filters': []},
    {'filters': [dict(column='order_date', operator='>=', value='2026-08-01')]},
    {'filters': [dict(column='order_date', operator='>', value='2026-09-01'), dict(column='order_date', operator='<', value='2026-10-01')]},
    {'aggregations': {'quantity': 'avg'}}, {'group_by': ['store_id']},
    {'select_columns': ['quantity', 'store_id']},
    {'select_columns': ['quantity', 'store_id', 'product_id', 'order_date']},
    {'having': [dict(column='quantity', aggregation='sum', operator='>', value=1)]},
    {'order_by': ['quantity']}, {'order_directions': {'quantity': 'asc'}}, {'limit': 10},
])
def test_gate_rejects_semantic_drift(context, change):
    catalog, _, envelope = context
    output = generation(envelope.task, catalog, settings())
    output.query_plan = output.query_plan.model_copy(update=change)
    assert 'semantic_drift' in {i.code for i in validate_task_sql(envelope, output, catalog=catalog, settings=settings())}


def test_gate_accepts_condition_order_and_in_value_order_equivalence(context):
    catalog, _, envelope = context
    from cpea.application.models.decomposition import PlanningFilter
    envelope.task.filters.append(PlanningFilter(column='sales_channel', operator='IN', value=['online', 'in_store']))
    envelope.task.required_columns.append('sales_channel')
    output = generation(envelope.task, catalog, settings())
    output.query_plan.filters.reverse()
    output.query_plan.filters[0].value.reverse()
    from cpea.infrastructure.sql_compiler import compile_single_view
    output.sql = compile_single_view(output.query_plan, catalog, max_rows=settings().max_rows)
    assert not validate_task_sql(envelope, output, catalog=catalog, settings=settings())


def test_gate_rejects_sql_that_differs_from_recompiled_plan(context):
    catalog, _, envelope = context
    output = generation(envelope.task, catalog, settings())
    output.sql += ' AND [quantity] > 0'
    assert 'sql_mismatch' in {i.code for i in validate_task_sql(envelope, output, catalog=catalog, settings=settings())}
    output.sql = 'SELECT * FROM demo.stock; DROP TABLE x'
    assert 'sql_policy_violation' in {i.code for i in validate_task_sql(envelope, output, catalog=catalog, settings=settings())}


@pytest.mark.parametrize('dialect', ['mssql', 'postgresql'])
def test_gate_rejects_wrong_dialect_and_unapproved_source(context, dialect):
    catalog, _, envelope = context
    conf = replace(settings(), database=DatabaseSettings(dialect=dialect))
    output = generation(envelope.task, catalog, conf)
    assert not validate_task_sql(envelope, output, catalog=catalog, settings=conf)
    wrong = replace(conf, database=DatabaseSettings(dialect='postgresql' if dialect == 'mssql' else 'mssql'))
    assert validate_task_sql(envelope, output, catalog=catalog, settings=wrong)
    output.selected_views = ['demo.stock']
    assert 'semantic_drift' in {i.code for i in validate_task_sql(envelope, output, catalog=catalog, settings=conf)}


def test_handoff_too_long_is_rejected_without_truncation(context):
    from cpea.application.models.decomposition import PlanningFilter
    catalog, plan, _ = context
    task = plan.draft.tasks[1]
    task.required_columns.append('sales_channel')
    task.filters.append(PlanningFilter(column='sales_channel', operator='=', value='x' * 4000))
    assert [i.code for i in preflight_tasks(plan, catalog=catalog)] == ['handoff_too_long']
