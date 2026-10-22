from dataclasses import replace
from tests.decomposition_support import FakeLLM, catalog_at, draft, settings


def service(tmp_path,llm=None,**kw):
    from cpea.application.services.task_decomposition import TaskDecompositionService
    return TaskDecompositionService(llm or FakeLLM(),catalog_at(tmp_path),settings=kw.pop('settings',settings()),**kw)


def test_inventory_plus_custom_period_sales_prepares_two_requests(tmp_path):
    llm=FakeLLM();result=service(tmp_path,llm).plan('目前庫存與九月銷量')
    assert result.status=='ready'
    assert len(llm.calls)==1 and len(result.prepared_requests)==2
    assert result.prepared_requests[1].view=='demo.sales'
    assert '2026-10-01' in result.prepared_requests[1].payload['request']


def test_inventory_30d_sales_can_stay_single_view(tmp_path):
    data=draft();data['tasks']=data['tasks'][:1];data['strategy']='single_view';data['integration']['edges']=[]
    assert service(tmp_path,FakeLLM(data)).plan('只看庫存').status=='ready'


def test_missing_policy_and_unavailable_fields_do_not_dispatch(tmp_path):
    for status,key in [('needs_clarification','clarifications'),('unsupported','unsupported_reasons')]:
        r=service(tmp_path,FakeLLM({'status':status,key:['缺必要資料']})).plan('需求')
        assert r.status==status and not r.prepared_requests


def test_full_prompt_budget_rejects_before_model_call(tmp_path):
    llm=FakeLLM();s=replace(settings(),context_window=100)
    r=service(tmp_path,llm,settings=s).plan('問題')
    assert r.code=='context_budget_exceeded' and not llm.calls


def test_parse_and_validation_errors_are_not_retried(tmp_path):
    for data in ({'bogus':True}, {**draft(),'tasks':[]}):
        llm=FakeLLM(data);r=service(tmp_path,llm).plan('問題')
        assert r.status=='error' and len(llm.calls)==1 and not r.prepared_requests


def test_prompt_contains_all_contracts_and_no_case_or_oracle(tmp_path):
    llm=FakeLLM();r=service(tmp_path,llm).plan('QUESTION_SENTINEL')
    text=' '.join(m.content for m in llm.calls[0])
    for view in ('demo.stock','demo.sales','demo.kpi','demo.monthly'):assert view in text
    assert 'QUESTION_SENTINEL' in text
    assert 'expected_tasks' not in text and 'case_id' not in text
    assert r.context_tokens>0


def test_provider_failure_is_sanitized_and_observed_once(tmp_path):
    events=[];llm=FakeLLM(error=RuntimeError('429 secret-key endpoint'))
    r=service(tmp_path,llm,observer=events.append).plan('問題')
    assert r.code=='provider_error' and len(llm.calls)==1
    assert 'secret-key' not in r.model_dump_json()
    assert events[-1]['error_type']=='RuntimeError'
