"""Public workflow summaries, separate from model output and private reasoning."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class WorkflowStep:
    step: str
    info: str | list | dict

    def format(self) -> str:
        info = self.info if isinstance(self.info, str) else json.dumps(
            self.info, ensure_ascii=False, allow_nan=False)
        return f'{self.step}: {info}'
