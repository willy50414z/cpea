"""Execute with the CPEA interpreter, never with the WrenAI interpreter."""
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'src'))
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.workflows.task_decomposition.wrenai_client import WrenAIWorkerClient
from cpea.workflows.task_decomposition.wrenai_workflow import WrenAIDecompositionWorkflow

recording=Path(sys.argv[1]).resolve()
runtime=json.loads((recording/'runtime.json').read_text(encoding='utf-8'))
expected={k:runtime['provenance'][k] for k in ('upstream_sha','patch_sha','lock_sha256','python_version')}
with WrenAIWorkerClient([str(ROOT/'.runtime/env/bin/python'),str(ROOT/'worker.py'),'--recording',str(recording)],
    expected_metadata=expected,expected_import_root=ROOT/'.runtime/upstream/wren-ai-service',
    artifact_root=ROOT/'.runtime'/('parent-smoke-'+uuid.uuid4().hex),env={**os.environ,'PYTHONPATH':str(REPO/'src')}) as client:
    result=WrenAIDecompositionWorkflow(client,SchemaCatalog(REPO/'projects/retail')).plan('customer_id',case_id='offline-customer')
    print(json.dumps({'status':result.status,'code':result.code,'prepared_count':len(result.prepared_requests),
        'validation_errors':result.validation_errors},ensure_ascii=False))
