from copy import deepcopy

import pytest

from tests.decomposition_support import catalog_at
from tests.schema_mapping_support import REQUEST, extraction, mapped_draft, mapping, review, span


def bundle(tmp_path, *, monthly=False):
    from cpea.workflows.task_decomposition.mapping_models import (
        RequirementExtraction, ViewMapping, MappingReview, MappedDraft)
    from cpea.workflows.task_decomposition.mapping import validate_review, validate_mapped_draft
    catalog = catalog_at(tmp_path)
    extracted = RequirementExtraction.model_validate(extraction())
    mappings = [ViewMapping.model_validate(mapping(v.name, monthly=monthly)) for v in catalog.views()]
    return catalog, extracted, mappings, MappingReview, MappedDraft, validate_review, validate_mapped_draft


@pytest.mark.parametrize('monthly', [False, True])
def test_reviewed_sources_bind_to_actual_task_columns_and_accept_equivalent_sources(tmp_path, monthly):
    catalog, extracted, mappings, rm, dm, vr, vd = bundle(tmp_path, monthly=monthly)
    checked = rm.model_validate(review(monthly=monthly))
    assert vr(REQUEST, extracted, mappings, checked, catalog.views()) == []
    assert vd(extracted, mappings, checked, dm.model_validate(mapped_draft(monthly=monthly)), catalog) == []


@pytest.mark.parametrize('mutation', ['missing_term', 'invalid_missing_span', 'unknown_candidate',
                                     'duplicate_candidate', 'missing_required', 'missing_view',
                                     'missing_constraint', 'period_without_filter', 'unknown_filter',
                                     'aux_without_evidence', 'aux_unknown_requirement', 'wrong_anchor'])
def test_review_rejects_omissions_and_unsupported_selections(tmp_path, mutation):
    catalog, extracted, mappings, rm, _, validate, _ = bundle(tmp_path)
    data = review()
    if mutation == 'missing_term': data['missing_requirements'] = [span('暫不計算採購量')]
    if mutation == 'invalid_missing_span': data['missing_requirements'] = [{'start': 0, 'end': 1, 'text': '假'}]
    if mutation == 'unknown_candidate': data['selected_candidate_ids'].append('made-up')
    if mutation == 'duplicate_candidate': data['selected_candidate_ids'].append(data['selected_candidate_ids'][0])
    if mutation == 'missing_required':
        data['selected_candidate_ids'].remove('demo.stock:stock:stock_qty')
        data['rejected_candidates'].append({'candidate_id': 'demo.stock:stock:stock_qty', 'reason': '拒絕'})
    if mutation == 'missing_view': mappings.pop()
    if mutation == 'missing_constraint': data['constraints'].pop()
    if mutation == 'period_without_filter': data['constraints'][0]['filters'] = []
    if mutation == 'unknown_filter': data['constraints'][0]['filters'][0]['condition']['column'] = 'snapshot_date'
    if mutation.startswith('aux_'):
        data['auxiliary_columns'] = [{'view': 'demo.stock', 'column': 'snapshot_date',
            'operations': ['metadata'], 'requirement_ids': ['stock' if mutation == 'aux_without_evidence' else 'missing'],
            'evidence': [{'path': ['columns', 'store_id', 'description'], 'quote': 'store_id'}],
            'reason': '盤點日期上下文。'}]
    if mutation == 'wrong_anchor': data['constraints'][1]['anchor_view'] = 'demo.kpi'
    assert validate(REQUEST, extracted, mappings, rm.model_validate(data), catalog.views())


@pytest.mark.parametrize('mutation', ['unknown_view', 'unknown_column', 'unapproved_operation',
                                     'missing_binding', 'wrong_task_binding', 'unbacked_binding',
                                     'changed_period', 'lost_anchor', 'inner_join', 'forbidden_use'])
