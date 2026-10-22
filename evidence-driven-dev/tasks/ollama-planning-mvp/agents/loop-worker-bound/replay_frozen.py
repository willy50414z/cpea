"""Relocated, hash-checked source replay; no inference or source rewriting."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

repo=Path(__file__).resolve().parents[5]
work=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--snapshot',choices=['before','after'],default='before')
parser.add_argument('--run',type=Path,default=repo/'evidence-driven-dev/tasks/ollama-planning-mvp/.local/qwen-managed-20261021T171721Z-fa4587')
parser.add_argument('--evidence-bound',action='store_true')
args=parser.parse_args()
folder=args.run.resolve()
snapshot=work/('sources-'+args.snapshot)
manifest=json.loads((work/('sources-'+args.snapshot+'.json')).read_text(encoding='utf-8'))
canonical={}
for name,digest in manifest.items():
    path=snapshot/name.lstrip('/') if Path(name).is_absolute() else snapshot/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
    canonical[str(path)]=name if Path(name).is_absolute() else str(repo/name)
os.chdir(snapshot)
sys.path[:0]=[str(snapshot),str(snapshot/'src')]
mod=importlib.import_module('evaluations.managed_three_stage_runner')
mod.LOOPCTL=snapshot/str(mod.LOOPCTL).lstrip('/')
original=mod.fingerprint

def relocated(catalog,case,**kwargs):
    result=original(catalog,case,**kwargs)
    # Map relocated absolute source keys to their canonical identities. Hashes
    # and all schema/input/artifact comparisons remain the original algorithm.
    for group in ('source_hashes','managed_sources'):
        result[group]={canonical.get(k,k):v for k,v in result[group].items()}
    return result
mod.fingerprint=relocated
contract=importlib.import_module('evaluations.evidence_bound_managed_contract') if args.evidence_bound else None
meta=mod.read_json(folder/'run.json')
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
kwargs={'contract':contract} if args.evidence_bound else {}
print(json.dumps(mod.replay(folder,SchemaCatalog('projects/retail'),meta['case'],**kwargs),ensure_ascii=False))
