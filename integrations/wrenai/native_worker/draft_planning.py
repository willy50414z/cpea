import json
import sys
from typing import Any

from hamilton import base
from hamilton.async_driver import AsyncDriver
from haystack.components.builders import PromptBuilder
from src.core.pipeline import BasicPipeline
from .generation import canonical

SYSTEM = ('Produce only the supplied DecompositionDraft JSON schema. Do not generate SQL. '
          'Preserve every original identifier, filter, time range, negation and population. '
          'Use qualified view names from model_to_view. Respect complete grain/scope/time/capability '
          'and integration contracts. Add only necessary allowed grain/integration keys. '
          'Do not invent measures or replace missing fields. Ask clarification when ambiguous.')
TEMPLATE = '''Original request: {{ request }}
Intent evidence (does not replace original request): {{ intent }}
Naturally retrieved schema: {{ retrieval }}
model_to_view: {{ mapping }}
Complete read-only selected view contracts: {{ contracts }}
Output JSON schema: {{ response_schema }}'''


def draft_prompt(request: str, intent: dict, retrieval: dict, mapping: dict,
                 contracts: dict, response_schema: dict, prompt_builder: Any) -> str:
    return prompt_builder.run(request=request,intent=canonical(intent),
        retrieval=canonical(retrieval),mapping=canonical(mapping),
        contracts=canonical(contracts),response_schema=canonical(response_schema))['prompt']


async def draft_generation(draft_prompt: str, generator: Any) -> dict:
    return await generator(prompt=draft_prompt)


def draft_result(draft_generation: dict) -> dict:
    return json.loads(draft_generation['replies'][0])


class DraftPlanning(BasicPipeline):
    def __init__(self, llm_provider, response_schema):
        self.components={'prompt_builder':PromptBuilder(template=TEMPLATE),
            'generator':llm_provider.get_generator(system_prompt=SYSTEM,generation_kwargs={
                'response_format':{'type':'json_schema','json_schema':{'name':'decomposition_draft','schema':response_schema}}})}
        super().__init__(AsyncDriver({},sys.modules[__name__],result_builder=base.DictResult()))

    async def run(self, **inputs):
        return await self._pipe.execute(['draft_result'],inputs={**self.components,**inputs})
