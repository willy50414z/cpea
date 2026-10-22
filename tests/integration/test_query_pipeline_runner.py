import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpea.application.models.query import SQLGenerationResponse
from cpea.config.settings import AssistantSettings
from evaluations.query_pipeline_cases import CASE_SCHEMA_VERSION, case_sha256
from evaluations.query_pipeline_runner import evaluate_query_pipeline, replay_query_pipeline
from tests.decomposition_support import catalog_at, settings
from tests.query_pipeline_support import generation, planning


def dataset(tmp_path, *, reviewed=True):
    catalog = catalog_at(tmp_path / 'profile')
    plan = planning(catalog, single=True)
    case = dict(schema_version=CASE_SCHEMA_VERSION, case_id='oracle-secret-id', request='目前庫存',
        requirements=['門市商品庫存'], required_capabilities=['raw_rows'],
        expected_stage_status='sql_ready', expected_planning_status='ready',
        approved_plans=[plan.draft.model_dump()], profile_id=catalog.profile_id,
        contract_fingerprint=catalog.fingerprint, review_state='approved' if reviewed else 'pending')
    case['case_sha256'] = case_sha256(case)
    if reviewed:
        case.update(reviewer='offline-fixture', reviewed_at='2026-10-22T00:00:00Z',
                    reviewed_case_sha256=case['case_sha256'], reviewed_contract_fingerprint=catalog.fingerprint)
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps([case], ensure_ascii=False), encoding='utf-8')
    return catalog, plan, path


def factories(plan, calls, *, failure=False):
    def planner_factory(*, catalog, settings, observer):
        calls.append(('planner_factory', settings.llm_model))
        def plan_request(request):
            assert request == '目前庫存' and 'oracle-secret-id' not in request
            calls.append(('planning', request))
            return plan
        return SimpleNamespace(plan=plan_request)
    def generator_factory(*, catalog, settings, repository):
        calls.append(('sql_factory', settings.llm_model, str(repository.path)))
        assert not repository.read().mappings
        def generate(request, history, **kwargs):
            assert 'oracle-secret-id' not in request and not history
            calls.append(('sql', request))
            if failure: raise RuntimeError('API_KEY=private-token rate limit 429')
            return generation(plan.draft.tasks[0], catalog, settings)
        return SimpleNamespace(generate=generate)
    return planner_factory, generator_factory


def run(tmp_path, mode='integrated', *, reviewed=True, failure=False, runs=1):
    catalog, plan, path = dataset(tmp_path, reviewed=reviewed)
    calls = []
    planner, generator = factories(plan, calls, failure=failure)
    result = evaluate_query_pipeline(mode=mode, profile=catalog.root, cases_path=path,
        env_file=tmp_path / 'unused.env', planner_settings=replace(settings(), llm_model='planning-model'),
        sql_settings=replace(settings(), llm_model='sql-model'), runs=runs,
        output_root=tmp_path / 'runs', planner_factory=planner, generator_factory=generator)
    return result, calls, path, catalog


@pytest.mark.parametrize('mode,origins,expected', [
    ('planning', 'original_request', ['planning']), ('sql', 'approved_tasks', ['sql']),
    ('integrated', 'natural_planning', ['planning', 'sql'])])
def test_modes_use_expected_input_origins_and_model_factories(tmp_path, mode, origins, expected):
    result, calls, _, _ = run(tmp_path, mode)
    assert [c[0] for c in calls if c[0] in {'planning', 'sql'}] == expected
    metadata = json.loads((Path(result['output']) / 'run.json').read_text(encoding='utf-8'))
    assert metadata['input_origin'] == origins
    assert metadata['kind'] == 'stub' and result['natural_success'] == 0
    assert metadata['nodes']['planning']['settings']['llm_model'] == 'planning-model'
    assert metadata['nodes']['sql']['settings']['llm_model'] == 'sql-model'
    assert metadata['nodes']['planning']['schema_sha256'] and metadata['nodes']['sql']['source_sha256']


def test_pending_cases_require_exploratory(tmp_path):
    with pytest.raises(ValueError, match='exploratory'):
        run(tmp_path, reviewed=False)


def test_provider_error_preserves_first_failure_and_marks_remaining_skipped(tmp_path):
    result, calls, _, _ = run(tmp_path, failure=True, runs=3)
    assert result['failed'] == 1 and result['skipped'] == 2
    assert len([c for c in calls if c[0] == 'sql']) == 1
    output = Path(result['output'])
    for path in output.glob('*'):
        if path.is_file(): assert 'private-token' not in path.read_text(encoding='utf-8')
    assert 'private-token' in (output / 'private/provider-error.txt').read_text(encoding='utf-8')


