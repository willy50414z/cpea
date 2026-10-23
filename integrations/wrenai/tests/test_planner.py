import asyncio
import json
from pathlib import Path
import pytest
import uuid
from copy import deepcopy


def test_native_graph_draft_and_raw_transport_ledger(tmp_path,retail_schema,qdrant_url,planning_contract,monkeypatch):
    from native_worker.planner import NativeWrenAIPlanner
    from litellm import ModelResponse, EmbeddingResponse
    schema=retail_schema; first=schema['mdl']['models'][0]
    replies=[{'results':'TEXT_TO_SQL','rephrased_question':'customer_id','reasoning':'explicit'},
        {'results':[{'table_name':first['name'],'table_contents':{'columns':[c['name'] for c in first['columns']], 'chain_of_thought_reasoning':[]},'table_selection_reason':'fixture'}]},
        {'status':'ready','strategy':'single_view','tasks':[{'task_id':'customer','view':schema['model_to_view'][first['name']],
            'required_columns':['customer_id'],'output_grain':['customer_id'],'request':'customer_id'}],
         'integration':{'anchor_task':'customer','output_grain':['customer_id']}}]
    original_replies=deepcopy(replies)
    async def completion(**kwargs):
        return ModelResponse(model='offline',choices=[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(replies.pop(0))}}])
    async def embedding(**kwargs):
        return EmbeddingResponse(model='offline',data=[{'embedding':[1.,0.,0.,0.],'index':i,'object':'embedding'} for i,_ in enumerate(kwargs['input'])])
    recording_root=Path(__file__).resolve().parents[1]/'.runtime'/('test-recording-'+uuid.uuid4().hex)
    planner=NativeWrenAIPlanner(runtime_root=recording_root,qdrant_url=qdrant_url,
        embedding_dimension=4,completion_transport=completion,embedding_transport=embedding)
    payload={'request':'customer_id','run_id':'native-e2e','request_id':'q','case_id':'offline-customer',
        'schema':schema,**planning_contract}
    result=asyncio.run(planner.plan(payload))
    assert result['draft']['status']=='ready'
    assert result['context_tokens']>0
    calls=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(result['artifacts']['run_dir'])).glob('call-*.json')]
    assert len([c for c in calls if c['kind']=='completion'])==3
    assert {c['node_id'] for c in calls}=={'schema_index','intent','schema_retrieval','draft_planning'}
    assert all(c['attempt']==1 and c['raw_response'] for c in calls)
    ledger=json.loads((Path(result['artifacts']['run_dir'])/'ledger.json').read_text(encoding='utf-8'))
    assert {k:v['sent_attempts'] for k,v in ledger['summary']['groups'].items()}=={
        'schema_index_embedding':2,'query_embedding':2,'completion':3}
    assert ledger['summary']['sent_attempts']==7
    assert not replies
    from native_worker.replay import replay_recording
    repeated=replay_recording(result['artifacts']['run_dir'])
    assert repeated['draft']==result['draft']
    assert repeated['replay']['transport_calls']==len(calls)
    import subprocess
    root=Path(__file__).resolve().parents[1]; repo=root.parents[1]
    checked=json.loads(subprocess.check_output([str(repo/'.venv/bin/python'),str(root/'tests/parent_smoke.py'),
        result['artifacts']['run_dir']],cwd=repo,text=True,encoding='utf-8'))
    assert checked=={'status':'ready','code':None,'prepared_count':1,'validation_errors':[]}
    replies.extend(deepcopy(original_replies))
    warm=asyncio.run(planner.plan({**payload,'run_id':'native-warm','request_id':'q-warm'}))
    warm_dir=Path(warm['artifacts']['run_dir'])
    assert all(json.loads((warm_dir/name).read_text(encoding='utf-8'))['node_id']!='schema_index' for name in warm['artifacts']['calls'])
    warm_repeated=replay_recording(warm_dir)
    assert warm_repeated['draft']==warm['draft']
    checked=json.loads(subprocess.check_output([str(repo/'.venv/bin/python'),str(root/'tests/parent_smoke.py'),str(warm_dir)],cwd=repo,text=True,encoding='utf-8'))
    assert checked['status']=='ready' and checked['prepared_count']==1
    from src.pipelines.indexing.table_description import TableDescription
    async def failed_write(*args,**kwargs): raise RuntimeError('injected_second_store_failure')
    with monkeypatch.context() as patch:
        patch.setattr(TableDescription,'run',failed_write)
        with pytest.raises(RuntimeError,match='injected_second_store_failure'):
            asyncio.run(planner.plan({**payload,'run_id':'native-partial','catalog_fingerprint':payload['catalog_fingerprint']+'-partial'}))
    states=[json.loads(p.read_text(encoding='utf-8')) for p in (recording_root/'generations').glob('*/generation.json')]
    assert sorted(s['status'] for s in states)==['failed','ready']
