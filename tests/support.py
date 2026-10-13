import importlib
import os
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import yaml

from cpea.domain import models
from cpea.config.settings import AssistantSettings as Settings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog as Catalog
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow as Workflow
from cpea.application.services import sql_execution as Execution
from cpea.application.services.answering import AnswerSynthesisService as Answering
from cpea.infrastructure import sql_compiler as Compiler
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.retrieval.schema import SchemaRetriever as Retriever

VIEW = 'gms2.v_inventory'
QUESTION = '請查詢 ZX100 目前各倉庫庫存數量'

def view_contract(view=VIEW):
    return {
        'view': view, 'summary': '合成示例：目前各倉庫的品號庫存數量。',
        'grain': '品號、倉庫', 'temporal_scope': 'current_snapshot',
        'columns': {
            '品号': {'type': '字串', 'description': '合成品號', 'capabilities': ['select', 'filter'], 'aliases': ['品號']},
            '仓库名称': {'type': '字串', 'description': '合成倉庫', 'capabilities': ['select', 'filter', 'group_by'], 'aliases': ['倉庫']},
            '库存数量': {'type': '數值', 'description': '合成數量', 'capabilities': ['select'], 'aggregations': ['sum'], 'default_aggregation': 'sum', 'aliases': ['庫存數量']},
        },
        'filter_operators': {'default': ['=', 'IN', 'LIKE'], 'number': ['=', '>']},
        'scope_rules': [{'name': '各倉庫', 'request_patterns': ['各倉庫'], 'required_dimension': '仓库名称', 'required_group_by': True, 'prohibited_filter_columns': ['仓库名称']}],
    }

def write_profile(root, view=VIEW, profile_id='synthetic', version='1'):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in {
        'catalog.yaml': {'schema': view.split('.')[0], 'views': {view: {'path': 'inventory.yaml'}}},
        'inventory.yaml': view_contract(view),
        'manifest.yaml': {'profile_id': profile_id, 'contract_version': version, 'source_kind': 'sql', 'catalog': 'catalog.yaml'},
    }.items():
        (root / name).write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding='utf-8')
    return root

class Counter:
    name = 'synthetic-offline'
    def count(self, text):
        return max(1, len(text) // 4)
    def count_messages(self, messages):
        return sum(self.count(content) + 8 for _, content in messages)

class StubLLM:
    def __init__(self, view=VIEW):
        self.view = view
        self.calls = 0
    def with_structured_output(self, model, **kwargs):
        def invoke(messages):
            self.calls += 1
            if model.__name__ == 'FactDraft':
                return model.model_validate({'facts': [
                    {'kind': 'entity', 'text': 'ZX100'}, {'kind': 'time', 'text': '目前'},
                    {'kind': 'dimension', 'text': '各倉庫'}, {'kind': 'metric', 'text': '庫存數量'},
                ]})
            return model.model_validate({'supported': True, 'links': [
                {'fact_text': 'ZX100', 'view': self.view, 'column': '品号', 'role': 'filter', 'operator': '=', 'value': 'ZX100'},
                {'fact_text': '各倉庫', 'view': self.view, 'column': '仓库名称', 'role': 'dimension'},
                {'fact_text': '庫存數量', 'view': self.view, 'column': '库存数量', 'role': 'metric', 'aggregation': 'sum'},
            ]})
        return SimpleNamespace(invoke=invoke)
    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content='{"answer":"合成庫存資料 [Source 1]","citations":["Source 1"]}')
    def stream(self, messages):
        yield self.invoke(messages)

def dependencies(root, view=VIEW, max_rows=2):
    settings = replace(Settings.from_env(), retrieval_mode='lexical', context_window=16000, max_rows=max_rows)
    profile = write_profile(root, view)
    catalog = Catalog(profile)
    packer = ContextPacker(settings, token_counter=Counter())
    llm = StubLLM(view)
    retriever = Retriever(settings, catalog=catalog)
    return settings, catalog, packer, llm, retriever
