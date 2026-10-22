from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
from cpea.bootstrap import AssistantRuntime, ProjectRuntimes
from cpea.application.errors import DependencyUnavailable
from cpea.application.models.confirmation import ConfirmationError, ConfirmationRequest
from cpea.application.models.query import SQLGenerationResponse, AssistantQueryResponse
from cpea.application.services.sql_execution import SQLExecutionError
from cpea.interfaces.api.schemas import SQLGenerationRequest, StreamQueryRequest
from cpea.interfaces.api.streaming import ERROR_MESSAGE, STREAM_PATH, query_events

def create_app(runtime: AssistantRuntime | None = None, *, projects: ProjectRuntimes | None = None) -> FastAPI:
    if runtime is None:
        projects = projects or ProjectRuntimes.from_env()
        runtime = projects.get('gms2')
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if projects is not None:
                projects.close()
            else:
                runtime.close()
    app = FastAPI(title='CPEA', version='0.1.0', lifespan=lifespan)
    app.state.runtime = runtime
    app.state.projects = projects
    router = APIRouter(prefix='/api/assistant', tags=['assistant'])

    @app.exception_handler(ConfirmationError)
    async def confirmation_error(request: Request, exc: ConfirmationError):
        return JSONResponse({'detail': {'code': exc.code}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.endswith('/stream'):
            return JSONResponse({'message': ERROR_MESSAGE}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @router.post('/query/stream')
    async def stream_query(payload: StreamQueryRequest, request: Request):
        try:
            runtime.require_execution()
        except Exception:
            return JSONResponse({'message': ERROR_MESSAGE}, status_code=503)
        return StreamingResponse(query_events(runtime, request, payload.request),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})

    @router.post('/sql', response_model=SQLGenerationResponse)
    def generate_sql(payload: SQLGenerationRequest):
        try:
            return runtime.generate(payload.request, payload.history)
        except ConfirmationError:
            raise
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post('/query', response_model=AssistantQueryResponse | SQLGenerationResponse)
    def query_assistant(payload: SQLGenerationRequest):
        try:
            runtime.require_execution()
            return runtime.query(payload.request, payload.history)
        except DependencyUnavailable as exc:
            raise HTTPException(status_code=503, detail={'code': exc.code, 'message': str(exc)}) from exc
        except ConfirmationError:
            raise
        except (FileNotFoundError, ValueError, SQLExecutionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post('/sql/confirm', response_model=SQLGenerationResponse)
    def confirm_sql(payload: ConfirmationRequest):
        return runtime.confirm(payload, mode='sql')

    @router.post('/query/confirm', response_model=AssistantQueryResponse | SQLGenerationResponse)
    def confirm_query(payload: ConfirmationRequest):
        try:
            return runtime.confirm(payload, mode='query')
        except DependencyUnavailable as exc:
            raise HTTPException(status_code=503, detail={'code': exc.code}) from exc
        except ConfirmationError:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=ERROR_MESSAGE) from exc

    @router.post('/query/confirm/stream')
    async def confirm_stream(payload: ConfirmationRequest, request: Request):
        try:
            runtime.require_execution()
        except DependencyUnavailable as exc:
            raise HTTPException(status_code=503, detail={'code': exc.code}) from exc
        claimed = runtime.generation_service().workflow.registry.claim(payload, 'stream', None)
        return StreamingResponse(query_events(runtime, request, '', confirmation=payload, claimed=claimed),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})

    app.include_router(router)
    import gradio as gr
    from cpea.interfaces.web.ui import create_ui
    return gr.mount_gradio_app(app, create_ui(runtime, projects=projects), path='/',
        show_error=False, footer_links=[], run_history=False, ssr_mode=False,
        enable_monitoring=False, mcp_server=False,
        css='''#cpea-conversation { max-width: 880px; margin: 0 auto; height: calc(100dvh - 32px); min-height: 0; flex-wrap: nowrap; font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", sans-serif; }
            #cpea-thread { flex: 1 1 0%; min-height: 0; overflow-y: auto; padding-bottom: 12px; }
            #cpea-thread > * { flex-shrink: 0; }
            #cpea-sql .cm-scroller { min-height: 7em !important; max-height: 22em; overflow: auto; }
            #cpea-composer { flex: 0 0 auto; position: static; background: var(--body-background-fill); padding: 12px 0; z-index: 2; }
            #cpea-assistant-confirmation:has(input[type=radio]) { border: 1px solid var(--border-color-primary); border-radius: 16px; padding: 16px; }
            #cpea-assistant-confirmation label { max-width: 100%; min-width: 0; }
            #cpea-assistant-confirmation label span { white-space: normal !important; overflow: visible !important; overflow-wrap: anywhere; text-overflow: clip !important; min-width: 0; }
            #cpea-chat :is([aria-label="Clear"], [title="Clear"]) { display: none; }
            #cpea-abandon { display: none; }
            html[data-cpea-unknown] #cpea-abandon { display: block; }
            #cpea-transport { padding: 12px; }
            .toast-body.error { display: none !important; }
            @media (max-width: 600px) { #cpea-conversation { padding: 4px; } #cpea-composer { padding-bottom: env(safe-area-inset-bottom, 8px); } }''')
