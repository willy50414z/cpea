"""Latest-question-only Gradio UI over the governed application services."""
import json
import logging
import re
from html import escape
from importlib.resources import files
from threading import Lock
from dataclasses import dataclass, field
from secrets import token_urlsafe
from traceback import walk_tb
from contextlib import closing

from cpea.application.models.confirmation import ConfirmationRequest, ConfirmationError
from cpea.application.models.progress import WorkflowStep
from cpea.application.services.staged_query import SQLStage
from cpea.workflows.text_to_sql.clarification import business_label

import gradio as gr

from cpea.application.errors import DependencyUnavailable
from cpea.config.database import SQLServerConfigurationError
from cpea.interfaces.api.schemas import StreamQueryRequest
from cpea.interfaces.api.streaming import ERROR_MESSAGE, _encode_value
from cpea.application.models.query import ClarificationChoice, ClarificationRequest

logger = logging.getLogger(__name__)

EDITABLE_STATES = ('idle', 'completed', 'cancelled', 'error', 'expired', 'editing')
PROJECT_LABELS = {'gms2': 'GMS2 業務資料', 'retail': '零售示範資料'}

# Never forward workflow info to the browser; it can contain schema details.
PROGRESS_MESSAGES = {
    'initialize services': '正在準備查詢。',
    'execution mode': '目前僅能產生查詢，尚未連接資料庫。',
    'vector search': '正在尋找相關資料。',
    'lexical search': '正在尋找相關資料。',
    'match candidate view': '正在比對問題與資料內容。',
    'repair candidate mapping': '正在重新核對查詢條件。',
    'check field semantics': '正在確認詞彙含義。',
    'resolve semantic choices': '正在整理需要確認的詞彙選項。',
    'reject semantic source': '正在核對其他相關資料。',
    'reuse terms mapping': '已套用先前確認的詞彙含義。',
    'HILP required': '有詞彙需要你確認。',
    'HILP confirmation': '已收到你的選擇。',
    'compile SQL': '正在準備查詢。',
    'validate SQL': '正在檢查查詢條件。',
    'persist terms mapping': '正在核對詞彙對應。',
    'execute SQL': '正在查詢資料。',
    'skip execution': '尚未連接資料庫，未執行查詢。',
    'query result': '已取得查詢結果。',
    'workflow error': '查詢未完成。',
}


def business_progress(steps):
    messages = []
    for step in steps:
        if step.step == 'select project':
            label = PROJECT_LABELS.get(step.info) if isinstance(step.info, str) else None
            message = f'本題資料集：{label}。' if label else None
        else:
            message = PROGRESS_MESSAGES.get(step.step)
        if message and (not messages or messages[-1] != message):
            messages.append(message)
    return messages


def business_headers(generation, columns, catalog):
    """Describe result columns without sending database identifiers to users."""
    view = generation.selected_views[0] if generation.selected_views else None
    aggregate_labels = {'sum': '合計', 'avg': '平均', 'min': '單筆最小值',
                        'max': '單筆最大值', 'count': '筆數', 'count_distinct': '不重複筆數'}
    headers = []
    for index, column in enumerate(columns, 1):
        label = None
        if view and column in catalog.columns(view):
            spec = catalog.field_contract(view, column)
            description = re.split(r'[。；;\n]', spec.get('description', ''))[0]
            label = business_label(description, catalog)
            if label and generation.query_plan:
                aggregation = generation.query_plan.aggregations.get(column)
                if aggregation:
                    label += '（' + aggregate_labels[aggregation] + '）'
        elif re.search(r'[\u3400-\u9fff]', column):
            label = business_label(column, catalog)
        headers.append(label or f'結果 {index}')
    return headers


