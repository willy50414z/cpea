"""Fixed named identity slots retain all existing semantic guards, offline only."""
from copy import deepcopy
import importlib
import importlib.util
import json

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.three_stage_view_selection import RecallResult, finish_selection
from test_three_stage_view_selection import INV, SALES, MONTH, REQUEST, recall, selection
from test_referenced_view_coverage import referenced


def api():
    name = 'evaluations.slotted_view_coverage'
    assert importlib.util.find_spec(name) is not None, 'fixed named coverage slots are not implemented'
    return importlib.import_module(name)


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def policy(catalog, view=INV):
    return next(v.policy for v in catalog.views() if v.name == view)


def slots(catalog, view=INV):
    return dict(entries={e['requirement_id']: {k: v for k, v in e.items() if k != 'requirement_id'}
                         for e in referenced(catalog, view)['entries']})


def materialize(catalog, data, view=INV, rec=None, source=None):
    rec = rec or recall(catalog)
    wire = api().parse_slots(AIMessage(content=json.dumps(data, ensure_ascii=False)), api().coverage_schema(rec))
    return api().materialize_slots(wire, rec, REQUEST, catalog, source or policy(catalog, view))


@pytest.mark.parametrize('ids', [['庫存'], ['model_dump', '_private', 'a/b~c', 'quote"\\\n', 'slot_0', '中文🧾']])
def test_required_named_schema_handles_arbitrary_ids_without_position_or_reserved_name_loss(catalog, ids):
    rec = recall(catalog).model_dump()
    original = rec['requirements'][0]
    rec['requirements'] = [dict(original, requirement_id=i) for i in ids]
    rec = RecallResult.model_validate(rec)
    schema = api().coverage_schema(rec)
    spec = schema.model_json_schema()
    entry_spec = spec['$defs'][spec['properties']['entries']['$ref'].rsplit('/', 1)[1]]
    assert set(entry_spec['properties']) == set(ids)
    assert set(entry_spec['required']) == set(ids)
    assert entry_spec['additionalProperties'] is False
    data = {'entries': {i: dict(status='unsupported', mappings=[], contract_path=None,
                               missing_requirements=['缺口:' + i]) for i in reversed(ids)}}
    result = api().materialize_slots(api().parse_slots(AIMessage(content=json.dumps(data)), schema),
                                     rec, REQUEST, catalog, policy(catalog))
    assert [e.requirement_id for e in result.entries] == ids
    assert [e.missing_requirements for e in result.entries] == [['缺口:' + i] for i in ids]


def test_trusted_source_facts_come_from_exact_summary_and_partial_is_retained(catalog):
    result = materialize(catalog, slots(catalog, MONTH), MONTH)
    source = policy(catalog, MONTH)
    assert result.view == MONTH
    assert result.grain == source['grain']['description']
    assert result.keys == source['grain']['keys']
    assert result.population == source['summary']
    assert result.contract_evidence[0].path == '/summary'
    assert result.contract_evidence[0].quote == source['summary']
    sales = next(e for e in result.entries if e.requirement_id == 'sales')
    assert sales.status == 'partial' and sales.missing_requirements
    assert {m.column for m in sales.mappings} == {'discount_amount', 'net_sales'}


@pytest.mark.parametrize('summary', ['僅含已完成訂單。', '來源明確排除退貨，僅含已完成訂單。'])
def test_summary_text_is_preserved_without_inferred_exclusion(catalog, monkeypatch, summary):
    source = policy(catalog, SALES)
    source['summary'] = summary
    # Catalog policies are the only accepted source, including explicit exclusions.
    original = catalog.views
    monkeypatch.setattr(catalog, 'views', lambda: [type('View', (), {'name': v.name,
        'policy': source if v.name == SALES else v.policy})() for v in original()])
    assert materialize(catalog, slots(catalog, SALES), SALES).population == summary


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'old_list', 'id', 'population', 'view', 'grain', 'keys'])
def test_invalid_slot_shape_and_source_overrides_are_rejected(catalog, mutation):
    data = slots(catalog)
    if mutation == 'missing': data['entries'].pop('stock')
    if mutation == 'extra': data['entries']['extra'] = deepcopy(data['entries']['stock'])
    if mutation == 'old_list': data['entries'] = list(data['entries'].values())
    if mutation == 'id': data['entries']['stock']['requirement_id'] = 'stock'
    if mutation in ('population', 'view', 'grain', 'keys'): data[mutation] = 'invented source fact'
    with pytest.raises(ValueError):
        materialize(catalog, data)


@pytest.mark.parametrize('raw', [
    '{"entries":{},"entries":{}}',
    '{"entries":{"stock":{"status":"unsupported"},"stock":{"status":"unsupported"}}}',
    '{"entries":{"stock":{"status":"supported"},"stock":{"status":"unsupported"}}}',
    '{"entries":{"stock":{"mappings":[{"column":"stock_qty","column":"net_sales"}]}}}',
    '{"entries":{"stock":{"mappings":[{"conditions":[{"value":1,"value":2}]}]}}}',
])
def test_duplicate_json_keys_are_rejected_before_schema_or_last_wins(catalog, raw):
    with pytest.raises(ValueError, match='duplicate JSON key'):
        api().parse_slots(AIMessage(content=raw), api().coverage_schema(recall(catalog)))


