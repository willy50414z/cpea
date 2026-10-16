from dataclasses import replace
from pathlib import Path
import os
import pytest
import yaml
from langchain_core.embeddings import Embeddings
from cpea.config.settings import AssistantSettings
from cpea.config.deployment import DeploymentSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.retrieval.schema import SchemaRetriever, get_schema_retriever
from tests.support import write_profile, dependencies, Workflow, StubLLM, ContextPacker, Counter, QUESTION

@pytest.fixture
def clean_settings(monkeypatch):
    for name in list(os.environ):
        if name.startswith(('CPEA_', 'ASSISTANT_', 'LLM_', 'EMBEDDING_', 'RETRIEVAL_', 'RERANKER_', 'RERANK_', 'TOKEN_COUNT_')):
            monkeypatch.delenv(name, raising=False)

def test_explicit_env_file_priority_and_paths(tmp_path, monkeypatch, clean_settings):
    file = tmp_path / '.env'
    file.write_text('ASSISTANT_LLM_MODEL=file-model\nASSISTANT_MAX_ROWS=12\nCPEA_PROFILE_PATH=profile\n', encoding='utf-8')
    monkeypatch.setenv('LLM_MODEL', 'process-model')
    settings = AssistantSettings.from_env(file)
    assert settings.llm_model == 'process-model' and settings.max_rows == 12
    assert settings.integration_path == str(tmp_path / 'profile')
    assert 'ASSISTANT_MAX_ROWS' not in os.environ
    monkeypatch.chdir(tmp_path)
    assert AssistantSettings.from_env().max_rows == 200

@pytest.mark.parametrize('name', ['ASSISTANT_MAX_ROWS', 'ASSISTANT_LLM_TIMEOUT_SECONDS', 'ASSISTANT_LLM_TEMPERATURE'])
def test_invalid_setting_diagnostic_omits_value(monkeypatch, clean_settings, name):
    monkeypatch.setenv(name, 'sensitive-placeholder')
    with pytest.raises(ValueError) as error:
        AssistantSettings.from_env()
    assert name in str(error.value)
    assert 'sensitive-placeholder' not in str(error.value)

def test_deployment_relative_path_and_secret_repr(tmp_path, clean_settings):
    file = tmp_path / 'enterprise.yaml'
    file.write_text('deployment_id: acme\nprofile_path: profile\ndatasource_id: datasource\nsecret_references: {db: vault-reference}\n', encoding='utf-8')
    deployment = DeploymentSettings.load(str(file))
    assert deployment.profile_path == tmp_path / 'profile'
    assert deployment.datasource_id == 'datasource'
    assert 'vault-reference' not in repr(deployment)

@pytest.mark.parametrize('resource', ['../outside.yaml', '/absolute.yaml'])
def test_profile_escape_rejected(tmp_path, resource):
    profile = write_profile(tmp_path / 'profile')
    config = yaml.safe_load((profile / 'catalog.yaml').read_text(encoding='utf-8'))
    next(iter(config['views'].values()))['path'] = resource
    (profile / 'catalog.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    with pytest.raises(ValueError, match='inside its profile root'):
        SchemaCatalog(profile)

def test_profile_symlink_escape(tmp_path):
    profile = write_profile(tmp_path / 'profile')
    outside = tmp_path / 'outside.yaml'
    outside.write_text('secret: outside', encoding='utf-8')
    link = profile / 'linked.yaml'
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable; path traversal is covered separately')
    (profile / 'catalog.yaml').write_text('views:\n  gms2.v_inventory:\n    path: linked.yaml\n', encoding='utf-8')
    with pytest.raises(ValueError, match='inside its profile root'):
        SchemaCatalog(profile)

class OfflineEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]
    def embed_query(self, text):
        return [1.0, 0.0]

def test_other_schema_lexical_vector_and_generation(tmp_path, clean_settings):
    profile = write_profile(tmp_path, 'other.v_inventory', profile_id='other')
    catalog = SchemaCatalog(profile)
    settings = replace(AssistantSettings.from_env(), context_window=16000, retrieval_mode='lexical')
    for mode in ['lexical', 'vector']:
        retriever = SchemaRetriever(replace(settings, retrieval_mode=mode), catalog, embeddings=OfflineEmbeddings())
        assert retriever.retrieve(QUESTION).candidates[0].document.metadata['document_id'] == 'other.v_inventory'
    workflow = Workflow(StubLLM('other.v_inventory'), catalog, settings=settings, retriever=SchemaRetriever(settings, catalog), context_packer=ContextPacker(settings, Counter()))
    assert 'FROM other.v_inventory' in workflow.invoke(QUESTION).sql

def test_cache_profile_identity_and_content_change(tmp_path, clean_settings):
    settings = replace(AssistantSettings.from_env(), retrieval_mode='lexical')
    a = SchemaCatalog(write_profile(tmp_path / 'a', profile_id='a'))
    b = SchemaCatalog(write_profile(tmp_path / 'b', 'other.v_inventory', profile_id='b'))
    first = get_schema_retriever(settings, a)
    assert first is get_schema_retriever(settings, a)
    assert first is not get_schema_retriever(settings, b)
    path = a.root / 'inventory.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace('合成示例', '更新示例'), encoding='utf-8')
    changed = SchemaCatalog(a.root)
    assert changed.fingerprint != a.fingerprint
    assert get_schema_retriever(settings, changed) is not first

def test_injected_catalog_does_not_require_hashability(tmp_path, clean_settings):
    class UnhashableCatalog(SchemaCatalog):
        __hash__ = None
    catalog = UnhashableCatalog(write_profile(tmp_path))
    settings = replace(AssistantSettings.from_env(), retrieval_mode='lexical')
    assert get_schema_retriever(settings, catalog).catalog is catalog

def test_compiler_directives_cannot_be_injected_from_profile(tmp_path):
    profile = write_profile(tmp_path)
    path = profile / 'inventory.yaml'
    policy = yaml.safe_load(path.read_text(encoding='utf-8'))
    policy['columns']['库存数量']['aggregations'] = ['sum); DROP TABLE x; --']
    path.write_text(yaml.safe_dump(policy), encoding='utf-8')
    with pytest.raises(ValueError, match='aggregations'):
        SchemaCatalog(profile)

def test_invalid_v3_grain_key_identifies_contract_and_column(tmp_path):
    profile = write_profile(tmp_path / 'profile')
    path = profile / 'inventory.yaml'
    policy = {
        'version': 3,
        'view': 'gms2.v_inventory',
        'summary': '合成庫存',
        'grain': {'description': '每個品號一列', 'keys': ['品号, 仓库名称']},
        'columns': {'品号': {'type': 'string', 'role': 'identifier', 'description': '品號'}},
    }
    path.write_text(yaml.safe_dump(policy, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError) as error:
        SchemaCatalog(profile)
    message = str(error.value)
    assert 'inventory.yaml (gms2.v_inventory)' in message
    assert "grain.keys[0] '品号, 仓库名称' is not a column" in message
