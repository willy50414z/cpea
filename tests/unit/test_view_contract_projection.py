from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from cpea.application.catalog_contract import CatalogContract
from cpea.domain.catalog import ViewDefinition
from cpea.domain.models import QueryPlan, SchemaLink
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.retrieval.documents import build_documents
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import SQLPolicyError
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from cpea.workflows.text_to_sql.sql_generation import candidate_schema, SQLGenerationWorkflow, ViewComparison
from tests.view_contract_v4_support import v4_policy, write_v4_profile


def test_v4_preserves_v3_capabilities_and_operators(tmp_path):
    policy = v4_policy()
    policy['columns']['库存数量']['disallowed_aggregations'] = ['avg']
    catalog = SchemaCatalog(write_v4_profile(tmp_path / 'v4', policy))
    legacy = deepcopy(policy)
    legacy['version'] = 3
    for name in ('source', 'scope', 'time', 'usage', 'metrics'):
        legacy.pop(name)
    legacy['columns']['仓库名称'].pop('entity')
    v3 = SchemaCatalog(write_v4_profile(tmp_path / 'v3', legacy))
    for column in policy['columns']:
        for key in ('capabilities', 'aggregations'):
            assert catalog.field_contract(policy['view'], column)[key] == v3.field_contract(policy['view'], column)[key]
        assert catalog._operators_for(policy['view'], column) == v3._operators_for(policy['view'], column)


def test_v4_metadata_reaches_retrieval_candidate_and_detail(tmp_path):
    policy = v4_policy()
    catalog = SchemaCatalog(write_v4_profile(tmp_path, policy))
    definition = catalog.views()[0]
    projected = candidate_schema(definition)
    assert projected['columns']['仓库名称']['entity'] == '倉庫'
    document = build_documents(catalog)[0]
    assert document.metadata['summary'] == policy['summary']
    assert 'snapshot_date' not in document.page_content
    for name in ('source', 'scope', 'time', 'usage', 'metrics'):
        assert projected[name] == policy[name]
        assert json.dumps(policy[name], ensure_ascii=False) in catalog.detail(definition.name)
    for text in ('每個品號及倉庫組合一列', '不可跨快照日期直接加總', '歷史銷售趨勢', '限同一快照日期加總'):
        assert text in document.page_content


def test_source_relations_do_not_expand_sql_allowlist(tmp_path):
    policy = v4_policy()
    policy['source'] = {'verification': 'metadata_verified', 'relations': ['gms2.inventory'],
                        'definition_sha256': 'a' * 64}
    catalog = SchemaCatalog(write_v4_profile(tmp_path, policy))
    assert [v.name for v in catalog.views()] == ['gms2.v_inventory']
    plan = QueryPlan(supported=True, source_views=['gms2.inventory'], select_columns=['库存数量'])
    with pytest.raises((SQLPolicyError, ValueError)):
        compile_single_view(plan, catalog, max_rows=20, dialect='postgresql')


def test_candidate_comparison_receives_v4_semantics():
    first = v4_policy()
    first['columns']['库存数量']['entity'] = '商品'
    second = deepcopy(first)
    second['view'] = 'gms2.v_other'
    second['scope']['population'] = '另一種庫存母體'
    second['columns']['库存数量']['entity'] = '另一種商品'
    definitions = [ViewDefinition(p['view'], p['summary'], '', p) for p in (first, second)]

    class Catalog(CatalogContract):
        fingerprint = 'test-contract'
        def views(self):
            return definitions

    workflow = object.__new__(SQLGenerationWorkflow)
    workflow.catalog = Catalog()
    workflow.match_prompt = load_match_prompt('v10')
    captured = []

    def compare(prompt, variables, model):
        captured.extend(json.loads(variables['candidates']))
        return ViewComparison(decision='clarify')

    workflow._invoke_model = compare
    schemas = {d.name: candidate_schema(d) for d in definitions}
    successful = [(d.name, {'links': SimpleNamespace(links=[SchemaLink(
        fact_text='庫存數量', view=d.name, column='库存数量', role='metric')])}, {}, 0)
        for d in definitions]
    selected, clarification = workflow._compare_valid_candidates('列出庫存數量', schemas, successful)
    assert selected is None and clarification is not None
    assert len(captured) == 2
    for evidence, policy in zip(captured, (first, second), strict=True):
        assert evidence['mapped_fields'][0]['entity'] == policy['columns']['库存数量']['entity']
        for name in ('source', 'scope', 'time', 'usage', 'metrics'):
            assert evidence[name] == policy[name]
