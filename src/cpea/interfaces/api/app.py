from fastapi import FastAPI, APIRouter, HTTPException
from cpea.bootstrap import AssistantRuntime
from cpea.application.errors import DependencyUnavailable
from cpea.application.models.query import SQLGenerationResponse, AssistantQueryResponse
from cpea.application.services.sql_execution import SQLExecutionError
from cpea.interfaces.api.schemas import SQLGenerationRequest

def create_app(runtime: AssistantRuntime | None = None) -> FastAPI:
    runtime = runtime if runtime is not None else AssistantRuntime.from_env()
    app = FastAPI(title='CPEA', version='0.1.0')
    app.state.runtime = runtime
    router = APIRouter(prefix='/api/assistant', tags=['assistant'])

    @router.post('/sql', response_model=SQLGenerationResponse)
    def generate_sql(payload: SQLGenerationRequest):
        try:
            return runtime.generate(payload.request, payload.history)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post('/query', response_model=AssistantQueryResponse)
    def query_assistant(payload: SQLGenerationRequest):
        try:
            runtime.require_execution()
            return runtime.query(payload.request, payload.history)
        except DependencyUnavailable as exc:
            raise HTTPException(status_code=503, detail={'code': exc.code, 'message': str(exc)}) from exc
        except (FileNotFoundError, ValueError, SQLExecutionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    app.include_router(router)
    return app
