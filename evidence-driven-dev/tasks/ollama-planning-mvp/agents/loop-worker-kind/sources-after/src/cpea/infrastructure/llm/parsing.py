from typing import Any, TypeVar
from pydantic import BaseModel

Model = TypeVar('Model', bound=BaseModel)

def parse_model(raw: Any, model: type[Model]) -> Model:
    """Preserve the original answering JSON parser for answering and evaluation."""
    content = getattr(raw, 'content', raw)
    if isinstance(content, dict):
        return model.model_validate(content)
    if isinstance(content, list):
        content = ''.join(item.get('text', '') if isinstance(item, dict) else str(item) for item in content)
    return model.model_validate_json(str(content))
