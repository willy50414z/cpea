"""Latest-question-only Gradio UI over the governed application services."""
import json
import logging
from html import escape
from importlib.resources import files
from threading import Lock

import gradio as gr

from cpea.interfaces.api.schemas import StreamQueryRequest
from cpea.interfaces.api.streaming import ERROR_MESSAGE, _encode_value

logger = logging.getLogger(__name__)


class SessionGate:
    """A separate nonblocking submission lock for each transient UI session."""
    def __init__(self):
        self.lock = Lock()

    def __deepcopy__(self, memo):
        return SessionGate()


def query_updates(runtime, question: str, gate: SessionGate):
    if not question.strip():
        yield (gr.skip(),) * 5
        return
    if not gate.lock.acquire(blocking=False):
        yield (gr.skip(),) * 5
        return
    sql = ''
    phase = 'validation'
    try:
        question = StreamQueryRequest(request=question).request
        yield ([{'role': 'user', 'content': escape(question)},
                {'role': 'assistant', 'content': '產生 SQL 中…'}],
               gr.Code(value='', visible=False), gr.Dataframe(value={'headers': [], 'data': []}, visible=False),
               gr.Textbox(value='', interactive=False), gr.Button(interactive=False))
        phase = 'preflight'
        runtime.require_execution()
        service = runtime.staged_query_service()
        phase = 'generation'
        stage = service.generate(question)
        sql = stage.sql
        yield ([{'role': 'user', 'content': escape(question)},
                {'role': 'assistant', 'content': 'SQL 已產生，查詢中…'}],
               gr.Code(value=sql, visible=True), gr.Dataframe(value={'headers': [], 'data': []}, visible=False),
               gr.Textbox(value='', interactive=False), gr.Button(interactive=False))
        phase = 'execution'
        result = service.execute(question, stage)
        phase = 'encoding'
        # Use the same precise SQL value representation as the SSE endpoint.
        execution = result.execution
        encoded = json.loads(json.dumps({'headers': execution.columns, 'data': execution.rows},
            default=_encode_value, ensure_ascii=False, allow_nan=False))
        status = '查無資料' if not execution.rows else f'查詢完成，共 {len(execution.rows)} 列。'
        if execution.rows_truncated:
            status += f' 結果已裁切，最多顯示 {result.row_limit} 列。'
        elif len(execution.rows) >= result.row_limit:
            status += f' 已達查詢上限 {result.row_limit} 列，可能仍有其他資料。'
        yield ([{'role': 'user', 'content': escape(question)}, {'role': 'assistant', 'content': status}],
               gr.Code(value=sql, visible=True), gr.Dataframe(value=encoded, visible=bool(execution.rows)),
               gr.Textbox(value='', interactive=True), gr.Button(interactive=True))
    except Exception:
        logger.warning('UI query failed at stage=%s', phase)
        yield ([{'role': 'user', 'content': escape(question)}, {'role': 'assistant', 'content': ERROR_MESSAGE}],
               gr.Code(value=sql, visible=bool(sql)),
               gr.Dataframe(value={'headers': [], 'data': []}, visible=False),
               gr.Textbox(interactive=True), gr.Button(interactive=True))
    finally:
        gate.lock.release()


def create_ui(runtime) -> gr.Blocks:
    with gr.Blocks(title='CPEA', analytics_enabled=False, fill_height=True) as ui:
        gate = gr.State(SessionGate(), time_to_live=3600)
        gr.Markdown('## CPEA\n\n範例問題：\n\n'
                    '- 請查詢品號 GN2300 目前各倉庫的庫存數量，依倉庫名稱排序\n'
                    '- 請列出目前庫存的品號、倉庫名稱與批號，按批號排序\n'
                    '- 請列出目前庫存的品號、倉庫名稱、批號、最近一個月的銷售量，按品號排序\n'
                    '- 列出所有銷退貨單號與業務員，依銷退貨日期排序')
        with gr.Row(elem_id='cpea-composer'):
            question = gr.Textbox(label='問題', placeholder='輸入問題，Enter 送出，Shift+Enter 換行',
                                  lines=1, max_lines=5, scale=8, max_length=4000, elem_id='cpea-question')
            submit = gr.Button('送出', variant='primary', scale=1, elem_id='cpea-submit')
        gr.HTML('<div id="cpea-transport" hidden role="status" aria-live="polite">'
                '<p class="question"></p><p class="error"></p></div>')
        chat = gr.Chatbot(label='最新問答', render_markdown=False, allow_tags=False,
                          sanitize_html=True, height=None, min_height=180, scale=1,
                          buttons=[], feedback_options=(), layout='bubble', elem_id='cpea-chat')
        sql = gr.Code(label='SQL', language='sql', interactive=False, visible=False,
                      buttons=['copy'], wrap_lines=True, elem_id='cpea-sql')
        table = gr.Dataframe(label='查詢結果', type='array', datatype='str',
                             interactive=False, visible=False, max_height=350, elem_id='cpea-results')

        def respond(question, gate):
            yield from query_updates(runtime, question, gate)

        gr.on(triggers=[question.submit, submit.click], fn=respond,
              inputs=[question, gate], outputs=[chat, sql, table, question, submit],
              trigger_mode='once', concurrency_limit=None, api_visibility='private',
              show_progress='hidden', stream_every=0)
        ui.load(fn=None, js=files('cpea.interfaces.web').joinpath('input.js').read_text(encoding='utf-8'))
    ui.queue(api_open=False)
    return ui
