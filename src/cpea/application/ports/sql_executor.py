from typing import Any, Protocol

class SQLQueryExecutor(Protocol):
    """Deployment supplies the existing callable; the core implements no DB access."""
    def __call__(self, datasource: str, sql: str) -> tuple[list[str], list[list[Any]]]: ...
