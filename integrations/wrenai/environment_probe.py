"""Read-only provenance probe; run with the isolated interpreter."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent / '.runtime' / 'upstream'
service = root / 'wren-ai-service'
sys.path.insert(0, str(service))
modules = ['src.pipelines.indexing.db_schema', 'src.pipelines.indexing.table_description',
           'src.pipelines.generation.intent_classification', 'src.pipelines.retrieval.db_schema_retrieval']
sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
assert sha == 'ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc'
assert sys.version_info[:2] == (3, 12)
paths = {name: str(Path(importlib.import_module(name).__file__).resolve()) for name in modules}
assert all(Path(path).is_relative_to(service) for path in paths.values())
print(json.dumps({'upstream_sha': sha, 'python_version': sys.version,
                  'lock_sha256': hashlib.sha256((service/'poetry.lock').read_bytes()).hexdigest(),
                  'import_sources': paths}, ensure_ascii=False))
