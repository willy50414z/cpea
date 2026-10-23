from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import uuid
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary,path)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)
    path.chmod(0o600)


class Generation:
    # absent/failed/building -> building -> ready|failed; readers accept ready only.
    def __init__(self, root, identity):
        if not identity.get('project_id') or not identity.get('identity'):
            raise ValueError('empty_project_id')
        self.identity = identity
        Path(root).mkdir(parents=True,exist_ok=True,mode=0o700)
        Path(root).chmod(0o700)
        self.root = Path(root)/identity['namespace']
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.path = self.root/'generation.json'

    @contextmanager
    def lock(self):
        fd = os.open(self.root/'writer.lock', os.O_RDWR|os.O_CREAT, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise TimeoutError('index_locked') from None
            yield
        finally:
            os.close(fd)

    def _state(self, status, stores=None):
        private_write(self.path, {'identity':self.identity,'status':status,'stores':stores})

    def building(self): self._state('building')
    def failed(self): self._state('failed')
    def ready(self, stores):
        if set(stores) != {'Document','table_descriptions'} or any(v['count'] <= 0 for v in stores.values()):
            raise ValueError('incomplete_index')
        self._state('ready', stores)

    def state(self):
        if not self.path.exists(): return None
        try: return json.loads(self.path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            self.failed()
            return {'identity':self.identity,'status':'failed'}

    def verify(self, stores):
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if state['identity'] != self.identity: raise ValueError('manifest_identity_mismatch')
        if state['status'] != 'ready': raise ValueError('index_not_ready')
        if state['stores'] != stores: raise ValueError('index_drift')
        return True


async def store_state(provider, project_id):
    result = {}
    filters={'field':'project_id','operator':'==','value':project_id}
    for name in ('Document','table_descriptions'):
        docs = await provider.get_store(name)._query_by_filters(filters=filters)
        payloads = sorted(canonical({'content':d.content,'meta':d.meta}) for d in docs)
        result[name]={'count':len(docs),'digest':fingerprint(payloads)}
    return result


async def snapshot_stores(provider, project_id, document_order):
    from src.providers.document_store.qdrant import convert_qdrant_point_to_haystack_document
    from qdrant_client import models
    snapshots={}
    for name in ('Document','table_descriptions'):
        store=provider.get_store(name); offset=None; docs=[]
        while True:
            points,offset=await store.async_client.scroll(collection_name=store.index,offset=offset,limit=100,
                scroll_filter=models.Filter(must=[models.FieldCondition(key='project_id',match=models.MatchValue(value=project_id))]),
                with_vectors=True,with_payload=True)
            docs.extend(convert_qdrant_point_to_haystack_document(p,use_sparse_embeddings=False).to_dict(flatten=False) for p in points)
            if offset is None: break
        order={fingerprint({'content':d.content,'meta':d.meta}):i for i,d in enumerate(document_order[name])}
        docs.sort(key=lambda d:order[fingerprint({'content':d['content'],'meta':d['meta']})])
        snapshots[name]=docs
    return snapshots


async def restore_snapshot(root, manifest, snapshots, qdrant_url, dimension):
    from .namespace import NamespaceQdrantProvider
    from haystack import Document
    provider=NamespaceQdrantProvider(namespace=manifest['namespace'],location=qdrant_url,embedding_model_dim=dimension)
    generation=Generation(Path(root)/'generations',manifest)
    with generation.lock():
        generation.building()
        try:
            for name in ('Document','table_descriptions'):
                await provider.get_store(name).write_documents([Document.from_dict(d) for d in snapshots[name]])
            generation.ready(await store_state(provider,manifest['project_id']))
        except BaseException:
            generation.failed(); raise
