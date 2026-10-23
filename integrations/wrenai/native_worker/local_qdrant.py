"""A private test instance; never attaches to or stops a shared service."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


@contextmanager
def local_qdrant(root, binary=None):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True,mode=0o700); root.chmod(0o700)
    binary=Path(binary or Path(__file__).resolve().parents[1]/'.runtime/qdrant').resolve()
    port,grpc=free_port(),free_port()
    env={k:v for k,v in os.environ.items() if not k.startswith('QDRANT__')}
    env.update(QDRANT__STORAGE__STORAGE_PATH=str(root/'storage'),QDRANT__SERVICE__HOST='127.0.0.1',
        QDRANT__SERVICE__HTTP_PORT=str(port),QDRANT__SERVICE__GRPC_PORT=str(grpc),QDRANT__TELEMETRY_DISABLED='true')
    fd=os.open(root/'qdrant.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as log:
        process=subprocess.Popen([str(binary)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,umask=0o077)
        url=f'http://127.0.0.1:{port}'
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if process.poll() is not None: raise RuntimeError('local_qdrant_start_failed')
                try:
                    with urlopen(url+'/readyz',timeout=0.3): break
                except OSError: time.sleep(0.05)
            else: raise RuntimeError('local_qdrant_start_timeout')
            yield url
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
