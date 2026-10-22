from typing import Any
import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, convert_to_messages
from langchain_ollama import ChatOllama
from pydantic import BaseModel

from cpea.config.settings import AssistantSettings


def response_schema_for(response_model: type[BaseModel], *,
                        column_names=None, view_names=None) -> dict[str, Any]:
    """Derive name constraints from admitted contracts, never from evaluation data."""
    schema = response_model.model_json_schema()
    semantic_schema = 'clarifications' in schema.get('properties', {})
    if semantic_schema and 'fields' in schema['properties']:
        # Parsing keeps migration defaults, but constrained generators must
        # explicitly return the query clauses instead of omitting them.
        schema['required'] = list(schema['properties'])
    for definition in schema.get('$defs', {}).values():
        properties = definition.get('properties', {})
        if semantic_schema and properties:
            definition['required'] = list(properties)
        if column_names is not None and 'column' in properties:
            properties['column']['enum'] = sorted(column_names)
        if view_names is not None and 'view' in properties:
            properties['view']['enum'] = sorted(view_names)
        if column_names is not None and 'candidates' in properties:
            properties['candidates'].setdefault('items', {})['enum'] = sorted(column_names)
    if view_names is not None and 'candidate_view' in schema.get('properties', {}):
        for branch in schema['properties']['candidate_view'].get('anyOf', []):
            if branch.get('type') == 'string':
                branch['enum'] = sorted(view_names)
    return schema


def prepare_structured_messages(messages, response_model: type[BaseModel], *, schema=None):
    """Expose the same output contract to every provider before token counting."""
    schema = schema if schema is not None else response_schema_for(response_model)
    serialized = json.dumps(schema, ensure_ascii=False)
    prepared = convert_to_messages([messages] if isinstance(messages, str) else messages)
    if any(isinstance(message.content, str) and serialized in message.content for message in prepared):
        return prepared
    instruction = ('只回傳符合以下 JSON Schema 的 JSON 物件，必須包含所有 required 欄位。'
                   '\n輸出契約：' + serialized)
    if prepared and isinstance(prepared[0], SystemMessage):
        content = prepared[0].content
        content = (content + '\n\n' + instruction if isinstance(content, str)
                   else [*content, {'type': 'text', 'text': instruction}])
        prepared[0] = prepared[0].model_copy(update={'content': content})
    else:
        prepared.insert(0, SystemMessage(content=instruction))
    return prepared


def bind_response_schema(llm: Any, response_model: type[BaseModel], *, schema=None) -> Any:
    """Constrain a response without changing the shared model's format."""
    schema = schema if schema is not None else response_schema_for(response_model)
    if hasattr(llm, 'with_response_schema'):
        return llm.with_response_schema(schema)
    if isinstance(llm, ChatOllama):
        return llm.bind(format=schema)
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        pass
    else:
        if isinstance(llm, ChatOpenAI):
            # The full schema travels in common messages. JSON mode does not
            # assume that this deployment supports native strict JSON Schema.
            return llm.bind(response_format={'type': 'json_object'})
    return llm


def get_llm_config(
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    top_p: float | None = None,
    settings: AssistantSettings | None = None,
) -> BaseChatModel:
    settings = settings or AssistantSettings.from_env()
    selected_base_url = base_url or settings.llm_base_url
    selected_model = model or settings.llm_model
    selected_temperature = (
        temperature if temperature is not None else settings.temperature
    )
    selected_seed = seed if seed is not None else settings.seed
    selected_context = num_ctx if num_ctx is not None else settings.context_window
    selected_output = (
        num_predict if num_predict is not None else settings.max_output_tokens
    )
    selected_top_p = top_p if top_p is not None else settings.top_p

    if settings.llm_provider == "ollama":
        return ChatOllama(
            base_url=selected_base_url,
            model=selected_model,
            temperature=selected_temperature,
            seed=selected_seed,
            num_ctx=selected_context,
            num_predict=selected_output,
            top_p=selected_top_p,
            # Thinking is explicit and needs enough budget for the final JSON.
            reasoning=settings.llm_reasoning,
            format="json",
            client_kwargs={"timeout": settings.request_timeout_seconds},
        )

    if settings.llm_provider == "gcp":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("gcp provider requires 'langchain-google-genai'") from exc
        if not settings.gcp_project:
            raise ValueError("gcp provider requires CPEA_GCP_PROJECT")
        return ChatGoogleGenerativeAI(
            model=selected_model,
            api_key=None if settings.llm_api_key == "not-needed" else settings.llm_api_key,
            project=settings.gcp_project,
            location=settings.gcp_location,
            vertexai=True,
            temperature=selected_temperature,
            top_p=selected_top_p,
            max_output_tokens=None if selected_output == -1 else selected_output,
            timeout=settings.request_timeout_seconds,
            max_retries=0,
        )
    # Imported lazily so local-only deployments need no cloud dependency.
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - deployment guard
        raise RuntimeError(
            f"{settings.llm_provider} provider requires the 'langchain-openai' package"
        ) from exc
    if settings.llm_provider == "azure" and settings.llm_api_key == "not-needed":
        raise ValueError("azure provider requires ASSISTANT_LLM_API_KEY")
    if settings.llm_provider == "azure" and "example.invalid" in selected_base_url:
        raise ValueError("azure provider requires ASSISTANT_LLM_BASE_URL")
    return ChatOpenAI(
        base_url=selected_base_url,
        api_key=settings.llm_api_key,
        model=selected_model,
        temperature=selected_temperature,
        top_p=selected_top_p,
        seed=selected_seed,
        max_tokens=None if selected_output == -1 else selected_output,
        timeout=settings.request_timeout_seconds,
        max_retries=0,
        model_kwargs={"response_format": {"type": "json_object"}} if settings.llm_provider == "llamacpp" else {},
    )
