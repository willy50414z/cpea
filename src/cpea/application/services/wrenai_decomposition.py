"""Planning-only application service for the isolated WrenAI worker."""
from cpea.workflows.task_decomposition.wrenai_workflow import WrenAIDecompositionWorkflow


class WrenAIDecompositionService:
    def __init__(self, client, catalog):
        self.workflow=WrenAIDecompositionWorkflow(client,catalog)

    def plan(self, request, *, run_id=None, case_id=None):
        return self.workflow.invoke(request,run_id=run_id,case_id=case_id)
