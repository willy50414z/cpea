import json
from pathlib import Path
import pytest
from tests.decomposition_support import FakeLLM,catalog_at
from tests.unit.test_decomposition_evaluation import case_for


def workspace(tmp_path):
    from evaluations.decomposition_cases import case_sha256
    catalog=catalog_at(tmp_path/'retail');c=case_for(catalog)
    cases=[]
    for n in range(30):
        row={**c,'case_id':f'case-{n}'};row['case_sha256']=case_sha256(row);cases.append(row)
    p=tmp_path/'retail/evaluations';p.mkdir()
    (p/'task_decomposition_cases.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in cases),encoding='utf-8')
    env=tmp_path/'.env';env.write_text('ASSISTANT_LLM_PROVIDER=ollama\nASSISTANT_LLM_MODEL=local\nCPEA_AZURE_LLM_BASE_URL=https://azure.example\nCPEA_AZURE_LLM_API_KEY=synthetic-secret\nASSISTANT_LLM_NUM_CTX=64000\nASSISTANT_LLM_NUM_PREDICT=8000\n',encoding='utf-8')
    return catalog,env,p/'task_decomposition_cases.jsonl'


def test_runner_overrides_ollama_uses_root_azure_and_no_model_cap(tmp_path):
    from evaluations.decomposition_runner import evaluate_decomposition
    catalog,env,cases=workspace(tmp_path);llm=FakeLLM();observed=[]
    def factory(settings):observed.append(settings);return llm
    result=evaluate_decomposition(profile=catalog.root,env_file=env,model='gpt-6-sol',cases_path=cases,
                                  runs=3,exploratory=True,llm_factory=factory)
    assert len(llm.calls)==90 and result['model_calls']==90
    assert observed[0].llm_provider=='azure' and observed[0].llm_model=='gpt-6-sol'
    assert not observed[0].sqlserver.enabled
    output=Path(result['output']);metadata=json.loads((output/'run.json').read_text(encoding='utf-8'))
    assert metadata['max_model_calls'] is None and metadata['planned']==90
    assert metadata['casefile_sha256'] and metadata['prompt_sha256'] and metadata['schema_sha256']
    assert 'synthetic-secret' not in (output/'run.json').read_text(encoding='utf-8')


def test_pending_cases_require_exploratory(tmp_path):
    from evaluations.decomposition_runner import evaluate_decomposition
    catalog,env,cases=workspace(tmp_path)
    with pytest.raises(ValueError,match='approved'):
        evaluate_decomposition(profile=catalog.root,env_file=env,model='gpt-6-sol',cases_path=cases,llm_factory=lambda s:FakeLLM())


def test_provider_error_records_trigger_and_skips_without_retry(tmp_path):
    from evaluations.decomposition_runner import evaluate_decomposition
    catalog,env,cases=workspace(tmp_path);llm=FakeLLM(error=RuntimeError('429 rate limit synthetic-secret'))
    result=evaluate_decomposition(profile=catalog.root,env_file=env,model='gpt-6-sol',cases_path=cases,
                                  exploratory=True,llm_factory=lambda s:llm)
    assert result['model_calls']==1 and len(llm.calls)==1
    assert result['failed']==1 and result['skipped']==29
    public=(Path(result['output'])/'overview.md').read_text(encoding='utf-8')
    assert 'synthetic-secret' not in public


def test_endpoint_normalization_is_idempotent(tmp_path):
    from evaluations.decomposition_runner import azure_planning_settings
    _,env,_=workspace(tmp_path)
    assert azure_planning_settings(env,'gpt-6-sol').llm_base_url=='https://azure.example/openai/v1'
    with env.open('a',encoding='utf-8') as f:f.write('CPEA_AZURE_LLM_BASE_URL=https://azure.example/openai/v1/\n')
    assert azure_planning_settings(env,'gpt-6-sol').llm_base_url=='https://azure.example/openai/v1'


def test_regrade_preserves_original_and_makes_no_model_calls(tmp_path):
    from evaluations.decomposition_runner import evaluate_decomposition
    from evaluations.decomposition_reports import regrade_run
    catalog,env,cases=workspace(tmp_path);llm=FakeLLM()
    result=evaluate_decomposition(profile=catalog.root,env_file=env,model='gpt-6-sol',cases_path=cases,
                                  exploratory=True,llm_factory=lambda s:llm)
    source=Path(result['output']);before=(source/'results.jsonl').read_bytes()
    target=regrade_run(source,profile=catalog.root,cases_path=cases,revalidate=True)
    assert source!=target and len(llm.calls)==30
    assert (source/'results.jsonl').read_bytes()==before
    meta=json.loads((target/'run.json').read_text(encoding='utf-8'))
    assert meta['additional_model_calls']==0 and meta['source_results_sha256']
    assert meta['revalidated'] and meta['changed_status_count']==0
    assert all(meta[key] for key in ('grading_code_sha256','validation_code_sha256','response_models_sha256','grading_diff_sha256'))


def test_installed_runner_finds_workspace_git_not_site_packages(tmp_path,monkeypatch):
    import evaluations.decomposition_runner as module
    catalog,env,cases=workspace(tmp_path)
    monkeypatch.setattr(module,'__file__',str(tmp_path/'site-packages/evaluations/decomposition_runner.py'))
    result=module.evaluate_decomposition(profile=catalog.root,env_file=env,model='gpt-6-sol',cases_path=cases,
                                        exploratory=True,llm_factory=lambda s:FakeLLM())
    assert result['model_calls']==30
