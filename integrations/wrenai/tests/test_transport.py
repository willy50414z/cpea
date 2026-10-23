import asyncio
import json
from types import SimpleNamespace
import pytest


def test_raw_completion_is_persisted_before_length_finish_error(tmp_path):
    from native_worker.transport import Recorder, install_policy
    from native_worker.guards import Budget
    from src.providers.llm.litellm import LitellmLLMProvider
    async def transport(**kwargs):
        assert kwargs['num_retries'] == 0
        assert kwargs['max_retries'] == 0
        assert kwargs['max_tokens'] == 20
        from litellm import ModelResponse
        return ModelResponse(model='azure/deployment', choices=[{'finish_reason':'length','message':{'role':'assistant','content':'leading {"x":1} trailing'}}])
    recorder=Recorder(tmp_path, {'run_id':'r','case_id':'c'}, Budget(context_window=500,output_reserve=20,safety=10,encoding='cl100k_base'))
    install_policy(recorder, transport, None)
    provider=LitellmLLMProvider('offline')
    generator=provider.get_generator(system_prompt='system')
    with pytest.raises(Exception): asyncio.run(generator(prompt='user'))
    calls=list(tmp_path.glob('call-*.json'))
    assert len(calls)==1
    saved=json.loads(calls[0].read_text(encoding='utf-8'))
    assert saved['raw_response']['choices'][0]['message']['content']=='leading {"x":1} trailing'
    assert saved['raw_response']['choices'][0]['finish_reason']=='length'
    assert saved['ended_ns']>=saved['started_ns']
    assert saved['model_sku'] is None
    assert recorder.summary()['cost_complete'] is False


def test_embedding_batch_failure_is_not_retried_and_no_sibling_sends(tmp_path):
    from native_worker.transport import Recorder, install_policy
    from native_worker.guards import Budget
    from src.providers.embedder.litellm import AsyncDocumentEmbedder
    from haystack import Document
    async def transport(**kwargs): raise RuntimeError('rate_limit')
    recorder=Recorder(tmp_path, {'run_id':'r'}, Budget(context_window=500,output_reserve=20,safety=10,encoding='cl100k_base'))
    install_policy(recorder, None, transport)
    async def run():
        with pytest.raises(RuntimeError): await AsyncDocumentEmbedder('offline',batch_size=1).run([Document(content='a'),Document(content='b')])
        await recorder.drain()
    asyncio.run(run())
    assert recorder.sent_attempts == 1
    saved=json.loads(next(tmp_path.glob('call-*.json')).read_text(encoding='utf-8'))
    assert saved['status']=='error'
    assert saved['money']['amount'] is None


def test_budget_rejection_sends_no_transport(tmp_path):
    from native_worker.transport import Recorder, install_policy
    from native_worker.guards import Budget
    from src.providers.llm.litellm import LitellmLLMProvider
    async def transport(**kwargs): raise AssertionError('transport called')
    recorder=Recorder(tmp_path,{},Budget(context_window=20,output_reserve=10,safety=5,encoding='cl100k_base'))
    install_policy(recorder,transport,None)
    with pytest.raises(ValueError,match='context_budget'):
        asyncio.run(LitellmLLMProvider('offline').get_generator()(prompt='large '*100))
    assert recorder.sent_attempts==0


def test_unknown_usage_is_not_replaced_with_zero():
    from native_worker.transport import normalized_usage
    assert normalized_usage({})=={'input_tokens':None,'output_tokens':None,'total_tokens':None,'source':'unknown'}


def test_cancelled_embedding_preserves_unknown_outcome(tmp_path):
    from native_worker.transport import Recorder
    from native_worker.guards import Budget
    recorder=Recorder(tmp_path,{'run_id':'r'},Budget(context_window=100,output_reserve=10,safety=5,encoding='cl100k_base'))
    async def transport(**kwargs): await asyncio.sleep(10)
    async def run():
        task=asyncio.create_task(recorder.call('embedding',transport,model='azure/deployment',input=['text']))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        await recorder.drain()
    asyncio.run(run())
    record=json.loads(next(tmp_path.glob('call-*.json')).read_text(encoding='utf-8'))
    assert record['status']=='unknown_outcome'
    assert record['provider']=='azure' and record['deployment']=='deployment' and record['model_sku'] is None
