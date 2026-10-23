from copy import deepcopy
from hashlib import sha256
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from scripts import generate_view_contracts as generator
from tests.view_contract_v4_support import v4_policy


@pytest.fixture
def evidence():
    definition = 'SELECT * FROM demo_retail.inventory i LEFT JOIN last_30d ON true'
    policy = v4_policy()
    policy['view'] = 'demo_retail.v_inventory_status'
    policy['grain'] = {'description': '每個門市商品組合一列', 'keys': ['store_id', 'product_id']}
    policy['columns'] = {
        'store_id': {'type': 'number', 'role': 'identifier', 'description': '門市'},
        'product_id': {'type': 'number', 'role': 'identifier', 'description': '商品'},
        '库存数量': policy['columns']['库存数量'],
        'snapshot_date': policy['columns']['snapshot_date'],
    }
    relations = ['demo_retail.inventory', 'demo_retail.products', 'demo_retail.stores',
                 'demo_retail.v_sales_detail']
    policy['source'] = {'verification': 'metadata_verified', 'relations': relations,
                        'definition_sha256': sha256(definition.encode('utf-8')).hexdigest()}
    return dict(name='v_inventory_status', definition=definition,
        columns=[('store_id', 'integer', '粒度／情境等混雜註解'),
                 ('product_id', 'integer', None), ('库存数量', 'numeric(14,2)', None),
                 ('snapshot_date', 'date', None)],
        constraints={'inventory': [('p', ('store_id', 'product_id'))],
                     'stores': [('p', ('store_id',))], 'products': [('p', ('product_id',))]},
        semantics=policy, relations=relations)


def test_generation_uses_explicit_semantics_not_comment(evidence):
    original = deepcopy(evidence)
    assert generator.build_view_contract(**evidence) == evidence['semantics']
    assert evidence == original


@pytest.mark.parametrize('drift', ['definition', 'type', 'columns', 'uniqueness', 'relations', 'grain'])
def test_generation_rejects_definition_type_or_uniqueness_drift(evidence, drift):
    if drift == 'definition':
        evidence['definition'] += ' '
    elif drift == 'type':
        evidence['columns'][0] = ('store_id', 'text', None)
    elif drift == 'columns':
        evidence['columns'].pop()
    elif drift == 'uniqueness':
        evidence['constraints']['inventory'] = []
    elif drift == 'relations':
        evidence['relations'] = ['demo_retail.inventory']
    else:
        evidence['semantics']['grain']['keys'] = ['store_id']
    with pytest.raises(ValueError):
        generator.build_view_contract(**evidence)


def test_generation_requires_semantic_definition(evidence):
    evidence['semantics'] = None
    with pytest.raises(ValueError, match='semantic'):
        generator.build_view_contract(**evidence)


def test_generation_does_not_overwrite_different_contract(tmp_path, evidence):
    path = tmp_path / 'view.yaml'
    policy = evidence['semantics']
    generator.write_contract_file(path, policy)
    original = path.read_bytes()
    generator.write_contract_file(path, policy)
    assert path.read_bytes() == original
    changed = deepcopy(policy)
    changed['summary'] = '不同描述。'
    with pytest.raises(ValueError, match='manual merge'):
        generator.write_contract_file(path, changed)
    assert path.read_bytes() == original


def test_main_reads_canonical_semantics_and_preserves_approval(tmp_path, evidence, monkeypatch):
    root = tmp_path / 'profile'
    root.mkdir()
    name = 'demo_retail.v_inventory_status'
    manifest = {'profile_id': 'reviewed_profile', 'contract_version': '4',
                'source_kind': 'sql', 'catalog': 'catalog.yaml', 'status': 'approved'}
    generator.write_contract_file(root / 'manifest.yaml', manifest)
    generator.write_contract_file(root / 'catalog.yaml', {'schema': 'demo_retail',
        'views': {name: {'path': 'views/demo_retail/v_inventory_status.yaml'}}})
    generator.write_contract_file(root / 'views/demo_retail/v_inventory_status.yaml', evidence['semantics'])
    (root / '.env').write_text('RETAILER_DB_SCHEMA=demo_retail\nCPEA_DATABASE_URL=unused\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['generate', '--root', str(root), '--semantic-profile', str(root)])
    monkeypatch.setattr(generator.psycopg, 'connect', lambda *a, **k: MagicMock())
    monkeypatch.setattr(generator, 'discover', lambda *a: [
        (evidence['name'], evidence['definition'], '不可作為 summary 的混雜註解',
         evidence['columns'], evidence['constraints'])])
    monkeypatch.setattr(generator, 'discover_relations', lambda *a: evidence['relations'])
    original = {p: p.read_bytes() for p in root.rglob('*.yaml')}
    generator.main()
    assert {p: p.read_bytes() for p in root.rglob('*.yaml')} == original
    assert yaml.safe_load((root / 'manifest.yaml').read_text(encoding='utf-8')) == manifest


def test_generation_rejects_missing_canonical_view_before_writing(tmp_path, evidence, monkeypatch):
    (tmp_path / '.env').write_text('RETAILER_DB_SCHEMA=demo_retail\nCPEA_DATABASE_URL=unused\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['generate', '--root', str(tmp_path)])
    view = SimpleNamespace(name=evidence['semantics']['view'], policy=evidence['semantics'])
    monkeypatch.setattr(generator, 'SchemaCatalog', lambda *a, **k: SimpleNamespace(views=lambda: [view]))
    monkeypatch.setattr(generator.psycopg, 'connect', lambda *a, **k: MagicMock())
    monkeypatch.setattr(generator, 'discover', lambda *a: [])
    with pytest.raises(ValueError, match='canonical'):
        generator.main()
    assert not (tmp_path / 'views').exists()
