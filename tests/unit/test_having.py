from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest

from cpea.domain.models import HavingFilter, QueryFilter, QueryPlan
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.application.services.sql_execution import SQLExecutionAgent
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from cpea.workflows.text_to_sql.schemas import SQLClauseMapping, SQLClauseMappingV3
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from evaluations.view_matching_cases import ViewMatchingCase, validate_view_case
from evaluations.view_matching_grading import grade_view_matching
from cpea.application.models.query import MappingAttempt, QueryTaskTrace, SQLGenerationResponse
from tests.support import Counter


ROOT = Path(__file__).resolve().parents[2]
VIEW = "demo_retail.v_daily_sales"


def test_having_schema_versions_and_hidden_aggregate():
    v2 = load_match_prompt("v2")
    v3 = load_match_prompt("v3")
    v4 = load_match_prompt()
    assert v2.response_model is SQLClauseMapping
    assert v3.response_model is SQLClauseMappingV3
    assert v4.version == "v4" and v4.response_model is SQLClauseMappingV3
    assert v3.system_sha256 != v4.system_sha256
    assert v2.response_schema_sha256 != v3.response_schema_sha256
    with pytest.raises(ValueError, match="having"):
        SQLClauseMappingV3.model_validate({"fields": [], "table": None})
    catalog = SchemaCatalog(ROOT / "projects/retail", allow_drafts=True)
    plan = QueryPlan(supported=True, source_views=[VIEW], select_columns=["store_id"],
                     group_by=["store_id"], having=[HavingFilter(column="revenue", aggregation="sum",
                                                                  operator=">", value=100)])
    sql = compile_single_view(plan, catalog)
    assert "SELECT TOP (200) [store_id]" in sql
    assert "GROUP BY [store_id] HAVING SUM([revenue]) > 100" in sql
    assert "SUM([revenue]) AS" not in sql
    validate_generated_sql(sql, {VIEW})
    for invalid in (True, "100", float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite numeric literal"):
            HavingFilter(column="revenue", aggregation="sum", operator=">", value=invalid)


def test_having_contract_rejects_ungrouped_and_disallowed_aggregate():
    catalog = SchemaCatalog(ROOT / "projects/retail", allow_drafts=True)
    base = QueryPlan(supported=True, source_views=[VIEW], select_columns=["store_id"],
                     having=[HavingFilter(column="revenue", aggregation="sum", operator=">", value=100)])
    with pytest.raises(SQLPolicyError, match="HAVING 必須有 GROUP BY"):
        compile_single_view(base, catalog)
    restricted = QueryPlan(supported=True, source_views=["demo_retail.v_store_monthly_kpi"],
                           select_columns=["region"], group_by=["region"],
                           having=[HavingFilter(column="gross_margin_pct", aggregation="sum", operator=">", value=10)])
    with pytest.raises(SQLPolicyError, match="aggregation 不允許"):
        compile_single_view(restricted, catalog)


def test_where_group_having_order_and_multiple_conditions():
    catalog = SchemaCatalog(ROOT / "projects/retail", allow_drafts=True)
    plan = QueryPlan(supported=True, source_views=[VIEW], select_columns=["store_id"],
                     filters=[QueryFilter(column="sales_date", operator=">=", value="2026-01-01")],
                     group_by=["store_id"], order_by=["store_id"],
                     having=[HavingFilter(column="revenue", aggregation="sum", operator=">", value=100),
                             HavingFilter(column="order_count", aggregation="count", operator=">=", value=2)])
    sql = compile_single_view(plan, catalog)
    assert sql.index(" WHERE ") < sql.index(" GROUP BY ") < sql.index(" HAVING ") < sql.index(" ORDER BY ")
    assert "HAVING SUM([revenue]) > 100 AND COUNT([order_count]) >= 2" in sql
    validate_generated_sql(sql, {VIEW})


def test_v2_case_shape_remains_readable_and_v3_having_is_graded():
    catalog = SchemaCatalog(ROOT / "projects/retail", allow_drafts=True)
    lines = (ROOT / "projects/retail/evaluations/cases.jsonl").read_text(encoding="utf-8").splitlines()
    raw = next(json.loads(line) for line in lines if '"case_id": "RETAIL-DAILY_SALES-B-09"' in line)
    case = ViewMatchingCase.model_validate(raw)
    validate_view_case(case, catalog)
    spec = case.expected_sql
    assert spec is not None
    plan = QueryPlan(supported=True, source_views=[VIEW], select_columns=spec.select_columns,
                     filters=spec.filters, having=spec.having or [], group_by=spec.group_by,
                     aggregations=spec.aggregations, order_by=spec.order_by)
    sql = compile_single_view(plan, catalog, request=case.request)
    trace = QueryTaskTrace(request=case.request, selected_mapping_index=1,
                           mapping_attempts=[MappingAttempt(attempt_index=1, mapping=case.expected_match,
                                                            outcome="selected")])
    result = SQLGenerationResponse(supported=True, sql=sql, selected_views=[VIEW], explanation="test",
                                   query_plan=plan, query_trace=trace)
    assert grade_view_matching(case, result, catalog=catalog) == ("pass", "pass", [])
    wrong = plan.model_copy(update={"having": []})
    assert "sql_having" in grade_view_matching(case, result.model_copy(update={"query_plan": wrong}), catalog=catalog)[2]
    legacy = json.loads(lines[0])
    legacy["prompt_version"] = "v2"
    legacy["prompt_sha256"] = load_match_prompt("v2").system_sha256
    legacy["expected_match"].pop("having")
    legacy["expected_sql"].pop("having")
    old_case = ViewMatchingCase.model_validate(legacy)
    assert isinstance(old_case.expected_match, SQLClauseMapping)
    validate_view_case(old_case, catalog)


def test_workflow_having_keeps_hidden_metric_out_of_select():
    request = "請從 demo_retail.v_daily_sales 依門市識別碼分組，只顯示門市識別碼，只保留折扣後銷售淨額合計大於 100 的群組。"
    class HavingLLM:
        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps({
                "fields": [{"text": "門市識別碼", "column": "store_id", "aggregation": None}],
                "table": {"text": VIEW, "view": VIEW}, "criteria": [],
                "having": [{"text": "折扣後銷售淨額合計大於 100", "column": "revenue", "aggregation": "sum",
                            "operator": ">", "value": 100}],
                "order": [], "group": [{"text": "門市識別碼", "column": "store_id"}], "ignored": [],
            }, ensure_ascii=False))
    settings = replace(AssistantSettings.from_env(), retrieval_mode="lexical", context_window=16000)
    catalog = SchemaCatalog(ROOT / "projects/retail", allow_drafts=True)
    workflow = SQLGenerationWorkflow(HavingLLM(), catalog=catalog, settings=settings,
                                     retriever=SchemaRetriever(settings, catalog=catalog),
                                     context_packer=ContextPacker(settings, token_counter=Counter()))
    result = workflow.invoke(request)
    assert result.supported, result.explanation
    assert result.query_plan.select_columns == ["store_id"]
    assert result.query_plan.having == [HavingFilter(column="revenue", aggregation="sum", operator=">", value=100)]
    assert "HAVING SUM([revenue]) > 100" in result.sql
    agent = SQLExecutionAgent(HavingLLM(), catalog=catalog,
                              executor=lambda _source, _sql: (["store_id"], [[1]]),
                              settings=settings, retriever=SchemaRetriever(settings, catalog=catalog),
                              context_packer=ContextPacker(settings, token_counter=Counter()))
    assert agent.execute_generation(result, "test", request=request).rows == [[1]]


