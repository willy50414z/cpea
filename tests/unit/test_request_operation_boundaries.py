"""Business names cannot authorize a different query operation or row grain."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from tests.hilp_support import VIEW, runtime_for


def mapped_runtime(tmp_path, draft, *, repair=None):
    runtime = runtime_for(tmp_path)
    runtime.catalog.views()[0].policy['filter_operators']['number'].append('>=')
    columns = runtime.catalog.views()[0].policy['columns']
    columns['order_amount'].update(description='已完成訂單筆數', aliases=['已完成訂單筆數'],
                                    aggregations=['sum', 'avg', 'count', 'max'])
    columns['net_amount'].update(description='區域', aliases=['區域'])
    contexts = []

    def invoke(messages):
        context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
        contexts.append(context)
        result = repair if repair is not None and context.get('repair') else draft
        return SimpleNamespace(content=json.dumps(result, ensure_ascii=False))

    runtime.llm.invoke = invoke
    return runtime, contexts


def grouped_mapping(name='已完成訂單筆數'):
    return {'table': {'view': VIEW}, 'having': [], 'fields': [
        {'text': '區域', 'column': 'net_amount'},
        {'text': name + '合計', 'column': 'order_amount', 'aggregation': 'sum'}],
        'group': [{'text': '區域', 'column': 'net_amount'}],
        'criteria': [{'text': name + ' >= 5', 'column': 'order_amount', 'operator': '>=', 'value': 5}]}


@pytest.mark.parametrize('name', ['已完成訂單筆數', '歷來平均值', '核准總和'])
def test_statistical_business_name_remains_a_row_filter(tmp_path, name):
    runtime, contexts = mapped_runtime(tmp_path, grouped_mapping(name))
    runtime.catalog.views()[0].policy['columns']['order_amount'].update(description=name, aliases=[name])
    try:
        result = runtime.generate(f'依區域分組，顯示{name}合計，限定{name} >= 5。')
        assert result.status == 'ready'
        assert result.query_plan.filters[0].column == 'order_amount'
        assert not result.query_plan.having
        assert len(contexts) == 1
    finally:
        runtime.close()


@pytest.mark.parametrize('name', ['已完成訂單筆數', '歷來平均值', '核准總和'])
def test_statistical_name_does_not_authorize_having(tmp_path, name):
    correct = grouped_mapping(name)
    wrong = deepcopy(correct)
    wrong['having'] = [{**wrong['criteria'].pop(), 'aggregation': 'sum'}]
    runtime, contexts = mapped_runtime(tmp_path, wrong, repair=correct)
    runtime.catalog.views()[0].policy['columns']['order_amount'].update(description=name, aliases=[name])
    try:
        result = runtime.generate(f'依區域分組，顯示{name}合計，限定{name} >= 5。')
        assert result.status == 'ready' and not result.query_plan.having
        assert len(contexts) == 2
        assert 'HAVING requires an explicit aggregate threshold' in str(contexts[1]['repair'])
    finally:
        runtime.close()


@pytest.mark.parametrize('prefix', ['列出', '幫我看每列的', '我想看逐筆的'])
@pytest.mark.parametrize('name', ['已完成訂單筆數', '核准總和', '部門合計'])
def test_row_listing_cannot_invent_aggregation_or_grouping(tmp_path, prefix, name):
    wrong = grouped_mapping(name)
    wrong['fields'][1]['text'] = name
    wrong['criteria'] = []
    runtime, _ = mapped_runtime(tmp_path, wrong)
    runtime.catalog.views()[0].policy['columns']['order_amount'].update(description=name, aliases=[name])
    try:
        result = runtime.generate(prefix + '區域、' + name + '。')
        assert not result.supported and result.sql is None
        assert 'unrequested' in str(result.limitations)
    finally:
        runtime.close()


def test_real_aggregate_threshold_still_cannot_be_where(tmp_path):
    wrong = grouped_mapping()
    wrong['criteria'][0]['text'] = '已完成訂單筆數合計 >= 5'
    runtime, _ = mapped_runtime(tmp_path, wrong)
    try:
        result = runtime.generate('依區域分組，顯示已完成訂單筆數合計，只保留已完成訂單筆數合計 >= 5。')
        assert not result.supported and result.sql is None
        assert 'aggregate threshold cannot be a WHERE criterion' in str(result.limitations)
    finally:
        runtime.close()


def test_numeric_business_qualifier_requires_the_complete_mapped_phrase(tmp_path):
    wrong = {'table': {'view': VIEW}, 'having': [], 'fields': [
        {'text': '單列最大值', 'column': 'order_amount', 'aggregation': 'max'}]}
    correct = deepcopy(wrong)
    correct['fields'][0]['text'] = '未來45日可售天數的單列最大值'
    runtime, contexts = mapped_runtime(tmp_path, wrong, repair=correct)
    runtime.catalog.views()[0].policy['columns']['order_amount'].update(
        description='未來45日可售天數', aliases=[])
    try:
        result = runtime.generate('顯示未來45日可售天數的單列最大值。')
        assert result.status == 'ready' and len(contexts) == 2
        errors = str(contexts[1]['repair']['validation_errors'])
        assert 'unmapped request literals: 45' in errors
        assert 'complete business phrase' in errors
    finally:
        runtime.close()



def test_row_listing_unknown_column_is_a_rejection_not_an_exception(tmp_path):
    wrong = grouped_mapping()
    wrong['fields'][1]['column'] = 'missing_metric'
    wrong['criteria'] = []
    runtime, _ = mapped_runtime(tmp_path, wrong)
    try:
        result = runtime.generate('列出區域、已完成訂單筆數。')
        assert not result.supported and result.sql is None
        assert 'column is not' in str(result.limitations)
    finally:
        runtime.close()


@pytest.mark.parametrize('operator,value', [
    ('LIKE', '平均%'), ('LIKE', '合計%'), ('LIKE', '總和%'),
    ('IN', ['平均', '合計', '總和']),
])
def test_filter_literal_cannot_become_an_aggregate_operation(tmp_path, operator, value):
    literal = '、'.join(value) if isinstance(value, list) else value
    question = f'列出區域，限定區域 {operator} {literal}。'
    draft = {'table': {'view': VIEW}, 'having': [],
             'fields': [{'text': '區域', 'column': 'net_amount'}],
             'criteria': [{'text': f'區域 {operator} {literal}', 'column': 'net_amount',
                           'operator': operator, 'value': value}]}
    if isinstance(value, list):
        start = question.index('區域 IN')
        draft['terms'] = [{'clause': 'criteria', 'index': 0, 'term': '區域',
                           'start': start, 'end': start + 2, 'candidates': ['net_amount']}]
    runtime, contexts = mapped_runtime(tmp_path, draft)
    runtime.catalog.views()[0].policy['columns']['net_amount']['type'] = '字串'
    try:
        result = runtime.generate(question)
        assert result.status == 'ready' and len(contexts) == 1
        assert result.query_plan.filters[0].value == value
        assert not result.query_plan.having
    finally:
        runtime.close()


@pytest.mark.parametrize('name', ['各類狀態', '分組標籤', '彙總分類', '匯總狀態'])
@pytest.mark.parametrize('explicit_group', [False, True])
def test_group_words_inside_business_names_do_not_authorize_grouping(tmp_path, name, explicit_group):
    draft = {'table': {'view': VIEW}, 'having': [],
             'fields': [{'text': name, 'column': 'net_amount'}],
             'group': [{'text': name, 'column': 'net_amount'}]}
    runtime, _ = mapped_runtime(tmp_path, draft)
    runtime.catalog.views()[0].policy['columns']['net_amount'].update(description=name, aliases=[name])
    try:
        question = f'列出{name}。' + (f'依{name}分組。' if explicit_group else '')
        result = runtime.generate(question)
        assert result.supported == explicit_group
        assert (result.sql is not None) == explicit_group
    finally:
        runtime.close()


@pytest.mark.parametrize('text,expected', [
    ('平均每筆已完成訂單消費額 >= 100', False),
    ('會員平均已完成訂單消費額 >= 100', False),
    ('平均每筆已完成訂單消費額的平均值 >= 100', True),
    ('平均每筆已完成訂單消費額的單列最大值 >= 100', True),
    ('AVG(order_amount) >= 100', True),
])
def test_precomputed_average_paraphrase_is_not_a_new_avg_operation(tmp_path, text, expected):
    from cpea.workflows.text_to_sql.schemas import ClauseCriterion
    from cpea.workflows.text_to_sql.semantics import aggregate_threshold
    runtime, _ = mapped_runtime(tmp_path, {})
    runtime.catalog.views()[0].policy['columns']['order_amount'].update(
        description='會員平均已完成訂單消費額', aliases=[], aggregations=['min', 'max'])
    try:
        item = ClauseCriterion(text=text, column='order_amount', operator='>=', value=100)
        assert aggregate_threshold(item, runtime.catalog, VIEW) == expected
    finally:
        runtime.close()
