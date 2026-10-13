from dataclasses import replace
import json
from pathlib import Path
import pytest
from cpea.application.errors import DependencyUnavailable
from evaluations.metadata import run_metadata, write_jsonl
from evaluations.runners.model_comparison import EvaluationCase, compare_models
from evaluations.runners.query_reliability import QueryReliabilityCase, evaluate_cases, main
from tests.integration.test_runtime import runtime_fixture
from tests.support import StubLLM, VIEW, QUESTION

def test_comparison_requires_execution_before_model_factory(tmp_path):
    runtime = runtime_fixture(tmp_path)
    called = []
    with pytest.raises(DependencyUnavailable):
        compare_models([EvaluationCase(question=QUESTION)], ['a', 'b'], runtime=runtime,
            llm_factory=lambda model: called.append(model))
    assert not called and runtime.llm.calls == 0

def test_comparison_preserves_prompt_replay_and_parsing(tmp_path):
    runtime = runtime_fixture(tmp_path, executor=lambda datasource, sql: (['仓库名称', '库存数量'], [['A', 10]]), datasource_id='test')
    models = []
    def factory(model):
        models.append(model)
        return StubLLM()
    records = compare_models([EvaluationCase(question=QUESTION)], ['a', 'b'], runtime=runtime,
        llm_factory=factory, warmup=False, kind='offline-synthetic')
    assert len(records) == 2 and all(record.error is None for record in records)
    assert records[0].final_prompt == records[1].final_prompt
    assert records[0].citations == records[1].citations == ['[Source 1]']
    assert records[0].run_metadata['kind'] == 'offline-synthetic'
    assert records[0].run_metadata['run_id'] == records[1].run_metadata['run_id']

def test_metadata_omits_secrets_and_versions_dataset(tmp_path):
    runtime = runtime_fixture(tmp_path)
    runtime.settings = replace(runtime.settings, llm_api_key='super-secret', embedding_api_key='another-secret', llm_base_url='https://user:pass@example.com?token=secret')
    cases = [QueryReliabilityCase(question=QUESTION, expected_supported=True)]
    metadata = run_metadata(runtime, cases, kind='offline-synthetic')
    serialized = json.dumps(metadata)
    assert all(value not in serialized for value in ['super-secret', 'another-secret', 'user:pass', '?token=secret'])
    assert metadata['profile_id'] == 'synthetic' and metadata['contract_version'] == '1'
    assert metadata['dataset_fingerprint'] != run_metadata(runtime, [], kind='offline-synthetic')['dataset_fingerprint']
    assert len(metadata['source_fingerprint']) == 64

def test_reliability_runner_offline_and_output_not_overwritten(tmp_path):
    runtime = runtime_fixture(tmp_path / 'profile')
    cases = [QueryReliabilityCase(question=QUESTION, expected_supported=True, expected_view=VIEW,
        expected_filters={'品号': 'ZX100'}, expected_group_by=['仓库名称'], expected_aggregations={'库存数量': 'sum'})]
    records = evaluate_cases(cases, runtime.generation_service(), runs=2)
    assert len(records) == 2 and all(record['passed'] for record in records)
    dataset = tmp_path / 'cases.jsonl'
    dataset.write_text(cases[0].model_dump_json() + '\n', encoding='utf-8')
    output = tmp_path / 'results.jsonl'
    assert main(['--dataset', str(dataset), '--output', str(output), '--runs', '1'], runtime=runtime, kind='offline-synthetic') == 0
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['run_metadata']['kind'] == 'offline-synthetic'
    with pytest.raises(FileExistsError):
        write_jsonl(output, records)
