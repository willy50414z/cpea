import asyncio
import json
from pathlib import Path


def test_real_retail_native_dual_index_and_retrieval(retail_schema,qdrant_url):
    from native_worker.namespace import NamespaceQdrantProvider
    from src.pipelines.indexing.db_schema import DBSchema
    from src.pipelines.indexing.table_description import TableDescription
    from src.pipelines.generation.intent_classification import IntentClassification
    from src.pipelines.retrieval.db_schema_retrieval import DbSchemaRetrieval
    from haystack import component
    schema = retail_schema
    assert len(schema['mdl']['models']) == 7
    assert sum(len(m['columns']) for m in schema['mdl']['models']) == 102

    @component
    class Documents:
        @component.output_types(documents=list)
        async def run(self, documents):
            for doc in documents:
                doc.embedding = [1., 0., 0., 0.]
            return {'documents': documents}

    class Embedder:
        def get_document_embedder(self): return Documents()
        def get_text_embedder(self): return self
        async def run(self, text): return {'embedding':[1.,0.,0.,0.]}

    class LLM:
        def get_model(self): return 'offline'
        def get_context_window_size(self): return 100000
        def get_generator(self, system_prompt, generation_kwargs):
            async def generate(prompt):
                if 'intent_classification' == generation_kwargs['response_format']['json_schema']['name']:
                    reply = {'results':'TEXT_TO_SQL','rephrased_question':'customer_id','reasoning':'explicit identifier'}
                else:
                    model = schema['mdl']['models'][0]
                    reply = {'results':[{'table_name':model['name'],'table_contents':{'columns':[c['name'] for c in model['columns']], 'chain_of_thought_reasoning':[]},'table_selection_reason':'fixture'}]}
                return {'replies':[json.dumps(reply)],'meta':[{}]}
            return generate

    async def run():
        provider = NamespaceQdrantProvider(namespace='cpea_wrenai_retail_spike',location=qdrant_url,embedding_model_dim=4)
        embedder, llm = Embedder(), LLM()
        for cls in (DBSchema, TableDescription):
            await cls(embedder_provider=embedder,document_store_provider=provider).run(json.dumps(schema['mdl']),project_id='spike-retail')
        db = provider.get_store(); tables = provider.get_store('table_descriptions')
        assert await db.count_documents() == 14
        assert await tables.count_documents() == 7
        intent = await IntentClassification(llm,embedder,provider,wren_ai_docs=[]).run('customer_id',project_id='spike-retail')
        assert intent['post_process']['intent'] == 'TEXT_TO_SQL'
        retrieval = await DbSchemaRetrieval(llm,embedder,provider).run('customer_id',project_id='spike-retail',enable_column_pruning=True)
        assert retrieval['construct_retrieval_results']['retrieval_results'][0]['table_name'] == schema['mdl']['models'][0]['name']
    asyncio.run(run())
