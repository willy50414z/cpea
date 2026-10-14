"""Optional SQL Server deployment configuration; never expose credentials."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SQLServerSettings:
    connection_string: str = field(default='', repr=False)
    connect_timeout_seconds: int = 5
    query_timeout_seconds: int = 30
    freetds_config_file: str | None = None

    def __post_init__(self):
        for name in ('connect_timeout_seconds', 'query_timeout_seconds'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'SQL Server {name} must be a positive integer')

    @property
    def enabled(self) -> bool:
        return bool(self.connection_string.strip())
