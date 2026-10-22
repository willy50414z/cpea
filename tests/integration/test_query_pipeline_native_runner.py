"""Native adapters share the pipeline artifact writer and preserve first attempts."""
import json
from pathlib import Path

import pytest

from evaluations.query_pipeline_grading import content_hash
from tests.unit.test_query_pipeline_experiments import descriptor, fixed_input


def experiment():
    from evaluations.query_pipeline_experiments import ExperimentManifest
    return ExperimentManifest(experiment_id='offline-pilot', scope='internal_coverage', mode='planning',
        case_hashes=['a' * 64], strategies=[descriptor()], runs=3, group='Diagnostic',
        preregistration_ref='private/approval.json')


def execute(tmp_path, *, transport=None, parser=json.loads):
    from evaluations.query_pipeline_runner import evaluate_strategy
    return evaluate_strategy(manifest=experiment(), inputs=[fixed_input()], strategy=descriptor(),
        transport=transport or (lambda context: '{"mapping": ["stock_qty"]}'),
        parser=parser, normalizer=lambda value: value, output_root=tmp_path)


def test_raw_is_persisted_before_parse_and_all_stages_are_hashed(tmp_path):
    def parser(raw):
        files = list(tmp_path.glob('*/private/trials/*/raw.json'))
        assert files and json.loads(files[-1].read_text(encoding='utf-8')) == raw
        return json.loads(raw)
    result = execute(tmp_path, parser=parser)
    root = Path(result['output'])
    observations = json.loads((root / 'observations.json').read_text(encoding='utf-8'))
    assert result['planned'] == 3 and result['completed'] == 3 and result['natural_success'] == 0
    for observation in observations:
        assert observation['input_tokens'] is None and observation['retries'] == 0
        for key in ('raw', 'parsed', 'normalized'):
            ref = observation[key]
            assert content_hash(json.loads((root / ref['ref']).read_text(encoding='utf-8'))) == ref['sha256']
    assert json.loads((root / 'run.json').read_text(encoding='utf-8'))['kind'] == 'stub'
    assert (root / 'experiment.json').exists() and (root / 'strategy.json').exists()


@pytest.mark.parametrize('stage', ['provider', 'parse', 'normalize'])
def test_interruption_keeps_first_error_and_fixed_denominator(tmp_path, stage):
    from evaluations.query_pipeline_runner import evaluate_strategy
    calls = []
    def transport(context):
        calls.append(context)
        if stage == 'provider':
            raise RuntimeError('private provider diagnostic 429')
        return 'not json' if stage == 'parse' else '{}'
    def normalize(value):
        if stage == 'normalize':
            raise ValueError('native contract invalid')
        return value
    result = evaluate_strategy(manifest=experiment(), inputs=[fixed_input()], strategy=descriptor(),
        transport=transport, parser=json.loads, normalizer=normalize, output_root=tmp_path)
    assert len(calls) == 1
    assert (result['planned'], result['failed'], result['skipped']) == (3, 1, 2)
    root = Path(result['output'])
    obs = json.loads((root / 'observations.json').read_text(encoding='utf-8'))
    assert obs[0]['first_error'] == stage + '_error'
    assert obs[0]['normalized'] is None
    assert (obs[0]['raw'] is None) == (stage == 'provider')
    assert 'private provider' not in (root / 'run.json').read_text(encoding='utf-8')


