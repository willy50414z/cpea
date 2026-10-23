import hashlib
import importlib
import json
from pathlib import Path
import sys

import jsonschema
from src.pipelines.indexing.db_schema import DBSchema, DDLChunker
from src.pipelines.indexing.table_description import TableDescription, TableDescriptionChunker
from src.pipelines.generation.intent_classification import IntentClassification
from src.pipelines.retrieval.db_schema_retrieval import DbSchemaRetrieval
from src.providers.llm.litellm import LitellmLLMProvider
from src.providers.embedder.litellm import LitellmEmbedderProvider
from src.web.v1.services import Configuration

from .draft_planning import DraftPlanning
from .generation import Generation, canonical, fingerprint, private_write, store_state
from .guards import Budget, validate_selection
from .namespace import NamespaceQdrantProvider
from .transport import Recorder, install_policy
from .source import verify_checkout

UPSTREAM_SHA='ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc'
MODULES=('src.pipelines.indexing.db_schema','src.pipelines.indexing.table_description',
         'src.pipelines.generation.intent_classification','src.pipelines.retrieval.db_schema_retrieval','src.core.pipeline')


def provenance():
    sources={m:str(Path(importlib.import_module(m).__file__).resolve()) for m in MODULES}
    service=Path(sources[MODULES[0]]).parents[3]
    sha,lock=verify_checkout(service)
    if not all(Path(path).is_relative_to(service/'src') for path in sources.values()):
        raise ValueError('upstream_source_drift')
    local=Path(__file__).parent
    files=sorted(local.glob('*.py'))+[local.parent/'worker.py',local.parent/'bootstrap.py']
    patch=fingerprint({str(p.relative_to(local.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    return {'upstream_sha':sha,'patch_sha':patch,
        'lock_sha256':lock,
        'python_version':'.'.join(map(str,sys.version_info[:3])),'import_sources':sources,
        'capabilities':['native_indexing','native_intent','native_retrieval','draft_planning','transport_replay']}


class GuardedLLM(LitellmLLMProvider):
    def __init__(self, *, mdl, root, recorder, **kwargs):
        self.mdl=mdl; self.root=Path(root); self.recorder=recorder
        super().__init__(**kwargs)

    def get_generator(self, *args, **kwargs):
        generator=super().get_generator(*args,**kwargs)
        schema=kwargs.get('generation_kwargs',{}).get('response_format',{}).get('json_schema',{})
        async def guarded(**inputs):
            result=await generator(**inputs)
            try:
                raw=json.loads(result['replies'][0])
                private_write(self.root/(schema['name']+'-raw.json'),raw)
                jsonschema.validate(raw,schema['schema'])
                if schema['name']=='retrieval_schema': validate_selection(raw,self.mdl)
                self.recorder.parsed(raw)
            except Exception as exc:
                self.recorder.parsed(error=type(exc).__name__)
                raise
            return result
        return guarded


class NativeWrenAIPlanner:
    def __init__(self, *, runtime_root, qdrant_url, embedding_dimension,
                 model='offline', embedding_model='offline', context_window=32768,
                 output_reserve=4096, safety=512, tokenizer='cl100k_base',
                 completion_transport=None, embedding_transport=None):
        if completion_transport is None or embedding_transport is None:
            raise ValueError('explicit_model_transports_required')
        self.root=Path(runtime_root); self.qdrant_url=qdrant_url; self.dimension=embedding_dimension
        for path in (self.root,self.root/'runs'):
            path.mkdir(parents=True,exist_ok=True,mode=0o700); path.chmod(0o700)
        self.model=model; self.embedding_model=embedding_model
        self.completion_transport=completion_transport; self.embedding_transport=embedding_transport
        self.budget=Budget(context_window=context_window,output_reserve=output_reserve,safety=safety,encoding=tokenizer)
        self.configuration={'model':model,'embedding_model':embedding_model,'embedding_dimension':embedding_dimension,
            'context_window':context_window,'output_reserve':output_reserve,'safety':safety,'tokenizer':tokenizer}
        self.last_recorder=None

    async def plan(self, payload):
        # A worker serializes requests; the manifest lock also protects other processes.
        ids={k:payload.get(k) for k in ('request_id','run_id','case_id')}
        run_key=fingerprint(ids)
        run_dir=self.root/'runs'/run_key
        private_write(run_dir/'input.json',payload)
        metadata=provenance()
        fields={'catalog_fingerprint':payload['catalog_fingerprint'],'adapter_version':payload['schema']['adapter_version'],
            'upstream_sha':UPSTREAM_SHA,'patch_sha':metadata['patch_sha'],'lock_sha256':metadata['lock_sha256'],
            'embedding_provider':'litellm','embedding_model':self.embedding_model,'embedding_dimension':self.dimension}
        identity=fingerprint(fields)
        manifest={**fields,'identity':identity,'project_id':identity,'namespace':'cpea_wrenai_'+identity[:24]}
        from .draft_planning import SYSTEM,TEMPLATE
        runtime_identity={k:metadata[k] for k in ('upstream_sha','patch_sha','lock_sha256','python_version')}
        runtime_identity.update(model=self.model,embedding_model=self.embedding_model,tokenizer=self.configuration['tokenizer'],
            prompt_sha256=fingerprint({'system':SYSTEM,'template':TEMPLATE}),schema_sha256=fingerprint(payload['response_schema']),
            input_sha256=fingerprint(payload),catalog_fingerprint=payload['catalog_fingerprint'],index_identity=manifest)
        runtime_identity['configuration_sha256']=fingerprint(self.configuration)
        runtime={'identity':runtime_identity,'configuration':self.configuration,
            'provenance':metadata,'manifest':manifest,'input_fingerprint':fingerprint(payload),
            'fixture_source':'fake','execution_mode':'offline_injected'}
        private_write(run_dir/'runtime.json',runtime)
        recorder=Recorder(run_dir,ids,self.budget); self.last_recorder=recorder
        install_policy(recorder,self.completion_transport,self.embedding_transport)
        provider=NamespaceQdrantProvider(namespace=manifest['namespace'],location=self.qdrant_url,embedding_model_dim=self.dimension)
        embedder=LitellmEmbedderProvider(model=self.embedding_model,batch_size=32)
        llm=GuardedLLM(mdl=payload['schema']['mdl'],root=run_dir,recorder=recorder,model=self.model,context_window_size=self.budget.context_window)
        generation=Generation(self.root/'generations',manifest)
        try:
            with generation.lock():
                if generation.path.exists():
                    old=generation.state()
                    if old['identity']!=manifest: raise ValueError('manifest_identity_mismatch')
                    reuse=old['status']=='ready'
                else: reuse=False
                if not reuse:
                    generation.building()
                    try:
                        mdl=payload['schema']['mdl']; project_id=identity
                        pipelines=[cls(embedder_provider=embedder,document_store_provider=provider) for cls in (DBSchema,TableDescription)]
                        expected={}
                        dbchunks=await DDLChunker().run(mdl=mdl,column_batch_size=50,project_id=project_id)
                        tablechunks=TableDescriptionChunker().run(mdl=mdl,project_id=project_id)
                        for name,chunks in [('Document',dbchunks),('table_descriptions',tablechunks)]:
                            expected[name]={'count':len(chunks['documents']),'digest':fingerprint(sorted(canonical({'content':d.content,'meta':d.meta}) for d in chunks['documents']))}
                        for pipeline in pipelines:
                            await pipeline.run(json.dumps(mdl),project_id=identity)
                        actual=await store_state(provider,identity)
                        private_write(run_dir/'index-verification.json',{'expected':expected,'actual':actual})
                        if actual!=expected: raise ValueError('index_content_mismatch')
                        generation.ready(actual)
                    except BaseException:
                        generation.failed(); raise
                generation.verify(await store_state(provider,identity))
                from .generation import snapshot_stores
                from src.pipelines.indexing.utils.helper import load_helpers
                load_helpers()
                ordered_db=await DDLChunker().run(mdl=payload['schema']['mdl'],column_batch_size=50,project_id=identity)
                ordered_tables=TableDescriptionChunker().run(mdl=payload['schema']['mdl'],project_id=identity)
                snapshot=await snapshot_stores(provider,identity,{'Document':ordered_db['documents'],'table_descriptions':ordered_tables['documents']})
                private_write(run_dir/'index-snapshot.json',snapshot)
                runtime['snapshot_sha256']=fingerprint(snapshot)
                runtime['index_state']=await store_state(provider,identity)
                recorder.node_id='intent'
                intent=(await IntentClassification(llm,embedder,provider,wren_ai_docs=[]).run(
                    payload['request'],project_id=identity,histories=[],sql_samples=[],instructions=[],
                    configuration=Configuration(language='Traditional Chinese')))['post_process']
                private_write(run_dir/'intent.json',intent)
                if intent['intent']!='TEXT_TO_SQL':
                    status='needs_clarification' if intent['intent']=='MISLEADING_QUERY' else 'unsupported'
                    draft={'status':status,'tasks':[], 'clarifications':[intent['reasoning']] if status=='needs_clarification' else [],
                        'unsupported_reasons':[intent['reasoning']] if status=='unsupported' else []}
                else:
                    recorder.node_id='schema_retrieval'
                    retrieval=(await DbSchemaRetrieval(llm,embedder,provider).run(payload['request'],project_id=identity,
                        histories=[],enable_column_pruning=True))['construct_retrieval_results']
                    private_write(run_dir/'retrieval-rendered.json',retrieval)
                    if not retrieval['retrieval_results']:
                        draft={'status':'needs_clarification','tasks':[], 'clarifications':['No schema candidates; specify the requested view or fields.']}
                    else:
                        selected=[r['table_name'] for r in retrieval['retrieval_results']]
                        mapping={n:payload['schema']['model_to_view'][n] for n in selected}
                        contracts={v:payload['schema']['contracts'][v] for v in mapping.values()}
                        recorder.node_id='draft_planning'
                        draft=(await DraftPlanning(llm,payload['response_schema']).run(request=payload['request'],intent=intent,
                            retrieval=retrieval,mapping=mapping,contracts=contracts,response_schema=payload['response_schema']))['draft_result']
                jsonschema.validate(draft,payload['response_schema'])
                private_write(run_dir/'draft.json',draft)
                result={'draft':draft,'context_tokens':recorder.context_tokens,'token_counter':self.budget.counter,
                    'artifacts':{'run_dir':str(run_dir.resolve()),'calls':recorder.calls,'manifest':manifest,
                                 'input_fingerprint':fingerprint(payload),'sent_attempts':recorder.sent_attempts}}
                private_write(run_dir/'response.json',result)
                return result
        finally:
            await recorder.drain()
            runtime_identity['prompt_sha256']=fingerprint(recorder.rendered_prompts)
            runtime['rendered_prompt_fingerprints']=recorder.rendered_prompts
            private_write(run_dir/'runtime.json',runtime)
            private_write(run_dir/'ledger.json',{'calls':recorder.calls,'sent_attempts':recorder.sent_attempts,
                'transport_complete':not recorder.failed,'node_id':recorder.node_id,'summary':recorder.summary()})
