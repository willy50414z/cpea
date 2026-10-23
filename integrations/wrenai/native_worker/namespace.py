import re

from src.providers.document_store.qdrant import QdrantProvider

DATASETS = ('Document', 'table_descriptions', 'view_questions', 'sql_pairs', 'instructions', 'project_meta')


class NamespaceQdrantProvider(QdrantProvider):
    """Map every native dataset before upstream initializes any store."""
    def __init__(self, *, namespace, **kwargs):
        if not re.fullmatch(r'cpea_wrenai_[a-zA-Z0-9_]+', namespace):
            raise ValueError('invalid namespace')
        if kwargs.pop('recreate_index', False):
            raise ValueError('recreate is forbidden')
        self.namespace = namespace
        self.stores = {}
        super().__init__(recreate_index=False, **kwargs)

    def get_store(self, dataset_name=None, recreate_index=False):
        if recreate_index:
            raise ValueError('recreate is forbidden')
        logical = dataset_name or 'Document'
        if logical not in DATASETS:
            raise ValueError('unknown dataset')
        if logical not in self.stores:
            self.stores[logical] = super().get_store(
                dataset_name=f'{self.namespace}_{logical}', recreate_index=False)
        return self.stores[logical]
