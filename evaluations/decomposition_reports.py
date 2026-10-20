"""Separate benchmark counts from unverified integration/request semantics."""
from collections import defaultdict
import json


def summarize(results,*,planned,runs):
    groups=defaultdict(list)
    completed=[r for r in results if r['status']=='completed']
    for row in completed:groups[row['case_id']].append(row)
    all_pass=consistent_failure=0
    for rows in groups.values():
        if len(rows)!=runs:continue
        passed=[row['score']['automated_pass'] for row in rows]
        all_pass+=all(passed)
        consistent_failure+=not any(passed) and len({r['response']['status'] for r in rows})==1
    return {'planned':planned,'completed':len(completed),'failed':sum(r['status']=='failed' for r in results),
            'ready_responses':sum(r['response']['status']=='ready' for r in completed),
            'skipped':sum(r['status']=='skipped' for r in results),
            'automated_pass_count':sum(r['score']['automated_pass'] for r in completed),
            'canonical_views_match_count':sum(r['score'].get('canonical_views_match',False) for r in completed),
            'views_and_columns_match_count':sum(r['score'].get('views_and_columns_match',False) for r in completed),
            'equivalent_tasks_match_count':sum(r['score'].get('equivalent_tasks_match',False) for r in completed),
            'all_runs_pass_cases':all_pass,'consistent_failure_cases':consistent_failure,
            'semantic_review_required':True}


def write_reports(output,cases,results,metadata):
    summary=summarize(results,planned=metadata['planned'],runs=metadata['runs'])
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Retail 需求拆分 benchmark','',f"模型：`{metadata['model']}`；模式：{'探索性' if metadata['exploratory'] else '已核准題庫'}。",
           f"預定 {summary['planned']} 題次；完成 {summary['completed']}；provider 失敗 {summary['failed']}；略過 {summary['skipped']}。",
           f"自動結構檢查通過 {summary['automated_pass_count']}/{summary['planned']}；主要 View 命中 {summary['canonical_views_match_count']}；等價任務正確 {summary['equivalent_tasks_match_count']}。",
           f"符合來源與必要欄位的題次：{summary['views_and_columns_match_count']}/{summary['planned']}。",
           f"通過 planner 驗證並準備 requests 的題次：{summary['ready_responses']}/{summary['planned']}。來源選擇評分包含被 validator 拒絕之草稿，不能等同 request 已就緒。",
           f"每輪皆通過的案例 {summary['all_runs_pass_cases']}/{len(cases)}；狀態一致但失敗的案例 {summary['consistent_failure_cases']}。",'',
           '本次只準備 text-to-sql requests，沒有生成或執行 SQL。自動結構評分不代表 request、整合語意已經人工審核通過。','',
           '| 案例 | 輪次 | 狀態 | 自動檢查 |','|---|---:|---|---|']
    for row in results:lines.append(f"| {row['case_id']} | {row['run']+1} | {row['status']} | {row.get('score',{}).get('automated_pass','未完成')} |")
    (output/'overview.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def regrade_run(run_dir,*,profile,cases_path,revalidate=False):
    """Re-evaluate saved responses without modifying the original run or calling a model."""
    from datetime import datetime,timezone
    from hashlib import sha256
    from uuid import uuid4
    import subprocess
    from cpea.application.models.decomposition import DecompositionResponse
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    from evaluations.decomposition_cases import load_decomposition_cases
    from evaluations.decomposition_grading import grade_decomposition
    from cpea.workflows.task_decomposition.validation import validate_decomposition,prepare_requests
    metadata=json.loads((run_dir/'run.json').read_text(encoding='utf-8'))
    if not metadata.get('finished_at'):
        raise ValueError('cannot regrade an unfinished run')
    catalog=SchemaCatalog(profile)
    if catalog.fingerprint!=metadata['contract_fingerprint'] or sha256(cases_path.read_bytes()).hexdigest()!=metadata['casefile_sha256']:
        raise ValueError('regrading requires the original contract and casefile')
    cases=load_decomposition_cases(cases_path,catalog);by_id={c['case_id']:c for c in cases}
    results=[json.loads(line) for line in (run_dir/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(results)!=metadata['planned']:
        raise ValueError('source run has incomplete result records')
    for row in results:
        if row['status']=='completed':
            response=DecompositionResponse.model_validate(row['response'])
            if revalidate and response.draft and response.draft.status=='ready':
                errors=validate_decomposition(response.draft,catalog)
                row['source_response_status']=response.status
                payloads=[]
                if not errors:
                    try:payloads=prepare_requests(response.draft,catalog)
                    except ValueError as exc:errors=[str(exc)]
                response=DecompositionResponse(status='error' if errors else 'ready',
                    code='invalid_plan' if errors else None,draft=response.draft,
                    prepared_requests=payloads,validation_errors=errors,
                    contract_fingerprint=response.contract_fingerprint,
                    context_tokens=response.context_tokens,token_counter=response.token_counter)
                row['response']=response.model_dump()
            row['score']=grade_decomposition(by_id[row['case_id']],response,catalog)
    destination=run_dir.parent/(run_dir.name+'-regrade-'+uuid4().hex[:6]);destination.mkdir(mode=0o700)
    metadata.update(source_run=str(run_dir.resolve()),source_results_sha256=sha256((run_dir/'results.jsonl').read_bytes()).hexdigest(),
                    grading_revision=subprocess.run(['git','rev-parse','HEAD'],text=True,capture_output=True,check=True).stdout.strip(),
                    regraded_at=datetime.now(timezone.utc).isoformat(),additional_model_calls=0,
                    revalidated=revalidate,
                    changed_status_count=sum(r.get('source_response_status',r.get('response',{}).get('status'))!=r.get('response',{}).get('status') for r in results))
    metadata.update(summarize(results,planned=metadata['planned'],runs=metadata['runs']))
    (destination/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results),encoding='utf-8')
    (destination/'run.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_reports(destination,cases,results,metadata)
    return destination
