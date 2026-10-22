"""Shared runner records the new wire, exact first errors and complete prepared output."""
import importlib
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from test_kind_mapping_managed_contract import api, inputs


FAILURES=[None,'provider','parse','predicate','inapplicable','mapping','own_gap','dependency','typed','null','old_wire']


def fake(catalog,failure=None):
    request,rec,maps,sel=inputs(catalog); responses=iter([rec,*maps,sel]); calls=[]
    def invoke(name,messages,schema):
        calls.append(name); payload=json.loads(messages[1].content)
        assert payload['request']==request and payload['response_schema']==schema.model_json_schema()
        value=next(responses)
        if name=='map-02':
            if failure=='provider': raise OSError('offline provider lost')
            if failure=='parse': return AIMessage(content='not json')
            if failure=='predicate': value['entries']['period'].update(status='supported',own_gap=False,contract_path='/columns/sales_date/description',mappings=[dict(column='sales_date',operator='>=')])
            if failure=='inapplicable': value['entries']['grain']['mappings']=[dict(column='store_id',conditions=[])]
            if failure=='own_gap': value['entries']['stock']['own_gap']=False
            if failure=='mapping': value['entries']['stock'].update(status='partial',mappings=[dict(column='missing',aggregation='sum',conditions=[])])
            if failure=='old_wire': value['entries']['period'].update(mappings=[dict(column='sales_date',role='filter',conditions=[dict(column='sales_date',operator='>=',value='2031-02-01')])])
        if name=='map-03' and failure=='dependency': value['entries']['grain'].update(status='unsupported',mappings=[],own_gap=True)
        if name=='selection':
            if failure=='typed': value['draft']['tasks'][0].pop('filters')
            if failure=='null': value['draft']['integration']=None
        return AIMessage(content=json.dumps(value,ensure_ascii=False),usage_metadata=dict(input_tokens=10,output_tokens=20,total_tokens=30))
    return request,invoke,calls


@pytest.mark.parametrize('failure',FAILURES)
def test_record_and_replay_complete_nine_nodes_or_exact_first_failure_prefix(tmp_path,failure):
    mod=importlib.import_module('evaluations.managed_three_stage_runner'); catalog=SchemaCatalog('projects/retail')
    request,invoke,calls=fake(catalog,failure); case=mod.diagnostic_case(catalog,request)
    meta=mod.record_run(tmp_path,catalog,case,invoke,contract=api())
    assert bool(meta['stopped'])==bool(failure)
    result=mod.replay(tmp_path,catalog,case,contract=api())
    assert result['result']=='PASS' and result['stopped']==meta['stopped']
    if failure:
        last='selection' if failure in ('typed','null') else 'map-03' if failure=='dependency' else 'map-02'
        assert calls[-1]==last and not (tmp_path/'response.json').exists()
        assert (tmp_path/(last+'-error.json')).exists()
        assert (tmp_path/(last+'-provider-error.json' if failure=='provider' else last+'-call.json')).exists()
        assert not (tmp_path/(last+'-normalized.json')).exists()
    else:
        assert calls==['recall',*[f'map-{i:02}' for i in range(1,8)],'selection']
        response=json.loads((tmp_path/'response.json').read_text(encoding='utf-8'))
        assert response['status']=='ready' and len(response['prepared_requests'])==2
        draft=json.loads((tmp_path/'selection-normalized.json').read_text(encoding='utf-8'))['draft']
        stock,sales=draft['tasks']; integration=draft['integration']
        assert stock['metrics']=={'stock_qty':'sum'} and stock['metadata_collections']==['snapshot_date']
        assert stock['filters']==[] and stock['group_by']==['store_id','product_id']
        assert sales['metrics']=={'discount_amount':'sum','net_sales':'sum'}
        assert sales['filters']==[dict(column='sales_channel',operator='=',value='online'),dict(column='order_date',operator='>=',value='2026-09-01'),dict(column='order_date',operator='<',value='2026-10-01')]
        assert sales['group_by']==['store_id','product_id']
        assert integration['anchor_task']=='stock' and integration['edges'][0]['mode']=='left'
        assert integration['missing_data_policy']=='保留未匹配資料並標記缺值；契約沒有保證時不可把缺值當成零。'
        raw=json.loads((tmp_path/'map-06-parsed.json').read_text(encoding='utf-8'))['entries']
        normalized=json.loads((tmp_path/'map-06-normalized.json').read_text(encoding='utf-8'))['entries']
        assert raw['sales']['mappings'][0]['conditions']==[] and 'role' not in raw['sales']['mappings'][0]
        assert next(e for e in normalized if e['requirement_id']=='sales')['mappings'][0]['role']=='metric'
    with pytest.raises(ValueError,match='version'): mod.replay(tmp_path,catalog,case)


def test_cli_kind_mapping_is_dry_and_all_contract_flags_are_mutually_exclusive(monkeypatch,capsys):
    mod=importlib.import_module('evaluations.managed_three_stage_runner')
    monkeypatch.setattr(mod,'ManagedInvoke',lambda *a,**k:pytest.fail('provider constructed'))
    monkeypatch.setattr(mod,'verify_model_identity',lambda *a:pytest.fail('network called'))
    assert mod.main(['--kind-mapping'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['version']==api().VERSION and result['execute'] is False
    for other in ('--own-responsibility','--evidence-bound'):
        with pytest.raises(SystemExit) as exc: mod.main(['--kind-mapping',other])
        assert exc.value.code==2


def test_fingerprint_includes_new_and_reused_contracts_prompts_and_tests():
    mod=importlib.import_module('evaluations.managed_three_stage_runner'); catalog=SchemaCatalog('projects/retail')
    frozen=mod.fingerprint(catalog,mod.diagnostic_case(catalog),contract=api())
    assert frozen['managed_version']==api().VERSION
    for name in ['evaluations/kind_mapping_managed_contract.py','evaluations/own_responsibility_managed_contract.py',
        'evaluations/evidence_bound_managed_contract.py','evaluations/prompts/kind_mapping/coverage.md',
        'evaluations/prompts/own_responsibility/recall.md','evaluations/prompts/evidence_bound/selection.md',
        'tests/unit/test_kind_mapping_managed_contract.py','tests/unit/test_kind_mapping_managed_runner.py']:
        assert any(Path(key).as_posix().endswith(name) for key in frozen['managed_sources'])
