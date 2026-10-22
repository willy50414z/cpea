"""Public planning-only application boundary."""
from cpea.workflows.task_decomposition.workflow import TaskDecompositionWorkflow


class TaskDecompositionService:
    def __init__(self,llm,catalog,*,settings,token_counter=None,observer=None):
        self.workflow=TaskDecompositionWorkflow(llm,catalog,settings=settings,token_counter=token_counter,observer=observer)

    def plan(self,request):
        return self.workflow.invoke(request)
