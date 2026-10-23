"""Real subprocess lifecycle tests; these do not claim native pipeline semantics."""
import json
from pathlib import Path
import sys
import pytest

WORKER = r'''
import json, os, sys, time
print(json.dumps({'protocol_version':1,'type':'handshake','upstream_sha':'fixture','import_sources':{'fixture':__file__}}),flush=True)
for line in sys.stdin:
 p=json.loads(line)
 if p['type']=='shutdown': break
 if p['type']!='plan': continue
 base={k:p[k] for k in ('protocol_version','request_id','run_id','case_id')}
 def emit(t,**kw): print(json.dumps({**base,'type':t,**kw}),flush=True)
 emit('accepted');emit('running')
 mode=p['request']
 if mode=='stderr':
  for _ in range(400): os.write(2,b'x'*8192)
 if mode=='bad': print('not-json',flush=True);continue
 if mode=='huge': print('x'*10000,flush=True);continue
 if mode=='crash': os._exit(3)
 if mode=='timeout': time.sleep(3)
 if mode=='late':
  emit('result',draft={'status':'unsupported'},context_tokens=1,token_counter='fixture',artifacts={})
  emit('result',draft={'status':'ready'},context_tokens=1,token_counter='fixture',artifacts={})
  continue
 emit('result',draft={'status':'unsupported'},context_tokens=1,token_counter='fixture',artifacts={})
'''


def client_at(tmp_path,**kw):
    from cpea.workflows.task_decomposition.wrenai_client import WrenAIWorkerClient
    script=tmp_path/'worker.py';script.write_text(WORKER,encoding='utf-8')
    return WrenAIWorkerClient([sys.executable,str(script)],expected_metadata={'upstream_sha':'fixture'},
        expected_import_root=tmp_path,artifact_root=tmp_path/'private',timeout=0.4,cancel_grace=0.05,
        terminate_grace=0.05,**kw)


def test_real_subprocess_drains_large_stderr_and_sequential_runs(tmp_path):
    with client_at(tmp_path) as client:
        a=client.plan(request='stderr',run_id='r1',case_id='c1')
        b=client.plan(request='normal',run_id='r2',case_id='c2')
        assert a['draft']['status']==b['draft']['status']=='unsupported'
        assert client.runs['r1']['states']==['accepted','running','result']
        assert sum(p.stat().st_size for p in (tmp_path/'private').glob('*.stderr'))>3_000_000
        assert client.process.poll() is None
    assert client.process.poll() is not None


@pytest.mark.parametrize('mode,code',[('bad','invalid_protocol'),('huge','protocol_limit_exceeded'),('crash','worker_crash'),('timeout','worker_timeout')])
def test_failures_reap_then_accept_second_request(tmp_path,mode,code):
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    with client_at(tmp_path,max_line_bytes=4096) as client:
        with pytest.raises(WorkerError) as exc: client.plan(request=mode,run_id='first',case_id='case')
        assert exc.value.code==code
        old=client.process
        assert old.poll() is not None
        assert client.runs['first']['terminal'] in ('error','unknown_outcome')
        assert client.plan(request='normal',run_id='second',case_id='case')['draft']['status']=='unsupported'
        assert client.process is not old


def test_duplicate_terminal_fails_closed_before_reusing_worker(tmp_path):
    import time
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    with client_at(tmp_path) as client:
        assert client.plan(request='late',run_id='old',case_id='c')['draft']['status']=='unsupported'
        old=client.process
        time.sleep(.05)  # A completed run must not hide an already queued duplicate terminal.
        with pytest.raises(WorkerError) as exc:
            client.plan(request='normal',run_id='rejected',case_id='c')
        assert exc.value.code=='duplicate_terminal'
        assert old.poll() is not None
        assert client.runs['old']['states']==['accepted','running','result']
        assert client.runs['rejected']['terminal']=='error'
        assert client.plan(request='normal',run_id='new',case_id='c')['draft']['status']=='unsupported'
        assert client.process.pid != old.pid
        events=''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'private').glob('*.jsonl'))
        assert '"run_id": "old"' in events and 'duplicate_terminal' in events


def test_late_nonterminal_is_archived_under_original_run(tmp_path):
    with client_at(tmp_path) as client:
        script=tmp_path/'worker.py'
        script.write_text(WORKER.replace("emit('result',draft={'status':'ready'},context_tokens=1,token_counter='fixture',artifacts={})",
                                         "emit('running')"),encoding='utf-8')
        assert client.plan(request='late',run_id='old',case_id='c')['draft']['status']=='unsupported'
        old=client.process
        assert client.plan(request='normal',run_id='new',case_id='c')['draft']['status']=='unsupported'
        assert client.process is old
        assert client.runs['old']['states']==['accepted','running','result']
        events=[json.loads(line) for p in (tmp_path/'private').glob('*.jsonl') for line in p.read_text(encoding='utf-8').splitlines()]
        assert sum(row.get('run_id')=='old' and row.get('type')=='running' for row in events)==2


