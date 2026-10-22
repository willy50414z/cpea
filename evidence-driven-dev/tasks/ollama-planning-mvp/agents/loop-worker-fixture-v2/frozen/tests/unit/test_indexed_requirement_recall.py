"""Request evidence comes from Python slices, not generated quotation text."""
import pytest

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations import indexed_requirement_recall as indexed


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def wire(catalog, start, end):
    return {'requirements': [{'requirement_id': 'r1', 'start': start, 'end': end,
             'business_object': '庫存', 'kind': 'attribute', 'scope_ids': [],
             'grain': '門市×商品', 'population': '庫存商品'}],
            'candidate_views': [{'view': v.name, 'reason': '全來源控制'} for v in catalog.views()]}


@pytest.mark.parametrize('request_text,start,end,expected', [
    ('顯示盤點日期。', 2, 6, '盤點日期'),
    ('A🧾庫存 B', 1, 4, '🧾庫存'),
    ('庫存 2026 年。', 3, 9, '2026 年'),
    ('庫存、銷售；庫存。', 6, 8, '庫存'),
    ('庫存\r\n日期', 4, 6, '日期'),
])
def test_python_slices_exact_original_codepoints(catalog, request_text, start, end, expected):
    result = indexed.materialize_recall(indexed.IndexedRecallResult.model_validate(wire(catalog, start, end)), request_text, catalog)
    assert result.requirements[0].quote == expected
    assert 'quote' not in indexed.IndexedRecallResult.model_json_schema()['$defs']['IndexedRequirement']['properties']


@pytest.mark.parametrize('start,end', [(-1, 2), (0, 20), (2, 2), (3, 1), (True, 2), (0, False), (0.0, 2), ('0', 2)])
def test_invalid_indices_cannot_be_silently_coerced_or_clamped(catalog, start, end):
    with pytest.raises(ValueError):
        parsed = indexed.IndexedRecallResult.model_validate(wire(catalog, start, end))
        indexed.materialize_recall(parsed, '庫存日期', catalog)


def test_whitespace_only_span_is_rejected(catalog):
    with pytest.raises(ValueError, match='blank'):
        indexed.materialize_recall(indexed.IndexedRecallResult.model_validate(wire(catalog, 2, 4)), '庫存  日期', catalog)


def test_model_cannot_supply_or_override_derived_quote(catalog):
    data = wire(catalog, 0, 2)
    data['requirements'][0]['quote'] = '庫存...最新'
    with pytest.raises(ValueError):
        indexed.IndexedRecallResult.model_validate(data)


def test_index_table_includes_punctuation_spaces_and_emoji():
    assert indexed.request_index('庫 🧾。') == [
        {'index': 0, 'character': '庫'}, {'index': 1, 'character': ' '},
        {'index': 2, 'character': '🧾'}, {'index': 3, 'character': '。'}]


def test_existing_scope_validation_is_preserved(catalog):
    data = wire(catalog, 0, 2)
    data['requirements'][0]['scope_ids'] = ['missing']
    with pytest.raises(ValueError, match='scope'):
        indexed.materialize_recall(indexed.IndexedRecallResult.model_validate(data), '庫存日期', catalog)


def test_valid_offset_is_not_semantic_proof(catalog):
    # The label says inventory while the selected text says sales: a valid
    # slice alone cannot certify business meaning. Keep that boundary explicit.
    result = indexed.materialize_recall(indexed.IndexedRecallResult.model_validate(wire(catalog, 3, 5)), '庫存與銷售', catalog)
    assert result.requirements[0].quote == '銷售'


def test_indexed_messages_provide_exact_character_table(catalog):
    import json
    from evaluations.three_stage_view_selection_runner import messages_for
    messages = messages_for('recall', indexed.IndexedRecallResult, '庫 🧾。', views=[v.policy for v in catalog.views()])
    context = json.loads(messages[1].content)
    assert context['request_length'] == 4
    assert context['request_characters'][2] == {'index': 2, 'character': '🧾'}
    assert 'quote' not in context['response_schema']['$defs']['IndexedRequirement']['properties']


def test_recall_only_preserves_wire_and_derives_quote_without_another_call(catalog):
    import json
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    saved = {}
    raw_data = wire(catalog, 0, 4)
    def invoke(messages, schema):
        assert schema is indexed.IndexedRecallResult
        return AIMessage(content=json.dumps(raw_data, ensure_ascii=False))
    budget = Budget(calls_limit=1)
    result = run_pipeline('庫存日期', catalog, invoke, saved.__setitem__, budget, recall_only=True)
    assert budget.calls == 1
    assert result.requirements[0].quote == '庫存日期'
    assert json.loads(saved['recall-call.json']['response']) == raw_data
    assert saved['recall-parsed.json']['requirements'][0]['end'] == 4
    assert saved['recall-result.json']['requirements'][0]['quote'] == '庫存日期'
    assert not any(name.startswith('map-') for name in saved)


def test_invalid_span_stops_before_mapping_and_keeps_raw(catalog):
    import json
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    saved = {}
    budget = Budget()
    with pytest.raises(ValueError, match='span'):
        run_pipeline('庫存日期', catalog, lambda *args: AIMessage(content=json.dumps(wire(catalog, 0, 999))),
                     saved.__setitem__, budget)
    assert budget.calls == 1 and 'recall-call.json' in saved
    assert not any(name.startswith('map-') for name in saved)
