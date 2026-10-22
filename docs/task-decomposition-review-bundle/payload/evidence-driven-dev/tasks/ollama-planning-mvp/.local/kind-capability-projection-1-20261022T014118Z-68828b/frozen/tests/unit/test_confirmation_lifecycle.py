from threading import Event, Thread
import pytest
from cpea.application.models.confirmation import ConfirmationError, ConfirmationRequest
from tests.hilp_support import QUESTION, runtime_for, selection


def test_expiry_capacity_and_cleanup_of_all_versions(tmp_path):
    runtime = runtime_for(tmp_path)
    workflow = runtime.generation_service().workflow
    now = [1000.0]
    workflow.registry.clock = lambda: now[0]
    workflow.registry.capacity = 1
    pending = runtime.generate(QUESTION)
    with pytest.raises(ConfirmationError) as error:
        runtime.generate(QUESTION)
    assert error.value.status_code == 503
    now[0] += 901
    workflow.registry.sweep()
    with pytest.raises(ConfirmationError) as error:
        runtime.confirm(selection(pending))
    assert error.value.status_code == 410
    assert not workflow.registry.runs and not workflow.checkpointer.storage and not workflow.checkpointer.writes
    runtime.close()


def test_resolving_is_not_reaped_or_executed_twice(tmp_path):
    started, release = Event(), Event()
    calls = []
    def executor(d, s):
        calls.append(s)
        started.set()
        assert release.wait(5)
        return ['value'], [[1]]
    runtime = runtime_for(tmp_path, executor=executor)
    pending = runtime.execute(QUESTION)
    payload = selection(pending)
    output = []
    thread = Thread(target=lambda: output.append(runtime.confirm(payload, mode='execute')))
    thread.start()
    try:
        assert started.wait(5)
        workflow = runtime.generation_service().workflow
        workflow.registry.clock = lambda: 10**12
        workflow.registry.sweep()
        assert len(workflow.registry.runs) == 1
        with pytest.raises(ConfirmationError) as error:
            runtime.confirm(payload, mode='execute')
        assert error.value.status_code == 409
        with pytest.raises(ConfirmationError) as error:
            runtime.confirm(ConfirmationRequest(confirmation_id=payload.confirmation_id, action='cancel'), mode='execute')
        assert error.value.status_code == 409
    finally:
        release.set()
        thread.join(5)
    assert len(calls) == len(output) == 1
    assert not workflow.registry.runs and not workflow.checkpointer.storage
    runtime.close()
