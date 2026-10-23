import json
import pytest


@pytest.mark.parametrize('results', [[], [{'table_name':'bad','table_contents':{'columns':['id']}}],
    [{'table_name':'a','table_contents':{'columns':[]}}],
    [{'table_name':'a','table_contents':{'columns':['missing']}}],
    [{'table_name':'a','table_contents':{'columns':['id','id']}}],
    [{'table_name':'a','table_contents':{'columns':['id']}}]*2])
def test_pruning_rejects_raw_invalid_selection(results):
    from native_worker.guards import validate_selection
    with pytest.raises(ValueError):
        validate_selection({'results':results}, {'models':[{'name':'a','columns':[{'name':'id'}]}]})


def test_budget_counts_rendered_system_user_and_response_schema():
    from native_worker.guards import Budget
    budget=Budget(context_window=100,output_reserve=10,safety=5,encoding='cl100k_base')
    with pytest.raises(ValueError,match='context_budget'):
        budget.check([{'role':'system','content':'x '*150}], {'response_format':{'schema':{'description':'y '*150}}})


def test_manifest_refuses_half_index_and_detects_content_drift(tmp_path):
    from native_worker.generation import Generation
    g=Generation(tmp_path, {'identity':'a'*64,'project_id':'a'*64,'namespace':'cpea_wrenai_'+ 'a'*24})
    with g.lock():
        g.building()
        with pytest.raises(ValueError,match='not_ready'): g.verify({'Document':{'count':1,'digest':'x'},'table_descriptions':{'count':1,'digest':'y'}})
        actual={'Document':{'count':1,'digest':'x'},'table_descriptions':{'count':1,'digest':'y'}}
        g.ready(actual)
        assert g.verify(actual)
        with pytest.raises(ValueError,match='index_drift'): g.verify({**actual,'Document':{'count':1,'digest':'bad'}})


def test_manifest_lock_excludes_second_writer(tmp_path):
    from native_worker.generation import Generation
    g=Generation(tmp_path,{'identity':'a'*64,'project_id':'a'*64,'namespace':'cpea_wrenai_'+ 'a'*24})
    with g.lock():
        with pytest.raises(TimeoutError):
            with g.lock(): pass


def test_corrupt_generation_recovers_as_failed(tmp_path):
    from native_worker.generation import Generation
    g=Generation(tmp_path,{'identity':'a'*64,'project_id':'a'*64,'namespace':'cpea_wrenai_'+ 'a'*24})
    g.path.write_text('{"status":',encoding='utf-8')
    assert g.state()['status']=='failed'
    g.building()
    assert g.state()['status']=='building'


@pytest.mark.parametrize('drift',['head','dirty'])
def test_runtime_rejects_upstream_head_or_dirty_drift(monkeypatch,drift):
    from native_worker import source
    service=__import__('pathlib').Path(__file__).resolve().parents[1]/'.runtime/upstream/wren-ai-service'
    def command(args,**kwargs):
        if 'rev-parse' in args: return 'bad' if drift=='head' else source.UPSTREAM_SHA
        return ' M wren-ai-service/src/core/pipeline.py' if drift=='dirty' else ''
    monkeypatch.setattr(source.subprocess,'check_output',command)
    with pytest.raises(ValueError,match='upstream_source_drift'): source.verify_checkout(service)