@pytest.mark.parametrize('raw', ['```json\n{}\n```', '{"entries": NaN}', '{"entries":{}} trailing'])
def test_slot_parser_requires_original_valid_json(catalog, raw):
    with pytest.raises(ValueError):
        api().parse_slots(AIMessage(content=raw), api().coverage_schema(recall(catalog)))


@pytest.mark.parametrize('mutation', ['wrong_role', 'fake_column', 'bad_path', 'empty_supported',
                                      'monthly_scope', 'monthly_channel', 'metadata_empty'])
def test_slot_adapter_keeps_all_field_role_scope_and_evidence_guards(catalog, mutation):
    view = MONTH if mutation.startswith('monthly') else INV
    data = slots(catalog, view)
    if mutation == 'wrong_role': data['entries']['stock']['mappings'][0]['role'] = 'attribute'
    if mutation == 'fake_column': data['entries']['stock']['mappings'][0]['column'] = 'invented'
    if mutation == 'bad_path': data['entries']['stock']['contract_path'] = '/not-real'
    if mutation == 'empty_supported': data['entries']['stock']['mappings'] = []
    if mutation == 'monthly_scope': data['entries']['sales'].update(status='supported', missing_requirements=[])
    if mutation == 'monthly_channel':
        data['entries']['channel'].update(status='supported', mappings=[dict(column='sales_channel',role='filter',operator='=',value='online')],missing_requirements=[])
    if mutation == 'metadata_empty':
        rec = recall(catalog).model_dump()
        rec['requirements'][0]['kind'] = 'metadata'
        data['entries']['stock']['mappings'] = []
        with pytest.raises(ValueError): materialize(catalog, data, rec=RecallResult.model_validate(rec))
        return
    with pytest.raises(ValueError): materialize(catalog, data, view)


@pytest.mark.parametrize('source_change', ['summary_missing', 'summary_empty', 'unadmitted', 'modified'])
def test_adapter_fails_closed_without_exact_valid_admitted_source(catalog, source_change):
    source = deepcopy(policy(catalog))
    if source_change == 'summary_missing': source.pop('summary')
    if source_change == 'summary_empty': source['summary'] = ''
    if source_change == 'unadmitted': source['view'] = 'not_admitted'
    if source_change == 'modified': source['summary'] += ' 不含退貨'
    with pytest.raises(ValueError): materialize(catalog, slots(catalog), source=source)


def test_program_bound_population_is_not_auto_supported(catalog):
    data = slots(catalog, SALES)
    data['entries']['population'].update(status='unsupported', mappings=[], contract_path='/summary',missing_requirements=['只有銷售鍵，不保證完整庫存母體'])
    row = next(e for e in materialize(catalog, data, SALES).entries if e.requirement_id == 'population')
    assert row.status == 'unsupported' and row.missing_requirements == ['只有銷售鍵，不保證完整庫存母體']


@pytest.mark.parametrize('mutation', ['inner', 'grain', 'zero'])
def test_slot_normalization_cannot_bypass_selection_population_grain_or_no_zero(catalog, mutation):
    mapped = [materialize(catalog, slots(catalog, v.name), v.name) for v in catalog.views()]
    selected = selection(catalog).model_dump()
    if mutation == 'inner': selected['draft']['integration']['edges'][0].update(mode='inner', preserve_task=None)
    if mutation == 'grain': selected['draft']['integration']['output_grain'] = ['product_id']
    if mutation == 'zero': selected['draft']['integration']['missing_data_policy'] = '未匹配銷售補零'
    from evaluations.three_stage_view_selection import SelectionResult
    with pytest.raises(ValueError):
        finish_selection(SelectionResult.model_validate(selected), recall(catalog), mapped, REQUEST, catalog)


def test_same_source_scope_rejects_inventory_date_substitution_at_selection(catalog):
    inventory = slots(catalog, INV)
    inventory['entries']['period'].update(status='supported', contract_path='/columns/snapshot_date/description',
        mappings=[dict(column='snapshot_date',role='filter',operator='>=',value='2026-09-01')], missing_requirements=[])
    # A date-capable field alone is structurally valid; intent still needs model/semantic review.
    mapped = [materialize(catalog, inventory if v.name == INV else slots(catalog, v.name), v.name)
              for v in catalog.views()]
    selected = selection(catalog).model_dump()
    next(a for a in selected['assignments'] if a['requirement_id']=='period').update(view=INV, task_id='stock')
    selected['draft']['tasks'][0]['required_columns'].append('snapshot_date')
    selected['draft']['tasks'][0]['filters'] = [dict(column='snapshot_date',operator='>=',value='2026-09-01')]
    selected['draft']['tasks'][1]['filters'] = [dict(column='sales_channel',operator='=',value='online')]
    from evaluations.three_stage_view_selection import SelectionResult
    with pytest.raises(ValueError,match='scope mapping'):
        finish_selection(SelectionResult.model_validate(selected), recall(catalog), mapped, REQUEST, catalog)
