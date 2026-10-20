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
