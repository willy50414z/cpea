import os
from pathlib import Path
import sys
import json
import subprocess
import pytest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.runtime/upstream/wren-ai-service'))
os.environ['LANGFUSE_ENABLED'] = 'false'
os.environ['HAYSTACK_TELEMETRY_ENABLED'] = 'false'


@pytest.fixture(scope='session')
def retail_schema():
    repo=ROOT.parents[1]
    # Cross the same isolation boundary as production; do not import CPEA src here.
    script=('import json; from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog; '
        'from cpea.workflows.task_decomposition.wrenai_schema import adapt_catalog; '
        'print(json.dumps(adapt_catalog(SchemaCatalog("projects/retail"))))')
    env={**os.environ,'PYTHONPATH':str(repo/'src')}
    return json.loads(subprocess.check_output([str(repo/'.venv/bin/python'),'-c',script],cwd=repo,env=env,text=True,encoding='utf-8'))


@pytest.fixture(scope='session')
def qdrant_url():
    from native_worker.local_qdrant import local_qdrant
    with local_qdrant(ROOT/'.runtime'/('test-qdrant-'+uuid.uuid4().hex)) as url:
        yield url


@pytest.fixture(scope='session')
def planning_contract():
    repo=ROOT.parents[1]
    script=('import json; from cpea.application.models.decomposition import DecompositionDraft; '
        'from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog; '
        'print(json.dumps({"response_schema":DecompositionDraft.model_json_schema(),"catalog_fingerprint":SchemaCatalog("projects/retail").fingerprint}))')
    return json.loads(subprocess.check_output([str(repo/'.venv/bin/python'),'-c',script],cwd=repo,
        env={**os.environ,'PYTHONPATH':str(repo/'src')},text=True,encoding='utf-8'))