def test_explicit_cancel_waits_for_ack_and_reaps(tmp_path):
    import threading
    import time
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    with client_at(tmp_path) as client:
        script=tmp_path/'worker.py'
        text=script.read_text(encoding='utf-8').replace("if mode=='timeout': time.sleep(3)",
            "if mode=='timeout': time.sleep(3)\n if mode=='cancel':\n  json.loads(sys.stdin.readline());emit('cancelled');continue")
        script.write_text(text,encoding='utf-8')
        errors=[]
        def run():
            try: client.plan(request='cancel',run_id='cancelled',case_id='c')
            except WorkerError as exc: errors.append(exc.code)
        thread=threading.Thread(target=run);thread.start()
        deadline=time.monotonic()+2
        while client.runs.get('cancelled',{}).get('states')!=['accepted','running']:
            assert time.monotonic()<deadline
            time.sleep(.005)
        assert client.cancel('cancelled')
        thread.join(timeout=2)
        assert not thread.is_alive() and errors==['worker_cancelled']
        assert client.runs['cancelled']['states']==['accepted','running','cancel_requested','cancelled']
        assert client.process.poll() is not None


def test_stdin_backpressure_obeys_timeout_and_private_files(tmp_path):
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    script=tmp_path/'blocked.py'
    script.write_text("import json,time\nprint(json.dumps({'protocol_version':1,'type':'handshake','upstream_sha':'fixture','import_sources':{'fixture':__file__}}),flush=True)\ntime.sleep(10)\n",encoding='utf-8')
    client=client_at(tmp_path)
    client.command=[sys.executable,str(script)]
    with client:
        with pytest.raises(WorkerError) as exc: client.plan(request='x'*500_000,run_id='blocked')
        assert exc.value.code=='worker_timeout'
        assert client.process.poll() is not None
    assert (tmp_path/'private').stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in (tmp_path/'private').iterdir())


def test_wrong_ids_never_cross_run_boundary(tmp_path):
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    client=client_at(tmp_path)
    script=tmp_path/'worker.py'
    script.write_text(WORKER.replace("'run_id','case_id')}","'run_id','case_id')}\n base['request_id']='wrong'"),encoding='utf-8')
    with client:
        with pytest.raises(WorkerError) as exc: client.plan(request='normal',run_id='ids')
        assert exc.value.code=='event_id_mismatch'
        assert client.runs['ids']['terminal']=='error'


def test_bounded_event_queue_rejects_flood_and_reaps(tmp_path):
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    client=client_at(tmp_path,max_queue=1)
    import time
    send=client._send
    def delayed_consumer(payload,deadline,**kwargs):
        send(payload,deadline,**kwargs)
        time.sleep(.05)
    client._send=delayed_consumer
    script=tmp_path/'worker.py'
    script.write_text(WORKER.replace("emit('accepted');emit('running')", "\n for _ in range(10000): emit('accepted')"),encoding='utf-8')
    with client:
        with pytest.raises(WorkerError) as exc: client.plan(request='normal',run_id='flood')
        assert exc.value.code=='protocol_limit_exceeded'
        assert client.process.poll() is not None


def test_lifecycle_artifact_records_limits_and_exact_terminal_once(tmp_path):
    with client_at(tmp_path) as client:
        client.plan(request='normal',run_id='record',case_id='case')
    rows=[json.loads(line) for p in (tmp_path/'private').glob('*.lifecycle.jsonl') for line in p.read_text(encoding='utf-8').splitlines()]
    assert rows[0]['limits']['timeout']==0.4
    states=[row['state'] for row in rows if row.get('run_id')=='record']
    assert states==['accepted','running','result']


@pytest.mark.parametrize('worker_code,expected',[('rate_limit','rate_limit'),('context_budget_exceeded','context_budget_exceeded'),('secret-token-value','worker_error')])
def test_native_error_codes_are_allowlisted_and_message_sanitized(tmp_path,worker_code,expected):
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    client=client_at(tmp_path)
    script=tmp_path/'worker.py'
    script.write_text(WORKER.replace("mode=p['request']", "emit('error',code="+repr(worker_code)+",message='secret credentials');continue\n mode=p['request']"),encoding='utf-8')
    with client:
        with pytest.raises(WorkerError) as exc: client.plan(request='normal',run_id='error')
        assert exc.value.code==expected
        assert 'credentials' not in str(exc.value) and 'secret' not in str(exc.value)
        assert client.runs['error']['states']==['accepted','running','error']


def test_external_cancel_interrupts_backpressured_send_with_default_timeout(tmp_path):
    import threading
    import time
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    client=client_at(tmp_path)
    client.timeout=120
    script=tmp_path/'worker.py'
    script.write_text("import json,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nprint(json.dumps({'protocol_version':1,'type':'handshake','upstream_sha':'fixture','import_sources':{'fixture':__file__}}),flush=True)\ntime.sleep(20)\n",encoding='utf-8')
    errors=[]
    def run():
        try: client.plan(request='normal',run_id='blocked',schema={'padding':'x'*500_000})
        except WorkerError as exc: errors.append(exc.code)
    thread=threading.Thread(target=run)
    with client:
        thread.start()
        try:
            deadline=time.monotonic()+1
            while len(client._threads)<3 or not client._threads[-1].is_alive():
                assert time.monotonic()<deadline
                time.sleep(.005)
            started=time.monotonic()
            assert client.cancel('blocked')
            thread.join(timeout=.5)
            still_running=thread.is_alive()
            elapsed=time.monotonic()-started
        finally:
            if thread.is_alive():
                client.process.kill()  # Bound cleanup of the intentionally failing RED case.
                thread.join(timeout=2)
        assert not still_running and elapsed<.5
        assert errors==['worker_cancelled']
        assert client.runs['blocked']['states']==['cancel_requested','unknown_outcome']
        assert client.process.poll() is not None
        assert not any(t.is_alive() for t in client._threads)
