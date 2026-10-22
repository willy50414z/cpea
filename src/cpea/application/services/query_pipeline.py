"""Independent application entry point for the SQL stage only."""
from cpea.workflows.query_pipeline.workflow import QueryPipelineWorkflow


class QueryPipelineService:
    def __init__(self, planner, generator, *, catalog, settings, observer=None):
        self.workflow = QueryPipelineWorkflow(planner, generator, catalog=catalog,
                                              settings=settings, observer=observer)

    def invoke(self, request, *, run_id=None):
        return self.workflow.invoke(request, run_id=run_id)

    def generate_from_plan(self, request, planning, *, run_id=None):
        return self.workflow.generate_from_plan(request, planning, run_id=run_id)
