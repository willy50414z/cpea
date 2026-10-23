"""Independent WrenAI planner; the existing validator remains the final boundary."""
from __future__ import annotations

from uuid import uuid4
from pydantic import ValidationError
from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from .validation import validate_decomposition, prepare_requests
from .wrenai_protocol import WorkerError
from .wrenai_schema import adapt_catalog


class WrenAIDecompositionWorkflow:
    def __init__(self, client, catalog):
        self.client,self.catalog=client,catalog

    def plan(self, request: str, *, run_id=None, case_id=None) -> DecompositionResponse:
        return self.invoke(request,run_id=run_id,case_id=case_id)

    def invoke(self, request: str, *, run_id=None, case_id=None) -> DecompositionResponse:
        metadata={'contract_fingerprint':self.catalog.fingerprint}
        def result(status, **kwargs):
            return DecompositionResponse(status=status,**metadata,**kwargs)
        if not isinstance(request,str) or not request.strip() or len(request)>4000:
            return result('error',code='invalid_request')
        if not self.catalog.views(): return result('unsupported',code='empty_catalog')
        try:
            response=self.client.plan(request=request,run_id=run_id or uuid4().hex,case_id=case_id,
                catalog_fingerprint=self.catalog.fingerprint,schema=adapt_catalog(self.catalog),
                response_schema=DecompositionDraft.model_json_schema())
        except WorkerError as exc:
            return result('error',code=exc.code)
        except (OSError,ValueError,TypeError):
            return result('error',code='worker_error')
        try:
            tokens=response['context_tokens'];counter=response['token_counter']
            if type(tokens) is not int or tokens<0 or not isinstance(counter,str): raise ValueError()
            metadata.update(context_tokens=tokens,token_counter=counter)
            draft=DecompositionDraft.model_validate(response['draft'])
        except (KeyError,ValueError,TypeError,ValidationError):
            return result('error',code='invalid_model_response')
        if draft.status!='ready': return result(draft.status,draft=draft)
        errors=validate_decomposition(draft,self.catalog)
        if errors: return result('error',code='invalid_plan',draft=draft,validation_errors=errors)
        try: prepared=prepare_requests(draft,self.catalog)
        except ValueError: return result('error',code='invalid_prepared_request',draft=draft)
        return result('ready',draft=draft,prepared_requests=prepared)
