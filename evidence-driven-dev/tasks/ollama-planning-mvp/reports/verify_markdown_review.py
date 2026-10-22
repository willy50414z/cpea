"""離線核對 Markdown planner 與獨立 evidence reviewer 的兩筆輸出。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from cpea.application.models import decomposition as models
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT, DECOMPOSITION_PROMPT_VERSION
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decision_chain_probe import finish_chained, fingerprint
from evaluations.decision_summary_comparison import TASK
from evaluations.markdown_review_probe import (
    PROMPTS, EvidenceReview, planner_messages, reviewer_messages, validate_review_references,
)
from evaluations.planning_mvp import semantic_check


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


folder = TASK / '.local/markdown-review-20261020T161155Z-4d197a'
meta = read(folder / 'run.json')
assert meta['calls'] == meta['completed'] == 2 and meta['stopped'] is None
for name, digest in meta['artifact_hashes'].items():
    assert sha256((folder / name).read_bytes()).hexdigest() == digest
assert meta['runner_sha256'] == sha256((ROOT / 'evaluations/markdown_review_probe.py').read_bytes()).hexdigest()
assert meta['prompt_hashes'] == {p.name: sha256(p.read_bytes()).hexdigest() for p in PROMPTS.glob('*.md')}
assert (PROMPTS / 'coverage_first_planner.md').read_text(encoding='utf-8').startswith('# 最高優先規則：完整涵蓋需求\n')
assert (PROMPTS / 'evidence_reviewer.md').read_text(encoding='utf-8').startswith('# 最高優先規則：決策須有完整證據\n')
for cls in (models.DecisionChainDecompositionDraft, EvidenceReview):
    assert sha256(json.dumps(cls.model_json_schema(), sort_keys=True).encode()).hexdigest() == meta['schema_hashes'][cls.__name__]
for name, digest in read(TASK / '.local/decision-chain-baseline-schemas.json').items():
    assert sha256(json.dumps(getattr(models, name).model_json_schema(), sort_keys=True).encode()).hexdigest() == digest
old_source = subprocess.run(['git', 'show', 'HEAD:src/cpea/workflows/task_decomposition/prompt.py'], capture_output=True, text=True, encoding='utf-8', check=True).stdout
old = {}
exec(old_source, old)
assert old['DECOMPOSITION_PROMPT'] == DECOMPOSITION_PROMPT and old['DECOMPOSITION_PROMPT_VERSION'] == DECOMPOSITION_PROMPT_VERSION
catalog = SchemaCatalog(Path('projects/retail'))
case = next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog) if c['case_id'] == meta['case_id'])
assert meta['frozen'] == fingerprint(catalog, case)
planner_call = read(folder / 'planner-call.json')
planner_row = read(folder / 'planner-result.json')
assert planner_row['parse_error'] is None
draft = parse_model(SimpleNamespace(content=planner_call['response']), models.DecisionChainDecompositionDraft)
response = finish_chained(draft, catalog)
assert response.model_dump() == planner_row['response']
assert grade_decomposition(case, response, catalog) == planner_row['score']
assert semantic_check(case, response, catalog) == planner_row['diagnostic']
reviewer_call = read(folder / 'reviewer-call.json')
reviewer_row = read(folder / 'reviewer-result.json')
assert reviewer_row['parse_error'] is None
review = validate_review_references(parse_model(SimpleNamespace(content=reviewer_call['response']), EvidenceReview), draft)
assert review.model_dump() == reviewer_row['review']
for phase, event, messages in [
    ('planner', planner_call, planner_messages(case['request'], catalog)),
    ('reviewer', reviewer_call, reviewer_messages(case['request'], catalog, json.loads(planner_call['response']), [p.model_dump() for p in response.prepared_requests])),
]:
    expected = [{'role': m.type, 'content': m.content} for m in messages]
    assert event['messages'] == read(folder / (phase + '-request.json'))['messages'] == expected
    context = json.loads(event['messages'][1]['content'])
    assert not {'expected_tasks', 'score', 'diagnostic', 'validation_errors'} & context.keys()
    assert len(event['messages']) == 2
    assert context['request'] == case['request']
    assert all('decision_chain' not in json.loads(p.payload['request'].split('\n', 1)[1]) for p in response.prepared_requests)

report = {
    'artifact_result': 'PASS', 'prompt_version': meta['prompt_version'], 'request': case['request'],
    'calls': 2, 'model': meta['model'], 'elapsed_seconds': meta['elapsed_seconds'],
    'input_tokens_estimated': meta['input_tokens_estimated'],
    'planner_semantic_result': 'FAIL', 'planner_runtime_status': response.status,
    'reviewer_verdict': review.verdict, 'reviewer_assessment': 'PASS_WITH_WARNINGS',
    'confirmed_finding': '決策1/3引用月表不存在的sales_channel；typed欄位與filter同樣使用該欄位，違反來源契約。第二模型已指出並reject。',
    'reviewer_limitations': [
        '第二項blocking對門市識別碼語意的額外懷疑未有獨立證據，不採為新增阻擋理由；核心通路缺口已由第一項涵蓋。',
        '盤點日期不保證全球最新是資料時間限制，但不能推成同店商品有多列，亦不能自動新增日期filter刪除庫存母體；來源鍵仍為店×商品。',
        '部分plan_references是task_id索引簡寫；planner_output.notes路徑不存在，decision_chain索引亦有步號與陣列位置混用。程式只驗證task/step引用存在，不宣稱所有文字路徑精確。',
        '同模型的新對話審查不等於獨立oracle；單題一次且沒有自動repair，未驗證對正確計畫的誤拒率。',
    ],
    'raw_replays': 2, 'v3_default_unchanged': True, 'old_four_schemas_unchanged': True,
    'reviewer_has_no_oracle_or_grade_feedback': True, 'planner_result': planner_row,
    'reviewer_result': reviewer_row, 'raw_folder': str(folder),
    'reviewer': '主agent依既有獨立oracle及完整契約核對，未新增跨agent驗收',
    'verification_model_calls': 0, 'sql_db_calls': 0, 'ollama_calls': 0,
}
(TASK / 'reports/markdown-evidence-review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: report[k] for k in ('artifact_result', 'calls', 'planner_semantic_result', 'reviewer_verdict', 'reviewer_assessment', 'elapsed_seconds')}, ensure_ascii=False))
