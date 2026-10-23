from dataclasses import replace
from types import SimpleNamespace

from langchain_core.documents import Document
import pytest

from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult, SchemaRetriever
from tests.decomposition_support import catalog_at, settings


class StaticRetriever:
    def __init__(self, candidates=(), error=None):
        self.candidates, self.error, self.calls = list(candidates), error, []

    def retrieve(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return RetrievalResult(query, self.candidates, 2.0, 1.0)


def item(view, score, rerank=None):
    return RetrievalCandidate(Document(page_content='', metadata={'document_id': view}), score, rerank)


def select(query, catalog, retriever, *, limit=1):
    from cpea.workflows.task_decomposition.mapping_retrieval import select_candidate_views
    return select_candidate_views(query, catalog, settings(), retriever=retriever, limit=limit)


def test_cutoff_ties_and_exclusion_reasons_are_preserved(tmp_path):
    catalog = catalog_at(tmp_path)
    retriever = StaticRetriever([item('demo.stock', .9, .8), item('demo.sales', .8, .8),
                                 item('demo.kpi', .7, .5), item('demo.monthly', .6, .4)])
    result = select('庫存與銷售', catalog, retriever)
    assert [c.view for c in result.candidates] == ['demo.sales', 'demo.stock']
    assert all(c.reranker_score == .8 and 'ranked' in c.reasons for c in result.candidates)
    assert {c.view for c in result.excluded} == {'demo.kpi', 'demo.monthly'}
    assert all(c.reason == 'below_cutoff_or_not_returned' for c in result.excluded)
    assert result.limit == 1 and result.status == 'completed'


def test_explicit_multisource_columns_and_multiple_named_views_are_pinned(tmp_path):
    catalog = catalog_at(tmp_path)
    retriever = StaticRetriever([item('demo.kpi', 1)])
    result = select('demo.stock stock_qty 及 demo.sales quantity', catalog, retriever)
    names = {c.view for c in result.candidates}
    assert names == {'demo.kpi', 'demo.stock', 'demo.sales'}
    for column in ['stock_qty', 'quantity']:
        assert column not in retriever.calls[0]
    pinned = {c.view: c.reasons for c in result.candidates}
    assert 'explicit_view' in pinned['demo.stock'] and 'explicit_column:stock_qty' in pinned['demo.stock']
    assert 'explicit_view' in pinned['demo.sales'] and 'explicit_column:quantity' in pinned['demo.sales']


def test_ambiguous_unqualified_column_preserves_all_owners(tmp_path):
    catalog = catalog_at(tmp_path)
    result = select('store_id', catalog, StaticRetriever())
    assert {c.view for c in result.candidates} == {'demo.stock', 'demo.sales', 'demo.kpi', 'demo.monthly'}
    assert all('explicit_column:store_id' in c.reasons for c in result.candidates)


def test_explicit_qualified_column_does_not_pin_other_owners(tmp_path):
    catalog = catalog_at(tmp_path)
    result = select('demo.stock.store_id', catalog, StaticRetriever())
    assert [c.view for c in result.candidates] == ['demo.stock']


def test_identifier_in_filter_value_is_not_treated_as_a_source_column(tmp_path):
    catalog = catalog_at(tmp_path)
    result = select("sales_channel = 'stock_qty'", catalog, StaticRetriever())
    assert [c.view for c in result.candidates] == ['demo.sales']


@pytest.mark.parametrize('query', ['sales_channel = "demo.stock"',
    'sales_channel IN ("demo.stock", "demo.monthly", "demo.kpi")',
    'sales_channel IN (demo.stock,demo.monthly,demo.kpi)', 'sales_channel = demo.stock'])
def test_filter_literals_do_not_pin_named_views(tmp_path, query):
    result = select(query, catalog_at(tmp_path), StaticRetriever())
    assert [c.view for c in result.candidates] == ['demo.sales']


def test_real_lexical_retriever_does_not_require_all_columns_in_one_view(tmp_path):
    catalog = catalog_at(tmp_path)
    configured = replace(settings(), retrieval_mode='lexical', reranker_enabled=False)
    retriever = SchemaRetriever(configured, catalog)
    assert retriever.retrieve('stock_qty quantity').candidates == []
    from cpea.workflows.task_decomposition.mapping_retrieval import select_candidate_views
    result = select_candidate_views('stock_qty quantity', catalog, configured, retriever=retriever, limit=1)
    assert {'demo.stock', 'demo.sales'} <= {c.view for c in result.candidates}


@pytest.mark.parametrize('candidate', [item('demo.secret', 1), item('demo.stock', float('nan')),
                                       item('demo.stock', .9, float('inf'))])
def test_unadmitted_or_nonfinite_retrieval_results_fail_closed(tmp_path, candidate):
    with pytest.raises(ValueError):
        select('庫存', catalog_at(tmp_path), StaticRetriever([candidate]))
