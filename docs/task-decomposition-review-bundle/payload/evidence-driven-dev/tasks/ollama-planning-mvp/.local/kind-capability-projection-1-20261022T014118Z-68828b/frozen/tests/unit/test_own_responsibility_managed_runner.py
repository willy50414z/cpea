"""Versioned own responsibility wire uses the existing recorder and transport."""
import importlib
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from test_own_responsibility_managed_contract import api, inputs


FAILURES=[None,'provider','parse','own_gap','dependency','mapping','typed','null','duplicate','old_wire']


def fake(catalog,failure=None):
    request,rec,maps,sel=inputs(catalog); responses=iter([rec,*maps,sel]); calls=[]
    def invoke(name,messages,schema):
        calls.append(name); payload=json.loads(messages[1].content)
        assert payload['request']==request and payload['response_schema']==schema.model_json_schema()
        value=next(responses)
        if name=='map-02':
            if failure=='provider': raise OSError('offline provider lost')
            if failure=='parse': return AIMessage(content='not json')
            if failure=='own_gap': value['entries']['stock']['own_gap']=False
            if failure=='mapping': value['entries']['stock'].update(status='partial',mappings=[dict(column='missing',role='metric',aggregation='sum')])
            if failure=='duplicate': return AIMessage(content=json.dumps(value).replace('"own_gap": true','"own_gap":true,"own_gap":false',1))
        if name=='map-03' and failure=='dependency':
            value['entries']['grain'].update(status='unsupported',mappings=[],own_gap=True)
        if name=='selection':
            if failure=='typed': value['draft']['tasks'][0].pop('filters')
            if failure=='null': value['draft']['integration']=None
        if name=='recall' and failure=='old_wire': value['candidate_views']=[]
        return AIMessage(content=json.dumps(value,ensure_ascii=False),usage_metadata=dict(input_tokens=10,output_tokens=20,total_tokens=30))
    return request,invoke,calls


@pytest.mark.parametrize('failure',FAILURES)
def test_record_replay_retains_complete_or_first_failure_prefix(tmp_path,failure):
    mod=importlib.import_module('evaluations.managed_three_stage_runner'); catalog=SchemaCatalog('projects/retail')
    request,invoke,calls=fake(catalog,failure); case=mod.diagnostic_case(catalog,request)
    meta=mod.record_run(tmp_path,catalog,case,invoke,contract=api())
    assert bool(meta['stopped'])==bool(failure)
    result=mod.replay(tmp_path,catalog,case,contract=api())
    assert result['result']=='PASS' and result['stopped']==meta['stopped']
    if failure:
        last='recall' if failure=='old_wire' else 'selection' if failure in ('typed','null') else 'map-03' if failure=='dependency' else 'map-02'
        assert calls[-1]==last and not (tmp_path/'response.json').exists()
        assert (tmp_path/(last+'-error.json')).exists()
        assert (tmp_path/(last+'-provider-error.json' if failure=='provider' else last+'-call.json')).exists()
    else:
        assert calls==['recall',*[f'map-{i:02}' for i in range(1,8)],'selection']
        response=json.loads((tmp_path/'response.json').read_text(encoding='utf-8'))
        assert response['status']=='ready' and len(response['prepared_requests'])==2
        selection=json.loads((tmp_path/'selection-normalized.json').read_text(encoding='utf-8'))
        stock,sales=selection['draft']['tasks']
        assert stock['metrics']=={'stock_qty':'sum'} and stock['metadata_collections']==['snapshot_date']
        assert sales['metrics']=={'discount_amount':'sum','net_sales':'sum'} and len(sales['filters'])==3
        integration=selection['draft']['integration']
        assert integration['anchor_task']=='stock' and integration['edges'][0]['mode']=='left'
        assert sales['group_by']==['store_id','product_id']
        assert integration['missing_data_policy']=='保留未匹配資料並標記缺值；契約沒有保證時不可把缺值當成零。'
        normalized=json.loads((tmp_path/'map-05-normalized.json').read_text(encoding='utf-8'))
        row=next(e for e in normalized['entries'] if e['requirement_id']=='sales')
        assert [json.loads(g)['aspect'] for g in row['missing_requirements']]==['scope']
        assert (tmp_path/'map-05-refs.json').exists()
    with pytest.raises(ValueError,match='version'): mod.replay(tmp_path,catalog,case)


def test_cli_own_contract_dry_run_and_conflicting_contracts(monkeypatch,capsys):
    mod=importlib.import_module('evaluations.managed_three_stage_runner')
    monkeypatch.setattr(mod,'ManagedInvoke',lambda *a,**k:pytest.fail('provider constructed'))
    monkeypatch.setattr(mod,'verify_model_identity',lambda *a:pytest.fail('network called'))
    assert mod.main(['--own-responsibility'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['version']==api().VERSION and result['execute'] is False
    with pytest.raises(SystemExit) as exc: mod.main(['--own-responsibility','--evidence-bound'])
    assert exc.value.code==2


def test_fingerprint_covers_new_and_reused_contract_sources():
    mod=importlib.import_module('evaluations.managed_three_stage_runner'); catalog=SchemaCatalog('projects/retail')
    frozen=mod.fingerprint(catalog,mod.diagnostic_case(catalog),contract=api())
    assert frozen['managed_version']==api().VERSION
    for name in ['evaluations/own_responsibility_managed_contract.py','evaluations/evidence_bound_managed_contract.py',
                 'evaluations/prompts/own_responsibility/recall.md','evaluations/prompts/own_responsibility/coverage.md',
                 'evaluations/prompts/evidence_bound/selection.md','tests/unit/test_own_responsibility_managed_contract.py',
                 'tests/unit/test_own_responsibility_managed_runner.py']:
        assert any(Path(key).as_posix().endswith(name) for key in frozen['managed_sources'])
