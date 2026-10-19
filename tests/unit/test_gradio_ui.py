from dataclasses import replace
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from cpea.interfaces.api.streaming import ERROR_MESSAGE
from cpea.interfaces.web.ui import SessionGate, query_updates
from tests.integration.test_streamed_query import make_runtime
from tests.support import QUESTION


def test_latest_question_and_precise_result_without_answering(tmp_path):
    calls = []
    runtime = make_runtime(tmp_path, lambda d, s: (calls.append(s) or (['中文'], [['<script>test</script>']])))
    gate = SessionGate()
    first = list(query_updates(runtime, QUESTION, gate))
    assert len(first) == 3
    assert first[0][1].value == '' and first[0][2].value['data'] == []
    assert gate.sql == calls[0]
    assert first[-1][1].value == calls[0] and first[-1][1].visible
    assert first[-1][2].value['data'] == [['<script>test</script>']]
    assert first[-1][3].interactive and first[-1][4].interactive
    assert runtime.llm.calls == 1 and len(calls) == 1
    second = list(query_updates(runtime, QUESTION + '。', gate))
    assert second[0][0][0]['content'] == QUESTION + '。'
    assert second[0][1].value == '' and second[0][2].value['data'] == []
    assert len(calls) == 2 and runtime.llm.calls == 2


@pytest.mark.parametrize('kind', ['zero', 'limit', 'truncated', 'db_error', 'encoding_error', 'generation_error', 'preflight'])
def test_ui_result_and_fixed_errors(tmp_path, monkeypatch, kind):
    def executor(d, s):
        if kind == 'db_error':
            raise RuntimeError('PWD=secret')
        return ['value'], [] if kind == 'zero' else [[object()]] if kind == 'encoding_error' else [[1], [2], [3]] if kind == 'truncated' else [[1], [2]]
    runtime = make_runtime(tmp_path, executor if kind != 'preflight' else None)
    if kind == 'generation_error':
        def fail():
            raise RuntimeError('PWD=secret')
        monkeypatch.setattr(runtime, 'staged_query_service', fail)
    updates = list(query_updates(runtime, QUESTION, SessionGate()))
    status = updates[-1][0][1]['content']
    if 'error' in kind or kind == 'preflight':
        assert status == ERROR_MESSAGE
        assert updates[-1][2].visible is False
        assert updates[-1][1].visible is (kind in ('db_error', 'encoding_error'))
    elif kind == 'zero':
        assert status == '查無資料' and updates[-1][2].visible is False
    elif kind == 'limit':
        assert '已達查詢上限 2 列' in status and '裁切' not in status
    else:
        assert '結果已裁切' in status
    assert updates[-1][3].interactive and updates[-1][4].interactive


def test_session_gate_rejects_duplicate_and_isolates_sessions(tmp_path):
    started = Event()
    release = Event()
    calls = []
    def executor(d, s):
        calls.append(s)
        started.set()
        assert release.wait(5)
        return ['v'], [[1]]
    runtime = make_runtime(tmp_path, executor)
    gate = SessionGate()
    updates = []
    thread = Thread(target=lambda: updates.extend(query_updates(runtime, QUESTION, gate)))
    thread.start()
    try:
        assert started.wait(5)
        duplicate = list(query_updates(runtime, QUESTION, gate))
        assert duplicate == [tuple({'__type__': 'update'} for i in range(7))]
        assert len(calls) == 1
        import copy
        other = copy.deepcopy(gate)
        assert other.lock is not gate.lock and other.lock.acquire(blocking=False)
        other.lock.release()
    finally:
        release.set()
        thread.join(5)
    assert len(updates) == 3 and gate.lock.acquire(blocking=False)
    gate.lock.release()


def test_blank_does_not_replace_current_result_or_call_backend(tmp_path):
    runtime = make_runtime(tmp_path)
    assert list(query_updates(runtime, ' \n ', SessionGate())) == [tuple({'__type__': 'update'} for i in range(7))]
    assert runtime.llm.calls == 0


def test_question_html_is_escaped_even_with_markdown_disabled(tmp_path):
    runtime = make_runtime(tmp_path, lambda d, s: ([], []))
    question = '<img src=x onerror="alert(1)"> & <script>alert(1)</script>'
    update = next(query_updates(runtime, question, SessionGate()))
    assert '<img' not in update[0][0]['content']
    assert '&lt;img' in update[0][0]['content'] and '&amp;' in update[0][0]['content']