def test_draft_cannot_expand_approved_sources_or_drop_constraints(tmp_path, mutation):
    catalog, extracted, mappings, rm, dm, _, validate = bundle(tmp_path)
    data, reviewed = mapped_draft(), review()
    stock, sales = data['draft']['tasks']
    if mutation == 'unknown_view': sales['view'] = 'demo.monthly'
    if mutation == 'unknown_column': stock['required_columns'].append('snapshot_date')
    if mutation == 'unapproved_operation':
        stock.update(attributes=[], metrics={'stock_qty': 'sum'}, group_by=['store_id', 'product_id'])
    if mutation == 'missing_binding': data['bindings'] = [b for b in data['bindings'] if b['requirement_id'] != 'sales']
    if mutation == 'wrong_task_binding': data['bindings'][0]['task_id'] = 'missing'
    if mutation == 'unbacked_binding': data['bindings'][0]['columns'] = ['stock_qty']
    if mutation == 'changed_period': sales['filters'][0]['value'] = '2026-09-15'
    if mutation == 'lost_anchor': data['draft']['integration']['anchor_task'] = 'sales'
    if mutation == 'inner_join': data['draft']['integration']['edges'][0]['mode'] = 'inner'
    if mutation == 'forbidden_use':
        reviewed['constraints'][-1]['forbidden_uses'] = [{'view': 'demo.stock', 'column': 'stock_qty', 'operations': ['attribute']}]
    assert validate(extracted, mappings, rm.model_validate(reviewed), dm.model_validate(data), catalog)


def test_auxiliary_date_is_usable_only_with_same_column_evidence_and_binding(tmp_path):
    catalog, extracted, mappings, rm, dm, vr, vd = bundle(tmp_path)
    data, reviewed = mapped_draft(), review()
    reviewed['auxiliary_columns'] = [{'view': 'demo.stock', 'column': 'snapshot_date',
        'operations': ['attribute'], 'requirement_ids': ['stock'], 'reason': '盤點上下文。',
        'evidence': [{'path': ['columns', 'snapshot_date', 'description'], 'quote': 'snapshot_date'}]}]
    data['draft']['tasks'][0]['required_columns'].append('snapshot_date')
    data['draft']['tasks'][0]['attributes'].append('snapshot_date')
    data['bindings'][2]['columns'].append('snapshot_date')
    checked = rm.model_validate(reviewed)
    assert vr(REQUEST, extracted, mappings, checked, catalog.views()) == []
    assert vd(extracted, mappings, checked, dm.model_validate(data), catalog) == []


@pytest.mark.parametrize('escape', ['conditional_decoy', 'extra_unfiltered_task'])
def test_period_applies_to_every_related_measure_use_and_task(tmp_path, escape):
    catalog, extracted, mappings, rm, dm, _, validate = bundle(tmp_path)
    data = mapped_draft()
    sales = data['draft']['tasks'][1]
    if escape == 'conditional_decoy':
        sales['conditional_metrics'] = [{'column': 'quantity', 'aggregation': 'sum',
                                         'conditions': sales.pop('filters')}]
    else:
        extra = deepcopy(sales)
        extra.update(task_id='sales_all_time', filters=[])
        extra['required_columns'].remove('order_date')
        data['draft']['tasks'].append(extra)
        edge = deepcopy(data['draft']['integration']['edges'][0])
        edge['right_task'] = 'sales_all_time'
        data['draft']['integration']['edges'].append(edge)
        data['bindings'].extend([{**b, 'task_id': 'sales_all_time'} for b in list(data['bindings'])
                                 if b['task_id'] == 'sales' and b['requirement_id'] != 'period'])
    assert validate(extracted, mappings, rm.model_validate(review()), dm.model_validate(data), catalog)


def test_conditional_measure_can_carry_its_own_complete_period(tmp_path):
    catalog, extracted, mappings, rm, dm, _, validate = bundle(tmp_path)
    data = mapped_draft()
    sales = data['draft']['tasks'][1]
    sales['metrics'] = {}
    sales['conditional_metrics'] = [{'column': 'quantity', 'aggregation': 'sum',
                                     'conditions': sales.pop('filters')}]
    assert validate(extracted, mappings, rm.model_validate(review()), dm.model_validate(data), catalog) == []


def test_preparation_cannot_remove_a_required_final_output_grain(tmp_path):
    catalog, extracted, mappings, rm, dm, _, validate = bundle(tmp_path)
    data = mapped_draft()
    data['draft']['integration']['output_grain'] = ['product_id']
    data['draft']['integration']['preparation'] = [{'task_id': 'stock', 'kind': 'aggregate',
        'keys': ['product_id'], 'description': '彙總各店資料為各商品。'}]
    assert validate(extracted, mappings, rm.model_validate(review()), dm.model_validate(data), catalog)


def test_population_anchor_must_support_its_related_data_requirement(tmp_path):
    catalog, extracted, mappings, rm, _, validate, _ = bundle(tmp_path)
    data = review()
    data['constraints'][1]['anchor_view'] = 'demo.sales'
    assert validate(REQUEST, extracted, mappings, rm.model_validate(data), catalog.views())