def _failure_details(exc):
    """Keep stack locations and exception causes without source or local data."""
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    code = DependencyUnavailable.code if isinstance(exc, DependencyUnavailable) else 'unclassified'
    lines = ['Traceback (exception messages, source lines and locals omitted):']
    packages = {'langchain_openai': 'langchain-openai', 'langchain_google_genai': 'langchain-google-genai'}
    for index, error in enumerate(reversed(chain)):
        if index:
            lines.append('The preceding exception led to:')
        for frame, lineno in walk_tb(error.__traceback__):
            lines.append(f'  File {json.dumps(frame.f_code.co_filename)}, line {lineno}, in {frame.f_code.co_name}')
        lines.append(type(error).__name__)
        if isinstance(error, SQLServerConfigurationError):
            code = error.code
            lines.append(str(error))
        if isinstance(error, ModuleNotFoundError) and error.name:
            package = packages.get(error.name.split('.')[0])
            if package:
                code = 'llm_dependency_missing'
                lines.append(f'Missing optional package: {package}')
    return code, '\n'.join(lines)


class SessionGate:
    """A separate nonblocking submission lock for each transient UI session."""
    def __init__(self, project_id=None):
        self.lock = Lock()
        self.project_id = project_id
        self.owner = token_urlsafe(32)
        self.version = 0
        self.state = 'idle'
        self.question = ''
        self.pending = None
        self.sql = ''
        self.reasoning = []
        self.summary = []
        self.steps = []
        self.execution_enabled = True

    def __deepcopy__(self, memo):
        return SessionGate(self.project_id)


def query_updates(runtime, question: str, gate: SessionGate, pending=None, choice=None):
    """Compatibility adapter for consumers of the original seven UI outputs."""
    if pending and not choice:
        yield (gr.skip(),) * 7
        return
    payload = None
    if pending:
        gate.pending = ClarificationRequest.model_validate(pending)
        gate.question, gate.state = gate.pending.original_request, 'waiting_confirmation'
        payload = ClarificationChoice(option_id=choice, contract_fingerprint=gate.pending.contract_fingerprint)
    emitted = False
    for frame in single_question_updates(runtime, question, gate, payload=payload, stream_progress=False):
        emitted = True
        idle = frame.state in EDITABLE_STATES
        view_pending = frame.pending if frame.pending and 'options' in frame.pending else None
        options = [(f"{item['label']}：{item['description']}", item['id'])
                   for item in view_pending['options']] if view_pending else []
        yield (frame.messages, gr.Code(value=frame.sql, visible=bool(frame.sql)),
            gr.Dataframe(value=frame.rows, visible=bool(frame.rows['data'])),
            gr.Textbox(value=frame.draft, interactive=idle), gr.Button(interactive=idle or bool(view_pending)),
            frame.pending, gr.Radio(choices=options, value=None, visible=bool(view_pending)))
    if not emitted:
        yield (gr.skip(),) * 7


@dataclass
class QuestionFrame:
    state: str
    messages: list = field(default_factory=list)
    sql: str = ''
    rows: dict = field(default_factory=lambda: {'headers': [], 'data': []})
    reasoning: str = ''
    pending: dict | None = None
    draft: str = ''


def _frame(gate, message, rows=None):
    reasoning = '\n'.join(gate.summary)
    content = '\n'.join([*business_progress(gate.steps), *gate.summary, *([message] if message else [])])
    return QuestionFrame(gate.state, [{'role': 'user', 'content': escape(gate.question)},
        {'role': 'assistant', 'content': escape(content)}], gate.sql,
        rows or {'headers': [], 'data': []}, reasoning,
        (gate.pending.model_dump(mode='json') if isinstance(gate.pending, ClarificationRequest)
         else gate.pending.public_payload()) if gate.pending and gate.state == 'waiting_confirmation' else None,
        gate.question if gate.state == 'editing' else '')


