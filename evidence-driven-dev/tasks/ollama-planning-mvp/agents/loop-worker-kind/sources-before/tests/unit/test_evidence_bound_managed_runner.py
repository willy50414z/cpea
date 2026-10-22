"""New managed wire uses the shared recorder, transport, and replay without repair."""
import importlib
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from test_evidence_bound_managed_contract import api, inputs


def fake(catalog, failure=None):
    request, rec, maps, sel=inputs(catalog)
    responses=iter([rec,*maps,sel]); calls=[]
    def invoke(name,messages,schema):
        calls.append(name)
        payload=json.loads(messages[1].content)
        assert payload['request']==request
        assert payload['response_schema']==schema.model_json_schema()
        value=next(responses)
        if failure=='provider' and name=='map-02': raise OSError('offline provider lost')
        if failure=='parse' and name=='map-02': return AIMessage(content='not json')
        if name=='map-02' and failure=='gap': value['entries']['stock']['gaps'][0]['requirement_ids']=['unknown']
        if name=='selection' and failure=='typed': value['draft']['tasks'][0].pop('filters')
        if name=='selection' and failure=='null': value['draft']['integration']=None
        if name=='recall' and failure=='old_wire': value['candidate_views']=[]
        if name=='map-02' and failure=='nested_duplicate':
            return AIMessage(content=json.dumps(value).replace('"status": "unsupported"','"status":"unsupported","status":"supported"',1))
        return AIMessage(content=json.dumps(value,ensure_ascii=False),usage_metadata=dict(input_tokens=10,output_tokens=20,total_tokens=30))
    return request,invoke,calls


@pytest.mark.parametrize('failure',[None,'provider','parse','gap','typed','null','old_wire','nested_duplicate'])
def test_bound_record_replay_complete_and_first_failure_prefix(tmp_path,failure):
    mod=importlib.import_module('evaluations.managed_three_stage_runner')
    catalog=SchemaCatalog('projects/retail')
    request,invoke,calls=fake(catalog,failure)
    case=mod.diagnostic_case(catalog,request)
    meta=mod.record_run(tmp_path,catalog,case,invoke,contract=api())
    assert bool(meta['stopped'])==bool(failure)
    assert mod.replay(tmp_path,catalog,case,contract=api())['result']=='PASS'
    if failure:
        assert calls[-1]==('recall' if failure=='old_wire' else 'selection' if failure in ('typed','null') else 'map-02')
        assert not (tmp_path/'response.json').exists()
        assert (tmp_path/(calls[-1]+'-call.json')).exists() or (tmp_path/(calls[-1]+'-provider-error.json')).exists()
        assert (tmp_path/(calls[-1]+'-error.json')).exists()
    else:
        assert calls==['recall',*[f'map-{i:02}' for i in range(1,8)],'selection']
        response=json.loads((tmp_path/'response.json').read_text(encoding='utf-8'))
        assert response['status']=='ready' and len(response['prepared_requests'])==2
        refs=json.loads((tmp_path/'recall-refs.json').read_text(encoding='utf-8'))
        assert refs['stock']['grain_binding']=='linked' and refs['stock']['grain_requirement_ids']==['grain']
        assert (tmp_path/'selection-refs.json').exists() and (tmp_path/'map-01-refs.json').exists()
    with pytest.raises(ValueError,match='version'): mod.replay(tmp_path,catalog,case)


def test_bound_dry_run_never_constructs_provider_or_calls_network(monkeypatch,capsys):
    mod=importlib.import_module('evaluations.managed_three_stage_runner')
    monkeypatch.setattr(mod,'ManagedInvoke',lambda *a,**k:pytest.fail('provider constructed'))
    monkeypatch.setattr(mod,'verify_model_identity',lambda *a:pytest.fail('network called'))
    assert mod.main(['--evidence-bound'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['version']==api().VERSION and result['execute'] is False
