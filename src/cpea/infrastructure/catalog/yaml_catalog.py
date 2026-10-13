"""Snapshot a bounded, versioned integration profile. No database or LLM calls."""
from __future__ import annotations
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
import re
from typing import Any
import yaml

from cpea.application.catalog_contract import CatalogContract
from cpea.domain.catalog import ViewDefinition

_VIEW_NAME = re.compile(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){1,2}\Z')
_AGGREGATIONS = {'sum', 'count', 'avg', 'min', 'max'}
_OPERATORS = {'=', '!=', '<>', '>', '>=', '<', '<=', 'IN', 'LIKE'}

class SchemaCatalog(CatalogContract):
    def __init__(self, profile_root: str | Path | None = None):
        self.root = Path(profile_root).resolve() if profile_root is not None else Path(str(files('cpea.resources').joinpath('demo'))).resolve()
        digest = sha256()
        def document(relative: str) -> dict[str, Any]:
            if not isinstance(relative, str) or not relative:
                raise ValueError('contract resource requires a relative path')
            candidate = (self.root / relative).resolve()
            if Path(relative).is_absolute() or not candidate.is_relative_to(self.root):
                raise ValueError('contract resource must remain inside its profile root')
            if not candidate.is_file():
                raise ValueError('contract resource does not exist')
            raw = candidate.read_bytes()
            digest.update(relative.encode('utf-8') + b'\0' + raw)
            try:
                value = yaml.safe_load(raw)
            except yaml.YAMLError:
                raise ValueError('contract resource is not valid YAML') from None
            if not isinstance(value, dict):
                raise ValueError('contract resource must contain a mapping')
            return value
        manifest = document('manifest.yaml')
        self.profile_id = manifest.get('profile_id')
        self.contract_version = manifest.get('contract_version')
        if not isinstance(self.profile_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', self.profile_id):
            raise ValueError('manifest requires a valid profile_id')
        if not isinstance(self.contract_version, str) or not self.contract_version.strip():
            raise ValueError('manifest requires a string contract_version')
        if manifest.get('source_kind') != 'sql':
            raise ValueError('only existing SQL catalogs are supported')
        catalog_name = manifest.get('catalog')
        raw = document(catalog_name)
        self.catalog_path = self.root / catalog_name
        configured = raw.get('views')
        if not isinstance(configured, dict) or not configured:
            raise ValueError('catalog must contain a nonempty views mapping')
        self._definitions = []
        for name, config in configured.items():
            if not isinstance(name, str) or not _VIEW_NAME.fullmatch(name) or not isinstance(config, dict):
                raise ValueError('catalog requires approved qualified view identifiers')
            relative = config.get('path')
            policy = document(relative)
            if policy.get('view') != name or not isinstance(policy.get('summary'), str):
                raise ValueError('view contract does not match its catalog entry')
            self._validate_policy(policy)
            self._definitions.append(ViewDefinition(name, policy['summary'], (self.root / relative).as_posix(), policy))
        self.fingerprint = digest.hexdigest()

    @staticmethod
    def _validate_policy(policy: dict[str, Any]) -> None:
        columns = policy.get('columns')
        if not isinstance(columns, dict) or not columns:
            raise ValueError('view contract requires columns')
        for name, spec in columns.items():
            if not isinstance(name, str) or not isinstance(spec, dict) or not isinstance(spec.get('type'), str) or not isinstance(spec.get('description'), str):
                raise ValueError('column contract requires name, type and description')
            capabilities = spec.get('capabilities', [])
            if not isinstance(capabilities, list) or not set(capabilities) <= {'select', 'filter', 'group_by', 'order_by'}:
                raise ValueError('column contract contains invalid capabilities')
            aggregations = spec.get('aggregations', [])
            if not isinstance(aggregations, list) or not set(aggregations) <= _AGGREGATIONS:
                raise ValueError('column contract contains invalid aggregations')
            if spec.get('default_aggregation') and spec['default_aggregation'] not in aggregations:
                raise ValueError('default aggregation must be declared')
        operators = policy.get('filter_operators', {})
        if not isinstance(operators, dict):
            raise ValueError('filter operator policy requires a mapping')
        values = [value for key, value in operators.items() if key != 'columns']
        values.extend(operators.get('columns', {}).values())
        if any(not isinstance(value, list) or not set(value) <= _OPERATORS for value in values):
            raise ValueError('filter operator policy contains invalid operators')

    def views(self) -> list[ViewDefinition]:
        return list(self._definitions)

    def overview(self) -> str:
        return '\n'.join(['# 資料視圖總覽', '', '| View 名稱 | 中文用途 | 對應詳細檔案 |', '|---|---|---|',
            *[f'| `{item.name}` | {item.summary} | `{item.detail_path}` |' for item in self.views()]]) + '\n'
