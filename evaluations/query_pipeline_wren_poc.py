"""Optional isolated Wren compiler probe: fixed semantic SQL, never an NL trial.

Run this file with the isolated interpreter, not the product environment. The
conversion is a technical draft; column policies remain in a lossless sidecar.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import re


def convert_catalog(snapshot):
    models, mapping, aliases = [], [], set()
    types = {'number': 'double', 'string': 'varchar', 'date': 'date', 'boolean': 'boolean'}
    for view, policy in sorted(snapshot.items()):
        if view != policy.get('view') or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){1,2}', view):
            raise ValueError('invalid or mismatched qualified view')
        alias = view.replace('.', '__')
        if alias in aliases:
            raise ValueError('native alias collision')
        aliases.add(alias)
        parts = view.split('.')
        reference = dict(zip(('catalog', 'schema', 'table')[-len(parts):], parts))
        columns, assumed = [], []
        for name, column in policy['columns'].items():
            if column['type'] not in types:
                raise ValueError('unsupported source column type')
            columns.append({'name': name, 'type': types[column['type']]})
            if column['type'] == 'number':
                assumed.append(name)
        models.append({'name': alias, 'tableReference': reference, 'columns': columns})
        mapping.append({'source_view': view, 'native_model': alias, 'original_contract': deepcopy(policy),
            'numeric_type_assumptions': assumed, 'uncompiled_fields': ['grain', 'summary', 'column_policies']})
    return {'mdl': {'catalog': 'cpea', 'schema': 'technical', 'models': models, 'relationships': []},
        'mapping': mapping, 'business_semantics_approved': False,
        'limitations': ['number is provisionally double, not proven storage type',
            'grain, units, filters, aggregation policies and missing-value rules are not enforced by this draft',
            'no primary keys or relationships inferred; no natural-language generation tested']}


def probe(snapshot, *, output):
    # Optional engine import occurs only in the separately provisioned process.
    from wren_core import SessionContext
    version = importlib.metadata.version('wren-core-py')
    if version != '0.8.1':
        raise ValueError('probe requires pinned wren-core-py==0.8.1')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    def write(name, value):
        with (output / name).open('x', encoding='utf-8') as stream:
            os.chmod(output / name, 0o600)
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    draft = convert_catalog(snapshot)
    write('conversion.json', draft)
    encoded = base64.b64encode(json.dumps(draft['mdl'], ensure_ascii=False).encode('utf-8')).decode('ascii')
    write('environment.json', {'package': 'wren-core-py', 'version': version,
        'input_kind': 'fixed_semantic_request', 'model_calls': 0, 'db_api_calls': 0,
        'business_semantics_approved': False})
    results = []
    for model in draft['mdl']['models']:
        query = 'SELECT * FROM "' + model['name'] + '"'
        record = {'model': model['name'], 'input_sql': query}
        # Save the request before touching the optional native engine.
        write(f'{len(results):04d}-request.json', record)
        try:
            sql = SessionContext(encoded).transform_sql(query)
            record.update(status='compiled', sql=sql)
        except Exception as exc:
            record.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        write(f'{len(results):04d}-result.json', record)
        results.append(record)
    write('result.json', {'planned': len(results), 'compiled': sum(r['status'] == 'compiled' for r in results),
        'natural_success': 0, 'business_semantics_approved': False, 'trials': results})
    write('integrity.json', {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    results = probe(json.loads(args.snapshot.read_text(encoding='utf-8')), output=args.output)
    print(json.dumps({'planned': len(results), 'compiled': sum(r['status'] == 'compiled' for r in results),
        'natural_success': 0, 'business_semantics_approved': False}))
    return 0 if all(r['status'] == 'compiled' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
