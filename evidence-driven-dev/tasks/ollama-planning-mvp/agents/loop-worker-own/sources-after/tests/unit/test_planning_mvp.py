"""Safety boundaries for the experimental, offline planning harness."""
import json
from pathlib import Path

import pytest

from cpea.application.models.decomposition import DecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.planning_mvp import close_columns, finish, semantic_check, compile_plan, SemanticPlan


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    not (ROOT / 'projects/retail/manifest.yaml').is_file(),
    reason='private Retail profile is not installed',
)


@pytest.fixture
def catalog():
    return SchemaCatalog(ROOT / 'projects/retail')


def case(number):
    rows = [json.loads(s) for s in (ROOT / 'projects/retail/evaluations/task_decomposition_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    return rows[number - 1]


def canonical(number):
    c = case(number)
    tasks = [{k: v for k, v in t.items() if k not in ('acceptable_alternatives',)} for t in c['expected_tasks']]
    for t in tasks:
        t['request'] = '依型別欄位準備資料'
    anchor = tasks[0]
    edges = []
    preparation = []
    fixed = {f['column'] for f in anchor.get('filters', []) if f['operator'] == '='}
    root = [k for k in anchor['output_grain'] if k not in fixed]
    for t in tasks[1:]:
        keys = [k for k in root if k in t['output_grain']]
        child_fixed = {f['column'] for f in t.get('filters', []) if f['operator'] == '='}
        finer = set(t['output_grain']) - child_fixed - set(keys)
        cardinality = 'many_to_one' if set(root) - set(keys) else 'one_to_many' if finer else 'one_to_one'
        edges.append(dict(left_task=anchor['task_id'], right_task=t['task_id'], left_keys=keys, right_keys=keys,
                          mode='left', cardinality=cardinality, preserve_task=anchor['task_id']))
        if finer:
            preparation.append(dict(task_id=t['task_id'], kind='nest', keys=keys, description='保留子集合'))
    return DecompositionDraft(status='ready', strategy=c['expected_strategy'], tasks=tasks,
                              integration=dict(anchor_task=anchor['task_id'], output_grain=root,
                                               edges=edges, preparation=preparation))


def test_closure_only_adds_typed_references_and_does_not_mutate(catalog):
    d = canonical(7)
    d.tasks[1].required_columns.remove('sales_channel')
    before = d.model_dump()
    closed, additions = close_columns(d, catalog)
    assert 'sales_channel' in closed.tasks[1].required_columns
    assert additions and d.model_dump() == before
    assert semantic_check(case(7), finish(closed, catalog), catalog)['safe']


def test_closure_rejects_invented_metric_instead_of_renaming(catalog):
    d = canonical(26)
    d.tasks[1].metrics['order_count'] = 'count'
    with pytest.raises(ValueError, match='order_count'):
        close_columns(d, catalog)


@pytest.mark.parametrize('mutation', ['channel', 'population', 'nest', 'grain', 'attribute', 'extra_metric'])
def test_semantic_check_catches_valid_but_wrong_plans(catalog, mutation):
    number = 20 if mutation in ('nest', 'grain') else 7
    d = canonical(number)
    assert semantic_check(case(number), finish(d, catalog), catalog)['safe']
    if mutation == 'channel':
        d.tasks[1].filters = [f for f in d.tasks[1].filters if f.column != 'sales_channel']
    elif mutation == 'population':
        d.integration.edges[0].mode = 'inner'
    elif mutation == 'nest':
        d.integration.preparation = []
    elif mutation == 'grain':
        d.integration.output_grain.append('product_id')
    elif mutation == 'attribute':
        d.tasks[0].attributes.remove('stock_qty')
    elif mutation == 'extra_metric':
        d.tasks[1].metrics['gross_margin_pct'] = 'avg'
    assert not semantic_check(case(number), finish(d, catalog), catalog)['safe']


def test_compiler_keeps_child_grain_separate_and_supplies_closure(catalog):
    d = canonical(20)
    p = {'status':'ready', 'anchor_task':d.tasks[0].task_id, 'root_grain':['customer_id'],
         'tasks':[{**{k:v for k,v in t.model_dump().items() if k in ('task_id','view','filters','metrics','conditional_metrics','attributes','metadata_collections')},
                   'query_grain':t.output_grain} for t in d.tasks],
         'links':[{'parent':d.tasks[0].task_id,'child':d.tasks[1].task_id,'parent_keys':['customer_id'],
                   'child_keys':['customer_id'],'mode':'left','shape':'collection','cardinality':'one_to_many'}]}
    compiled = compile_plan(SemanticPlan.model_validate(p), catalog)
    assert compiled.integration.output_grain == ['customer_id']
    assert compiled.tasks[1].output_grain == ['customer_id','product_id']
    assert compiled.integration.preparation[0].keys == ['customer_id']
    assert semantic_check(case(20), finish(compiled, catalog), catalog)['safe']


def test_compiler_does_not_repair_unknown_columns_or_missing_period(catalog):
    d = canonical(7)
    d.tasks[1].filters = [f for f in d.tasks[1].filters if f.column == 'sales_channel']
    closed, _ = close_columns(d, catalog)
    assert not semantic_check(case(7), finish(closed, catalog), catalog)['safe']


def test_singleton_count_does_not_substitute_for_a_requested_value(catalog):
    d = canonical(7)
    d.tasks[0].attributes.remove('stock_qty')
    d.tasks[0].metrics['stock_qty'] = 'count'
    d.tasks[0].group_by = list(d.tasks[0].output_grain)
    assert not semantic_check(case(7), finish(d, catalog), catalog)['safe']


def test_nested_store_only_join_does_not_satisfy_product_alignment(catalog):
    d = canonical(7)
    e = d.integration.edges[0]
    e.left_keys = e.right_keys = ['store_id']
    e.cardinality = 'many_to_one'
    from cpea.application.models.decomposition import Preparation
    d.integration.preparation.append(Preparation(task_id=d.tasks[1].task_id, kind='nest', keys=['store_id'], description='全店商品集合'))
    assert not semantic_check(case(7), finish(d, catalog), catalog)['safe']
