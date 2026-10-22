from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from cpea.bootstrap import ProjectRuntimes
from cpea.config.projects import configured_projects_root
from cpea.config.settings import AssistantSettings
from cpea.interfaces.api.app import create_app
from cpea.interfaces.web.ui import SessionGate, project_question_updates, reset_question
from cpea.interfaces.web.ui import single_question_updates, business_progress
from cpea.application.models.progress import WorkflowStep
from cpea.application.models.query import SQLGenerationResponse
from tests.hilp_support import QUESTION, runtime_for, selection
from tests.support import write_profile


def projects_fixture(root):
    for project_id in ProjectRuntimes.project_ids:
        profile = write_profile(root / project_id, profile_id=project_id)
        (profile / '.env').write_text(
            f'ASSISTANT_LLM_MODEL={project_id}-model\nASSISTANT_RETRIEVAL_MODE=lexical\n',
            encoding='utf-8')
    return ProjectRuntimes(root)


def test_project_runtimes_load_selected_env_and_ignore_startup_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('CPEA_PROFILE_PATH', str(tmp_path / 'stale-profile'))
    projects = projects_fixture(tmp_path / 'projects')
    try:
        gms2, retail = projects.get('gms2'), projects.get('retail')
        assert gms2 is projects.get('gms2')
        assert retail is projects.get('retail') and retail is not gms2
        for project_id, runtime in [('gms2', gms2), ('retail', retail)]:
            assert runtime.catalog.profile_id == project_id
            assert runtime.catalog.root == tmp_path / 'projects' / project_id
            assert runtime.settings.llm_model == f'{project_id}-model'
            assert runtime.datasource_id == runtime.settings.datasource_id == runtime.deployment.datasource_id == project_id
            assert 'llm' not in runtime.__dict__
        with pytest.raises(ValueError, match='not available'):
            projects.get('../gms2')
    finally:
        projects.close()


def test_project_name_binds_cli_web_executor_and_vocabulary_despite_stale_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('CPEA_DATASOURCE_ID', 'stale-startup-binding')
    projects = projects_fixture(tmp_path / 'custom-root')
    root = projects.projects_root / 'retail'
    with (root / '.env').open('a', encoding='utf-8') as file:
        file.write('CPEA_DATASOURCE_ID=old-retail-binding\n'
                   'CPEA_DEPLOYMENT_FILE=deployment.yaml\n'
                   'CPEA_DATABASE_URL=mssql+pymssql://test:test@server.example/retail\n')
    (root / 'deployment.yaml').write_text('datasource_id: old-deployment-binding\n', encoding='utf-8')
    bound = []
    def executor(settings, datasource_id, allowed_views, max_rows):
        bound.append(datasource_id)
        return SimpleNamespace(datasource_id=datasource_id)
    monkeypatch.setattr('cpea.infrastructure.database.sql_server.SQLServerExecutor', executor)
    try:
        # The CLI's explicit env path and the web project selector share this rule.
        assert AssistantSettings.from_env(root / '.env').datasource_id == 'retail'
        monkeypatch.setenv('CPEA_ENV_FILE', str(root / '.env'))
        assert AssistantSettings.from_env().datasource_id == 'retail'
        runtime = projects.get('retail')
        runtime.require_execution()
        assert runtime.datasource_id == runtime.executor.datasource_id == 'retail'
        assert bound == ['retail']
        from tests.support import Counter, StubLLM
        from cpea.infrastructure.llm.context_budget import ContextPacker
        runtime._llm = StubLLM()
        runtime._context_packer = ContextPacker(runtime.settings, token_counter=Counter())
        assert runtime.generation_service().workflow.repository.scope.datasource_id == 'retail'
        assert projects.get('gms2').datasource_id == 'gms2'
    finally:
        projects.close()


