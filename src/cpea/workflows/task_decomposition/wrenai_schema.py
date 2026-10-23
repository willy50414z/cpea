"""Structural schema projection; policies remain authoritative and unmodified."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

ADAPTER_VERSION = '1'
_TYPES = {'number':'NUMERIC', 'string':'VARCHAR', 'date':'DATE', 'boolean':'BOOLEAN'}


def encode_model_name(view: str) -> str:
    return 'm_' + view.encode('utf-8').hex()


def decode_model_name(model: str) -> str:
    if not model.startswith('m_'):
        raise ValueError('invalid structural model name')
    try:
        result = bytes.fromhex(model[2:]).decode('utf-8')
    except (ValueError, UnicodeError):
        raise ValueError('invalid structural model name') from None
    if encode_model_name(result) != model:
        raise ValueError('noncanonical structural model name')
    return result


def adapt_catalog(catalog) -> dict:
    models, mapping, contracts = [], {}, {}
    for view in catalog.views():
        name = encode_model_name(view.name)
        if name in mapping or view.name in contracts:
            raise ValueError('schema model name collision')
        columns = []
        for column, kind in catalog.columns(view.name).items():
            if kind not in _TYPES:
                raise ValueError('unsupported structural field type')
            columns.append({'name':column, 'type':_TYPES[kind], 'properties':{}})
        mapping[name] = view.name
        contracts[view.name] = deepcopy(view.policy)
        models.append({'name':name, 'tableReference':{'table':view.name},
                       'columns':columns, 'properties':{}})
    return {'adapter_version':ADAPTER_VERSION, 'mdl':{'catalog':'cpea','schema':'verified',
            'models':models,'relationships':[],'views':[],'metrics':[]},
            'model_to_view':mapping,'contracts':contracts}


def generation_manifest(*, catalog_fingerprint: str, upstream_sha: str, patch_sha: str,
                        lock_hash: str, embedding_provider: str, embedding_model: str,
                        embedding_dimension: int) -> dict:
    fields = dict(catalog_fingerprint=catalog_fingerprint, adapter_version=ADAPTER_VERSION,
                  upstream_sha=upstream_sha, patch_sha=patch_sha, lock_hash=lock_hash,
                  embedding_provider=embedding_provider, embedding_model=embedding_model,
                  embedding_dimension=embedding_dimension)
    if any(not isinstance(v,str) or not v.strip() for k,v in fields.items() if k!='embedding_dimension'):
        raise ValueError('generation identity requires all dependencies')
    if type(embedding_dimension) is not int or embedding_dimension <= 0:
        raise ValueError('embedding dimension must be positive')
    identity = sha256(json.dumps(fields,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    return {**fields,'identity':identity,'project_id':identity,'namespace':'cpea_wrenai_'+identity[:24]}
