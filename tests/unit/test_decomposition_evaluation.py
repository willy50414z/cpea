from copy import deepcopy
import json
import pytest
from tests.decomposition_support import catalog_at, draft


def response():
    from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
    from cpea.workflows.task_decomposition.validation import prepare_requests
    return DecompositionDraft,DecompositionResponse,prepare_requests


def case_for(catalog):
    return {'case_id':'test-case','profile_id':catalog.profile_id,'contract_fingerprint':catalog.fingerprint,
            'request':'庫存與九月銷量','expected_status':'ready','expected_strategy':'multi_view',
            'expected_tasks':[{**t,'acceptable_alternatives':[]} for t in draft()['tasks']],
            'expected_integration':{'anchor_task':'stock','keys':['store_id','product_id'],'mode':'left','required_steps':[]},
            'review_status':'pending'}


def test_grading_is_invariant_to_task_order_and_ids(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);c=case_for(catalog);d=m.model_validate(draft())
    result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert grade_decomposition(c,result,catalog)['automated_pass']
    data=deepcopy(draft());data['tasks'].reverse()
    rename={'stock':'x','sales':'y'}
    for t in data['tasks']:t['task_id']=rename[t['task_id']]
    data['integration']['anchor_task']='x'
    e=data['integration']['edges'][0];e['left_task']='x';e['right_task']='y';e['preserve_task']='x'
    d=m.model_validate(data);result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert grade_decomposition(c,result,catalog)['automated_pass']


def test_equivalent_sales_detail_plan_passes_without_canonical_hit(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);c=case_for(catalog)
    sales=c['expected_tasks'][1];sales['acceptable_alternatives']=[deepcopy(sales)]
    sales.update(view='demo.monthly',required_columns=['store_id','product_id','units_sold','sales_month'],
                 metrics={'units_sold':'sum'},filters=[{'column':'sales_month','operator':'=','value':'2026-09-01'}])
    d=m.model_validate(draft());result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    score=grade_decomposition(c,result,catalog)
    assert score['automated_pass'] and not score['canonical_views_match']


def test_wrong_channel_or_period_is_not_accepted(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);c=case_for(catalog)
    c['expected_tasks'][1]['filters'][0]['value']='2026-08-01'
    d=m.model_validate(draft());result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert not grade_decomposition(c,result,catalog)['automated_pass']


def test_case_loader_rejects_stale_fingerprint_and_invalid_alternative(tmp_path):
    from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
    catalog=catalog_at(tmp_path/'catalog');c=case_for(catalog);p=tmp_path/'cases.jsonl'
    for corruption in ('fingerprint','alternative'):
        bad=deepcopy(c)
        if corruption=='fingerprint':bad['contract_fingerprint']='stale'
        else:bad['expected_tasks'][0]['acceptable_alternatives']=[{**bad['expected_tasks'][0],'view':'demo.unknown'}]
        bad['case_sha256']=case_sha256(bad);p.write_text(json.dumps(bad)+'\n',encoding='utf-8')
        with pytest.raises(ValueError):load_decomposition_cases(p,catalog)


def test_partial_run_and_consistent_failure_do_not_count_as_stable_pass(tmp_path):
    from evaluations.decomposition_reports import summarize
    results=[{'case_id':'a','run':i,'status':'completed','score':{'automated_pass':False},'response':{'status':'error'}} for i in range(3)]
    results.append({'case_id':'b','run':0,'status':'completed','score':{'automated_pass':True},'response':{'status':'ready'}})
    summary=summarize(results,planned=6,runs=3)
    assert summary['all_runs_pass_cases']==0 and summary['consistent_failure_cases']==1
    assert summary['automated_pass_count']==1 and summary['planned']==6


def test_conditional_count_cannot_be_replaced_by_unconditional_count(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);c=case_for(catalog)
    expected=c['expected_tasks'][0]
    expected['conditional_metrics']=[{'column':'product_id','aggregation':'count_distinct',
                                      'conditions':[{'column':'stock_qty','operator':'=','value':0}]}]
    d=m.model_validate(draft())
    result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert not grade_decomposition(c,result,catalog)['automated_pass']


def test_conditional_metric_cannot_replace_unconditional_metric(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);c=case_for(catalog);data=draft()
    task=data['tasks'][1];task['metrics']={};task['required_columns'].append('sales_channel')
    task['conditional_metrics']=[{'column':'quantity','aggregation':'sum',
                               'conditions':[{'column':'sales_channel','operator':'=','value':'online'}]}]
    d=m.model_validate(data);result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert not grade_decomposition(c,result,catalog)['automated_pass']


def test_three_source_grading_requires_product_fact_keys(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);data=draft()
    data['tasks'].append({'task_id':'kpi','view':'demo.kpi','required_columns':['store_id','sales_month','target_amount'],
                         'output_grain':['store_id'],'attributes':['target_amount'],
                         'filters':[{'column':'sales_month','operator':'=','value':'2026-09-01'}],'request':'目標'})
    data['integration']['edges'].append({'left_task':'stock','right_task':'kpi','left_keys':['store_id'],
        'right_keys':['store_id'],'mode':'left','cardinality':'many_to_one','preserve_task':'stock'})
    c=case_for(catalog);c['expected_tasks'].append({**data['tasks'][2],'acceptable_alternatives':[]})
    # Valid structure for a store-level merge, but it loses the oracle's product comparison.
    data['integration']['edges'][0].update(left_keys=['store_id'],right_keys=['store_id'])
    data['integration']['preparation']=[{'task_id':name,'kind':'aggregate','keys':['store_id'],'description':'依店彙總'} for name in ('stock','sales')]
    data['integration']['output_grain']=['store_id']
    d=m.model_validate(data);result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert not grade_decomposition(c,result,catalog)['automated_pass']


