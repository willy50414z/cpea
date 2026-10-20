from dataclasses import replace
import json
from types import SimpleNamespace
import yaml

from cpea.bootstrap import AssistantRuntime
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from tests.support import Counter, dependencies

VIEW = 'demo_retail.v_order_summary'
QUESTION = f'請從 {VIEW} 查詢含稅發票總額。'


def clarification_drafts():
    return [{'term': term, 'options': [
        {'column': column, 'label': description, 'evidence_quote': description,
         'same_concept': True, 'grain_compatible': True}
        for column, description in [('order_amount', '訂單金額'), ('net_amount', '未稅訂單金額')]]}
        for term in ('含稅發票總額', '預估發票淨額')]


def runtime_for(root, *, column='order_amount', text='總額', executor=None, null_table=False, terms=None):
    settings, _, _, _, _ = dependencies(root, VIEW)
    path = root / 'inventory.yaml'
    contract = yaml.safe_load(path.read_text(encoding='utf-8'))
    contract['summary'] = '訂單摘要'
    contract['columns'] = {
        'order_amount': {'type': '數值', 'description': '訂單金額', 'capabilities': ['select', 'filter', 'order_by', 'group_by'],
                         'aggregations': ['sum'], 'aliases': ['訂單金額']},
        'net_amount': {'type': '數值', 'description': '未稅訂單金額', 'capabilities': ['select', 'filter', 'order_by', 'group_by'],
                       'aggregations': ['sum'], 'aliases': ['未稅訂單金額']},
    }
    contract.pop('scope_rules', None)
    path.write_text(yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding='utf-8')
    catalog = SchemaCatalog(root)
    class Model:
        calls = 0
        def invoke(self, messages):
            self.calls += 1
            if '語意確認資料:' in messages[-1].content:
                context = json.loads(messages[-1].content.split('語意確認資料: ', 1)[1])
                required_terms = {item['term'] for item in context['required_terms']}
                return SimpleNamespace(content=json.dumps({'source_compatible': True,
                    'clarifications': [item for item in clarification_drafts() if item['term'] in required_terms]},
                    ensure_ascii=False))
            if 'table定義:' not in messages[-1].content:
                return SimpleNamespace(content='{"answer":"測試結果","citations":[]}')
            return SimpleNamespace(content=json.dumps({'fields': [{'text': text, 'column': column, 'aggregation': None}],
                'table': None if null_table else {'view': VIEW}, 'candidate_view': VIEW if null_table else None,
                'criteria': [], 'having': [], 'group': [], 'order': [],
                'ignored': [{'text': '含稅發票', 'reason': '模型錯誤忽略限制'}] if text == '總額' else [],
                'terms': terms or [], 'clarifications': clarification_drafts()}, ensure_ascii=False))
    settings = replace(settings, terms_mapping_path=str(root / 'terms_mapping.json'))
    return AssistantRuntime(settings, catalog=catalog, llm=Model(),
        context_packer=ContextPacker(settings, token_counter=Counter()), retriever=SchemaRetriever(settings, catalog=catalog),
        executor=executor, datasource_id='test-datasource')


def selection(response, column='order_amount'):
    from cpea.application.models.confirmation import ConfirmationRequest
    c = response.clarification
    return ConfirmationRequest(confirmation_id=c.confirmation_id, action='confirm', decisions=[
        {'item_id': item.id, 'option_id': next(o.id for o in item.options if o.column == column)} for item in c.items])