def test_native_adapter_offline_has_no_network_db_or_oracle_context(tmp_path, monkeypatch):
    import socket
    import cpea.infrastructure.database.factory as database
    def forbidden(*args, **kwargs):
        raise AssertionError('network or DB forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    for name in vars(database).copy():
        if 'executor' in name.lower():
            monkeypatch.setattr(database, name, forbidden)
    def transport(context):
        assert set(context) == {'request', 'catalog', 'upstream'}
        return '{}'
    assert execute(tmp_path, transport=transport)['completed'] == 3


def test_native_replay_is_strict_readonly_and_detects_source_and_artifact_drift(tmp_path):
    from evaluations.query_pipeline_runner import replay_strategy
    result = execute(tmp_path)
    root = Path(result['output'])
    before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    replay = replay_strategy(root, parser=json.loads, normalizer=lambda value: value, output_root=tmp_path)
    report = json.loads((Path(replay['output']) / 'replay-report.json').read_text(encoding='utf-8'))
    assert report['kind'] == 'raw_replay' and report['compatible'] and report['reproduced']
    assert report['natural_success'] == 0 and report['model_calls'] == 0
    assert before == {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    raw = next(root.glob('private/trials/*/raw.json'))
    raw.write_text('"tampered"', encoding='utf-8')
    with pytest.raises(ValueError, match='integrity'):
        replay_strategy(root, parser=json.loads, normalizer=lambda value: value, output_root=tmp_path)


def test_failed_parse_replays_as_same_failure(tmp_path):
    from evaluations.query_pipeline_runner import replay_strategy
    result = execute(tmp_path, transport=lambda context: 'malformed')
    replay = replay_strategy(result['output'], parser=json.loads, normalizer=lambda value: value, output_root=tmp_path)
    report = json.loads((Path(replay['output']) / 'replay-report.json').read_text(encoding='utf-8'))
    assert report['reproduced'] and report['trials'][0]['first_error'] == 'parse_error'


def test_unregistered_input_fails_before_transport(tmp_path):
    from evaluations.query_pipeline_runner import evaluate_strategy
    calls = []
    with pytest.raises(ValueError, match='matrix'):
        evaluate_strategy(manifest=experiment(), inputs=[fixed_input(case_sha256='b' * 64)],
            strategy=descriptor(), transport=lambda context: calls.append(context), parser=json.loads,
            normalizer=lambda value: value, output_root=tmp_path)
    assert not calls


def test_regrade_writes_new_assessments_and_keeps_recorded_raw_and_scores(tmp_path):
    from evaluations.query_pipeline_runner import regrade_strategy
    from tests.unit.test_query_pipeline_research_grading import rules
    result = execute(tmp_path, transport=lambda _: '{"scope":"2026-08","population":"inventory","mapping":["stock_qty"]}')
    root = Path(result['output'])
    before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    regrade = regrade_strategy(root, rules=rules(), output_root=tmp_path)
    report = json.loads((Path(regrade['output']) / 'replay-report.json').read_text(encoding='utf-8'))
    assert report['kind'] == 'response_regrade' and report['natural_success'] == 0
    scores = json.loads((Path(regrade['output']) / 'assessments.json').read_text(encoding='utf-8'))
    assert scores[0]['layers']['requirements'] == 'FAIL'
    assert before == {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_parser_source_drift_is_incompatible_replay(tmp_path):
    from evaluations.query_pipeline_runner import replay_strategy
    result = execute(tmp_path)
    replay = replay_strategy(result['output'], parser=lambda raw: {'new': True},
        normalizer=lambda value: value, output_root=tmp_path)
    assert not replay['compatible'] and replay['reason'] == 'source_drift'


def test_managed_index_is_readonly_and_does_not_claim_raw_replay(tmp_path):
    from evaluations.query_pipeline_runner import index_managed_evidence
    source = tmp_path / 'managed'
    source.mkdir()
    raw = source / 'raw.json'
    raw.write_text('{"first":"response"}', encoding='utf-8')
    from hashlib import sha256
    refs = {'raw.json': sha256(raw.read_bytes()).hexdigest()}
    before = raw.read_bytes()
    index = index_managed_evidence(source, references=refs)
    assert index['kind'] == 'managed_readonly_index' and index['replayed'] is False
    assert raw.read_bytes() == before
    with pytest.raises(ValueError, match='integrity'):
        index_managed_evidence(source, references={'../outside': 'wrong'})


def test_live_requires_frozen_input_approval_before_model_construction(tmp_path, monkeypatch):
    from evaluations.query_pipeline_runner import evaluate_strategy
    import evaluations.query_pipeline_runner as runner
    from tests.decomposition_support import settings
    def forbidden(**kwargs):
        raise AssertionError('no model before preregistration approval')
    monkeypatch.setattr(runner, 'get_llm_config', forbidden)
    with pytest.raises(ValueError, match='approval'):
        evaluate_strategy(manifest=experiment(), inputs=[fixed_input()], strategy=descriptor(),
            parser=json.loads, normalizer=lambda value: value, output_root=tmp_path,
            settings=settings(), live=True)


def test_instrumented_research_calls_are_distinct_from_stub_and_never_self_approve(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import evaluations.query_pipeline_runner as runner
    from tests.decomposition_support import settings
    calls = []
    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content='{"mapping":["stock_qty"]}', usage_metadata={'input_tokens': 7, 'output_tokens': 3})
    monkeypatch.setattr(runner, 'get_llm_config', lambda **kwargs: SimpleNamespace(invoke=invoke))
    fingerprint = runner.research_execution_hash(experiment(), [fixed_input()], descriptor(), settings())
    review = dict(decision='approved', author='proposer', reviewer='independent', reviewed_at='2026-10-22',
                  input_sha256=fingerprint, artifact_sha256=fingerprint, rules_sha256=fingerprint)
    result = runner.evaluate_strategy(manifest=experiment(), inputs=[fixed_input()], strategy=descriptor(),
        parser=json.loads, normalizer=lambda value: value, output_root=tmp_path,
        settings=settings(), live=True, preregistration_review=review)
    assert result['kind'] == 'research_live' and result['model_calls'] == 3
    assert result['input_tokens'] == 21 and result['output_tokens'] == 9
    assert result['natural_success'] == 0 and len(calls) == 3
    assert 'case_ref' not in calls[0][0].content


def test_provider_failure_without_raw_cannot_be_claimed_reproduced(tmp_path):
    from evaluations.query_pipeline_runner import replay_strategy
    def fail(context):
        raise RuntimeError('provider unavailable')
    result = execute(tmp_path, transport=fail)
    report = replay_strategy(result['output'], parser=json.loads, normalizer=lambda value: value, output_root=tmp_path)
    assert not report['reproduced'] and report['trials'][0]['reproduced'] is None


def test_mutated_snapshot_is_rejected_before_transport(tmp_path):
    from evaluations.query_pipeline_runner import evaluate_strategy
    value = fixed_input()
    value.catalog_snapshot['views'].append('unapproved')
    with pytest.raises(ValueError, match='snapshot drift'):
        evaluate_strategy(manifest=experiment(), inputs=[value], strategy=descriptor(),
            transport=lambda _: '{}', parser=json.loads, normalizer=lambda value: value, output_root=tmp_path)


@pytest.mark.parametrize('native,expected', [('needs_confirmation', 'pending'), ('unsupported', 'unsupported')])
def test_pending_and_unsupported_native_responses_keep_full_denominator(tmp_path, native, expected):
    result = execute(tmp_path, transport=lambda _: json.dumps({'status': native}))
    assert result[expected] == 3 and result['planned'] == 3 and result['natural_success'] == 0
    observations = json.loads((Path(result['output']) / 'observations.json').read_text(encoding='utf-8'))
    assert all(observation['status'] == expected and observation['normalized'] for observation in observations)
