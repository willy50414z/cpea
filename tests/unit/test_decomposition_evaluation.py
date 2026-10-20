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