def single_question_updates(runtime, question, gate, *, payload=None, project_id=None, runtime_provider=None,
                            stream_progress=True):
    if not gate.lock.acquire(blocking=False):
        return
    version = gate.version
    generation = None
    phase = 'validate_request'
    try:
        if payload is None or isinstance(payload, ClarificationChoice):
            view_choice = payload if isinstance(payload, ClarificationChoice) else None
            if view_choice:
                if gate.state != 'waiting_confirmation' or not isinstance(gate.pending, ClarificationRequest):
                    return
                question = gate.question
            elif gate.state not in EDITABLE_STATES or not question.strip():
                return
            question = StreamQueryRequest(request=question).request
            if project_id is not None:
                gate.project_id = project_id
            gate.version += 1
            version = gate.version
            gate.question, gate.sql, gate.reasoning, gate.summary, gate.pending = question, '', [], [], None
            gate.steps = []
            if stream_progress:
                if gate.project_id:
                    gate.steps.append(WorkflowStep('select project', gate.project_id))
                gate.steps.append(WorkflowStep('initialize services', '開始'))
            gate.state = 'generating'
            yield _frame(gate, '分析欄位中…')
            if runtime_provider is not None:
                phase = 'load_project'
                runtime = runtime_provider()
            phase = 'execution_preflight'
            if view_choice is None:
                gate.execution_enabled = True
            try:
                if gate.execution_enabled:
                    runtime.require_execution()
            except DependencyUnavailable:
                if not stream_progress:
                    raise
                gate.execution_enabled = False
                gate.steps.append(WorkflowStep('execution mode', '僅產生 SQL：尚未設定資料庫連線'))
                yield _frame(gate, '')
            phase = 'initialize_services'
            service = runtime.staged_query_service() if gate.execution_enabled else runtime.generation_service()
            phase = 'generate_sql'
            choice_kwargs = {'clarification_choice': view_choice} if view_choice else {}
            if stream_progress:
                with closing(service.generate_updates(question, mode='web', owner=gate.owner, **choice_kwargs)) as updates:
                    for update in updates:
                        if isinstance(update, WorkflowStep):
                            if gate.version != version:
                                return
                            gate.steps.append(update)
                            yield _frame(gate, '')
                        else:
                            stage = update if isinstance(update, SQLStage) else SQLStage(update)
                            generation = stage.generation
            else:
                stage = service.generate(question, mode='web', owner=gate.owner, **choice_kwargs)
        else:
            if gate.state != 'waiting_confirmation' or gate.pending.confirmation_id != payload.confirmation_id:
                return
            gate.state = 'resuming'
            yield _frame(gate, '正在處理確認…')
            if runtime_provider is not None:
                phase = 'load_project'
                runtime = runtime_provider()
            previous = gate.pending
            phase = 'resume_confirmation'
            if stream_progress:
                with closing(runtime.resume_generation_updates(payload, mode='web', owner=gate.owner)) as updates:
                    for update in updates:
                        if isinstance(update, WorkflowStep):
                            if gate.version != version:
                                return
                            gate.steps.append(update)
                            yield _frame(gate, '')
                        else:
                            question, generation = update
            else:
                question, generation = runtime.resume_generation(payload, mode='web', owner=gate.owner)
            if gate.version != version:
                return
            if payload.action == 'confirm':
                chosen = {d.item_id: d.option_id for d in payload.decisions}
                gate.summary += [f'本次確認：{item.term} → {next(o.description for o in item.options if o.id == chosen[item.id])}'
                                 for item in previous.items]
            stage = SQLStage(generation)
            phase = 'initialize_services'
            service = runtime.staged_query_service() if gate.execution_enabled else None
        generation = stage.generation
        if gate.version != version:
            return
        if generation.status in ('needs_confirmation', 'needs_clarification'):
            gate.state, gate.pending = 'waiting_confirmation', generation.clarification
            yield _frame(gate, generation.explanation)
            return
        gate.pending = None
        if generation.status != 'ready':
            if generation.code == 'clarification_rephrase':
                gate.state = 'editing'
                yield _frame(gate, generation.explanation)
            elif generation.code == 'clarification_generation_failed':
                gate.state = 'error'
                yield _frame(gate, '暫時無法整理確認選項，請稍後再試。')
            elif generation.status == 'unsupported' and gate.project_id in PROJECT_LABELS:
                gate.state = 'editing'
                label = PROJECT_LABELS[gate.project_id]
                yield _frame(gate, f'在「{label}」中找不到能完整回答本題的資料。請確認下方的 Project 選擇，再送出原題。')
            else:
                gate.state = 'cancelled' if generation.status == 'cancelled' else 'error'
                yield _frame(gate, '已取消本題。' if generation.status == 'cancelled'
                             else '目前資料無法完整回答這個問題，請調整條件或換個說法。')
            return
        gate.sql, gate.reasoning = generation.sql, generation.term_mapping_reasoning
        prefixes = {'automatically_resolved': '自動採用', 'reused_confirmation': '沿用確認',
                    'confirmed_this_request': '本次確認'}
        for reason in gate.reasoning:
            if reason.description:
                summary = f'{prefixes[reason.source]}：{reason.term} → {reason.description}'
                if not any(line.startswith(f'{prefixes[reason.source]}：{reason.term} → ') for line in gate.summary):
                    gate.summary.append(summary)
        if not gate.execution_enabled:
            gate.state = 'completed'
            gate.steps.append(WorkflowStep('skip execution', '尚未設定資料庫連線'))
            yield _frame(gate, '查詢已準備完成；目前尚未連接資料庫，本次未執行查詢。')
            return
        gate.state = 'executing'
        if stream_progress:
            gate.steps.append(WorkflowStep('execute SQL', '開始查詢'))
        yield _frame(gate, '正在查詢資料…')
        phase = 'execute_sql'
        result = service.execute(question, stage)
        if gate.version != version:
            return
        execution = result.execution
        phase = 'encode_results'
        rows = json.loads(json.dumps({'headers': business_headers(generation, execution.columns, runtime.catalog),
            'data': execution.rows},
            default=_encode_value, ensure_ascii=False, allow_nan=False))
        gate.state = 'completed'
        if stream_progress:
            gate.steps.append(WorkflowStep('query result', {'rows': len(execution.rows),
                'rows_truncated': execution.rows_truncated}))
        message = '查無資料' if not execution.rows else f'查詢完成，共 {len(execution.rows)} 列。'
        if execution.rows_truncated:
            message += f' 結果已裁切，最多顯示 {result.row_limit} 列。'
        elif len(execution.rows) >= result.row_limit:
            message += f' 已達查詢上限 {result.row_limit} 列，可能仍有其他資料。'
        yield _frame(gate, message, rows)
    except ConfirmationError as exc:
        if gate.version == version:
            gate.state = 'resuming' if exc.status_code == 409 else 'expired' if exc.status_code == 410 else 'waiting_confirmation'
            yield _frame(gate, '本題仍在處理中。' if exc.status_code == 409 else '確認已失效，請重新提供完整問題。' if exc.status_code == 410 else '請完成所有必要選擇。')
    except Exception as exc:
        error_code, diagnostic = _failure_details(exc)
        logger.error('Single question failed at state=%s project=%s phase=%s error_type=%s error_code=%s\n%s',
                     gate.state, gate.project_id or '-', phase, type(exc).__name__, error_code, diagnostic)
        if gate.version == version:
            gate.state, gate.pending = 'error', None
            if stream_progress:
                gate.steps.append(WorkflowStep('workflow error', {'phase': phase, 'code': error_code}))
            message = ('資料庫連線設定不符合 SQL Server 格式，請檢查本題 project 的連線設定。'
                       if error_code in {'sqlserver_' + reason for reason in SQLServerConfigurationError.messages}
                       else ERROR_MESSAGE)
            yield _frame(gate, message)
    finally:
        if generation is not None and generation.status != 'needs_confirmation':
            runtime.finish(generation)
        gate.lock.release()