def test_projects_root_from_explicit_env_and_process_override(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('CPEA_PROJECTS_ROOT=private/projects\n', encoding='utf-8')
    monkeypatch.setenv('CPEA_ENV_FILE', str(env_file))
    monkeypatch.delenv('CPEA_PROJECTS_ROOT', raising=False)
    assert configured_projects_root() == tmp_path / 'private/projects'
    monkeypatch.setenv('CPEA_PROJECTS_ROOT', str(tmp_path / 'override'))
    assert configured_projects_root() == tmp_path / 'override'


def test_project_confirmation_stays_bound_and_mappings_are_isolated(tmp_path):
    runtimes = {project_id: runtime_for(tmp_path / project_id,
        executor=lambda d, s: (['value'], [[1]])) for project_id in ProjectRuntimes.project_ids}
    for project_id in runtimes:
        (tmp_path / project_id / '.env').write_text('', encoding='utf-8')
    projects = ProjectRuntimes(tmp_path,
        runtime_factory=lambda settings, **kwargs: runtimes[Path(settings.integration_path).name])
    gate = SessionGate('gms2')
    try:
        list(project_question_updates(projects, 'retail', QUESTION, gate))
        assert gate.project_id == 'retail' and gate.state == 'waiting_confirmation'
        assert list(project_question_updates(projects, 'gms2', QUESTION, gate)) == []
        from types import SimpleNamespace
        payload = selection(SimpleNamespace(clarification=gate.pending))
        # A stale or forged dropdown value cannot change the confirmation source.
        frames = list(project_question_updates(projects, 'gms2', '', gate, payload=payload))
        assert frames[-1].state == 'completed' and gate.project_id == 'retail'
        assert (tmp_path / 'retail' / 'terms_mapping.json').is_file()
        assert not (tmp_path / 'gms2' / 'terms_mapping.json').exists()
        assert runtimes['retail'].llm.calls == 1 and runtimes['gms2'].llm.calls == 0
        list(project_question_updates(projects, 'gms2', QUESTION, gate))
        assert gate.project_id == 'gms2' and gate.state == 'waiting_confirmation'
        fresh = reset_question(projects.get(gate.project_id), gate)
        assert fresh.project_id == 'gms2' and fresh.state == 'idle'
    finally:
        projects.close()


def test_web_project_dropdown_and_lifespan(tmp_path):
    projects = projects_fixture(tmp_path / 'projects')
    with TestClient(create_app(projects=projects)) as client:
        response = client.get('/config')
        assert response.status_code == 200
        components = response.json()['components']
        selector = next(c for c in components if c['props'].get('elem_id') == 'cpea-project')
        assert selector['props']['choices'] == [['gms2', 'gms2'], ['retail', 'retail']]
        assert selector['props']['value'] == 'gms2'
        assert selector['props']['visible'] is True
        assert projects.get('retail').catalog.profile_id == 'retail'


def test_project_load_failure_returns_controlled_error(tmp_path, caplog):
    projects = ProjectRuntimes(tmp_path)
    gate = SessionGate('gms2')
    frames = list(project_question_updates(projects, 'retail', QUESTION, gate))
    assert [frame.state for frame in frames] == ['generating', 'error']
    assert 'error_type=ValueError' in caplog.text
    assert str(tmp_path) not in str(frames[-1].messages)


def test_project_with_unsupported_url_reports_configuration_error_without_loading_model(tmp_path, caplog):
    projects = projects_fixture(tmp_path / 'projects')
    env = projects.projects_root / 'retail' / '.env'
    with env.open('a', encoding='utf-8') as file:
        file.write('CPEA_DATABASE_URL=mysql://private-user:top-secret@private-server/private-db\n')
    gate = SessionGate('retail')
    try:
        frames = list(project_question_updates(projects, 'retail', QUESTION, gate))
        assert frames[-1].state == 'error' and not frames[-1].sql
        assert '資料庫連線設定無效' in frames[-1].messages[-1]['content']
        assert 'phase=load_project' in caplog.text
        assert 'error_code=database_driver_unsupported' in caplog.text
        assert 'Database URL requires postgresql' in caplog.text
        for secret in ('private-user', 'top-secret', 'private-server', 'private-db'):
            assert secret not in caplog.text and secret not in str(frames)
        assert not projects._runtimes
    finally:
        projects.close()


@pytest.mark.parametrize('project_id, label', [('gms2', 'GMS2 業務資料'), ('retail', '零售示範資料')])
def test_unsupported_question_keeps_selected_dataset_visible_and_restores_question(project_id, label):
    def generate_updates(*args, **kwargs):
        yield WorkflowStep('match candidate view', {'view': 'private_schema.private_view'})
        yield SQLGenerationResponse(supported=False, explanation='private_schema.private_view unavailable',
                                    limitations=['private_schema.private_column'])
    runtime = SimpleNamespace(require_execution=lambda: None,
        staged_query_service=lambda: SimpleNamespace(generate_updates=generate_updates), finish=lambda result: None)
    gate = SessionGate(project_id)
    question = '依門市城市分組，顯示成本最大值。'
    frames = list(single_question_updates(runtime, question, gate))
    assert frames[-1].state == 'editing' and frames[-1].draft == question
    assert gate.project_id == project_id
    message = frames[-1].messages[-1]['content']
    assert f'本題資料集：{label}。' in message
    assert '請確認下方的 Project 選擇' in message
    assert 'private_schema' not in message and not frames[-1].sql


def test_dataset_progress_only_exposes_fixed_public_labels():
    assert business_progress([WorkflowStep('select project', 'gms2')]) == ['本題資料集：GMS2 業務資料。']
    assert business_progress([WorkflowStep('select project', 'private_schema.private_view'),
                              WorkflowStep('select project', {'secret': 'connection details'})]) == []
