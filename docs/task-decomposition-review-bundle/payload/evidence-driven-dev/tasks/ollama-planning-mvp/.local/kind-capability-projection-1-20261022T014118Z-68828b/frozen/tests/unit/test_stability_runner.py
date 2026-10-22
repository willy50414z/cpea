import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from evaluations.stability_runner import RecordedModel, check_mapping
from evaluations.runners.query_reliability import QueryReliabilityCase
from cpea.workflows.text_to_sql.schemas import SQLClauseMapping
from tests.support import dependencies, QUESTION, VIEW


class Model:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def invoke(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return AIMessage(content='{}')


def test_cloud_limit_switches_before_the_501st_call(tmp_path):
    ledger = tmp_path / 'ledger.jsonl'
    ledger.write_text((json.dumps({'provider': 'azure'}) + '\n') * 500, encoding='utf-8')
    cloud, local = Model(), Model()
    recorded = RecordedModel(cloud, 'azure', 'cloud', tmp_path / 'calls.jsonl', ledger)
    recorded.fallback = lambda: (local, 'local-model')
    recorded.invoke([HumanMessage(content='probe')])
    assert cloud.calls == 0 and local.calls == 1
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    assert sum(r['provider'] == 'azure' for r in rows) == 500
    assert rows[-1]['provider'] == 'ollama'


def test_provider_error_is_recorded_and_not_retried(tmp_path):
    model = Model(RuntimeError('rate limit'))
    recorded = RecordedModel(model, 'gcp', 'cloud', tmp_path / 'calls.jsonl', tmp_path / 'ledger.jsonl')
    with pytest.raises(RuntimeError, match='rate limit'):
        recorded.invoke([HumanMessage(content='probe')])
    with pytest.raises(RuntimeError, match='provider paused'):
        recorded.invoke([HumanMessage(content='probe')])
    assert model.calls == 1
    rows = [json.loads(line) for line in recorded.output.read_text(encoding='utf-8').splitlines()]
    assert [r['event'] for r in rows] == ['request', 'error']


def test_cloud_cap_without_fallback_does_not_reserve_or_call(tmp_path):
    ledger = tmp_path / 'ledger.jsonl'
    ledger.write_text((json.dumps({'provider': 'azure'}) + '\n') * 500, encoding='utf-8')
    cloud = Model()
    recorded = RecordedModel(cloud, 'azure', 'cloud', tmp_path / 'calls.jsonl', ledger)
    with pytest.raises(RuntimeError, match='cloud_call_cap_reached'):
        recorded.invoke([HumanMessage(content='probe')])
    assert cloud.calls == 0
    assert len(ledger.read_text(encoding='utf-8').splitlines()) == 500


def test_explicit_cloud_cap_uses_existing_ledger_and_stops_at_limit(tmp_path):
    ledger = tmp_path / 'ledger.jsonl'
    ledger.write_text((json.dumps({'provider': 'azure'}) + '\n') * 500, encoding='utf-8')
    cloud = Model()
    recorded = RecordedModel(cloud, 'azure', 'cloud', tmp_path / 'calls.jsonl', ledger,
                             cloud_call_limit=501)
    recorded.invoke([HumanMessage(content='probe')])
    with pytest.raises(RuntimeError, match='cloud_call_cap_reached'):
        recorded.invoke([HumanMessage(content='probe')])
    assert cloud.calls == 1
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    assert len(rows) == 501
    assert all(row['provider'] == 'azure' for row in rows)


def test_valid_json_with_empty_fields_fails_mvp_semantics(tmp_path):
    _, catalog, *_ = dependencies(tmp_path)
    mapping = SQLClauseMapping.model_validate({'table': {'view': VIEW}, 'fields': []})
    case = QueryReliabilityCase(question=QUESTION, expected_supported=True,
                               expected_filters={'品号': 'ZX100'},
                               expected_select_columns=['库存数量'],
                               expected_aggregations={'库存数量': 'sum'})
    failures = check_mapping(mapping, QUESTION, VIEW, catalog, case)
    assert {'empty_fields', 'select_mismatch:库存数量', 'filter_mismatch:品号',
            'aggregation_mismatch:库存数量'} <= set(failures)


def test_prompt_remains_under_user_character_limit():
    from cpea.workflows.text_to_sql.sql_generation import MATCH_PROMPT
    assert len(MATCH_PROMPT) <= 2000