def test_case_and_contract_drift_fail_before_factories(tmp_path):
    catalog, _, path = dataset(tmp_path)
    cases = json.loads(path.read_text(encoding='utf-8'))
    cases[0]['request'] = '內容遭更動'
    path.write_text(json.dumps(cases), encoding='utf-8')
    def forbidden(**kwargs): raise AssertionError('must reject before factory')
    with pytest.raises(ValueError, match='drift'):
        evaluate_query_pipeline(mode='integrated', profile=catalog.root, cases_path=path,
            env_file=tmp_path / 'unused', planner_settings=settings(), sql_settings=settings(),
            planner_factory=forbidden, generator_factory=forbidden)


def test_replay_makes_zero_model_and_db_calls_and_keeps_original_run(tmp_path, monkeypatch):
    result, _, cases, catalog = run(tmp_path)
    output = Path(result['output'])
    original = {str(p): p.read_bytes() for p in output.rglob('*') if p.is_file()}
    import evaluations.query_pipeline_runner as runner
    def forbidden(*args, **kwargs): raise AssertionError('no model during replay')
    monkeypatch.setattr(runner, 'get_llm_config', forbidden)
    replay = replay_query_pipeline(output, profile=catalog.root, cases_path=cases, output_root=tmp_path / 'replay')
    assert replay['natural_success'] == 0 and replay['model_calls'] == 0
    assert original == {str(p): p.read_bytes() for p in output.rglob('*') if p.is_file()}
    metadata = json.loads((Path(replay['output']) / 'run.json').read_text(encoding='utf-8'))
    assert metadata['mode'] == 'integrated' and metadata['input_origin'] == 'natural_planning'
    assert metadata['replay_of']['run_sha256'] and metadata['grader_sha256']


