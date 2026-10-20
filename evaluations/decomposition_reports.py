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
            'skipped':sum(r['status']=='skipped' for r in results),
            'automated_pass_count':sum(r['score']['automated_pass'] for r in completed),
            'canonical_views_match_count':sum(r['score'].get('canonical_views_match',False) for r in completed),
            'equivalent_tasks_match_count':sum(r['score'].get('equivalent_tasks_match',False) for r in completed),
            'all_runs_pass_cases':all_pass,'consistent_failure_cases':consistent_failure,
            'semantic_review_required':True}


def write_reports(output,cases,results,metadata):
    summary=summarize(results,planned=metadata['planned'],runs=metadata['runs'])
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Retail 需求拆分 benchmark','',f"模型：`{metadata['model']}`；模式：{'探索性' if metadata['exploratory'] else '已核准題庫'}。",
           f"預定 {summary['planned']} 題次；完成 {summary['completed']}；provider 失敗 {summary['failed']}；略過 {summary['skipped']}。",
           f"自動結構檢查通過 {summary['automated_pass_count']}/{summary['planned']}；主要 View 命中 {summary['canonical_views_match_count']}；等價任務正確 {summary['equivalent_tasks_match_count']}。",
           f"每輪皆通過的案例 {summary['all_runs_pass_cases']}/{len(cases)}；狀態一致但失敗的案例 {summary['consistent_failure_cases']}。",'',
           '本次只準備 text-to-sql requests，沒有生成或執行 SQL。自動結構評分不代表 request、整合語意已經人工審核通過。','',
           '| 案例 | 輪次 | 狀態 | 自動檢查 |','|---|---:|---|---|']
    for row in results:lines.append(f"| {row['case_id']} | {row['run']+1} | {row['status']} | {row.get('score',{}).get('automated_pass','未完成')} |")
    (output/'overview.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
