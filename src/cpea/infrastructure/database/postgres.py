"""Bounded PostgreSQL queries using one read-only connection per execution."""
from importlib import import_module
from urllib.parse import parse_qsl, urlsplit

from cpea.config.database import DatabaseConfigurationError, DatabaseSettings
from cpea.infrastructure.sql_policy import validate_generated_sql


class PostgreSQLExecutionError(RuntimeError):
    pass


class PostgreSQLExecutor:
    def __init__(self, settings: DatabaseSettings, datasource_id: str,
                 allowed_views: set[str], max_rows: int, *, connect=None):
        if not settings.enabled or not datasource_id or max_rows <= 0:
            raise ValueError('PostgreSQL requires connection settings and datasource binding')
        if settings.resolved_dialect != 'postgresql':
            raise DatabaseConfigurationError('driver_unsupported')
        try:
            url = urlsplit(settings.connection_string)
            if url.fragment:
                raise DatabaseConfigurationError('invalid_url')
            if not url.hostname or not url.path.strip('/'):
                raise DatabaseConfigurationError('host_or_database_missing')
            # Force validation of malformed ports without exposing the URL.
            url.port
        except DatabaseConfigurationError:
            raise
        except ValueError:
            raise DatabaseConfigurationError('invalid_url') from None
        options = parse_qsl(url.query, keep_blank_values=True)
        if any(key not in {'sslmode', 'sslrootcert', 'sslcert', 'sslkey'} for key, _ in options):
            raise DatabaseConfigurationError('query_options_unsupported')
        self.connection_string = settings.connection_string.replace('postgresql+psycopg://', 'postgresql://', 1)
        if connect is None:
            try:
                connect = import_module('psycopg').connect
            except ImportError:
                raise ValueError('PostgreSQL requires the postgres extra (psycopg)') from None
        self._connect = connect
        self.settings = settings
        self.datasource_id = datasource_id
        self.allowed_views = frozenset(allowed_views)
        self.max_rows = max_rows

    def __call__(self, datasource: str, sql: str):
        if datasource != self.datasource_id:
            raise ValueError('PostgreSQL datasource binding mismatch')
        validate_generated_sql(sql, self.allowed_views, dialect='postgresql')
        connection = cursor = None
        try:
            connection = self._connect(self.connection_string,
                connect_timeout=self.settings.connect_timeout_seconds, autocommit=False,
                options=f'-c default_transaction_read_only=on -c standard_conforming_strings=on -c statement_timeout={self.settings.query_timeout_seconds * 1000}',
                client_encoding='UTF8')
            connection.read_only = True
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [column[0] for column in cursor.description]
            rows = [list(row) for row in cursor.fetchmany(self.max_rows + 1)]
            return columns, rows
        except Exception:
            raise PostgreSQLExecutionError('PostgreSQL query failed') from None
        finally:
            # Closing an uncommitted read-only connection rolls back the query.
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass
