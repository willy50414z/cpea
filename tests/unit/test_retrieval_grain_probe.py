from types import SimpleNamespace

from cpea.application.models.query import SQLGenerationResponse
from cpea.domain.models import QueryPlan
from evaluations.retrieval_grain_probe import DETAIL, ORDER, grade_probe


def ready(view, *, aggregations=None, group_by=None):
    return SQLGenerationResponse(supported=True, status="ready", sql="SELECT ...", explanation="fixture",
        selected_views=[view], query_plan=QueryPlan(supported=True, source_views=[view],
            select_columns=[*(group_by or []), "gross_profit"],
            aggregations=aggregations or {}, group_by=group_by or []))


def test_order_probe_rejects_unaggregated_detail_and_accepts_safe_rollup():
    assert grade_probe("order", ready(ORDER))
    assert not grade_probe("order", ready(DETAIL))
    assert grade_probe("order", ready(DETAIL, aggregations={"gross_profit": "sum"}, group_by=["order_id"]))
    assert not grade_probe("order", ready(DETAIL, aggregations={"gross_profit": "sum"}, group_by=["product_id"]))
    assert grade_probe("detail", ready(DETAIL))
    assert not grade_probe("detail", ready(ORDER))
    assert grade_probe("equivalent", ready(DETAIL, aggregations={"gross_profit": "sum"}))


def test_ambiguous_probe_requires_both_interpretations_and_no_sql():
    response = SimpleNamespace(status="needs_clarification", sql=None,
        clarification=SimpleNamespace(options=[SimpleNamespace(id=ORDER)]))
    assert not grade_probe("ambiguous", response)
    response.clarification.options.append(SimpleNamespace(id=DETAIL))
    assert grade_probe("ambiguous", response)
    response.sql = "SELECT ..."
    assert not grade_probe("ambiguous", response)
