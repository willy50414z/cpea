from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from cpea.config.settings import AssistantSettings


def get_llm_config(
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
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

    if settings.llm_provider == "ollama":
        return ChatOllama(
            base_url=selected_base_url,
            model=selected_model,
            temperature=selected_temperature,
            seed=selected_seed,
            num_ctx=selected_context,
            num_predict=selected_output,
            # SQL generation needs a compact JSON artifact. Some local models
            # otherwise spend the output budget on hidden reasoning.
            reasoning=False,
            format="json",
            client_kwargs={"timeout": settings.request_timeout_seconds},
        )

    # Imported lazily so existing Ollama-only deployments fail with a useful
    # dependency message only when the llama.cpp provider is selected.
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - deployment guard
        raise RuntimeError(
            "llama.cpp provider requires the 'langchain-openai' package"
        ) from exc
    return ChatOpenAI(
        base_url=selected_base_url,
        api_key=settings.llm_api_key,
        model=selected_model,
        temperature=selected_temperature,
        seed=selected_seed,
        max_tokens=selected_output,
        timeout=settings.request_timeout_seconds,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
