"""MDL drafts preserve every source field and disclose unsupported semantics."""
import pytest


def convert(snapshot):
    from evaluations.query_pipeline_wren_poc import convert_catalog
    return convert_catalog(snapshot)


def test_conversion_does_not_invent_keys_joins_or_business_rules():
    policy = {'view': 'demo.inventory', 'summary': '庫存', 'version': 3,
        'grain': {'keys': ['store_id', 'product_id'], 'description': '門市商品'},
        'columns': {'product_id': {'type': 'number', 'role': 'identifier'},
                    'stock_qty': {'type': 'number', 'role': 'measure', 'unit': '件', 'disallowed_aggregations': ['avg']}}}
    result = convert({'demo.inventory': policy})
    model = result['mdl']['models'][0]
    assert 'primaryKey' not in model and not result['mdl']['relationships']
    assert model['tableReference'] == {'schema': 'demo', 'table': 'inventory'}
    assert result['mapping'][0]['original_contract'] == policy
    assert result['mapping'][0]['numeric_type_assumptions'] == ['product_id', 'stock_qty']
    assert result['business_semantics_approved'] is False
    assert result['mapping'][0]['uncompiled_fields'] == ['grain', 'summary', 'column_policies']


def test_same_short_view_names_remain_distinct_and_unknown_types_stop():
    snapshot = {name: {'view': name, 'columns': {'day': {'type': 'date'}}} for name in ['a.sales', 'b.sales']}
    result = convert(snapshot)
    assert len({m['name'] for m in result['mdl']['models']}) == 2
    snapshot['a.sales']['columns']['day']['type'] = 'opaque'
    with pytest.raises(ValueError, match='type'):
        convert(snapshot)


def test_mismatched_view_and_alias_collisions_stop():
    with pytest.raises(ValueError, match='view'):
        convert({'a.sales': {'view': 'b.sales', 'columns': {}}})
    with pytest.raises(ValueError, match='alias'):
        convert({name: {'view': name, 'columns': {'x': {'type': 'string'}}}
                 for name in ['a.b__c', 'a__b.c']})
