"""離線核對兩筆模型自填決策紀錄；不呼叫模型、SQL 或資料庫。"""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from cpea.application.models.decomposition import (
    DecompositionDraft, DecompositionResponse, ExplainedDecompositionDraft,
    ExplainedDecompositionResponse, DecisionChainDecompositionDraft,
)
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decision_chain_probe import TASK, MODELS, chain_messages, finish_chained, fingerprint
from evaluations.planning_mvp import semantic_check


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


folder = TASK / '.local/decision-chain-20261020T153804Z-eea260'
meta = read(folder / 'run.json')
assert meta['calls'] == meta['completed'] == 2 and meta['stopped'] is None
for name, digest in meta['artifact_hashes'].items():
    assert sha256((folder / name).read_bytes()).hexdigest() == digest
catalog = SchemaCatalog(Path('projects/retail'))
case = next(c for c in load_decomposition_cases(
    Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog
) if c['case_id'] == meta['case_id'])
assert fingerprint(catalog, case) == meta['frozen']
baseline = read(TASK / '.local/decision-chain-baseline-schemas.json')
for cls in (DecompositionDraft, DecompositionResponse, ExplainedDecompositionDraft, ExplainedDecompositionResponse):
    assert sha256(json.dumps(cls.model_json_schema(), sort_keys=True).encode()).hexdigest() == baseline[cls.__name__]

rows = []
expected_messages = [{'role': m.type, 'content': m.content} for m in chain_messages(case['request'], catalog)]
for model in MODELS:
    request = read(folder / (model + '-request.json'))
    event = read(folder / (model + '-call.json'))
    row = read(folder / (model + '-result.json'))
    assert request['messages'] == event['messages'] == expected_messages
    draft = parse_model(SimpleNamespace(content=event['response']), DecisionChainDecompositionDraft)
    response = finish_chained(draft, catalog)
    assert row['parse_error'] is None
    assert response.model_dump() == row['response']
    assert [record.model_dump() for record in draft.decision_chain] == row['decision_chain']
    assert grade_decomposition(case, response, catalog) == row['score']
    assert semantic_check(case, response, catalog) == row['diagnostic']
    for prepared in response.prepared_requests:
        payload = json.loads(prepared.payload['request'].split('\n', 1)[1])
        assert 'decision_chain' not in payload and 'decision_summary' not in payload
    rows.append({**row, 'usage': event.get('usage'), 'elapsed_seconds': event['elapsed_seconds']})

