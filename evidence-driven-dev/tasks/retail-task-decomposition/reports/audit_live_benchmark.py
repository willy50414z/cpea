"""Audit saved real calls and replay deterministic planning without a model client."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from cpea.application.models.decomposition import DecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_reports import regrade_run


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-run',required=True,type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[4]
    profile=root/'projects/retail'
    cases_path=profile/'evaluations/task_decomposition_cases.jsonl'
    catalog=SchemaCatalog(profile)
    cases=load_decomposition_cases(cases_path,catalog)
    by_id={c['case_id']:c for c in cases}
    source=args.source_run.resolve()
    original={p.name:sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
    metadata=json.loads((source/'run.json').read_text(encoding='utf-8'))
    assert metadata['finished_at'] and metadata['model']=='gpt-6-sol'
    assert metadata['max_model_calls'] is None and metadata['sdk_retries']==0
    calls=[json.loads(l) for l in (source/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    rows=[json.loads(l) for l in (source/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(cases)==30 and metadata['runs']==3 and len(calls)==len(rows)==metadata['model_calls']==90
    assert len({(r['case_id'],r['run']) for r in calls})==90
    assert all(r['status']=='completed' for r in rows)
    row_index={(r['case_id'],r['run']):r for r in rows}
    usage=Counter();parsable=0
    for call in calls:
        assert 'error' not in call
        assert call['messages'][0]['content']==DECOMPOSITION_PROMPT
        context=json.loads(call['messages'][1]['content'])
        assert set(context)=={'request','views','response_schema'}
        assert context['request']==by_id[call['case_id']]['request']
        assert context['response_schema']==DecompositionDraft.model_json_schema()
        assert context['views']==[{'view':v.name,**v.policy} for v in catalog.views()]
        try:
            parsed=parse_model(SimpleNamespace(content=call['response']),DecompositionDraft)
        except (ValueError,TypeError):
            assert row_index[(call['case_id'],call['run'])]['response']['code']=='invalid_model_response'
        else:
            parsable+=1
            assert parsed.model_dump()==row_index[(call['case_id'],call['run'])]['response']['draft']
        if call.get('usage'):
            usage['reported_calls']+=1
            for key in ('input_tokens','output_tokens','total_tokens'):
                if isinstance(call['usage'].get(key),int):usage[key]+=call['usage'][key]
    destination=regrade_run(source,profile=profile,cases_path=cases_path,revalidate=True)
    assert original=={p.name:sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
    summary=json.loads((destination/'summary.json').read_text(encoding='utf-8'))
    replay_meta=json.loads((destination/'run.json').read_text(encoding='utf-8'))
    assert replay_meta['additional_model_calls']==0 and replay_meta['revalidated']
    replay=[json.loads(l) for l in (destination/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    grouped=defaultdict(list)
    missing=defaultdict(set)
    for row in replay:
        grouped[row['case_id']].append(row)
        for expected,score in zip(by_id[row['case_id']]['expected_tasks'],row['score'].get('task_scores',[])):
            if not score['columns']:
                actual=next((t for t in (row['response'].get('draft') or {}).get('tasks',[]) if t['view']==expected['view']),None)
                if actual:missing[row['case_id']].update(set(expected['required_columns'])-set(actual['required_columns']))
    stable={key:sum(len(v)==3 and all(row['score'].get(flag,False) for row in v) for v in grouped.values())
            for key,flag in [('views','canonical_views_match'),('views_and_columns','views_and_columns_match'),('payload_ready','payload_ready')]}
    result={'source_run':str(source),'regraded_run':str(destination),'source_revision':metadata['revision'],
            'grading_revision':replay_meta['grading_revision'],'model':'gpt-6-sol','real_model_calls':90,
            'additional_model_calls':0,'parsable_responses':parsable,'usage':dict(usage),'summary':summary,
            'stable_cases':stable,'missing_required_columns':{k:sorted(v) for k,v in missing.items()},
            'changed_status_count':replay_meta['changed_status_count'],'original_run_unchanged':True,
            'prompt_schema_contract_oracle_isolation':'PASS'}
    report=Path(__file__).parent/'live-benchmark-audit.json'
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Retail 任務拆分實測結果','',
           '使用 Azure `gpt-6-sol`、根目錄 `.env` 的 Azure 專用連線資訊。30 個跨 View 需求各跑三次，共 90 次真實模型呼叫；不設模型呼叫次數上限，無隱藏重試。未生成或執行 SQL。','',
           '| 指標 | 題次／案例 |','|---|---:|',
           f"| 預期主要 View 選擇 | {summary['canonical_views_match_count']}/90 |",
           f"| 來源與必要欄位完整涵蓋 | {summary['views_and_columns_match_count']}/90 |",
           f"| 現行 validator 通過並準備 request | {summary['ready_responses']}/90 |",
           f"| 條件、聚合、粒度、整合鍵等自動結構檢查全通過 | {summary['automated_pass_count']}/90 |",
           f"| 三次皆選對 View | {stable['views']}/30 |",
           f"| 三次皆涵蓋必要欄位 | {stable['views_and_columns']}/30 |",
           f"| 三次皆準備 request | {stable['payload_ready']}/30 |",'',
           '## 方法與可重現性','',
           f"原始模型呼叫使用 `{metadata['revision']}` 的已載入規劃程式；實測期間修補離線評分及 deterministic 驗證，沒有改動生成 prompt、response schema 或 View 契約。90 次 request 已逐一比對目前 prompt/schema/契約及題目，沒有把預期答案或案例 metadata 放入模型 context。",
           f"以 `{replay_meta['grading_revision']}` 的驗證器與評分器重播保存草稿，額外模型呼叫 0 次，原始 run 所有檔案 SHA-256 維持不變；{replay_meta['changed_status_count']} 題次的 ready/error 狀態因驗證修補改變。重評產物另存 source results、grader、validator 及 models SHA-256。",
           '原始實測與現行版本重播分開保存，不將舊程式的結果冒稱為新版本 live 呼叫。題庫人工審核皆為 pending，本次屬探索性 benchmark；自動正確不等於完整業務語意、資料整合或 SQL 正確。','',
           f"原始產物：`{source}`。",f"重播／重評產物：`{destination}`。",'',
           '## 必要欄位差異','', '| 案例 | 至少一次遺漏的主要來源必要欄位 |','|---|---|']
    for key,fields in sorted(missing.items()):lines.append(f"| {key} | {', '.join(fields)} |")
    lines.extend(['','必要欄位依原始題庫標註判斷，未因模型輸出修改答案；部分差異是快照時間 metadata。日期 filter 的月份／日期等價表示與可由唯一鍵證明的單列／計數等價已由一般規則處理。額外 grain 或其他語意差異仍需審核，不能只看 View 命中率。','',
                  '## 驗證界線','',
                  '- 已新增獨立前置規劃服務及 benchmark CLI，既有單 View 網頁與 SQL API 尚未自動串接。',
                  '- 不驗證實際 SQL、資料數值、DB 權限、真正合併結果或採購決策。',
                  '- 真實呼叫失敗或限流不重跑；本次 completed/failed/skipped 以 run metadata 為準。',
                  '- 獨立 code review 與負面重播為 PASS_WITH_WARNINGS；自然語言 request 與整合語意仍需人工審核。',''])
    (Path(__file__).parent/'benchmark-results.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
