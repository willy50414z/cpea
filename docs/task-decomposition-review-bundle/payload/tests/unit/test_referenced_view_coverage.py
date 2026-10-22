"""Path-only evidence must preserve the existing coverage and population guards."""
import pytest
from pydantic import ValidationError

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.referenced_view_coverage import ReferencedViewCoverage, materialize_coverage
from evaluations import three_stage_view_selection as stage
from test_three_stage_view_selection import INV, SALES, MONTH, REQUEST, coverage, recall, selection


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def referenced(catalog, view=INV):
    original = coverage(catalog, view).model_dump()
    rows = []
    for entry in original['entries']:
        maps = []
        for mapping in entry['mappings']:
            maps.append({k: v for k, v in mapping.items() if k not in ('source_quote', 'contract_evidence')})
        rows.append(dict(requirement_id=entry['requirement_id'], status=entry['status'], mappings=maps,
                         contract_path='/grain/description', missing_requirements=entry['missing_requirements']))
    return dict(view=view, entries=rows, grain=original['grain'], keys=original['keys'],
                population=original['population'], contract_path='/summary')


def test_python_derives_request_and_contract_quotes_without_llm_text(catalog):
    wire = ReferencedViewCoverage.model_validate(referenced(catalog))
    result = materialize_coverage(wire, recall(catalog), REQUEST, catalog)
    policy = next(v.policy for v in catalog.views() if v.name == INV)
    for entry in result.entries:
        requirement = next(r for r in recall(catalog).requirements if r.requirement_id == entry.requirement_id)
        for mapping in entry.mappings:
            assert mapping.source_quote == requirement.quote
            assert mapping.contract_evidence[0].quote == policy['columns'][mapping.column]['description']
    grain = next(e for e in result.entries if e.requirement_id == 'grain')
    assert len(grain.contract_evidence) == 1
    assert grain.contract_evidence[0].path == '/grain/description'


def test_population_keys_do_not_require_duplicate_llm_column_citations(catalog):
    data = referenced(catalog)
    pop = next(e for e in data['entries'] if e['requirement_id'] == 'population')
    pop['contract_path'] = '/summary'
    result = materialize_coverage(ReferencedViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)
    mapped = next(e for e in result.entries if e.requirement_id == 'population')
    assert {m.column for m in mapped.mappings} == {'store_id', 'product_id'}
    assert all(m.contract_evidence[0].path == f'/columns/{m.column}/description' for m in mapped.mappings)


@pytest.mark.parametrize('level', ['view', 'entry', 'mapping'])
def test_llm_cannot_supply_or_override_derived_quotations(catalog, level):
    data = referenced(catalog)
    target = data if level == 'view' else data['entries'][0]
    if level == 'mapping':
        target = next(e for e in data['entries'] if e['mappings'])['mappings'][0]
    target['quote'] = '模型自填引文'
    with pytest.raises(ValidationError):
        ReferencedViewCoverage.model_validate(data)


@pytest.mark.parametrize('path', ['/grain/keys', '/does-not-exist', '/grain/keys/01', '/grain/keys/-1'])
def test_invalid_or_non_string_contract_paths_are_rejected(catalog, path):
    data = referenced(catalog)
    data['contract_path'] = path
    with pytest.raises(ValueError, match='contract reference'):
        materialize_coverage(ReferencedViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)


def test_grain_has_one_explicit_description_reference(catalog):
    data = referenced(catalog)
    next(e for e in data['entries'] if e['requirement_id'] == 'grain')['contract_path'] = '/summary'
    with pytest.raises(ValueError, match='grain reference'):
        materialize_coverage(ReferencedViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)


@pytest.mark.parametrize('mutation', ['fake_column', 'wrong_role', 'missing_requirement', 'population_filter'])
def test_adapter_preserves_semantic_structure_guards(catalog, mutation):
    data = referenced(catalog)
    if mutation == 'fake_column':
        data['entries'][0]['mappings'][0]['column'] = 'nonexistent'
    elif mutation == 'wrong_role':
        data['entries'][0]['mappings'][0].update(role='attribute', aggregation=None)
    elif mutation == 'missing_requirement':
        data['entries'].pop()
    else:
        pop = next(e for e in data['entries'] if e['requirement_id'] == 'population')
        pop['mappings'][0].update(role='filter', operator='=', value=1)
    with pytest.raises(ValueError):
        materialize_coverage(ReferencedViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)


def test_partial_monthly_cannot_be_upgraded_to_supported(catalog):
    data = referenced(catalog, MONTH)
    valid = materialize_coverage(ReferencedViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)
    assert next(e for e in valid.entries if e.requirement_id == 'sales').status == 'partial'
    row = next(e for e in data['entries'] if e['requirement_id'] == 'sales')
    row.update(status='supported', missing_requirements=[])
    with pytest.raises(ValueError, match='same-source scope'):
        materialize_coverage(ReferencedViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)


def test_inner_join_still_cannot_claim_preserved_inventory_population(catalog):
    mappings = [materialize_coverage(ReferencedViewCoverage.model_validate(referenced(catalog, v.name)),
                                   recall(catalog), REQUEST, catalog) for v in catalog.views()]
    data = selection(catalog).model_dump()
    data['draft']['integration']['edges'][0].update(mode='inner', preserve_task=None)
    with pytest.raises(ValueError, match='population'):
        stage.finish_selection(stage.SelectionResult.model_validate(data), recall(catalog), mappings, REQUEST, catalog)


@pytest.mark.parametrize('fail_at', [None, 'map-02'])
def test_reference_runner_retains_raw_normalizes_and_stops_without_other_stages(catalog, fail_at):
    import json
    from langchain_core.messages import AIMessage
    from evaluations.coverage_reference_runner import run_mappings

    calls, saved = [], {}

    def invoke(name, messages, schema):
        payload = json.loads(messages[1].content)
        calls.append(name)
        assert schema is ReferencedViewCoverage
        assert 'response_schema' in payload
        data = referenced(catalog, payload['view']['view'])
        if name == fail_at:
            data['contract_path'] = '/grain/keys'
        return AIMessage(content=json.dumps(data, ensure_ascii=False))

    result = run_mappings(catalog, {'request': REQUEST}, recall(catalog), invoke, saved.__setitem__)
    assert result['calls'] == (2 if fail_at else 7)
    assert result['valid_views'] == (1 if fail_at else 7)
    assert 'map-01-normalized.json' in saved and 'map-01-call.json' in saved
    assert not any(n.startswith(('recall-', 'selection')) for n in saved)
    if fail_at:
        assert calls == ['map-01', 'map-02']
        assert 'map-02-parsed.json' in saved and 'map-02-error.json' in saved
        assert 'map-02-result.json' not in saved
    else:
        assert result['stopped'] is None