def test_workflow_rejects_having_threshold_mapped_to_where():
    request = "請從 demo_retail.v_daily_sales 依門市識別碼分組，只顯示門市識別碼，只保留折扣後銷售淨額合計大於 100 的群組。"
    class MisplacedLLM:
        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps({
                "fields": [{"text": "門市識別碼", "column": "store_id", "aggregation": None}],
                "table": {"text": VIEW, "view": VIEW},
                "criteria": [{"text": "折扣後銷售淨額合計大於 100", "column": "revenue",
                              "operator": ">", "value": 100}],
                "having": [], "order": [],
                "group": [{"text": "門市識別碼", "column": "store_id"}], "ignored": [],
            }, ensure_ascii=False))
    settings = replace(AssistantSettings.from_env(), retrieval_mode="lexical", context_window=16000)
    catalog = SchemaCatalog(ROOT / "projects/retail", allow_drafts=True)
    workflow = SQLGenerationWorkflow(MisplacedLLM(), catalog=catalog, settings=settings,
                                     retriever=SchemaRetriever(settings, catalog=catalog),
                                     context_packer=ContextPacker(settings, token_counter=Counter()))
    result = workflow.invoke(request)
    assert not result.supported and result.sql is None
    assert any("HAVING" in error or "aggregate threshold" in error for error in result.query_trace.validation_errors)
