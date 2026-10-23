"""Pinned execution-policy seam: one transport attempt, private raw recording."""
import asyncio
import inspect
import json
from pathlib import Path
import time
import uuid

from .generation import fingerprint, private_write


def serializable(value):
    if hasattr(value, 'model_dump'): return value.model_dump(mode='json')
    if isinstance(value, dict): return {k:serializable(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [serializable(v) for v in value]
    return value


def safe_request(kwargs):
    # Allowlist avoids auth headers, arbitrary provider secrets and exception reprs.
    return {k:serializable(v) for k,v in kwargs.items() if k in {
        'model','messages','input','response_format','temperature','max_tokens','num_retries',
        'max_retries','stream','timeout','allowed_openai_params','dimensions','encoding_format'}}


def normalized_usage(raw):
    usage=raw.get('usage') or {}
    def count(*keys):
        for key in keys:
            value=usage.get(key)
            if type(value) is int and value>=0: return value
        return None
    return {'input_tokens':count('prompt_tokens','input_tokens'),
        'output_tokens':count('completion_tokens','output_tokens'),'total_tokens':count('total_tokens'),
        'source':'provider' if usage else 'unknown'}


class Recorder:
    def __init__(self, root, ids, budget):
        self.root=Path(root); self.ids=ids; self.budget=budget
        self.sent_attempts=0; self.failed=False; self.node_id='schema_index'
        self.context_tokens=0; self.calls=[]; self.rendered_prompts=[]; self.tasks=set(); self.gate=asyncio.Lock()

    async def drain(self):
        pending=[t for t in self.tasks if t is not asyncio.current_task()]
        if pending: await asyncio.gather(*pending, return_exceptions=True)

    def parsed(self, value=None, error=None):
        path=self.root/self.calls[-1]
        record=json.loads(path.read_text(encoding='utf-8'))
        record.update(parsed=value,parse_error=error)
        private_write(path,record)

    def summary(self):
        records=[json.loads((self.root/name).read_text(encoding='utf-8')) for name in self.calls]
        def totals(items):
            usage={}
            for key in ('input_tokens','output_tokens','total_tokens'):
                values=[r.get('normalized_usage',{}).get(key) for r in items]
                usage[key]=sum(values) if values and all(v is not None for v in values) else None
            return {'sent_attempts':len(items),'usage':usage,
                'usage_complete':all(r.get('normalized_usage',{}).get('total_tokens') is not None for r in items),
                'cost_complete':not items,'money':{'amount':None,'currency':None,'status':'unknown'}}
        return {**totals(records),'transport_complete':not self.failed,'groups':{
            'schema_index_embedding':totals([r for r in records if r['kind']=='embedding' and r['node_id']=='schema_index']),
            'query_embedding':totals([r for r in records if r['kind']=='embedding' and r['node_id']!='schema_index']),
            'completion':totals([r for r in records if r['kind']=='completion'])}}

    async def call(self, kind, transport, **kwargs):
        task=asyncio.current_task(); self.tasks.add(task)
        try:
            async with self.gate:
                if self.failed: raise RuntimeError('transport_stopped_after_error')
                kwargs['num_retries']=0; kwargs['max_retries']=0
                if kind=='completion':
                    try: count=self.budget.check(kwargs['messages'], kwargs)
                    except ValueError:
                        private_write(self.root/('preflight-'+self.node_id+'.json'),{**self.ids,'node_id':self.node_id,
                            'status':'context_budget_exceeded','model_calls':0,'request':safe_request(kwargs),
                            'context_window':self.budget.context_window,'output_reserve':self.budget.output_reserve,
                            'safety':self.budget.safety,'token_counter':self.budget.counter})
                        raise
                    self.context_tokens=max(self.context_tokens,count)
                    kwargs['max_tokens']=self.budget.output_reserve
                    if kwargs.get('stream'): raise ValueError('streaming_not_supported')
                request=safe_request(kwargs)
                if kind=='completion': self.rendered_prompts.append(fingerprint(request))
                call_id='call-'+uuid.uuid4().hex
                path=self.root/(call_id+'.json')
                record={**self.ids,'node_id':self.node_id,'call_id':call_id,'batch_id':call_id if kind=='embedding' else None,
                    'kind':kind,'attempt':1,'request':request,'request_fingerprint':fingerprint(request),
                    'status':'sent','raw_response':None,'usage':None,'started_ns':time.time_ns(),
                    'provider':kwargs['model'].split('/',1)[0] if '/' in kwargs['model'] else 'unknown',
                    'deployment':kwargs['model'].split('/',1)[1] if kwargs['model'].startswith('azure/') else None,
                    'model_sku':None,'normalized_usage':{'input_tokens':None,'output_tokens':None,'total_tokens':None,'source':'unknown'},
                    'money':{'amount':None,'currency':None,'status':'unknown','pricing_source':None,'pricing_version':None}}
                private_write(path,record)
                self.calls.append(path.name); self.sent_attempts+=1
                started=time.monotonic()
                try:
                    response=await transport(**kwargs)
                    raw=serializable(response)
                    record.update(status='response',raw_response=raw,usage=raw.get('usage'),
                        usage_source='provider' if raw.get('usage') is not None else 'unknown',
                        normalized_usage=normalized_usage(raw),ended_ns=time.time_ns(),
                        actual_model=raw.get('model'),elapsed_ms=(time.monotonic()-started)*1000)
                    private_write(path,record)  # Before upstream finish/parser/extraction.
                    if kind=='completion' and any(c.get('finish_reason') not in ('stop',) for c in raw.get('choices', [])):
                        raise ValueError('completion_not_finished')
                    return response
                except asyncio.CancelledError:
                    self.failed=True
                    record.update(status='unknown_outcome',error_code='cancelled',ended_ns=time.time_ns(),elapsed_ms=(time.monotonic()-started)*1000)
                    private_write(path,record); raise
                except Exception as exc:
                    self.failed=True
                    record.update(status='error',error_code=type(exc).__name__,ended_ns=time.time_ns(),elapsed_ms=(time.monotonic()-started)*1000)
                    private_write(path,record); raise
        finally:
            self.tasks.discard(task)


def install_policy(recorder, completion_transport=None, embedding_transport=None):
    import src.providers.llm.litellm as llm
    import src.providers.embedder.litellm as emb
    from litellm import acompletion, aembedding

    async def completion(**kwargs): return await recorder.call('completion',completion_transport or acompletion,**kwargs)
    async def embedding(**kwargs): return await recorder.call('embedding',embedding_transport or aembedding,**kwargs)
    llm.acompletion=completion
    emb.aembedding=embedding
    # Narrow pinned decorators only; do not globally alter backoff behavior.
    if not hasattr(llm.LitellmLLMProvider,'_cpea_original_generator'):
        original=llm.LitellmLLMProvider.get_generator
        llm.LitellmLLMProvider._cpea_original_generator=original
        def generator(self,*args,**kwargs):
            if self._has_fallbacks: raise ValueError('fallbacks_forbidden')
            return inspect.unwrap(original(self,*args,**kwargs))
        llm.LitellmLLMProvider.get_generator=generator
    emb.AsyncTextEmbedder.run=inspect.unwrap(emb.AsyncTextEmbedder.run)
    if not hasattr(emb.AsyncDocumentEmbedder,'_cpea_original_run'):
        document_run=inspect.unwrap(emb.AsyncDocumentEmbedder.run)
        emb.AsyncDocumentEmbedder._cpea_original_run=document_run
        async def stable_document_run(self, documents):
            # Stable point IDs retain native retrieval ordering across exact replay.
            for doc in documents:
                doc.id=str(uuid.uuid5(uuid.NAMESPACE_URL,fingerprint({'content':doc.content,'meta':doc.meta})))
            return await document_run(self,documents)
        emb.AsyncDocumentEmbedder.run=stable_document_run


class ReplayTransport:
    """Consume recorded raw transport responses; never opens a model connection."""
    def __init__(self, calls):
        self.calls=list(calls); self.position=0

    async def _next(self, kind, kwargs):
        if self.position >= len(self.calls): raise ValueError('replay_exhausted')
        record=self.calls[self.position]; self.position+=1
        if record['kind'] != kind or record['request_fingerprint'] != fingerprint(safe_request(kwargs)):
            raise ValueError('replay_input_drift')
        if record['status'] != 'response': raise ValueError('replay_recorded_failure')
        from litellm import ModelResponse, EmbeddingResponse
        return (ModelResponse if kind=='completion' else EmbeddingResponse)(**record['raw_response'])

    async def completion(self, **kwargs): return await self._next('completion',kwargs)
    async def embedding(self, **kwargs): return await self._next('embedding',kwargs)
