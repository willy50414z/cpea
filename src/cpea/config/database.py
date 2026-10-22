"""Optional database deployment configuration; never expose credentials."""
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class DatabaseConfigurationError(ValueError):
    """Fixed diagnostics shared by automatic adapter selection."""
    messages = {
        'invalid_url': 'Database requires a valid connection URL',
        'driver_unsupported': 'Database URL requires postgresql, postgresql+psycopg, or mssql+pymssql',
        'dialect_unsupported': 'Database dialect must be auto, mssql, or postgresql',
        'dialect_mismatch': 'Database dialect does not match the connection URL',
        'host_or_database_missing': 'Database URL requires a host and database',
        'query_options_unsupported': 'PostgreSQL URL supports only sslmode, sslrootcert, sslcert, and sslkey options',
    }

    def __init__(self, reason: str):
        self.code = 'database_' + reason
        super().__init__(self.messages[reason])


@dataclass(frozen=True)
class DatabaseSettings:
    connection_string: str = field(default='', repr=False)
    connect_timeout_seconds: int = 5
    query_timeout_seconds: int = 30
    dialect: str = 'auto'

    def __post_init__(self):
        for name in ('connect_timeout_seconds', 'query_timeout_seconds'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'Database {name} must be a positive integer')
        if self.dialect not in {'auto', 'mssql', 'postgresql'}:
            raise DatabaseConfigurationError('dialect_unsupported')

    @property
    def enabled(self) -> bool:
        return bool(self.connection_string.strip())

    @property
    def resolved_dialect(self) -> str:
        if not self.enabled:
            return 'mssql' if self.dialect == 'auto' else self.dialect
        try:
            scheme = urlsplit(self.connection_string).scheme
        except ValueError:
            raise DatabaseConfigurationError('invalid_url') from None
        if not scheme:
            raise DatabaseConfigurationError('invalid_url')
        inferred = {'mssql+pymssql': 'mssql', 'postgresql': 'postgresql',
                    'postgresql+psycopg': 'postgresql'}.get(scheme)
        if inferred is None:
            raise DatabaseConfigurationError('driver_unsupported')
        if self.dialect != 'auto' and self.dialect != inferred:
            raise DatabaseConfigurationError('dialect_mismatch')
        return inferred


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