def project_question_updates(projects, project_id, question, gate, *, payload=None):
    if payload is None:
        if gate.state not in EDITABLE_STATES:
            return
        if not isinstance(question, str) or not question.strip():
            return
        selected_project = project_id
    else:
        # A pending confirmation always resolves through its original project.
        selected_project = gate.project_id
    yield from single_question_updates(None, question, gate, payload=payload,
        project_id=project_id if payload is None else None,
        runtime_provider=lambda: projects.get(selected_project))


def reset_question(runtime, gate, *, abandon=False):
    if abandon:
        # The old server run keeps its own lock/lifecycle; never claim rollback.
        gate.version += 1
        return SessionGate(gate.project_id)
    if not gate.lock.acquire(blocking=False):
        raise ConfirmationError('confirmation_in_progress', 409)
    try:
        if gate.state == 'waiting_confirmation' and not isinstance(gate.pending, ClarificationRequest):
            runtime.resume_generation(ConfirmationRequest(confirmation_id=gate.pending.confirmation_id,
                action='cancel'), mode='web', owner=gate.owner)
        elif gate.state in ('generating', 'resuming', 'executing'):
            raise ConfirmationError('confirmation_in_progress', 409)
        gate.version += 1
        return SessionGate(gate.project_id)
    finally:
        gate.lock.release()


