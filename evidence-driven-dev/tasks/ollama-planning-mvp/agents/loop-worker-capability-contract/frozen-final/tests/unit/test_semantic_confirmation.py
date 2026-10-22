import pytest
from cpea.workflows.text_to_sql.semantics import assess, description_supports
from cpea.workflows.text_to_sql.schemas import SQLClauseMappingV10
from tests.hilp_support import QUESTION, VIEW, runtime_for


def draft(text='總額', **kwargs):
    return SQLClauseMappingV10.model_validate({'fields': [{'text': text, 'column': 'order_amount'}],
        'table': {'view': VIEW}, 'having': [], **kwargs})


@pytest.mark.parametrize('term, description, quote, expected', [
    ('訂單成立日期', '訂單成立日期（曆日），不含時間。', None, True),
    ('會員居住城市', '訂單門市所在城市，不是會員居住城市。', None, False),
    ('含稅發票總額', '不是含稅發票總額。', '含稅發票總額', False),
    ('含稅發票總額', '訂單金額，不含稅。', None, False),
])
def test_description_negation_is_scoped_to_the_complete_term(term, description, quote, expected):
    assert description_supports(term, description, quote) is expected


def test_ignored_and_shrunken_term_cannot_remove_qualifiers(tmp_path):
    runtime = runtime_for(tmp_path)
    mapping = draft(ignored=[{'text': '含稅發票', 'reason': 'irrelevant'}])
    uses, reused, errors = assess(QUESTION, mapping, runtime.catalog, VIEW,
                                runtime.generation_service().workflow.repository.read())
    assert not errors and not reused
    assert uses[0]['term'] == '含稅發票總額'
    runtime.close()


def test_invalid_unicode_evidence_and_typed_syntax_spans(tmp_path):
    runtime = runtime_for(tmp_path)
    snapshot = runtime.generation_service().workflow.repository.read()
    mapping = draft(terms=[{'clause': 'fields', 'index': 0, 'start': 1, 'end': 3,
                            'term': '含稅發票總額', 'candidates': [], 'evidence_quote': None}])
    assert 'term span does not match original request' in assess(QUESTION, mapping, runtime.catalog, VIEW, snapshot)[2]
    mapping = draft(syntax_spans=[{'kind': 'aggregation', 'clause': 'fields', 'index': 0,
                                 'start': 0, 'end': 1}])
    assert 'syntax span does not match typed mapping' in assess(QUESTION, mapping, runtime.catalog, VIEW, snapshot)[2]
    runtime.close()


@pytest.mark.parametrize('business_term, mapped_term', [('和平金額', '平金額'), ('夢想金額', '金額')])
def test_business_word_containing_grammar_is_not_stripped(tmp_path, business_term, mapped_term):
    runtime = runtime_for(tmp_path)
    contract = runtime.catalog.views()[0].policy['columns']['order_amount']
    contract['description'] = mapped_term
    contract['aliases'] = [mapped_term]
    request = f'請從 {VIEW} 查詢{business_term}。'
    uses, _, errors = assess(request, draft(mapped_term), runtime.catalog, VIEW,
                            runtime.generation_service().workflow.repository.read())
    assert not errors and uses[0]['term'] == business_term
    runtime.close()


@pytest.mark.parametrize('aggregation, phrase', [
    ('max', '最大值'), ('max', '單列最大值'),
    ('min', '最小值'), ('min', '單列最小值'),
])
def test_aggregate_value_suffix_is_typed_query_syntax(tmp_path, aggregation, phrase):
    runtime = runtime_for(tmp_path)
    mapping = draft('訂單金額', fields=[
        {'text': '訂單金額', 'column': 'order_amount', 'aggregation': aggregation}
    ])
    uses, _, errors = assess(f'顯示訂單金額的{phrase}。', mapping, runtime.catalog, VIEW,
                            runtime.generation_service().workflow.repository.read())
    assert not errors
    assert not uses
    runtime.close()


def test_query_syntax_is_not_saved_as_part_of_business_terms(tmp_path):
    runtime = runtime_for(tmp_path)
    request = '整理報表時照預估總額分組，顯示預估淨額的單列最大值，限定預估總額 >= 10且預估淨額 >= 2，依預估總額排序。'
    mapping = draft('預估淨額', fields=[
        {'text': '預估總額', 'column': 'order_amount'},
        {'text': '預估淨額的單列最大值', 'column': 'net_amount', 'aggregation': 'max'},
    ], group=[{'text': '預估總額', 'column': 'order_amount'}],
       order=[{'text': '依預估總額排序', 'column': 'order_amount'}],
       criteria=[{'text': '預估總額 >= 10', 'column': 'order_amount', 'operator': '>=', 'value': 10},
                 {'text': '預估淨額 >= 2', 'column': 'net_amount', 'operator': '>=', 'value': 2}])
    uses, _, errors = assess(request, mapping, runtime.catalog, VIEW,
                            runtime.generation_service().workflow.repository.read())
    assert not errors
    assert {use['term'] for use in uses} == {'預估總額', '預估淨額'}
    runtime.close()


