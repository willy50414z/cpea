import hashlib
from pathlib import Path
import subprocess

UPSTREAM_SHA='ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc'
LOCK_SHA='092fed1a63f08594e1f9eff3c8c6564d50f31d9be760dc2914c31ffe026a5e25'


def verify_checkout(service):
    service=Path(service).resolve()
    checkout=service.parent
    head=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(checkout),'status','--porcelain','--untracked-files=all'],text=True)
    lock=hashlib.sha256((service/'poetry.lock').read_bytes()).hexdigest()
    if head!=UPSTREAM_SHA or dirty or lock!=LOCK_SHA:
        raise ValueError('upstream_source_drift')
    return head,lock