def create_ui(runtime, *, projects=None) -> gr.Blocks:
    with gr.Blocks(title='CPEA', analytics_enabled=False, fill_height=True) as ui:
        gate_state = gr.State(SessionGate('gms2' if projects is not None else None), time_to_live=3600)
        pending_state = gr.State(None, time_to_live=900)
        with gr.Column(elem_id='cpea-conversation'):
            with gr.Row():
                gr.Markdown('## CPEA\n一次處理一個完整問題；不保存歷史對話。')
                new = gr.Button('新問題', size='sm', elem_id='cpea-new')
            with gr.Column(elem_id='cpea-thread', scale=1, min_width=0):
                chat = gr.Chatbot(label='本題訊息', render_markdown=False, allow_tags=False,
                    sanitize_html=True, height=None, min_height=180, scale=1,
                    buttons=[], feedback_options=(), layout='bubble', elem_id='cpea-chat')
                with gr.Column(elem_id='cpea-assistant-confirmation'):
                    @gr.render(inputs=[pending_state])
                    def render_confirmation(pending):
                        if not pending:
                            return
                        clarification = pending
                        if 'options' in clarification:
                            gr.Textbox(value=clarification['question'], label='請確認查詢口徑', interactive=False)
                            view_choice = gr.Radio(label='查詢口徑', value=None, choices=[
                                (f"{o['label']}：{o['description']}", o['id']) for o in clarification['options']])
                            confirm_view = gr.Button('確認，繼續查詢', interactive=False, variant='primary')
                            view_choice.change(lambda value: gr.Button(interactive=value is not None),
                                view_choice, confirm_view, api_visibility='private', show_progress='hidden')
                            def resolve_view(value, gate):
                                if value is None:
                                    return
                                payload = ClarificationChoice(option_id=value,
                                    contract_fingerprint=clarification['contract_fingerprint'])
                                for frame in updates(gate.question, gate, payload=payload):
                                    yield outputs(frame)
                            confirm_view.click(resolve_view, [view_choice, gate_state], common_outputs,
                                concurrency_limit=None, api_visibility='private', show_progress='hidden', stream_every=0)
                            return
                        gr.Markdown('### 請確認詞彙的意思\n選擇符合原意的業務含義；確認後會記住這項選擇。')
                        radios = []
                        for item in clarification['items']:
                            gr.Textbox(value=item['reason'], label='需要確認的原因', interactive=False)
                            radios.append(gr.Radio(label=item['term'], value=None,
                                choices=[(o['description'], o['id']) for o in item['options']]))
                        confirm = gr.Button('確認並記住，繼續' if clarification['kind'] == 'field_mapping' else '確認更新，繼續查詢',
                            interactive=False, variant='primary', elem_classes=['cpea-confirm'])
                        cancel = gr.Button('取消本題', elem_classes=['cpea-cancel'])
                        def validate_choices(*values):
                            stop = any(value == option['id'] for value, item in zip(values, clarification['items'])
                                       for option in item['options'] if option['rephrase'])
                            return gr.Button(value='修改問題' if stop else '確認並記住，繼續' if clarification['kind'] == 'field_mapping' else '確認更新，繼續查詢',
                                             interactive=stop or all(value is not None for value in values))
                        for radio in radios:
                            radio.change(validate_choices, radios, confirm, api_visibility='private', show_progress='hidden')
                        def resolve(*values):
                            gate = values[-1]
                            choices = values[:-1]
                            stop = any(value == o['id'] for value, item in zip(choices, clarification['items'])
                                       for o in item['options'] if o['rephrase'])
                            if not stop and not all(choices):
                                return
                            payload = ConfirmationRequest(confirmation_id=clarification['confirmation_id'],
                                action='rephrase' if stop else 'confirm', decisions=None if stop else [
                                    {'item_id': item['id'], 'option_id': value} for item, value in zip(clarification['items'], choices)])
                            for frame in updates(gate.question, gate, payload=payload):
                                yield outputs(frame)
                        def cancel_question(gate):
                            payload = ConfirmationRequest(confirmation_id=clarification['confirmation_id'], action='cancel')
                            for frame in updates(gate.question, gate, payload=payload):
                                yield outputs(frame)
                        confirm.click(resolve, [*radios, gate_state], common_outputs, concurrency_limit=None,
                            api_visibility='private', show_progress='hidden', stream_every=0)
                        cancel.click(cancel_question, gate_state, common_outputs, concurrency_limit=None,
                            api_visibility='private', show_progress='hidden', stream_every=0)
                sql = gr.Code(label='SQL', language='sql', interactive=False, visible=False,
                              buttons=['copy'], wrap_lines=True, elem_id='cpea-sql')
                table = gr.Dataframe(label='查詢結果', type='array', datatype='str', interactive=False,
                                     visible=False, max_height=350, elem_id='cpea-results')
                status = gr.HTML('<div data-cpea-state="idle" role="status" aria-live="polite"></div>', elem_id='cpea-state')
                gr.HTML('<div id="cpea-transport" hidden role="alert" aria-live="assertive"><p class="error"></p></div>')
                abandon = gr.Button('放棄等待，開始新問題', elem_id='cpea-abandon')
            with gr.Column(elem_id='cpea-composer', scale=0, min_width=0):
                with gr.Row():
                    question = gr.Textbox(label='問題', placeholder='輸入完整問題，Enter 送出，Shift+Enter 換行',
                        lines=1, max_lines=5, scale=8, max_length=4000, elem_id='cpea-question')
                    submit = gr.Button('送出', variant='primary', scale=1, elem_id='cpea-submit')
                project = gr.Dropdown(label='Project', choices=['gms2', 'retail'],
                    value='gms2', allow_custom_value=False, filterable=False,
                    visible=projects is not None, elem_id='cpea-project')
        common_outputs = [chat, sql, table, question, submit, pending_state, status, new, project]
        def outputs(frame):
            idle = frame.state in EDITABLE_STATES
            return (frame.messages, gr.Code(value=frame.sql, visible=bool(frame.sql)),
                gr.Dataframe(value=frame.rows, visible=bool(frame.rows['data'])),
                gr.Textbox(value=frame.draft, interactive=idle), gr.Button(interactive=idle), frame.pending,
                f'<div data-cpea-state="{frame.state}" role="status" aria-live="polite"></div>',
                gr.Button(interactive=idle or frame.state == 'waiting_confirmation'),
                gr.Dropdown(interactive=idle))
        def updates(question, gate, *, project_id=None, payload=None):
            if projects is not None:
                yield from project_question_updates(projects, project_id, question, gate, payload=payload)
            else:
                yield from single_question_updates(runtime, question, gate, payload=payload)
        def respond(question, project_id, gate):
            for frame in updates(question, gate, project_id=project_id):
                yield outputs(frame)
        def clear(gate):
            try:
                selected_runtime = projects.get(gate.project_id) if projects is not None else runtime
                fresh = reset_question(selected_runtime, gate)
                return (*outputs(QuestionFrame('idle')), fresh)
            except ConfirmationError:
                return (*outputs(_frame(gate, '本題仍在處理中，暫時無法開始新題。')), gate)
        def detach(gate):
            fresh = reset_question(runtime, gate, abandon=True)
            return (*outputs(QuestionFrame('idle')), fresh)
        gr.on(triggers=[question.submit, submit.click], fn=respond, inputs=[question, project, gate_state],
            outputs=common_outputs, trigger_mode='once', concurrency_limit=None, api_visibility='private',
            show_progress='hidden', stream_every=0)
        new.click(clear, gate_state, [*common_outputs, gate_state], concurrency_limit=None, api_visibility='private')
        abandon.click(detach, gate_state, [*common_outputs, gate_state], concurrency_limit=None, api_visibility='private')
        ui.load(fn=None, js=files('cpea.interfaces.web').joinpath('input.js').read_text(encoding='utf-8'))
    ui.queue(api_open=False)
    return ui