@pytest.mark.parametrize('clause', ['fields', 'criteria', 'group', 'order', 'having'])
def test_every_column_use_requires_semantic_evidence(tmp_path, clause):
    runtime = runtime_for(tmp_path)
    item = {'text': '總額', 'column': 'order_amount'}
    if clause in ('criteria', 'having'):
        item.update(operator='>', value=100)
    if clause == 'having':
        item['aggregation'] = 'sum'
    data = {'fields': [], 'having': [], clause: [item]}
    mapping = SQLClauseMappingV10.model_validate(data)
    request = '含稅發票總額' + ('大於100' if clause == 'criteria' else '合計大於100' if clause == 'having' else '')
    uses, _, errors = assess(request, mapping, runtime.catalog, VIEW,
                            runtime.generation_service().workflow.repository.read())
    assert not errors and uses[0]['term'] == '含稅發票總額'
    runtime.close()


def test_legacy_schema_fingerprints_and_separate_v10_schema():
    from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
    from cpea.workflows.text_to_sql.schemas import SQLClauseMappingV3
    assert load_match_prompt().version == 'v10'
    for version in ('v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9'):
        assert load_match_prompt(version).response_model is SQLClauseMappingV3
    assert load_match_prompt('v10').response_model is SQLClauseMappingV10
    assert load_match_prompt('v6').response_schema_sha256 != load_match_prompt('v10').response_schema_sha256


def test_explicit_column_cannot_be_replaced_with_another_metric(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        _, _, errors = assess('請查詢order_amount合計。',
            draft('order_amount', fields=[{'text': 'order_amount', 'column': 'net_amount', 'aggregation': 'sum'}]),
            runtime.catalog, VIEW, runtime.generation_service().workflow.repository.read())
        assert any('order_amount' in error for error in errors)
    finally:
        runtime.close()


@pytest.mark.parametrize('mode', ['lexical', 'vector'])
def test_explicit_columns_are_admitted_before_retrieval_cutoff(tmp_path, mode):
    from dataclasses import replace
    from copy import deepcopy
    from cpea.infrastructure.retrieval.schema import SchemaRetriever
    runtime = runtime_for(tmp_path)
    try:
        original = runtime.catalog.views()[0]
        policy = deepcopy(original.policy)
        policy['view'] = 'demo_retail.v_other'
        policy['columns'] = {'net_amount': policy['columns']['net_amount']}
        other = replace(original, name=policy['view'], summary='請查詢金額合計', policy=policy)
        runtime.catalog._definitions.insert(0, other)
        retriever = SchemaRetriever(replace(runtime.settings, retrieval_mode=mode, retrieval_k=1, rerank_top_k=1),
                                    catalog=runtime.catalog)
        if mode == 'vector':
            from types import SimpleNamespace
            retriever.vector_store = SimpleNamespace(similarity_search_with_score=lambda query, k, filter:
                [(doc, 1.0) for doc in retriever.documents if filter(doc)][:k])
        result = retriever.retrieve('請查詢order_amount合計。')
        assert [item.document.metadata['document_id'] for item in result.candidates] == [VIEW]
    finally:
        runtime.close()


@pytest.mark.parametrize('question', [
    "查詢門市名稱 = 'order_amount'", '查詢門市名稱 LIKE order_amount',
    "查詢門市名稱 IN ('order_amount', 'net_amount')", '查詢fake_order_amount',
])
def test_filter_values_and_partial_names_are_not_explicit_column_references(tmp_path, question):
    from cpea.infrastructure.retrieval.schema import explicit_column_references
    runtime = runtime_for(tmp_path)
    try:
        assert not explicit_column_references(question, runtime.catalog)
    finally:
        runtime.close()


def test_polite_group_query_and_having_suffix_are_not_business_qualifiers(tmp_path):
    runtime = runtime_for(tmp_path)
    mapping = draft('預估淨額', fields=[{'text': '預估總額', 'column': 'order_amount'},
        {'text': '預估淨額', 'column': 'net_amount', 'aggregation': 'sum'}],
        group=[{'text': '預估總額', 'column': 'order_amount'}],
        having=[{'text': '預估淨額合計 > 100', 'column': 'net_amount', 'aggregation': 'sum', 'operator': '>', 'value': 100}])
    try:
        uses, _, errors = assess('想按預估總額分組，顯示預估淨額合計，只保留預估淨額合計 > 100的群組。',
            mapping, runtime.catalog, VIEW, runtime.generation_service().workflow.repository.read())
        assert not errors
        assert {use['term'] for use in uses} == {'預估總額', '預估淨額'}
    finally:
        runtime.close()
