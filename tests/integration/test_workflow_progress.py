from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import json
import yaml

from cpea.application.models.progress import WorkflowStep
from cpea.application.models.query import SQLGenerationResponse
from cpea.bootstrap import AssistantRuntime
from cpea.interfaces.web.ui import SessionGate, single_question_updates
from tests.hilp_support import QUESTION, VIEW, runtime_for, selection
from tests.support import dependencies, view_contract, StubLLM, Catalog, QUESTION as INVENTORY_QUESTION


def test_progress_reaches_dialog_while_model_is_still_blocked(tmp_path):
    runtime = runtime_for(tmp_path, executor=lambda d, s: (['value'], [[1]]))
    started, release, completed = Event(), Event(), Event()
    original = runtime.llm.invoke

    def invoke(messages):
        started.set()
        assert release.wait(10)
        value = original(messages)
        value.additional_kwargs = {'reasoning_content': 'private-model-reasoning'}
        completed.set()
        return value

    runtime.llm.invoke = invoke
    gate = SessionGate('retail')
    updates = single_question_updates(runtime, QUESTION, gate)
    try:
        while True:
            frame = next(updates)
            content = frame.messages[-1]['content']
            if '正在比對問題與資料內容。' in content:
                break
        assert started.wait(5) and not completed.is_set()
        assert frame.state == 'generating' and VIEW not in content
        assert '正在尋找相關資料。' in content
        release.set()
        remaining = list(updates)
        assert remaining[-1].state == 'waiting_confirmation'
        assert '有詞彙需要你確認。' in remaining[-1].messages[-1]['content']
        assert 'private-model-reasoning' not in str(remaining)
        from types import SimpleNamespace
        payload = selection(SimpleNamespace(clarification=gate.pending))
        resumed = list(single_question_updates(runtime, '', gate, payload=payload))
        final = resumed[-1]
        assert final.state == 'completed' and runtime.llm.calls == 1
        for step in ['已收到你的選擇。', '正在準備查詢。', '正在檢查查詢條件。', '正在核對詞彙對應。',
                     '正在查詢資料。', '已取得查詢結果。']:
            assert step in final.messages[-1]['content']
        assert final.messages[-1]['content'].count('正在尋找相關資料。') == 1
        assert VIEW not in final.messages[-1]['content'] and VIEW in final.sql
    finally:
        release.set()
        updates.close()
        runtime.close()


def test_concurrent_progress_is_isolated_in_shared_runtime(tmp_path):
    barrier = Barrier(2)
    views = ['alpha.v_inventory', 'beta.v_inventory']
    settings, _, packer, _, _ = dependencies(tmp_path, view=views[0])
    (tmp_path / 'beta.yaml').write_text(yaml.safe_dump(view_contract(views[1]), allow_unicode=True), encoding='utf-8')
    (tmp_path / 'catalog.yaml').write_text(yaml.safe_dump({'views': {
        views[0]: {'path': 'inventory.yaml'}, views[1]: {'path': 'beta.yaml'}}}), encoding='utf-8')
    catalog = Catalog(tmp_path)

    class Model:
        def invoke(self, messages):
            context = json.loads(messages[-1].content.split('table定義: ', 1)[1])
            view = context['candidates'][0]['view']
            barrier.wait(timeout=10)
            return StubLLM(view).invoke(messages)

    runtime = AssistantRuntime(settings, catalog=catalog, llm=Model(), context_packer=packer)
    service = runtime.generation_service()

    def generate(view):
        question = INVENTORY_QUESTION.replace('請查詢', f'請從 {view} 查詢')
        return list(service.generate_updates(question))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(generate, views))
        for index, updates in enumerate(results):
            # Retrieval may legitimately return both Views; admission and
            # mapping events must stay bound to the requesting invocation.
            scoped_steps = {'context budget candidate views', 'match candidate view', 'selected columns', 'generation result'}
            progress = '\n'.join(item.format() for item in updates
                if isinstance(item, WorkflowStep) and item.step in scoped_steps)
            own, other = ('alpha.v_inventory', 'beta.v_inventory')[index], ('alpha.v_inventory', 'beta.v_inventory')[1-index]
            assert own in progress and other not in progress
            assert isinstance(updates[-1], SQLGenerationResponse) and updates[-1].status == 'ready'
            assert updates[-1].selected_views == [own]
    finally:
        runtime.close()


def test_closing_progress_stream_cleans_unfinished_checkpoint(tmp_path):
    runtime = runtime_for(tmp_path)
    workflow = runtime.generation_service().workflow
    try:
        updates = workflow.generate_updates(QUESTION, mode='web')
        assert isinstance(next(updates), WorkflowStep)
        updates.close()
        assert not workflow.registry.runs
        assert not workflow.checkpointer.storage
    finally:
        runtime.close()
