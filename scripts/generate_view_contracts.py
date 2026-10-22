"""Verify explicit v4 semantics against read-only PostgreSQL metadata."""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re

from dotenv import dotenv_values
import psycopg
import yaml

from cpea.infrastructure.catalog.view_contract_v4 import validate_view_contract_v4
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog


GRAINS = {
    'v_customer_value': (['customer_id'], {'customers': ('customer_id',)}, ['GROUP BY c.customer_id']),
    'v_daily_sales': (['store_id', 'sales_date'], {'stores': ('store_id',)}, ['GROUP BY order_date, store_id']),
    'v_inventory_status': (['store_id', 'product_id'], {'inventory': ('store_id', 'product_id'), 'stores': ('store_id',), 'products': ('product_id',)}, ['FROM demo_retail.inventory i', 'LEFT JOIN last_30d']),
    'v_order_summary': (['order_id'], {'orders': ('order_id',), 'order_items': ('order_item_id',), 'stores': ('store_id',), 'customers': ('customer_id',)}, ['GROUP BY o.order_id']),
    'v_product_monthly': (['store_id', 'sales_month', 'product_id'], {'products': ('product_id',), 'stores': ('store_id',)}, ['GROUP BY order_month, store_id', 'product_id']),
    'v_sales_detail': (None, {'order_items': ('order_item_id',)}, ['FROM demo_retail.orders o', 'JOIN demo_retail.order_items oi']),
    'v_store_monthly_kpi': (['store_id', 'sales_month'], {'monthly_targets': ('store_id', 'target_month'), 'stores': ('store_id',)}, ['FROM demo_retail.monthly_targets t', 'GROUP BY v_order_summary.store_id, v_order_summary.order_month']),
}
IDENTIFIERS = {'order_id', 'order_no', 'customer_id', 'store_id', 'product_id', 'sku'}
TYPE_MAP = {
    'integer': 'number', 'bigint': 'number', 'smallint': 'number', 'numeric': 'number',
    'text': 'string', 'character varying': 'string', 'boolean': 'boolean', 'date': 'date',
}


def pg_type(value: str) -> str:
    base = re.sub(r'\(.*\)$', '', value)
    if base not in TYPE_MAP:
        raise ValueError(f'unsupported PostgreSQL type: {value}')
    return TYPE_MAP[base]


def unit(comment: str) -> str | None:
    match = re.search(r'單位\s*(TWD/筆|TWD/件|TWD|件|天|%)', comment)
    return match.group(1) if match else None


def column_spec(name: str, db_type: str, comment: str | None) -> dict:
    kind = pg_type(db_type)
    if not comment:
        raise ValueError(f'column comment missing: {name}')
    role = 'identifier' if name in IDENTIFIERS else 'measure' if kind == 'number' else 'dimension'
    spec = {'type': kind, 'role': role, 'description': comment}
    stated_unit = unit(comment)
    if stated_unit:
        spec['unit'] = stated_unit
    if '勿直接加總或平均' in comment or ('跨門市或月份' in comment and '重算' in comment) or ('跨會員平均' in comment and '重算' in comment):
        spec['disallowed_aggregations'] = ['sum', 'avg']
    elif '不應直接加總單價' in comment:
        spec['disallowed_aggregations'] = ['sum']
    return spec


def discover(cursor, schema: str):
    cursor.execute("""SELECT c.oid, c.relname, pg_get_viewdef(c.oid, true), obj_description(c.oid, 'pg_class')
                      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname=%s AND c.relkind='v' ORDER BY c.relname""", (schema,))
    views = cursor.fetchall()
    cursor.execute("""SELECT c.relname, co.contype, array_agg(a.attname ORDER BY k.ord)
                      FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid
                      JOIN pg_namespace n ON n.oid=c.relnamespace
                      JOIN unnest(co.conkey) WITH ORDINALITY k(attnum,ord) ON true
                      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
                      WHERE n.nspname=%s AND c.relkind IN ('r','p') AND co.contype IN ('p','u')
                      GROUP BY c.relname,co.oid,co.contype""", (schema,))
    constraints = {}
    for table, kind, keys in cursor.fetchall():
        constraints.setdefault(table, []).append((kind, tuple(keys)))
    for oid, name, definition, comment in views:
        cursor.execute("""SELECT a.attname,format_type(a.atttypid,a.atttypmod),col_description(a.attrelid,a.attnum)
                          FROM pg_attribute a WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped
                          ORDER BY a.attnum""", (oid,))
        yield name, definition, comment, cursor.fetchall(), constraints


def discover_relations(cursor, schema: str, name: str) -> list[str]:
    cursor.execute("""SELECT DISTINCT rn.nspname || '.' || rel.relname
                      FROM pg_rewrite rw JOIN pg_class v ON v.oid=rw.ev_class
                      JOIN pg_namespace vn ON vn.oid=v.relnamespace
                      JOIN pg_depend d ON d.classid='pg_rewrite'::regclass AND d.objid=rw.oid
                      JOIN pg_class rel ON d.refclassid='pg_class'::regclass AND rel.oid=d.refobjid
                      JOIN pg_namespace rn ON rn.oid=rel.relnamespace
                      WHERE vn.nspname=%s AND v.relname=%s AND rel.oid<>v.oid
                        AND rel.relkind IN ('r','p','v','m','f')
                      ORDER BY 1""", (schema, name))
    return [row[0] for row in cursor.fetchall()]


