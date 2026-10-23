from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog


def test_retail_adapter_preserves_seven_views_102_fields_and_full_contract():
    from cpea.workflows.task_decomposition.wrenai_schema import adapt_catalog, decode_model_name
    catalog = SchemaCatalog(Path(__file__).resolve().parents[2] / 'projects/retail')
    result = adapt_catalog(catalog)
    assert len(result['mdl']['models']) == 7
    assert sum(len(model['columns']) for model in result['mdl']['models']) == 102
    assert result['mdl']['relationships'] == result['mdl']['views'] == result['mdl']['metrics'] == []
    for model in result['mdl']['models']:
        view = result['model_to_view'][model['name']]
        assert decode_model_name(model['name']) == view
        assert 'primaryKey' not in model
        assert model['properties'] == {}
        assert {c['name']: c['type'] for c in model['columns']} == {
            k: {'number':'NUMERIC','string':'VARCHAR','date':'DATE','boolean':'BOOLEAN'}[v]
            for k,v in catalog.columns(view).items()}
        assert result['contracts'][view] == next(v.policy for v in catalog.views() if v.name == view)


def test_names_are_distinct_reversible_and_adapter_does_not_alias_policy():
    from cpea.workflows.task_decomposition.wrenai_schema import adapt_catalog, decode_model_name
    views = [SimpleNamespace(name=n, policy={'grain': {'keys':['id']}, 'columns':{'id':{'type':'boolean'}}})
             for n in ('a.b_c','a_b.c')]
    catalog = SimpleNamespace(views=lambda:views, columns=lambda _: {'id':'boolean'})
    result = adapt_catalog(catalog)
    assert len(result['model_to_view']) == 2
    assert {decode_model_name(n) for n in result['model_to_view']} == {v.name for v in views}
    result['contracts']['a.b_c']['grain']['keys'].append('changed')
    assert views[0].policy['grain']['keys'] == ['id']
    with pytest.raises(ValueError):
        adapt_catalog(SimpleNamespace(views=lambda:views+views[:1],columns=catalog.columns))


def test_manifest_identity_requires_every_dependency_and_dimension():
    from cpea.workflows.task_decomposition.wrenai_schema import generation_manifest
    fields = dict(catalog_fingerprint='c', upstream_sha='u', patch_sha='p', lock_hash='l',
                  embedding_provider='fixture', embedding_model='embed', embedding_dimension=8)
    a = generation_manifest(**fields)
    b = generation_manifest(**{**fields, 'embedding_dimension':16})
    assert a['project_id'] == a['identity'] and a['identity'] != b['identity']
    assert a['namespace'] == 'cpea_wrenai_' + a['identity'][:24]
    with pytest.raises(ValueError): generation_manifest(**{**fields,'upstream_sha':''})
