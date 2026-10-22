"""離線核對來源選擇事後說明並保存報告，沒有模型或 DB 呼叫。"""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.source_selection_followup import BASE, TASK, MODELS, QUESTION, SourceSelectionReason, messages_for


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


folder = TASK / '.local/source-reasons-20261020T155003Z-1cfda9'
meta = read(folder / 'run.json')
assert meta['calls'] == meta['completed'] == 2 and meta['stopped'] is None
assert sha256((BASE / 'run.json').read_bytes()).hexdigest() == meta['base_run_sha256']
assert sha256((ROOT / 'evaluations/source_selection_followup.py').read_bytes()).hexdigest() == meta['runner_sha256']
for source, hashes in ((folder, meta['artifact_hashes']), (BASE, read(BASE / 'run.json')['artifact_hashes'])):
    for name, digest in hashes.items():
        assert sha256((source / name).read_bytes()).hexdigest() == digest
rows = []
contexts = []
for model in MODELS:
    event = read(folder / (model + '-call.json'))
    request = read(folder / (model + '-request.json'))
    row = read(folder / (model + '-result.json'))
    assert request['messages'] == event['messages'] == [{'role': m.type, 'content': m.content} for m in messages_for(model)]
    parsed = parse_model(SimpleNamespace(content=event['response']), SourceSelectionReason)
    assert row['parse_error'] is None and parsed.model_dump() == row['reason']
    prior = read(BASE / (model + '-result.json'))
    assert parsed.originally_selected_sales_view in {t['view'] for t in prior['response']['draft']['tasks']}
    context = json.loads(event['messages'][1]['content'])
    assert context.pop('previous_model_response') == json.loads(read(BASE / (model + '-call.json'))['response'])
    contexts.append(context)
    rows.append(row)
assert contexts[0] == contexts[1]

report = {'artifact_result': 'PASS', 'purpose': '事後來源選擇說明，非重新規劃或首次驗收',
          'question': QUESTION, 'calls': 2, 'elapsed_seconds': meta['elapsed_seconds'],
          'same_request_contract_question': True, 'each_model_sees_only_own_prior_response': True,
          'original_artifacts_unchanged': True, 'parsed_replays': 2, 'results': rows,
          'raw_folder': str(folder), 'verification_model_calls': 0, 'sql_db_calls': 0, 'ollama_calls': 0,
          'reviewer': '同一主 agent 依 View 契約核對，沒有新增獨立 reviewer',
          'interpretation': 'GPT 自述優先確保月份、通路、金額等需求均能表達；DeepSeek 自述月表粒度貼近需求且較直接，但承認缺通路欄位而未滿足需求。事後理由不能證明首次內部思考或因果。'}
(TASK / 'reports/source-selection-reasons.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
lines = ['# 銷售來源選擇理由：模型追加回覆', '',
         '原需求：對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。', '',
         '依使用者要求，GPT 與 DeepSeek 各追加一次詢問，提供原需求、完整七個 View 契約與各自上一份原始回覆；沒有提供另一模型輸出或評分回饋。兩模型使用相同問題與契約，但各自看到的上一份回覆不同。', '',
         '這是事後的簡短決策說明，不是首次生成時的內部思維紀錄。原計畫、ready 狀態與原分數沒有更新；DeepSeek 承認問題不計為首次成功。', '',
         '## 共同追加問題', '', '> ' + QUESTION, '', '## 模型原文', '']
for row in rows:
    r = row['reason']
    lines += ['### ' + row['model'], '', '**原選擇**：`' + r['originally_selected_sales_view'] + '`', '',
              '**選擇理由**：' + r['selection_reason'], '', '**契約依據**：', '']
    lines += ['- ' + item for item in r['contract_evidence']]
    lines += ['', '**另一來源比較**：' + r['alternative_comparison'], '',
              '**能否滿足線上通路條件**：' + ('能' if r['fulfills_online_condition'] else '不能'), '',
              '**限制**：' + r['limitation'], '']
lines += ['## 核對結果', '', report['interpretation'], '',
          '契約確認 `v_sales_detail` 有 `order_month`、`sales_channel`、`discount_amount`、`net_sales`；`v_product_monthly` 有月份及兩項金額，但沒有 `sales_channel`。原 DeepSeek typed filters 只有月份，仍不符合指定通路。', '',
          '兩次追加呼叫均取得有效 JSON；fresh subprocess 核對 request、raw、schema 解析、前次輸出與 artifact hash 一致。temperature=1、top_p=1、seed=42、輸出上限1536、context=16384、SDK retries=0；合計約12秒。沒有重做規劃、SQL／DB／Ollama 呼叫。', '',
          '本輪只新增診斷詢問腳本與報告，未修改產品模型或規則。完整模型文字見[機器資料](source-selection-reasons.json)，原始 request／call／result 位於本 Task 的 `.local/' + folder.name + '/`。']
(TASK / 'reports/source-selection-reasons.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(json.dumps({k: report[k] for k in ('artifact_result', 'calls', 'parsed_replays', 'original_artifacts_unchanged')}, ensure_ascii=False))
