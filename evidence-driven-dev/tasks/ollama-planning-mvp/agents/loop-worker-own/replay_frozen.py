"""Hash-checked relocated sources; preserve original artifact/input/error checks."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[5]
work = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--snapshot', choices=['before', 'after'], default='after')
parser.add_argument('--contract', choices=['slots', 'v1', 'own'], default='own')
parser.add_argument('--run', type=Path, required=True)
args = parser.parse_args()
folder = args.run.resolve()
snapshot = work / ('sources-' + args.snapshot)
manifest = json.loads((work / ('sources-' + args.snapshot + '.json')).read_text(encoding='utf-8'))
canonical = {}
for name, digest in manifest.items():
    path = snapshot / name.lstrip('/') if Path(name).is_absolute() else snapshot / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
    canonical[str(path)] = name if Path(name).is_absolute() else str(repo / name)
os.chdir(snapshot)
sys.path[:0] = [str(snapshot), str(snapshot / 'src')]
runner = importlib.import_module('evaluations.managed_three_stage_runner')
runner.LOOPCTL = snapshot / str(runner.LOOPCTL).lstrip('/')
original = runner.fingerprint


def relocated(catalog, case, **kwargs):
    result = original(catalog, case, **kwargs)
    # Only restore canonical identities of relocated absolute paths; no hashes,
    # schemas, inputs, saved artifacts, or stopped results are changed.
    for group in ('source_hashes', 'managed_sources'):
        result[group] = {canonical.get(key, key): value for key, value in result[group].items()}
    return result


runner.fingerprint = relocated
module = {'v1': 'evidence_bound_managed_contract', 'own': 'own_responsibility_managed_contract'}
contract = importlib.import_module('evaluations.' + module[args.contract]) if args.contract != 'slots' else None
meta = runner.read_json(folder / 'run.json')
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
print(json.dumps(runner.replay(folder, SchemaCatalog('projects/retail'), meta['case'], contract=contract), ensure_ascii=False))
