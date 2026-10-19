import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpea.application.models.query import SQLGenerationResponse
from cpea.config.settings import AssistantSettings
from cpea.domain.models import QueryPlan, SchemaLink
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.workflows.text_to_sql.schemas import SchemaLinkDraft
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow, candidate_schema
from tests.support import Counter


ORDER = "demo_retail.v_order_summary"
DETAIL = "demo_retail.v_sales_detail"


class ComparisonLLM:
    def __init__(self, payload):
        self.payload = payload
        self.messages = []

    def with_response_schema(self, schema):
        assert {"reason", "equivalent_views", "equivalence_evidence"} <= set(schema["required"])
        def invoke(messages):
            self.messages = messages
            return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))
        return SimpleNamespace(invoke=invoke)


def setup_comparison(*, scalar=False, native_detail=False, missing_evidence=False,
                     filter_difference=False, boilerplate_evidence=False):
    root = Path(__file__).resolve().parents[2] / "projects/retail"
    catalog = SchemaCatalog(root, allow_drafts=True)
    schemas = {view.name: candidate_schema(view) for view in catalog.views() if view.name in {ORDER, DETAIL}}
    payload = {"decision": "equivalent", "equivalent_views": [ORDER, DETAIL],
        "reason": "兩個已驗證方案的結果粒度、已完成訂單範圍、毛利定義與篩選相同。",
        "equivalence_evidence": {view: {"grain_or_scope": schema["grain"]["description"],
            "metric_definition": schema["columns"]["gross_profit"]["description"]} for view, schema in schemas.items()}}
    if missing_evidence:
        del payload["equivalence_evidence"][ORDER]
    if boilerplate_evidence:
        payload["equivalence_evidence"][DETAIL]["metric_definition"] = "由核准的 Schema Links 與 View 契約組成。"
    llm = ComparisonLLM(payload)
    settings = replace(AssistantSettings.from_env(), retrieval_mode="lexical", context_window=16000)
    workflow = SQLGenerationWorkflow(llm, catalog, settings=settings,
        context_packer=ContextPacker(settings, token_counter=Counter()))
    request = "計算所有已完成訂單的毛利總和。" if scalar else "查詢每張訂單的毛利。"
    successful = []
    for view in (DETAIL, ORDER):
        aggregation = "sum" if scalar or view == DETAIL and not native_detail else None
        group = ["order_id"] if not scalar and view == DETAIL and not native_detail else []
        plan = QueryPlan(supported=True, source_views=[view],
            select_columns=["gross_profit"] if scalar else ["order_id", "gross_profit"],
            aggregations={"gross_profit": aggregation} if aggregation else {}, group_by=group)
        if filter_difference and view == DETAIL:
            from cpea.domain.models import QueryFilter
            plan.filters = [QueryFilter(column="region", operator="=", value="北部")]
        sql = compile_single_view(plan, catalog, request=request)
        links = SchemaLinkDraft(supported=True, links=[SchemaLink(
            fact_text="毛利", view=view, column="gross_profit", role="metric", aggregation=aggregation)])
        response = SQLGenerationResponse(supported=True, sql=sql, explanation="validated fixture", query_plan=plan)
        successful.append((view, {"links": links}, {"response": response}, 0))
    return workflow, llm, schemas, successful, request


@pytest.mark.parametrize("scalar", [False, True])
def test_verified_equivalent_result_grains_do_not_require_confirmation(scalar):
    workflow, llm, schemas, successful, request = setup_comparison(scalar=scalar)
    selected, clarification = workflow._compare_valid_candidates(request, schemas, successful)
    assert selected == DETAIL and clarification is None
    assert '"query_plan"' in llm.messages[-1].content


@pytest.mark.parametrize("options", [
    {"native_detail": True}, {"missing_evidence": True}, {"filter_difference": True},
    {"boilerplate_evidence": True},
])
def test_equivalence_cannot_hide_different_grains_filters_or_missing_proof(options):
    workflow, _, schemas, successful, request = setup_comparison(**options)
    selected, clarification = workflow._compare_valid_candidates(request, schemas, successful)
    assert selected is None and clarification is not None
    assert {option.id for option in clarification.options} == {ORDER, DETAIL}