def test_raw_monthly_value_is_equivalent_to_sum_of_one_row(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,prepare=response();catalog=catalog_at(tmp_path);c=case_for(catalog);data=draft()
    expected=c['expected_tasks'][1]
    expected.update(view='demo.monthly',required_columns=['store_id','product_id','sales_month','units_sold'],
                    metrics={'units_sold':'sum'},filters=[{'column':'sales_month','operator':'=','value':'2026-09-01'}])
    actual=data['tasks'][1];actual.update(view=expected['view'],required_columns=expected['required_columns'],
         filters=expected['filters'],metrics={},group_by=[],attributes=['units_sold'])
    d=m.model_validate(data);result=r(status='ready',contract_fingerprint=catalog.fingerprint,draft=d,prepared_requests=prepare(d,catalog))
    assert grade_decomposition(c,result,catalog)['automated_pass']


def test_inclusive_date_end_is_equivalent_to_next_day_exclusive_end():
    from evaluations.decomposition_grading import _filters
    a=[{'column':'order_date','operator':'<=','value':'2026-09-14'}]
    b=[{'column':'order_date','operator':'<','value':'2026-09-15'}]
    assert _filters(a)==_filters(b)


def test_month_filter_and_day_bounds_match_without_losing_daily_output():
    from evaluations.decomposition_grading import _filters
    a=[{'column':'order_month','operator':'=','value':'2026-09-01'}]
    b=[{'column':'order_date','operator':'>=','value':'2026-09-01'},
       {'column':'order_date','operator':'<','value':'2026-10-01'}]
    assert _filters(a)==_filters(b)


def test_filter_date_alias_does_not_require_unused_date_column(tmp_path):
    from evaluations.decomposition_grading import _task_score
    model,_,_=response();catalog=catalog_at(tmp_path);expected=draft()['tasks'][1]
    data=deepcopy(expected);data['required_columns'].remove('order_date');data['required_columns'].append('order_month')
    data['filters']=[{'column':'order_month','operator':'=','value':'2026-09-01'}]
    task=model.model_validate({**draft(),'tasks':[data]}).tasks[0]
    assert _task_score(expected,task,catalog)['columns']
    expected['output_grain'].append('order_date')
    assert not _task_score(expected,task,catalog)['columns']


def test_count_equivalence_requires_source_uniqueness_within_group(tmp_path):
    from evaluations.decomposition_grading import _task_score
    model,_,_=response();catalog=catalog_at(tmp_path)
    data={'task_id':'m','view':'demo.monthly','required_columns':['store_id','product_id','sales_month'],
          'filters':[{'column':'sales_month','operator':'=','value':'2026-09-01'}],
          'metrics':{'product_id':'count'},'group_by':['store_id'],'output_grain':['store_id'],'request':'商品數'}
    task=model.model_validate({**draft(),'tasks':[data]}).tasks[0]
    expected={**data,'metrics':{'product_id':'count_distinct'}}
    assert _task_score(expected,task,catalog)['metrics']
    data['filters']=[]
    task=model.model_validate({**draft(),'tasks':[data]}).tasks[0]
    expected['filters']=[]
    assert not _task_score(expected,task,catalog)['metrics']


def test_rejected_plan_still_reports_source_choice_but_cannot_pass(tmp_path):
    from evaluations.decomposition_grading import grade_decomposition
    m,r,_=response();catalog=catalog_at(tmp_path);c=case_for(catalog)
    result=r(status='error',code='invalid_plan',contract_fingerprint=catalog.fingerprint,draft=m.model_validate(draft()))
    s=grade_decomposition(c,result,catalog)
    assert s['canonical_views_match'] and s['views_and_columns_match']
    assert not s['automated_pass'] and not s['payload_ready']


def test_extra_snapshot_dimension_requires_source_key_proof(tmp_path):
    from evaluations.decomposition_grading import _task_score
    model,_,_=response();catalog=catalog_at(tmp_path);expected=draft()['tasks'][0]
    data=deepcopy(expected);data['required_columns'].append('snapshot_date');data['output_grain'].append('snapshot_date')
    task=model.model_validate({**draft(),'tasks':[data]}).tasks[0]
    assert _task_score(expected,task,catalog)['grain']
    # Across products, a store does not determine all snapshot dates in the contract.
    expected.update(output_grain=['store_id'],group_by=['store_id'],metrics={'stock_qty':'sum'})
    data.update(output_grain=['store_id','snapshot_date'],group_by=['store_id','snapshot_date'],metrics={'stock_qty':'sum'})
    task=model.model_validate({**draft(),'tasks':[data]}).tasks[0]
    assert not _task_score(expected,task,catalog)['grain']
