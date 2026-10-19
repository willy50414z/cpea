"""SSE framing and explicit result encoding for the independent query API."""
import base64
from datetime import date, datetime, time
from decimal import Decimal
import json
import logging
from uuid import UUID

from starlette.concurrency import run_in_threadpool

ERROR_MESSAGE = '執行錯誤請再試一次'
STREAM_PATH = '/api/assistant/query/stream'
logger = logging.getLogger(__name__)


def _encode_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return 'base64:' + base64.b64encode(value).decode('ascii')
    raise TypeError('Unsupported SQL result type')


def event_frame(event: str, payload: dict) -> str:
    # Build the entire frame before yielding, including type/finite-number checks.
    body = json.dumps(payload, default=_encode_value, ensure_ascii=False, allow_nan=False)
    return f'event: {event}\ndata: {body}\n\n'


async def query_events(runtime, request, question: str, clarification_choice=None, *, confirmation=None, claimed=None):
    phase = 'generation'
    sql_stage = None
    resumed = False
    try:
        if await request.is_disconnected():
            return
        def generate():
            service = runtime.staged_query_service()
            return service, service.generate(question, clarification_choice)
        if confirmation is not None:
            from cpea.application.services.staged_query import SQLStage
            resumed = True
            question, generation = await run_in_threadpool(runtime.resume_generation,
                confirmation, mode='stream', claimed=claimed)
            service, sql_stage = runtime.staged_query_service(), SQLStage(generation)
        else:
            service, sql_stage = await run_in_threadpool(generate)
        if await request.is_disconnected():
            return
        generation = sql_stage.generation
        if generation.status == 'needs_clarification':
            yield event_frame('clarification', generation.clarification.model_dump(mode='json'))
            return
        if generation.status == 'needs_confirmation':
            yield event_frame('clarification', generation.model_dump(exclude={'query_trace'}))
            return
        if generation.status != 'ready':
            yield event_frame('cancelled' if generation.status == 'cancelled' else 'unsupported',
                              generation.model_dump(exclude={'query_trace'}))
            return
        yield event_frame('sql', {'sql': sql_stage.sql,
            'term_mapping_reasoning': [r.model_dump() for r in generation.term_mapping_reasoning]})
        # StreamingResponse awaits ASGI send before resuming this iterator.
        if await request.is_disconnected():
            return
        phase = 'execution'
        result = await run_in_threadpool(service.execute, question, sql_stage)
        if await request.is_disconnected():
            return
        phase = 'encoding'
        execution = result.execution
        frame = await run_in_threadpool(event_frame, 'result', {
            'columns': execution.columns, 'rows': execution.rows,
            'rows_truncated': execution.rows_truncated, 'row_limit': result.row_limit,
        })
        if await request.is_disconnected():
            return
        yield frame
    except Exception:
        # Only the stage is logged: no raw exception, question, SQL or rows.
        logger.warning('Independent query failed at stage=%s', phase)
        if not await request.is_disconnected():
            yield event_frame('error', {'message': ERROR_MESSAGE})

    finally:
        if sql_stage is not None and sql_stage.generation.status != 'needs_confirmation':
            runtime.finish(sql_stage.generation)
        if claimed is not None and not resumed:
            runtime.generation_service().workflow.registry.finish(claimed.id)
            claimed.lock.release()
