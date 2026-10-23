"""Launch from an isolated Python environment; stdout is exclusively JSONL."""
import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent
# Do not inherit CPEA's src namespace or a caller's PYTHONPATH.
sys.path=[str(ROOT),str(ROOT/'.runtime/upstream/wren-ai-service')]+[
    p for p in sys.path if p and not p.endswith('/src') and p not in os.environ.get('PYTHONPATH','').split(os.pathsep)]
os.environ['LANGFUSE_ENABLED']='false'
os.environ['HAYSTACK_TELEMETRY_ENABLED']='false'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='true'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--recording',type=Path,required=True,help='Private recording to replay through native pipelines')
    args=parser.parse_args()
    output=sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        from native_worker.local_qdrant import local_qdrant
        from native_worker.planner import NativeWrenAIPlanner
        from native_worker.protocol import serve
        from native_worker.transport import ReplayTransport
        from native_worker.offline import loopback_only
        from native_worker.generation import restore_snapshot
        load=lambda name:json.loads((args.recording/name).read_text(encoding='utf-8'))
        runtime=load('runtime.json'); ledger=load('ledger.json')
        replay=ReplayTransport([load(name) for name in ledger['calls']])
        private_root=ROOT/'.runtime'/('worker-'+uuid.uuid4().hex)
        private_root.mkdir(mode=0o700)
        with loopback_only(),local_qdrant(private_root/'qdrant') as url:
            calls=[load(name) for name in ledger['calls']]
            if calls and calls[0]['node_id']!='schema_index':
                asyncio.run(restore_snapshot(private_root,runtime['manifest'],load('index-snapshot.json'),url,
                    runtime['configuration']['embedding_dimension']))
            planner=NativeWrenAIPlanner(runtime_root=private_root,qdrant_url=url,completion_transport=replay.completion,
                embedding_transport=replay.embedding,**runtime['configuration'])
            asyncio.run(serve(planner,output))


if __name__=='__main__': main()
