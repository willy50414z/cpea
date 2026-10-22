import pytest
from pydantic import ValidationError

from cpea.application.models.decomposition import DecisionChainDecompositionDraft
from evaluations.markdown_review_probe import EvidenceReview, validate_review_references
from tests.unit.test_decomposition_decision_chain import data


def review_data():
    return {
        'verdict': 'reject',
        'summary': '必要條件尚無來源依據。',
        'checks': [{
            'requirement': '保留指定條件', 'decision_step_ids': [1, 3], 'task_ids': ['sales'],
            'contract_references': ['來源契約沒有該條件欄位。'],
            'plan_references': ['tasks[1].filters'], 'status': 'missing',
            'missing_evidence': '缺少能支援指定條件的來源及 filter。',
        }],
        'findings': [{
            'severity': 'blocking', 'requirement': '保留指定條件',
            'decision_step_ids': [1, 3], 'task_ids': ['sales'],
            'plan_path': 'tasks[1].filters', 'observation': '結構與需求不符。',
            'required_evidence': '可支援條件的契約欄位及對應 typed filter。',
        }],
    }


def test_review_cannot_approve_a_recorded_missing_requirement():
    report = review_data()
    report['verdict'] = 'approve'
    with pytest.raises(ValidationError):
        EvidenceReview.model_validate(report)


@pytest.mark.parametrize('reference', ['task', 'step'])
def test_review_references_must_belong_to_the_plan_being_reviewed(reference):
    report = review_data()
    if reference == 'task':
        report['findings'][0]['task_ids'] = ['invented_task']
    else:
        report['checks'][0]['decision_step_ids'] = [7]
    with pytest.raises(ValueError):
        validate_review_references(EvidenceReview.model_validate(report), DecisionChainDecompositionDraft.model_validate(data()))
