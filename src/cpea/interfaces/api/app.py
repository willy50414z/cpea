from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
from cpea.bootstrap import AssistantRuntime
from cpea.application.errors import DependencyUnavailable
from cpea.application.models.query import SQLGenerationResponse, AssistantQueryResponse
from cpea.application.services.sql_execution import SQLExecutionError
from cpea.interfaces.api.schemas import SQLGenerationRequest, StreamQueryRequest
from cpea.interfaces.api.streaming import ERROR_MESSAGE, STREAM_PATH, query_events

def create_app(runtime: AssistantRuntime | None = None) -> FastAPI:
    runtime = runtime if runtime is not None else AssistantRuntime.from_env()
    app = FastAPI(title='CPEA', version='0.1.0')
    app.state.runtime = runtime
    router = APIRouter(prefix='/api/assistant', tags=['assistant'])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path == STREAM_PATH:
            return JSONResponse({'message': ERROR_MESSAGE}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @router.post('/query/stream')
    async def stream_query(payload: StreamQueryRequest, request: Request):
        try:
            runtime.require_execution()
        except Exception:
            return JSONResponse({'message': ERROR_MESSAGE}, status_code=503)
        return StreamingResponse(query_events(runtime, request, payload.request, payload.clarification_choice),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})

    @router.post('/sql', response_model=SQLGenerationResponse)
    def generate_sql(payload: SQLGenerationRequest):
        try:
            return runtime.generate(payload.request, payload.history, payload.clarification_choice)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post('/query', response_model=AssistantQueryResponse | SQLGenerationResponse)
    def query_assistant(payload: SQLGenerationRequest):
        try:
            runtime.require_execution()
            return runtime.query(payload.request, payload.history, payload.clarification_choice)
        except DependencyUnavailable as exc:
            raise HTTPException(status_code=503, detail={'code': exc.code, 'message': str(exc)}) from exc
        except (FileNotFoundError, ValueError, SQLExecutionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    app.include_router(router)
    import gradio as gr
    from cpea.interfaces.web.ui import create_ui
    return gr.mount_gradio_app(app, create_ui(runtime), path='/',
        show_error=False, footer_links=[], run_history=False, ssr_mode=False,
        enable_monitoring=False, mcp_server=False,
        css='''html[data-cpea-pending] :is(#cpea-chat, #cpea-sql, #cpea-results) { display: none !important; }
            .toast-body.error { display: none !important; }''')
