import pytest
from pydantic import ValidationError

from cpea.application.models.decomposition import (
    DecisionChainDecompositionDraft, ExplainedDecompositionDraft,
)
from evaluations.decision_chain_probe import chain_messages, finish_chained
from tests.decomposition_support import catalog_at, draft
from tests.unit.test_decomposition_decision_summary import summary


def chain():
    return [dict(step_id=i,stage=stage,decision='此節點的簡短決策。',
                 evidence=['需求指定目前庫存與九月銷量。'],task_ids=['stock','sales'],
                 depends_on=[] if i==1 else [i-1])
            for i,stage in enumerate(('source_selection','field_roles','conditions','grain','population','integration'),1)]


def data():
    return {**draft(),'decision_summary':summary(),'decision_chain':chain()}


def test_decision_chain_is_required_only_in_the_new_diagnostic_schema():
    assert 'decision_chain' not in ExplainedDecompositionDraft.model_json_schema()['properties']
    with pytest.raises(ValidationError):
        DecisionChainDecompositionDraft.model_validate({**draft(),'decision_summary':summary()})


@pytest.mark.parametrize('corruption',['self','forward','duplicate_id','missing_stage','unknown_task','blank_evidence'])
def test_rejects_invalid_chain_references_and_incomplete_evidence(corruption):
    d=data()
    if corruption=='self':d['decision_chain'][0]['depends_on']=[1]
    elif corruption=='forward':d['decision_chain'][0]['depends_on']=[2]
    elif corruption=='duplicate_id':d['decision_chain'][1]['step_id']=1
    elif corruption=='missing_stage':d['decision_chain'][-1]['stage']='population'
    elif corruption=='unknown_task':d['decision_chain'][0]['task_ids']=['not_a_task']
    else:d['decision_chain'][0]['evidence']=['  ']
    with pytest.raises(ValidationError):DecisionChainDecompositionDraft.model_validate(d)


def test_chain_is_retained_but_cannot_change_dispatch_payloads(tmp_path):
    a=DecisionChainDecompositionDraft.model_validate(data());b=a.model_copy(deep=True)
    b.decision_chain[0].decision='另一份模型決策紀錄。'
    catalog=catalog_at(tmp_path)
    first,second=finish_chained(a,catalog),finish_chained(b,catalog)
    assert first.status==second.status=='ready'
    assert first.prepared_requests==second.prepared_requests
    assert first.model_dump()['decision_chain']==chain()
    assert 'decision_chain' not in first.model_dump()['draft']


def test_invalid_plan_stays_blocked_even_with_a_valid_chain(tmp_path):
    d=data();d['tasks'][1]['metrics']={'invented_count':'count'}
    r=finish_chained(DecisionChainDecompositionDraft.model_validate(d),catalog_at(tmp_path))
    assert r.status=='error' and not r.prepared_requests and len(r.decision_chain)==6


def test_prompt_explicitly_requests_the_model_to_fill_the_chain(tmp_path):
    msgs=chain_messages('QUESTION_SENTINEL',catalog_at(tmp_path))
    text='\n'.join(m.content for m in msgs)
    assert 'decision_chain' in text and 'depends_on' in text and 'evidence' in text
    assert 'QUESTION_SENTINEL' in text and 'expected_tasks' not in text and 'case_id' not in text
