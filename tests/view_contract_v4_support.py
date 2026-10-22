from copy import deepcopy
from pathlib import Path

import yaml

from tests.support import write_profile


def v4_policy():
    return {
        'version': 4, 'view': 'gms2.v_inventory', 'summary': '庫存狀態資料。',
        'grain': {'description': '每個品號及倉庫組合一列', 'keys': ['品号', '仓库名称']},
        'source': {'verification': 'unknown', 'relations': None, 'definition_sha256': None},
        'scope': {'population': '庫存品項', 'included': [], 'excluded': [],
                  'row_coverage': '僅包含有庫存紀錄的組合。'},
        'time': {'kind': 'snapshot', 'dimensions': {'snapshot_date': '盤點日期'},
                 'coverage': None, 'rules': [{'columns': ['库存数量'],
                    'description': '不可跨快照日期直接加總。'}]},
        'usage': {'supported': ['查詢各倉庫庫存'], 'unsupported': [
            {'question': '歷史銷售趨勢', 'reason': '未提供交易資料。'}]},
        'columns': {
            '品号': {'type': 'string', 'role': 'identifier', 'description': '品號'},
            '仓库名称': {'type': 'string', 'role': 'dimension', 'description': '倉庫名稱', 'entity': '倉庫'},
            '库存数量': {'type': 'number', 'role': 'measure', 'description': '庫存數量', 'unit': '件'},
            'snapshot_date': {'type': 'date', 'role': 'dimension', 'description': '盤點日期'},
        },
        'metrics': {'stock': {'description': '庫存件數', 'columns': ['库存数量'],
            'calculation': '庫存數量', 'aggregation_notes': '限同一快照日期加總。'}},
    }


def write_v4_profile(root, policy=None):
    root = write_profile(root)
    policy = deepcopy(policy if policy is not None else v4_policy())
    (Path(root) / 'inventory.yaml').write_text(
        yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding='utf-8')
    return root