def build_view_contract(name, definition, columns, constraints, semantics, relations) -> dict:
    if not semantics or semantics.get('version') != 4:
        raise ValueError(f'explicit v4 semantic definition required: {name}')
    validate_view_contract_v4(semantics)
    if semantics['view'] != f'demo_retail.{name}' or name not in GRAINS:
        raise ValueError(f'no reviewed grain rule for {name}')
    source = semantics['source']
    if (source['verification'] != 'metadata_verified'
            or source['definition_sha256'] != sha256(definition.encode('utf-8')).hexdigest()):
        raise ValueError(f'view definition changed or unverified: {name}')
    if set(source['relations'] or []) != set(relations):
        raise ValueError(f'source relations changed: {name}')
    actual_columns = {col: pg_type(db_type) for col, db_type, _ in columns}
    if actual_columns != {col: spec['type'] for col, spec in semantics['columns'].items()}:
        raise ValueError(f'view output columns or types changed: {name}')
    keys, required, fragments = GRAINS[name]
    actual_keys = semantics['grain']['keys']
    if (keys is None) != (actual_keys is None) or set(keys or []) != set(actual_keys or []):
        raise ValueError(f'grain keys differ from reviewed evidence: {name}')
    for table, expected in required.items():
        if not any(kind in ('p', 'u') and tuple(actual) == expected
                   for kind, actual in constraints.get(table, [])):
            raise ValueError(f'missing source uniqueness evidence: {name}/{table}')
    if any(fragment not in definition for fragment in fragments):
        raise ValueError(f'view grain definition changed: {name}')
    return deepcopy(semantics)


def write_contract_file(path: Path, contract: dict) -> None:
    if path.exists():
        if yaml.safe_load(path.read_text(encoding='utf-8')) != contract:
            raise ValueError(f'existing contract differs; manual merge required: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(contract, allow_unicode=True, sort_keys=False, width=120),
                    encoding='utf-8', newline='\n')


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=project_root / 'projects' / 'retail',
                        help='integration profile directory for generated contracts')
    parser.add_argument('--semantic-profile', type=Path,
                        default=project_root / 'projects' / 'retail',
                        help='canonical profile containing explicit v4 semantics')
    args = parser.parse_args()
    root = args.root.resolve()
    semantics = SchemaCatalog(args.semantic_profile.resolve(), allow_drafts=True)
    policies = {view.name: view.policy for view in semantics.views()}
    config = dotenv_values(root / '.env', interpolate=False, encoding='utf-8')
    schema = config.get('RETAILER_DB_SCHEMA')
    if not schema or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', schema):
        raise ValueError('invalid RETAILER_DB_SCHEMA')
    if schema != 'demo_retail':
        raise ValueError('review the grain evidence rules for this schema before generating')
    generated = {}
    with psycopg.connect(config['CPEA_DATABASE_URL'], connect_timeout=8,
                         options='-c default_transaction_read_only=on') as db:
        with db.cursor() as cursor:
            cursor.execute('BEGIN READ ONLY')
            for name, definition, comment, columns, constraints in discover(cursor, schema):
                full_name = f'{schema}.{name}'
                policy = policies.get(full_name)
                generated[name] = build_view_contract(name, definition, columns, constraints, policy,
                                                     discover_relations(cursor, schema, name))
    if {f'{schema}.{name}' for name in generated} != set(policies):
        raise ValueError('discovered views differ from canonical semantic profile')
    destination = root / 'views' / schema
    destination.mkdir(parents=True, exist_ok=True)
    for name, contract in generated.items():
        path = destination / f'{name}.yaml'
        write_contract_file(path, contract)
    catalog = {'schema': schema, 'views': {f'{schema}.{name}': {'path': f'views/{schema}/{name}.yaml'} for name in generated}}
    catalog_path = root / 'catalog.yaml'
    if catalog_path.exists() and yaml.safe_load(catalog_path.read_text(encoding='utf-8')) != catalog:
        raise ValueError('existing catalog differs; manual merge required')
    if not catalog_path.exists():
        catalog_path.write_text(yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    manifest = {'profile_id': f'{schema}_draft', 'contract_version': '4', 'source_kind': 'sql',
                'catalog': 'catalog.yaml', 'status': 'draft'}
    manifest_path = root / 'manifest.yaml'
    if manifest_path.exists():
        prior = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
        if (prior.get('source_kind'), prior.get('catalog'), prior.get('contract_version')) != ('sql', 'catalog.yaml', '4'):
            raise ValueError('existing manifest differs; manual merge required')
    if not manifest_path.exists():
        manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    print(f'verified {len(generated)} v4 contracts in {destination}')


if __name__ == '__main__':
    main()
