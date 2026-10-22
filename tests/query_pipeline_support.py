from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.application.models.query import SQLGenerationResponse
from cpea.domain.models import QueryPlan
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.workflows.task_decomposition.validation import prepare_requests
from tests.decomposition_support import draft


def planning(catalog, *, single=False):
    data = draft()
    if single:
        data['tasks'] = data['tasks'][:1]
        data['strategy'] = 'single_view'
        data['integration']['edges'] = []
    parsed = DecompositionDraft.model_validate(data)
    return DecompositionResponse(status='ready', draft=parsed,
        prepared_requests=prepare_requests(parsed, catalog), contract_fingerprint=catalog.fingerprint)


def generation(task, catalog, settings):
    plan = QueryPlan(supported=True, source_views=[task.view],
        select_columns=list(dict.fromkeys(task.attributes + task.output_grain + list(task.metrics))),
        filters=[f.model_dump() for f in task.filters], aggregations=task.metrics, group_by=task.group_by)
    return SQLGenerationResponse(status='ready', supported=True, query_plan=plan,
        selected_views=[task.view], explanation='fixture',
        sql=compile_single_view(plan, catalog, max_rows=settings.max_rows,
            dialect=settings.database_settings.resolved_dialect))
