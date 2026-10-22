"""Optional SQL Server deployment configuration; never expose credentials."""
from dataclasses import dataclass, field


class SQLServerConfigurationError(ValueError):
    """Allowlisted diagnostics that never include a connection URL."""
    messages = {
        'invalid_url': 'SQL Server requires a valid mssql+pymssql URL',
        'driver_unsupported': 'SQL Server requires the mssql+pymssql URL driver',
        'host_or_database_missing': 'SQL Server URL requires a host and database',
        'query_options_unsupported': 'SQL Server URL query options are unsupported; use deployment settings',
    }

    def __init__(self, reason: str):
        message = self.messages[reason]
        self.code = 'sqlserver_' + reason
        super().__init__(message)


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
