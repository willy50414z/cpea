from dataclasses import replace
import json

import pytest

from evaluations.metadata import run_metadata, write_jsonl
from evaluations.runners.query_reliability import QueryReliabilityCase, evaluate_cases, main
from tests.integration.test_runtime import runtime_fixture
from tests.support import VIEW, QUESTION


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


def test_reliability_runner_checks_empty_group_and_order(tmp_path):
    runtime = runtime_fixture(tmp_path / 'profile')
    cases = [
        QueryReliabilityCase(question=QUESTION, expected_supported=True,
            expected_filters={'品号': 'ZX100'}, expected_group_by=['仓库名称'], expected_order_by=[]),
        QueryReliabilityCase(question=QUESTION, expected_supported=True,
            expected_filters={'品号': 'ZX100'}, expected_group_by=[], expected_order_by=['仓库名称']),
    ]
    passed, failed = evaluate_cases(cases, runtime.generation_service(), runs=1)
    assert passed['passed'], passed['failure_reasons']
    assert not failed['passed']
    assert {'group_by_mismatch', 'order_by_mismatch'} <= set(failed['failure_reasons'])
