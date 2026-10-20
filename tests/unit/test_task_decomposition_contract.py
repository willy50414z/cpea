from copy import deepcopy
import pytest
from pydantic import ValidationError

from tests.decomposition_support import catalog_at, draft


def api():
    from cpea.application.models.decomposition import DecompositionDraft
    from cpea.workflows.task_decomposition.validation import validate_decomposition, prepare_requests
    return DecompositionDraft, validate_decomposition, prepare_requests


def test_ready_plan_requires_admitted_views_and_all_used_columns(tmp_path):
    model, validate, prepare = api()
    catalog = catalog_at(tmp_path)
    plan = model.model_validate(draft())
    assert validate(plan,catalog)==[]
    requests = prepare(plan,catalog)
    assert len(requests)==2
    assert requests[1].payload['history']==[]
    assert '2026-09-01' in requests[1].payload['request']
    assert 'quantity' in requests[1].payload['request']
    for kind in ('view','filter','metric','group','edge'):
        bad=deepcopy(draft())
        if kind=='view': bad['tasks'][1]['view']='demo.secret'
        if kind=='filter': bad['tasks'][1]['filters'][0]['column']='missing'
        if kind=='metric': bad['tasks'][1]['metrics']={'quantity':'avg'};bad['tasks'][1]['required_columns'].remove('quantity')
        if kind=='group': bad['tasks'][1]['group_by'].append('missing')
        if kind=='edge': bad['integration']['edges'][0]['right_keys']=['missing','product_id']
        plan=model.model_validate(bad)
        assert validate(plan,catalog),kind
        with pytest.raises(ValueError): prepare(plan,catalog)


@pytest.mark.parametrize('mode',['unknown','cycle','self','duplicate'])
def test_dependencies_are_known_acyclic_and_not_self_referencing(tmp_path,mode):
    model, validate, _=api();data=draft()
    if mode=='unknown': data['tasks'][0]['depends_on']=['other']
    if mode=='cycle': data['tasks'][0]['depends_on']=['sales'];data['tasks'][1]['depends_on']=['stock']
    if mode=='self': data['tasks'][0]['depends_on']=['stock']
    if mode=='duplicate': data['tasks'][1]['task_id']='stock'
    assert validate(model.model_validate(data),catalog_at(tmp_path))


@pytest.mark.parametrize('status',['unsupported','needs_clarification','error'])
def test_non_ready_and_unbound_plans_expose_no_dispatch_payload(tmp_path,status):
    model, _, prepare=api();data=draft();data['status']=status
    assert prepare(model.model_validate(data),catalog_at(tmp_path))==[]
    data=draft();data['tasks'][1]['unbound_inputs']=['product_ids']
    with pytest.raises(ValueError):prepare(model.model_validate(data),catalog_at(tmp_path))


def test_three_source_edges_use_store_key_for_kpi(tmp_path):
    model,validate,_=api();data=draft()
    data['tasks'].append({'task_id':'kpi','view':'demo.kpi','required_columns':['store_id','sales_month','target_amount'],
                          'output_grain':['store_id'],'attributes':['target_amount'],
                          'filters':[{'column':'sales_month','operator':'=','value':'2026-09-01'}],'request':'門市目標'})
    data['integration']['edges'].append({'left_task':'stock','right_task':'kpi','left_keys':['store_id'],
        'right_keys':['store_id'],'mode':'left','cardinality':'many_to_one','preserve_task':'stock'})
    catalog=catalog_at(tmp_path)
    assert validate(model.model_validate(data),catalog)==[]
    data['integration']['edges'][1]['right_keys'].append('product_id')
    assert validate(model.model_validate(data),catalog)


def test_extra_model_fields_are_rejected():
    model,_,_=api();data=draft();data['sql']='SELECT secret'
    with pytest.raises(ValidationError):model.model_validate(data)


@pytest.mark.parametrize('corruption',['swapped_keys','lost_anchor','raw_grain','join_filter_key'])
def test_review_integration_and_grain_counterexamples(tmp_path,corruption):
    model,validate,_=api();data=draft()
    e=data['integration']['edges'][0]
    if corruption=='swapped_keys':e['right_keys'].reverse()
    if corruption=='lost_anchor':e.update(left_task='sales',right_task='stock',preserve_task='sales')
    if corruption=='raw_grain':data['tasks'][1].update(metrics={},group_by=[])
    if corruption=='join_filter_key':data['tasks'][1]['filters'].append({'column':'product_id','operator':'=','value':'not-a-number'})
    assert validate(model.model_validate(data),catalog_at(tmp_path)),corruption


@pytest.mark.parametrize('operator,value',[('>=',None),('LIKE','2026-09%')])
def test_invalid_date_filters_cannot_dispatch(tmp_path,operator,value):
    model,validate,prepare=api();data=draft();data['tasks'][1]['filters'][0].update(operator=operator,value=value)
    catalog=catalog_at(tmp_path)
    assert validate(model.model_validate(data),catalog)
    with pytest.raises(ValueError):prepare(model.model_validate(data),catalog)


