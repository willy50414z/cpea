"""Opt-in application boundary; the existing planner remains unchanged."""
from cpea.workflows.task_decomposition.schema_mapping_workflow import SchemaMappingDecompositionWorkflow


class SchemaMappingDecompositionService:
    def __init__(self, llm, catalog, *, settings, token_counter=None, observer=None, retriever=None, view_limit=None):
        self.workflow = SchemaMappingDecompositionWorkflow(
            llm, catalog, settings=settings, token_counter=token_counter, observer=observer,
            retriever=retriever, view_limit=view_limit)

    def plan(self, request):
        return self.workflow.invoke(request)
