from typing import Any, Protocol

class SQLQueryExecutor(Protocol):
    """Injected executor or optional configured adapter; one approved query."""
    def __call__(self, datasource: str, sql: str) -> tuple[list[str], list[list[Any]]]: ...
