"""Hash-check complete snapshots, restoring only relocated absolute identities."""
import argparse
import importlib
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[5]
work = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--run', type=Path, required=True)
args = parser.parse_args()
folder = args.run.resolve()
snapshot = work / 'sources-after'
manifest = json.loads((work / 'sources-after.json').read_text(encoding='utf-8'))
canonical = {}
for name, digest in manifest.items():
    path = snapshot / name.lstrip('/')
    assert sha256(path.read_bytes()).hexdigest() == digest, name
    canonical[str(path)] = name if Path(name).is_absolute() else str(repo / name)
os.chdir(snapshot)
sys.path[:0] = [str(snapshot), str(snapshot / 'src')]
runner = importlib.import_module('evaluations.managed_three_stage_runner')
runner.LOOPCTL = snapshot / str(runner.LOOPCTL).lstrip('/')
original = runner.fingerprint


def relocated(catalog, case, **kwargs):
    result = original(catalog, case, **kwargs)
    for group in ('source_hashes', 'managed_sources'):
        result[group] = {canonical.get(key, key): value for key, value in result[group].items()}
    return result


runner.fingerprint = relocated
contract = importlib.import_module('evaluations.kind_mapping_managed_contract')
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
meta = runner.read_json(folder / 'run.json')
print(json.dumps(runner.replay(folder, SchemaCatalog('projects/retail'), meta['case'], contract=contract), ensure_ascii=False))
