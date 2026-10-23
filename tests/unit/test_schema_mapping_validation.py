from copy import deepcopy

import pytest

from tests.decomposition_support import catalog_at
from tests.schema_mapping_support import REQUEST, extraction, mapping


def api():
    from cpea.workflows.task_decomposition.mapping_models import RequirementExtraction, ViewMapping
    from cpea.workflows.task_decomposition.mapping import validate_extraction, validate_view_mapping
    return RequirementExtraction, ViewMapping, validate_extraction, validate_view_mapping


def test_overlapping_business_spans_and_noncolumn_constraints_cover_request():
    model, _, validate, _ = api()
    value = model.model_validate(extraction())
    assert validate(REQUEST, value) == []
    assert [r.kind for r in value.requirements][-3:] == ['population', 'purpose', 'prohibition']


@pytest.mark.parametrize('mutation', ['span', 'gap', 'duplicate', 'relation', 'punctuation'])
def test_invalid_extraction_is_rejected(mutation):
    model, _, validate, _ = api()
    data = extraction()
    if mutation == 'span': data['requirements'][0]['span']['start'] = 1
    if mutation == 'gap': data['requirements'].pop(2)
    if mutation == 'duplicate': data['requirements'][1]['id'] = 'store'
    if mutation == 'relation': data['requirements'][0]['related_ids'] = ['missing']
    if mutation == 'punctuation': data['syntax'].append({'kind': 'punctuation', 'span': data['requirements'][0]['span']})
    assert validate(REQUEST, model.model_validate(data))


def test_all_requirements_have_view_result_and_noncolumn_constraints_need_no_candidates(tmp_path):
    extract, model, _, validate = api()
    view = next(v for v in catalog_at(tmp_path).views() if v.name == 'demo.stock')
    value = model.model_validate(mapping(view.name))
    assert validate(value, extract.model_validate(extraction()), view) == []


@pytest.mark.parametrize('mutation', ['missing_term', 'duplicate_term', 'wrong_view', 'unknown_column',
                                     'wrong_path', 'cross_column', 'empty_quote', 'duplicate_candidate',
                                     'constraint_as_data', 'unmatched_with_candidate'])
def test_mapping_completeness_and_same_column_path_evidence_are_enforced(tmp_path, mutation):
    extract, model, _, validate = api()
    view = next(v for v in catalog_at(tmp_path).views() if v.name == 'demo.stock')
    data = mapping(view.name)
    if mutation == 'missing_term': data['results'].pop()
    if mutation == 'duplicate_term': data['results'].append(deepcopy(data['results'][0]))
    if mutation == 'wrong_view': data['view'] = 'demo.sales'
    item = data['results'][0]
    candidate = item['candidates'][0]
    if mutation == 'unknown_column': candidate['column'] = 'missing'
    if mutation == 'wrong_path': candidate['evidence'][0]['path'] = ['columns', 'store_id', 'missing']
    if mutation == 'cross_column': candidate['evidence'][0] = {'path': ['columns', 'product_id', 'description'], 'quote': 'product_id'}
    if mutation == 'empty_quote': candidate['evidence'][0]['quote'] = ' '
    if mutation == 'duplicate_candidate': item['candidates'].append(deepcopy(candidate))
    if mutation == 'constraint_as_data': data['results'][2].update(status='constraint_only', candidates=[])
    if mutation == 'unmatched_with_candidate': item['status'] = 'unmatched'
    assert validate(model.model_validate(data), extract.model_validate(extraction()), view)
