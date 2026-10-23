import asyncio
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ['LANGFUSE_ENABLED']='false'
os.environ['HAYSTACK_TELEMETRY_ENABLED']='false'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='true'

from .generation import fingerprint,restore_snapshot
from .local_qdrant import local_qdrant
from .planner import NativeWrenAIPlanner, provenance
from .transport import ReplayTransport
from .offline import loopback_only


def replay_recording(run_dir, *, runtime_identity=None, allow_drift=False):
    run_dir=Path(run_dir).resolve()
    load=lambda name:json.loads((run_dir/name).read_text(encoding='utf-8'))
    runtime=load('runtime.json'); payload=load('input.json'); ledger=load('ledger.json')
    config=runtime['configuration']
    if not allow_drift:
        if fingerprint(config)!=runtime['identity']['configuration_sha256']: raise ValueError('replay_configuration_drift')
        if any(config[k]!=runtime['identity'][k] for k in ('model','embedding_model','tokenizer')):
            raise ValueError('replay_configuration_drift')
        if runtime['manifest']!=runtime['identity']['index_identity'] or config['embedding_dimension']!=runtime['manifest']['embedding_dimension']:
            raise ValueError('replay_index_identity_drift')
    snapshots=load('index-snapshot.json')
    if fingerprint(snapshots)!=runtime['snapshot_sha256']: raise ValueError('replay_snapshot_drift')
    if runtime_identity is not None and runtime_identity!=runtime['identity'] and not allow_drift:
        raise ValueError('replay_identity_drift')
    current=provenance()
    for key in ('upstream_sha','patch_sha','lock_sha256','python_version'):
        if current[key]!=runtime['identity'][key] and not allow_drift: raise ValueError('replay_identity_drift')
    if fingerprint(payload)!=runtime['identity']['input_sha256']: raise ValueError('replay_input_drift')
    calls=[]
    for filename in ledger['calls']:
        path=(run_dir/filename).resolve()
        if not path.is_relative_to(run_dir): raise ValueError('invalid_recording_path')
        calls.append(json.loads(path.read_text(encoding='utf-8')))
    replay=ReplayTransport(calls)
    root=Path(tempfile.mkdtemp(prefix='wrenai-replay-',dir=Path(__file__).resolve().parents[1]/'.runtime'))
    root.chmod(0o700)
    with loopback_only(),local_qdrant(root/'qdrant') as url:
        if calls and calls[0]['node_id']!='schema_index':
            asyncio.run(restore_snapshot(root,runtime['manifest'],snapshots,url,
                runtime['configuration']['embedding_dimension']))
        planner=NativeWrenAIPlanner(runtime_root=root,qdrant_url=url,completion_transport=replay.completion,
            embedding_transport=replay.embedding,**runtime['configuration'])
        result=asyncio.run(planner.plan(payload))
    if replay.position!=len(calls): raise ValueError('replay_unconsumed_calls')
    replay_runtime=json.loads((Path(result['artifacts']['run_dir'])/'runtime.json').read_text(encoding='utf-8'))
    if replay_runtime['identity']['prompt_sha256']!=runtime['identity']['prompt_sha256']:
        raise ValueError('replay_prompt_drift')
    result['replay']={'drift_allowed':allow_drift,'transport_calls':replay.position,'original_run_dir':str(run_dir)}
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('run_dir')
    parser.add_argument('--allow-drift',action='store_true')
    args=parser.parse_args()
    output=sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        result=replay_recording(args.run_dir,allow_drift=args.allow_drift)
    output.write(json.dumps(result,ensure_ascii=False)+'\n'); output.flush()
