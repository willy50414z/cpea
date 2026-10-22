import json
from pathlib import Path

import pytest

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from tests.support import write_profile
from tests.view_contract_v4_support import v4_policy, write_v4_profile


def test_v4_valid_contract_loads_and_preserves_policy(tmp_path):
    policy = v4_policy()
    catalog = SchemaCatalog(write_v4_profile(tmp_path, policy))
    assert catalog.views()[0].policy == policy
    assert catalog.views()[0].summary == '庫存狀態資料。'


@pytest.mark.parametrize('path,value', [
    (('unexpected',), True), (('summary',), '  '), (('summary',), '兩行\n描述'),
    (('grain', 'keys'), ['品号', '品号']), (('grain', 'keys'), ['missing']),
    (('grain', 'keys'), []), (('grain', 'unexpected'), True),
    (('source', 'verification'), 'approved'), (('source', 'definition_sha256'), 'invalid'),
    (('source', 'verification'), 'metadata_verified'),
    (('scope', 'population'), ''), (('scope', 'included'), 'string'),
    (('scope', 'unexpected'), True), (('time', 'kind'), 'latest'),
    (('time', 'dimensions'), {'missing': '日期'}),
    (('time', 'dimensions'), {'库存数量': '數量不是日期'}),
    (('time', 'rules'), [{'columns': ['missing'], 'description': '規則'}]),
    (('usage', 'unsupported'), [{'question': '問題'}]),
    (('columns', '库存数量', 'entity'), ''),
    (('columns', '库存数量', 'unexpected'), True),
    (('columns', '库存数量', 'disallowed_aggregations'), ['execute']),
    (('metrics', 'stock', 'columns'), ['missing']),
    (('metrics', 'stock', 'calculation'), ''),
])
def test_v4_rejects_invalid_shape_or_reference(tmp_path, path, value):
    policy = v4_policy()
    node = policy
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValueError) as error:
        SchemaCatalog(write_v4_profile(tmp_path, policy))
    assert 'inventory.yaml (gms2.v_inventory)' in str(error.value)


@pytest.mark.parametrize('field', ['grain', 'source', 'scope', 'time', 'usage', 'metrics'])
def test_v4_requires_semantic_sections(tmp_path, field):
    policy = v4_policy()
    policy.pop(field)
    with pytest.raises(ValueError):
        SchemaCatalog(write_v4_profile(tmp_path, policy))


@pytest.mark.parametrize('version', [0, 5, '4', True])
def test_unknown_version_is_rejected(tmp_path, version):
    policy = v4_policy()
    policy['version'] = version
    with pytest.raises(ValueError, match='version'):
        SchemaCatalog(write_v4_profile(tmp_path, policy))


def test_v4_unknown_and_verified_source_are_distinct(tmp_path):
    policy = v4_policy()
    policy['grain']['keys'] = None
    policy['source'] = {'verification': 'metadata_verified',
        'relations': ['gms2.inventory'], 'definition_sha256': 'a' * 64}
    assert SchemaCatalog(write_v4_profile(tmp_path, policy)).views()[0].policy['grain']['keys'] is None
    policy['source']['relations'] = []
    with pytest.raises(ValueError):
        SchemaCatalog(write_v4_profile(tmp_path, policy))


def test_legacy_and_v3_contract_remain_compatible(tmp_path):
    assert SchemaCatalog(write_profile(tmp_path / 'legacy')).views()
    policy = v4_policy()
    for name in ('source', 'scope', 'time', 'usage', 'metrics'):
        policy.pop(name)
    policy['version'] = 3
    policy['columns']['仓库名称'].pop('entity')
    assert SchemaCatalog(write_v4_profile(tmp_path / 'v3', policy)).views()[0].policy == policy


def test_standalone_json_schema_matches_model():
    path = Path(__file__).resolve().parents[2] / 'docs/view-schema-v4.schema.json'
    assert path.is_file()
    from cpea.infrastructure.catalog.view_contract_v4 import ViewContractV4
    assert json.loads(path.read_text(encoding='utf-8')) == ViewContractV4.model_json_schema()


@pytest.mark.parametrize('part', ['grain', 'time', 'metric', 'column'])
def test_v4_rejects_padded_column_names_and_references(tmp_path, part):
    policy = v4_policy()
    if part == 'grain':
        policy['grain']['keys'][0] = ' 品号 '
    elif part == 'time':
        policy['time']['dimensions'] = {' snapshot_date ': '日期'}
    elif part == 'metric':
        policy['metrics']['stock']['columns'] = [' 库存数量 ']
    else:
        policy['columns']['库存数量 '] = policy['columns']['库存数量'].copy()
    with pytest.raises(ValueError):
        SchemaCatalog(write_v4_profile(tmp_path, policy))


@pytest.mark.parametrize('field', ['unit', 'entity'])
def test_optional_column_text_schema_matches_null_rejection(tmp_path, field):
    from cpea.infrastructure.catalog.view_contract_v4 import ViewContractV4
    policy = v4_policy()
    policy['columns']['品号'][field] = None
    with pytest.raises(ValueError):
        SchemaCatalog(write_v4_profile(tmp_path, policy))
    spec = ViewContractV4.model_json_schema()['$defs']['Column']['properties'][field]
    assert spec.get('type') == 'string'