def test_factory_mode_never_connects_network_or_database(tmp_path, monkeypatch):
    import socket
    import cpea.infrastructure.database.factory as db
    def forbidden(*args, **kwargs): raise AssertionError('no DB or network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    for key in vars(db).copy():
        if 'executor' in key.lower(): monkeypatch.setattr(db, key, forbidden)
    result, _, _, _ = run(tmp_path)
    assert result['automated_pass'] == 1


def test_model_task_id_cannot_escape_artifact_directory(tmp_path):
    catalog, plan, path = dataset(tmp_path)
    malicious = '../../../../escaped'
    plan.draft.tasks[0].task_id = malicious
    plan.draft.integration.anchor_task = malicious
    from cpea.workflows.task_decomposition.validation import prepare_requests
    plan.prepared_requests = prepare_requests(plan.draft, catalog)
    calls = []
    planner, generator = factories(plan, calls)
    result = evaluate_query_pipeline(mode='integrated', profile=catalog.root, cases_path=path,
        env_file=tmp_path / 'unused', planner_settings=settings(), sql_settings=settings(),
        output_root=tmp_path / 'runs', planner_factory=planner, generator_factory=generator)
    output = Path(result['output'])
    task_inputs = list(output.glob('private/trials/*/tasks/*/input.json'))
    assert len(task_inputs) == 1 and task_inputs[0].parent.name == '0000'
    assert json.loads(task_inputs[0].read_text(encoding='utf-8'))['task']['task_id'] == malicious
    assert not (tmp_path / 'escaped').exists()


def test_live_requires_explicit_opt_in_before_constructing_models(tmp_path):
    catalog, _, path = dataset(tmp_path)
    with pytest.raises(ValueError, match='--live'):
        evaluate_query_pipeline(mode='integrated', profile=catalog.root, cases_path=path,
            env_file=tmp_path / 'unused', planner_settings=settings(), sql_settings=settings())


def test_replay_detects_catalog_and_source_drift(tmp_path, monkeypatch):
    result, _, cases, catalog = run(tmp_path)
    import evaluations.query_pipeline_runner as runner
    original_versions = runner._versions
    def changed(settings):
        versions = original_versions(settings)
        versions['pipeline_sha256'] = 'changed'
        return versions
    monkeypatch.setattr(runner, '_versions', changed)
    replay = replay_query_pipeline(Path(result['output']), profile=catalog.root, cases_path=cases,
                                   output_root=tmp_path / 'replays')
    assert json.loads((Path(replay['output']) / 'run.json').read_text(encoding='utf-8'))['source_drift']
    raw = json.loads(cases.read_text(encoding='utf-8'))
    raw[0]['request'] = 'new meaning'
    raw[0]['case_sha256'] = case_sha256(raw[0])
    raw[0]['reviewed_case_sha256'] = raw[0]['case_sha256']
    cases.write_text(json.dumps(raw), encoding='utf-8')
    with pytest.raises(ValueError, match='incompatible_replay'):
        replay_query_pipeline(Path(result['output']), profile=catalog.root, cases_path=cases)


def test_recorded_model_never_retries_provider_error_even_when_value_error(tmp_path):
    from evaluations.query_pipeline_runner import _RecordedModel
    journal = dict(calls=[], stopped=False, error=None)
    calls = []
    def fail(messages):
        calls.append(messages)
        raise ValueError('429 raw error')
    model = _RecordedModel(SimpleNamespace(invoke=fail), 'sql', journal)
    with pytest.raises(ValueError): model.invoke([])
    with pytest.raises(RuntimeError, match='no retry'): model.invoke([])
    assert len(calls) == 1 and len(journal['calls']) == 1


@pytest.mark.parametrize('mode', ['planning', 'integrated'])
def test_planning_provider_exception_skips_later_trials(tmp_path, mode):
    catalog, _, path = dataset(tmp_path)
    def planner_factory(**kwargs):
        def fail(request): raise RuntimeError('private planning provider failure')
        return SimpleNamespace(plan=fail)
    result = evaluate_query_pipeline(mode=mode, profile=catalog.root, cases_path=path,
        env_file=tmp_path / 'unused', planner_settings=settings(), sql_settings=settings(),
        runs=3, output_root=tmp_path / 'runs', planner_factory=planner_factory,
        generator_factory=lambda **kwargs: SimpleNamespace(generate=lambda *args, **kwargs: None))
    assert result['failed'] == 1 and result['skipped'] == 2
    assert 'private planning' in (Path(result['output']) / 'private/provider-error.txt').read_text(encoding='utf-8')


def test_pending_casefile_contains_twelve_synthetic_controls(tmp_path):
    from evaluations.query_pipeline_cases import load_pipeline_cases
    catalog = catalog_at(tmp_path)
    cases = load_pipeline_cases(Path('tests/fixtures/query_pipeline/cases.json'), catalog)
    assert len(cases) == 12
    assert sum(c['expected_stage_status'] == 'sql_ready' for c in cases) == 6
    assert all(c['review_state'] == 'pending' for c in cases)


def test_regrade_accepts_separate_human_reviews_without_changing_casefile(tmp_path):
    result, _, cases, catalog = run(tmp_path)
    original_casefile = cases.read_bytes()
    output = Path(result['output'])
    entries = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    fingerprint = entries[0]['grading']['response_sha256']
    reviews = tmp_path / 'reviews.json'
    reviews.write_text(json.dumps({'oracle-secret-id': {fingerprint: {
        'decision': 'approved', 'reviewer': 'fixture-reviewer', 'reviewed_at': '2026-10-22T00:00:00Z'}}}), encoding='utf-8')
    replay = replay_query_pipeline(output, profile=catalog.root, cases_path=cases,
        output_root=tmp_path / 'replay', reviews_path=reviews)
    rows = json.loads((Path(replay['output']) / 'result.json').read_text(encoding='utf-8'))
    assert rows[0]['grading']['success'] and not rows[0]['grading']['semantic_review_required']
    assert replay['natural_success'] == 0 and cases.read_bytes() == original_casefile
    meta = json.loads((Path(replay['output']) / 'run.json').read_text(encoding='utf-8'))
    assert meta['reviewfile_sha256']


def test_evaluation_failure_is_not_attributed_to_provider(tmp_path, monkeypatch):
    import evaluations.query_pipeline_runner as runner
    def fail(*args, **kwargs): raise ValueError('private grader configuration error')
    monkeypatch.setattr(runner, 'grade_pipeline_case', fail)
    result, _, _, _ = run(tmp_path, runs=3)
    output = Path(result['output'])
    entries = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert entries[0]['reason'] == 'evaluation_error'
    assert entries[0]['grading']['first_error_stage'] == 'evaluation'
    assert entries[1]['reason'] == 'evaluation_error'
    assert (output / 'private/evaluation-error.txt').is_file()
    assert not (output / 'private/provider-error.txt').exists()