def test_fixed_source_key_proves_redundant_output_dimension_is_single_row(tmp_path):
    model,validate,_=api();data=draft()
    data['tasks'][0]={'task_id':'stock','view':'demo.kpi',
        'required_columns':['store_id','sales_month','target_amount'],
        'filters':[{'column':'sales_month','operator':'=','value':'2026-09-01'}],
        'attributes':['target_amount'],'output_grain':['store_id','sales_month'],'request':'單月門市目標'}
    data['integration']['output_grain']=['store_id','sales_month']
    data['integration']['edges'][0].update(left_keys=['store_id'],right_keys=['store_id'],cardinality='one_to_many')
    data['integration']['preparation']=[{'task_id':'sales','kind':'nest','keys':['store_id'],'description':'各店商品銷量子集合'}]
    assert validate(model.model_validate(data),catalog_at(tmp_path))==[]


def test_time_metadata_collection_survives_prepared_request_without_changing_grain(tmp_path):
    import json
    model, validate, prepare = api()
    data = draft()
    task = data['tasks'][0]
    task.update(required_columns=['store_id', 'stock_qty', 'snapshot_date'],
                attributes=[], metrics={'stock_qty': 'sum'}, group_by=['store_id'],
                output_grain=['store_id'], metadata_collections=['snapshot_date'])
    data['tasks'][1].update(group_by=['store_id'], output_grain=['store_id'])
    data['integration']['output_grain'] = ['store_id']
    data['integration']['edges'][0].update(left_keys=['store_id'], right_keys=['store_id'])
    catalog = catalog_at(tmp_path)
    plan = model.model_validate(data)
    assert validate(plan, catalog) == []
    request = prepare(plan, catalog)[0].payload['request']
    payload = json.loads(request.split('\n')[-1])
    assert payload['metadata_collections'] == ['snapshot_date']
    assert payload['output_grain'] == ['store_id']
    assert 'DISTINCT' in request


@pytest.mark.parametrize('column', ['missing', 'stock_qty', 'store_id'])
def test_metadata_collections_reject_unadmitted_or_numeric_columns(tmp_path, column):
    model, validate, prepare = api()
    data = draft()
    task = data['tasks'][0]
    task['metadata_collections'] = [column]
    if column != 'missing' and column not in task['required_columns']:
        task['required_columns'].append(column)
    plan = model.model_validate(data)
    catalog = catalog_at(tmp_path)
    assert validate(plan, catalog)
    with pytest.raises(ValueError):
        prepare(plan, catalog)


@pytest.mark.parametrize('overlap', ['output_grain', 'conditional_metric', 'duplicate', 'attribute'])
def test_metadata_collection_cannot_duplicate_another_output_role(tmp_path, overlap):
    model, validate, _ = api()
    data = draft()
    task = data['tasks'][0]
    task['required_columns'].append('snapshot_date')
    task['metadata_collections'] = ['snapshot_date']
    if overlap == 'conditional_metric':
        task['conditional_metrics'] = [dict(column='snapshot_date', aggregation='count_distinct',
                                           conditions=[dict(column='stock_qty', operator='=', value=0)])]
        task['group_by'] = list(task['output_grain'])
    elif overlap == 'duplicate':
        task['metadata_collections'].append('snapshot_date')
    elif overlap == 'attribute':
        task['attributes'].append('snapshot_date')
    else:
        task['output_grain'].append('snapshot_date')
    assert validate(model.model_validate(data), catalog_at(tmp_path))


@pytest.mark.parametrize('output_grain,accepted', [(['store_id'], True), (['store_id', 'product_id'], False)])
def test_metadata_only_aggregation_still_has_an_explicit_grouping_grain(tmp_path, output_grain, accepted):
    model, validate, _ = api()
    task = dict(task_id='dates', view='demo.stock',
                required_columns=['store_id', 'product_id', 'snapshot_date'],
                metadata_collections=['snapshot_date'], group_by=['store_id'],
                output_grain=output_grain, request='按店收集盤點日期')
    data = dict(status='ready', strategy='single_view', tasks=[task],
                integration=dict(anchor_task='dates', output_grain=output_grain))
    assert (not validate(model.model_validate(data), catalog_at(tmp_path))) is accepted


@pytest.mark.parametrize('restriction', ['measure', 'select_forbidden'])
def test_metadata_respects_field_role_and_selection_capability(tmp_path, monkeypatch, restriction):
    model, validate, prepare = api()
    data = draft()
    task = data['tasks'][0]
    task.update(required_columns=task['required_columns'] + ['snapshot_date'],
                metadata_collections=['snapshot_date'], group_by=task['output_grain'])
    catalog = catalog_at(tmp_path)
    field_contract = catalog.field_contract
    def restricted(view, column):
        contract = dict(field_contract(view, column))
        if column == 'snapshot_date':
            if restriction == 'measure':
                contract['role'] = 'measure'
            else:
                contract['capabilities'] = [c for c in contract['capabilities'] if c != 'select']
        return contract
    monkeypatch.setattr(catalog, 'field_contract', restricted)
    plan = model.model_validate(data)
    assert validate(plan, catalog)
    with pytest.raises(ValueError):
        prepare(plan, catalog)


@pytest.mark.parametrize('prepared', [False, True])
def test_reducing_raw_anchor_grain_requires_explicit_collection(tmp_path, prepared):
    model, validate, _ = api()
    data = draft()
    data['tasks'] = data['tasks'][:1]
    data['strategy'] = 'single_view'
    data['integration'].update(output_grain=['store_id'], edges=[], preparation=[])
    if prepared:
        data['integration']['preparation'] = [dict(task_id='stock', kind='nest', keys=['store_id'], description='保留各商品資料為子集合')]
    assert (not validate(model.model_validate(data), catalog_at(tmp_path))) is prepared
