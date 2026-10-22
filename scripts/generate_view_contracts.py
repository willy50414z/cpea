"""Generate reviewable v3 contracts from PostgreSQL catalog metadata only."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from dotenv import dotenv_values
import psycopg
import yaml


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


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=project_root / 'projects' / 'retail',
                        help='integration profile directory for generated contracts')
    args = parser.parse_args()
    root = args.root.resolve()
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
                if name not in GRAINS:
                    raise ValueError(f'no reviewed grain rule for {name}')
                keys, required, fragments = GRAINS[name]
                for table, expected in required.items():
                    if not any(actual == expected for _, actual in constraints.get(table, [])):
                        raise ValueError(f'missing source uniqueness evidence: {name}/{table}')
                if any(fragment not in definition for fragment in fragments):
                    raise ValueError(f'view definition changed: {name}')
                if not comment:
                    raise ValueError(f'view comment missing: {name}')
                specs = {col: column_spec(col, db_type, note) for col, db_type, note in columns}
                if keys and not set(keys) <= set(specs):
                    raise ValueError(f'grain keys missing from output: {name}')
                summary = comment
                grain_description = re.split('[；。]', comment, maxsplit=1)[0].removeprefix('粒度：')
                if name == 'v_sales_detail':
                    grain_description = '每筆已完成訂單的每筆商品明細'
                generated[name] = {'version': 3, 'view': f'{schema}.{name}', 'summary': summary,
                                   'grain': {'description': grain_description, 'keys': keys},
                                   'columns': specs}
    destination = root / 'views' / schema
    destination.mkdir(parents=True, exist_ok=True)
    for name, contract in generated.items():
        path = destination / f'{name}.yaml'
        if path.exists():
            prior = yaml.safe_load(path.read_text(encoding='utf-8'))
            if prior != contract:
                raise ValueError(f'existing contract differs; manual merge required: {path}')
            continue
        path.write_text(yaml.safe_dump(contract, allow_unicode=True, sort_keys=False, width=120), encoding='utf-8', newline='\n')
    catalog = {'schema': schema, 'views': {f'{schema}.{name}': {'path': f'views/{schema}/{name}.yaml'} for name in generated}}
    catalog_path = root / 'catalog.yaml'
    if catalog_path.exists() and yaml.safe_load(catalog_path.read_text(encoding='utf-8')) != catalog:
        raise ValueError('existing catalog differs; manual merge required')
    if not catalog_path.exists():
        catalog_path.write_text(yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    manifest = {'profile_id': f'{schema}_draft', 'contract_version': '3-draft', 'source_kind': 'sql',
                'catalog': 'catalog.yaml', 'status': 'draft'}
    manifest_path = root / 'manifest.yaml'
    if manifest_path.exists() and yaml.safe_load(manifest_path.read_text(encoding='utf-8')) != manifest:
        raise ValueError('existing manifest differs; manual merge required')
    if not manifest_path.exists():
        manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    print(f'generated {len(generated)} draft contracts in {destination}')


if __name__ == '__main__':
    main()
