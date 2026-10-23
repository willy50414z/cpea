"""Versioned general planning policy, independent of benchmark answers."""

from importlib.resources import files

DECOMPOSITION_PROMPT_VERSION = 'v4'
DECOMPOSITION_PROMPT = files('cpea.workflows.task_decomposition').joinpath('prompt.md').read_text(encoding='utf-8')
