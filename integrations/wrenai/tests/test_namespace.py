import pytest


def test_all_six_stores_are_native_and_namespaced(qdrant_url):
    from native_worker.namespace import NamespaceQdrantProvider
    provider = NamespaceQdrantProvider(namespace='cpea_wrenai_spike',
        location=qdrant_url, embedding_model_dim=4)
    from src.providers.document_store.qdrant import AsyncQdrantDocumentStore
    assert len(provider.stores) == 6
    assert all(isinstance(s, AsyncQdrantDocumentStore) for s in provider.stores.values())
    assert {s.index for s in provider.stores.values()} == {
        'cpea_wrenai_spike_'+n for n in ('Document','table_descriptions','view_questions','sql_pairs','instructions','project_meta')}
    with pytest.raises(ValueError, match='recreate'):
        provider.get_store(recreate_index=True)
    with pytest.raises(ValueError, match='dataset'):
        provider.get_store('unknown')


def test_two_namespaces_and_dimensions_leave_shared_sentinel_untouched(qdrant_url):
    import asyncio
    from haystack import Document
    from native_worker.namespace import NamespaceQdrantProvider
    from qdrant_client import QdrantClient,models
    client=QdrantClient(url=qdrant_url)
    client.create_collection('Document',vectors_config=models.VectorParams(size=3,distance=models.Distance.COSINE))
    client.upsert('Document',[models.PointStruct(id=1,vector=[1.,0.,0.],payload={'sentinel':'keep'})])
    async def run():
        a=NamespaceQdrantProvider(namespace='cpea_wrenai_dimension_a',location=qdrant_url,embedding_model_dim=4)
        b=NamespaceQdrantProvider(namespace='cpea_wrenai_dimension_b',location=qdrant_url,embedding_model_dim=6)
        for provider,dimension in ((a,4),(b,6)):
            await provider.get_store().write_documents([Document(content=str(dimension),embedding=[1.]+[0.]*(dimension-1),meta={'project_id':str(dimension)})])
        assert await a.get_store().count_documents()==1
        assert await b.get_store().count_documents()==1
        assert (await a.get_store()._query_by_filters())[0].content=='4'
        assert (await b.get_store()._query_by_filters())[0].content=='6'
    asyncio.run(run())
    assert client.count('Document').count==1
    assert client.retrieve('Document',[1])[0].payload=={'sentinel':'keep'}
    assert client.get_collection('Document').config.params.vectors.size==3
    client.close()