# Immutable-run review findings, never runtime exceptions or grading overrides.
findings = {
    'first_visible_difference': 'source_selection：GPT 選 v_sales_detail；DeepSeek 選缺少通路欄位的 v_product_monthly。',
    'gpt_verdict': '安全 ready：來源具通路欄位，九月與 online 條件完整，折扣與淨銷售額按店商品加總，以庫存母體 left join；保留盤點日期、不跨日加總、不填零。',
    'deepseek_verdict': '不安全 ready：conditions 節點明說所選 View 無通路欄位，typed filters 也只有月份；卻仍生成 ready 與兩筆 prepared requests。',
    'deepseek_request_mismatch': '子任務 request 與整合 notes 仍宣稱線上通路，但實際送往下游的 typed payload 缺 sales_channel 條件，所選來源亦無該欄位。',
    'diagnostic_limit': 'GPT 原 sidecar 因自由文字 missing_data_policy 仍標記需獨立審核；主 agent 核對完整缺值文字及契約後判安全。原 sidecar 和自動分完整保留，沒有回寫。',
    'scope': '這是公開決策紀錄的第一個差異，不能據此證明真實內部推理先後或因果。',
}
summary = {
    'artifact_result': 'PASS', 'prompt_version': meta['prompt_version'], 'case_id': case['case_id'],
    'request': case['request'], 'calls': 2, 'elapsed_seconds': meta['elapsed_seconds'],
    'same_messages': True, 'old_four_schemas_unchanged': True, 'valid_chains': '2/2',
    'raw_response_chain_score_payload_replayed': 2, 'annotations_excluded_from_sql_payloads': True,
    'runtime_ready': '2/2', 'semantic_review': {'gpt-6-sol': 'SAFE', 'DeepSeek-V4.1-Flash': 'UNSAFE'},
    'findings': findings, 'results': rows, 'raw_folder': str(folder),
    'reviewer': 'main-agent using previously independently reviewed oracle and catalog; no fresh cross-agent review',
    'verification_model_calls': 0, 'sql_db_calls': 0, 'ollama_calls': 0,
}
(TASK / 'reports/decision-chain-comparison.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

lines = [
    '# 模型自填 decision_chain 比較', '',
    '已新增診斷型別 `DecisionChainDecompositionDraft` 與 `DecisionChainDecompositionResponse`，必填 `decision_chain`，由模型自行填寫。原有四個 schema 與預設流程不變。', '',
    '六個節點各涵蓋來源、欄位角色、條件、粒度、母體及整合一次。每節點包含 `step_id`、`stage`、`decision`、`evidence`、`task_ids`、`depends_on`；程式驗證步號連續、引用真實 task、依賴只指向前置節點。依據是否正確仍須核對需求與契約。', '',
    '這是有序的公開決策紀錄，不是私有思維鏈，也不證明模型內部思考順序。決策文字及摘要只保存在診斷 response，不參與驗證判斷或下游 request 組裝。', '',
    '## 測試背景與目的', '', case['request'], '',
    '使用第 11 題確認 GPT 與 DeepSeek 是否能各填寫一次有效紀錄，並核對自述、typed 計畫及下游 payload 的一致性；不是完整語意 Gate。', '',
    '兩模型各一次，相同 messages／schema／七個 View 契約；Chat Completions、temperature=1、top_p=1、seed=42、context=16384、輸出上限4096、SDK retries=0。輸入估計10711 tokens，連同輸出與安全預留15831，符合16K。兩次合計約31秒。', '',
    '## 測試結果', '',
    '| 模型 | 六節點結構 | Runtime | 原自動分 | 主 agent 語意核對 |',
    '|---|---|---|---|---|',
]
for row in rows:
    lines.append(f"| {row['model']} | 完整有效 | {row['response']['status']} | {'PASS' if row['score']['automated_pass'] else 'FAIL'} | {summary['semantic_review'][row['model']]} |")
lines += ['', findings['first_visible_difference'], '', findings['gpt_verdict'], '',
          findings['deepseek_verdict'], '', findings['deepseek_request_mismatch'], '',
          'DeepSeek 在第 3 節點寫道：「線上通路條件因 View 契約無通路欄位而無法以 filters 表達。」此紀錄與實際 filters 都揭露需求未滿足，卻與 ready 狀態及 request 的線上通路承諾矛盾。', '',
          findings['diagnostic_limit'], '', '## 完整模型紀錄', '']
escape = lambda text: text.replace('|', '\\|').replace('\n', '<br>')
for row in rows:
    lines += ['### ' + row['model'], '',
              '| 步號／類別 | 模型決策原文 | 模型依據原文 | Task 引用 | 前置節點 |',
              '|---|---|---|---|---|']
    for record in row['decision_chain']:
        lines.append('| ' + ' | '.join([
            str(record['step_id']) + ' / ' + record['stage'], escape(record['decision']),
            '<br>'.join(escape(e) for e in record['evidence']), ', '.join(record['task_ids']),
            str(record['depends_on']),
        ]) + ' |')
    lines.append('')
lines += ['## 驗證與限制', '',
          '兩筆原始輸出在 fresh subprocess 重播：artifact hash、凍結來源／契約／題文／messages、六節點、response、payload、自動分與 sidecar 均一致；四個既有 schema SHA256 不變。相關回歸 96 passed，涵蓋缺節點、無效依賴／引用、空白依據，以及說明不得改變 payload 或放行不合法計畫。', '',
          '驗證由同一主 agent 依既有獨立 oracle 與契約核對，未新增跨 agent 審查。模型自述可能不完整或錯誤，結構通過不代表語意正確；本輪每模型只有一題，不能推論整體成功率。', '',
          '完整 typed 計畫、原分、診斷與紀錄見[機器比較資料](decision-chain-comparison.json)。原始 request／call／result 保存在本 Task 的 `.local/' + folder.name + '/`，未更動原始輸出。', '',
          '離線驗證沒有新增模型呼叫；本輪共兩次首次呼叫、零重試，沒有 SQL／DB／Ollama 呼叫。DeepSeek 完整 Gate 仍未通過。']
(TASK / 'reports/decision-chain-comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(json.dumps({k: summary[k] for k in (
    'artifact_result', 'calls', 'valid_chains', 'runtime_ready', 'semantic_review',
    'same_messages', 'old_four_schemas_unchanged',
)}, ensure_ascii=False))
