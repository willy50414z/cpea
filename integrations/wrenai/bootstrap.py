"""Reproducible local bootstrap, without changing the CPEA environment."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'.runtime'
SHA='ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc'
LOCK='092fed1a63f08594e1f9eff3c8c6564d50f31d9be760dc2914c31ffe026a5e25'
QDRANT_SHA='8d0f3af71b4606581c6d4d943c0763aa7f368a7ee801b2f01e16ab2376e8f363'


def main():
    os.umask(0o077)
    RUNTIME.mkdir(exist_ok=True,mode=0o700); RUNTIME.chmod(0o700)
    with (RUNTIME/'bootstrap.log').open('a',encoding='utf-8') as log:
        def run(args,**kwargs):
            log.write(json.dumps(args)+'\n'); log.flush()
            subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT,**kwargs)
        upstream=RUNTIME/'upstream'
        if not upstream.exists(): run(['git','clone','--no-checkout','https://github.com/Canner/WrenAI.git',str(upstream)])
        run(['git','-C',str(upstream),'checkout','--detach',SHA])
        service=upstream/'wren-ai-service'
        def check_lock():
            if hashlib.sha256((service/'poetry.lock').read_bytes()).hexdigest()!=LOCK: raise ValueError('upstream_lock_drift')
        check_lock()
        if not (RUNTIME/'tools/bin/python').exists(): run(['uv','venv','--python','3.12',str(RUNTIME/'tools')])
        run(['uv','pip','install','--python',str(RUNTIME/'tools/bin/python'),'poetry==2.1.4'])
        if not (RUNTIME/'env/bin/python').exists(): run(['uv','venv','--python','3.12',str(RUNTIME/'env')])
        env={**os.environ,'VIRTUAL_ENV':str(RUNTIME/'env'),'POETRY_VIRTUALENVS_CREATE':'false'}
        env.pop('PYTHONPATH',None)
        run([str(RUNTIME/'tools/bin/poetry'),'install','--only','main','--no-root'],cwd=service,env=env)
        check_lock()
        run(['uv','pip','install','--python',str(RUNTIME/'env/bin/python'),'pytest==8.3.5','pytest-asyncio==0.24.0'])
        archive=RUNTIME/'qdrant.tar.gz'
        if not archive.exists():
            with urlopen('https://github.com/qdrant/qdrant/releases/download/v1.15.4/qdrant-x86_64-unknown-linux-gnu.tar.gz') as response:
                archive.write_bytes(response.read())
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=QDRANT_SHA: raise ValueError('qdrant_archive_drift')
        with tarfile.open(archive) as tar:
            binary=RUNTIME/'qdrant'
            member=next(m for m in tar.getmembers() if Path(m.name).name=='qdrant')
            expected_binary=hashlib.sha256(tar.extractfile(member).read()).hexdigest()
            if binary.exists():
                if hashlib.sha256(binary.read_bytes()).hexdigest()!=expected_binary: raise ValueError('qdrant_binary_drift')
            else: tar.extractall(RUNTIME,filter='data')
        run([str(RUNTIME/'env/bin/python'),str(ROOT/'environment_probe.py')],env=env)
    print('Bootstrap complete; private log: integrations/wrenai/.runtime/bootstrap.log')


if __name__=='__main__': main()
