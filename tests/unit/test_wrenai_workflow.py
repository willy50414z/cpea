from pathlib import Path
import pytest
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog


class Client:
    def __init__(self,draft=None,error=None):
        self.calls=[];self.error=error
        self.draft=draft or {'status':'unsupported','unsupported_reasons':['missing_metric_xyz']}
    def plan(self,**payload):
        self.calls.append(payload)
        if self.error: raise self.error
        return {'draft':self.draft,'context_tokens':123,'token_counter':'native-fixture','artifacts':{}}


def service(client):
    from cpea.application.services.wrenai_decomposition import WrenAIDecompositionService
    return WrenAIDecompositionService(client,SchemaCatalog(Path(__file__).resolve().parents[2]/'projects/retail'))


def test_service_passes_original_request_full_contract_and_unique_response_schema():
    from cpea.application.models.decomposition import DecompositionDraft
    client=Client();result=service(client).plan('missing_metric_xyz',run_id='run',case_id='case')
    assert result.status=='unsupported' and not result.prepared_requests
    sent=client.calls[0]
    assert sent['request']=='missing_metric_xyz'
    assert len(sent['schema']['contracts'])==7
    assert sent['response_schema']==DecompositionDraft.model_json_schema()
    assert sent['catalog_fingerprint']==result.contract_fingerprint
    assert result.context_tokens==123 and result.token_counter=='native-fixture'
    assert not {'expected_tasks','oracle','expected_status'} & sent.keys()


def ready():
    return {'status':'ready','strategy':'single_view','tasks':[
      {'task_id':'customers','view':'demo_retail.v_customer_value',
       'required_columns':['customer_id','registered_on','lifetime_spend'],
       'attributes':['registered_on','lifetime_spend'],'output_grain':['customer_id'],
       'request':'customer_id registered_on lifetime_spend'}],
      'integration':{'anchor_task':'customers','output_grain':['customer_id']}}


def test_ready_uses_existing_validator_and_preparer():
    result=service(Client(ready())).plan('customer_id registered_on lifetime_spend')
    assert result.status=='ready' and len(result.prepared_requests)==1
    assert result.prepared_requests[0].view=='demo_retail.v_customer_value'
    data=ready();data['tasks'][0]['required_columns'].append('missing_metric_xyz')
    invalid=service(Client(data)).plan('missing_metric_xyz')
    assert invalid.code=='invalid_plan' and not invalid.prepared_requests


@pytest.mark.parametrize('draft',[{'nonsense':True},{'status':'ready','tasks':[]},{'status':'needs_clarification','clarifications':['city?']}])
def test_malformed_or_nonready_never_prepares(draft):
    result=service(Client(draft)).plan('city')
    assert result.status!='ready' and not result.prepared_requests


def test_worker_failure_sanitized_and_invalid_request_does_not_dispatch():
    from cpea.workflows.task_decomposition.wrenai_protocol import WorkerError
    client=Client(error=WorkerError('worker_timeout'))
    assert service(client).plan(' ').code=='invalid_request' and not client.calls
    response=service(client).plan('question')
    assert response.code=='worker_timeout' and not response.prepared_requests
