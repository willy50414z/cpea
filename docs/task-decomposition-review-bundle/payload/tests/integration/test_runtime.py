import importlib
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from cpea.bootstrap import AssistantRuntime
from cpea.config.settings import AssistantSettings
from cpea.interfaces.api.app import create_app
from cpea.interfaces.cli.main import main
from cpea.application.errors import DependencyUnavailable
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.text_to_sql.schemas import AnswerDraft
from cpea.workflows.text_to_sql.sql_generation import create_graph
from tests.support import dependencies, write_profile, QUESTION, VIEW

def runtime_fixture(tmp_path, **kwargs):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    return AssistantRuntime(settings, catalog=catalog, llm=llm, retriever=retriever, context_packer=packer, **kwargs)

def test_unconfigured_execution_preflight_does_not_call_llm(tmp_path, capsys):
    runtime = runtime_fixture(tmp_path)
    client = TestClient(create_app(runtime))
    response = client.post('/api/assistant/query', json={'request': QUESTION})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'sql_executor_unavailable'
    assert runtime.llm.calls == 0
    assert main(['--execute'], runtime=runtime) == 3
    assert 'sql_executor_unavailable' in capsys.readouterr().err
    with pytest.raises(DependencyUnavailable):
        runtime.query(QUESTION)
    assert runtime.llm.calls == 0
    generated = client.post('/api/assistant/sql', json={'request': QUESTION})
    assert generated.status_code == 200 and generated.json()['supported']

def test_api_injected_query_and_payload(tmp_path):
    calls = []
    def executor(datasource, sql):
        calls.append((datasource, sql))
        return ['仓库名称', '库存数量'], [['A', 10]]
    runtime = runtime_fixture(tmp_path, executor=executor, datasource_id='test-datasource')
    client = TestClient(create_app(runtime))
    response = client.post('/api/assistant/query', json={'request': QUESTION, 'history': []})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {'answer', 'citations', 'sources', 'sql', 'columns', 'rows', 'rows_truncated', 'generation', 'term_mapping_reasoning'}
    assert payload['citations'] == ['[Source 1]'] and payload['rows'] == [['A', 10]]
    assert calls[0][0] == 'test-datasource' and len(calls) == 1
    rejected = client.post('/api/assistant/sql', json={'request': 'JOIN two views'})
    assert rejected.status_code == 200 and not rejected.json()['supported']
    assert client.post('/api/assistant/sql', json={'request': ''}).status_code == 422

def test_cli_and_graph_use_same_runtime(tmp_path, capsys):
    runtime = runtime_fixture(tmp_path)
    assert main(['--request', QUESTION], runtime=runtime) == 0
    assert json.loads(capsys.readouterr().out)['selected_views'] == [VIEW]
    assert set(create_graph(runtime).get_graph().nodes) >= {'retrieve_schema', 'match_candidates', 'finalize'}

@pytest.mark.parametrize('raw', [
    {'answer': 'example', 'citations': []},
    SimpleNamespace(content='{"answer":"example","citations":[]}'),
    SimpleNamespace(content=[{'text': '{"answer":"example",'}, {'text': '"citations":[]}'}]),
])
def test_shared_json_parser(raw):
    assert parse_model(raw, AnswerDraft).answer == 'example'

def test_import_and_factory_do_not_connect(tmp_path):
    profile = write_profile(tmp_path / 'projects' / 'gms2')
    (profile / '.env').write_text('ASSISTANT_RETRIEVAL_MODE=lexical\n', encoding='utf-8')
    code = f'''import os
import socket
def fail(*args, **kwargs):
    raise AssertionError("import/factory attempted a connection")
socket.socket.connect = fail
import cpea
from cpea.interfaces.api.app import create_app
from cpea.workflows.text_to_sql.sql_generation import create_graph
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
os.environ['CPEA_PROJECTS_ROOT'] = {str(tmp_path / 'missing-projects')!r}
try:
    create_app()
except ValueError as exc:
    assert 'selected project' in str(exc)
else:
    raise AssertionError('missing profile was accepted')
os.environ['CPEA_PROJECTS_ROOT'] = {str(profile.parent)!r}
app = create_app()
os.environ['CPEA_PROFILE_PATH'] = {str(profile)!r}
graph = create_graph()
assert SchemaCatalog({str(profile)!r}).profile_id == 'synthetic'
assert app.title == 'CPEA'
print(cpea.__version__)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_model_layer_import_direction():
    import ast
    import cpea
    package = Path(cpea.__file__).parent
    for folder in ['domain', 'application']:
        for path in (package / folder).rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            assert all(not (isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('cpea.interfaces')) for node in ast.walk(tree))
