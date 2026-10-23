"""Hand-authored staged responses for the independent mapping boundary."""
from copy import deepcopy
import json
from types import SimpleNamespace

from langchain_core.documents import Document
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, RetrievalResult

from tests.decomposition_support import draft

REQUEST = '各店各商品目前庫存件數及2026年9月銷售件數；保留所有庫存商品，準備補貨優先評估資料，暫不計算採購量。'


def span(text, request=REQUEST):
    start = request.index(text)
    return {'start': start, 'end': start + len(text), 'text': text}


def extraction():
    units = [
        ('store', '各店', 'grain', []),
        ('product', '各商品', 'grain', []),
        ('stock', '目前庫存件數', 'concept', []),
        ('period', '2026年9月', 'time', ['sales']),
        ('sales', '2026年9月銷售件數', 'concept', ['period']),
        ('population', '保留所有庫存商品', 'population', ['stock']),
        ('purpose', '準備補貨優先評估資料', 'purpose', ['stock', 'sales']),
        ('no_purchase', '暫不計算採購量', 'prohibition', []),
    ]
    return {'requirements': [{'id': name, 'span': span(text), 'kind': kind,
                              'required': True, 'related_ids': related}
                             for name, text, kind, related in units],
            'syntax': [{'span': {'start': i, 'end': i + 1, 'text': char},
                        'kind': 'syntax' if char == '及' else 'punctuation'}
                       for i, char in enumerate(REQUEST) if char in '及；，。']}


def candidate(view, requirement_id, column, operation):
    return {'id': f'{view}:{requirement_id}:{column}', 'column': column,
            'operations': [operation], 'reason': '契約描述支援本欄位用途。',
            'evidence': [{'path': ['columns', column, 'description'], 'quote': column}]}


def mapping(view, *, monthly=False):
    grants = {'demo.stock': {'store': ('store_id', 'grain'), 'product': ('product_id', 'grain'),
                             'stock': ('stock_qty', 'attribute')},
              'demo.sales': {'store': ('store_id', 'grain'), 'product': ('product_id', 'grain'),
                             'sales': ('quantity', 'metric'), 'period': ('order_date', 'filter')},
              'demo.monthly': {'store': ('store_id', 'grain'), 'product': ('product_id', 'grain'),
                               'sales': ('units_sold', 'attribute'), 'period': ('sales_month', 'filter')}}
    chosen = grants.get(view, {}) if view != 'demo.monthly' or monthly else {}
    rows = []
    for requirement in extraction()['requirements']:
        rid = requirement['id']
        candidates = [candidate(view, rid, *chosen[rid])] if rid in chosen else []
        status = ('matched' if candidates else 'constraint_only'
                  if requirement['kind'] in {'population', 'purpose', 'prohibition'} else 'unmatched')
        rows.append({'requirement_id': rid, 'status': status, 'candidates': candidates,
                     'reason': '保留約束。' if status == 'constraint_only' else '依完整契約比對。'})
    return {'view': view, 'results': rows}


def review(*, monthly=False):
    source = 'demo.monthly' if monthly else 'demo.sales'
    selected = [c['id'] for view in ['demo.stock', source]
                for result in mapping(view, monthly=monthly)['results'] for c in result['candidates']]
    column = 'sales_month' if monthly else 'order_date'
    filters = ([{'column': column, 'operator': '=', 'value': '2026-09-01'}] if monthly else
               [{'column': column, 'operator': '>=', 'value': '2026-09-01'},
                {'column': column, 'operator': '<', 'value': '2026-10-01'}])
    rejected = ([{'candidate_id': c['id'], 'reason': '此需求選用月彙總等價來源。'}
                 for row in mapping('demo.sales')['results'] for c in row['candidates']] if monthly else [])
    return {'status': 'ready', 'selected_candidate_ids': selected, 'auxiliary_columns': [],
            'missing_requirements': [], 'rejected_candidates': rejected, 'reasons': [],
            'constraints': [
                {'requirement_id': 'period', 'kind': 'time',
                 'filters': [{'view': source, 'condition': f} for f in filters], 'note': '完整九月。'},
                {'requirement_id': 'population', 'kind': 'population', 'anchor_view': 'demo.stock',
                 'note': '保留所有庫存商品。'},
                {'requirement_id': 'purpose', 'kind': 'purpose', 'note': '只準備評估資料。'},
                {'requirement_id': 'no_purchase', 'kind': 'prohibition',
                 'forbidden_uses': [], 'note': '僅執行核准欄位用途，不衍生採購計算。'}]}


def mapped_draft(*, monthly=False):
    value = deepcopy(draft())
    if monthly:
        value['tasks'][1].update(view='demo.monthly',
            required_columns=['store_id', 'product_id', 'units_sold', 'sales_month'],
            filters=[{'column': 'sales_month', 'operator': '=', 'value': '2026-09-01'}],
            metrics={}, group_by=[], attributes=['units_sold'])
    bindings = []
    for task in value['tasks']:
        for rid, column in [('store', 'store_id'), ('product', 'product_id')]:
            bindings.append({'requirement_id': rid, 'task_id': task['task_id'], 'columns': [column]})
        bindings.append({'requirement_id': 'stock' if task['task_id'] == 'stock' else 'sales',
                         'task_id': task['task_id'],
                         'columns': ['stock_qty' if task['task_id'] == 'stock' else
                                     'units_sold' if monthly else 'quantity']})
        if task['task_id'] == 'sales':
            bindings.append({'requirement_id': 'period', 'task_id': 'sales',
                             'columns': ['sales_month' if monthly else 'order_date']})
    return {'draft': value, 'bindings': bindings}


class StagedLLM:
    def __init__(self, payloads):
        self.payloads = deepcopy(payloads)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        payload = self.payloads[len(self.calls) - 1]
        if isinstance(payload, Exception):
            raise payload
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False),
                               usage_metadata={'input_tokens': 10, 'output_tokens': 20})


class StaticViewRetriever:
    def __init__(self, names, error=None):
        self.names, self.error, self.calls = names, error, []

    def retrieve(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        candidates = [RetrievalCandidate(Document(page_content='', metadata={'document_id': name}), 1.0)
                      for name in self.names]
        return RetrievalResult(query, candidates, 2.0, 1.0)
