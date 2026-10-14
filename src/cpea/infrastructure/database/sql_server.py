"""Single-use, bounded, read-only SQL Server executor."""
from importlib import import_module
from importlib.resources import files
import os
from pathlib import Path

from cpea.config.database import SQLServerSettings
from cpea.infrastructure.sql_policy import validate_generated_sql


class SQLServerExecutionError(RuntimeError):
    pass


class SQLServerExecutor:
    def __init__(self, settings: SQLServerSettings, datasource_id: str,
                 allowed_views: set[str], max_rows: int, *, engine_factory=None):
        if not settings.enabled or not datasource_id or max_rows <= 0:
            raise ValueError('SQL Server requires connection settings and datasource binding')
        try:
            sqlalchemy = import_module('sqlalchemy')
            url = sqlalchemy.engine.make_url(settings.connection_string)
        except ImportError:
            raise ValueError('SQL Server requires the sqlserver extra (SQLAlchemy and pymssql)') from None
        except Exception:
            raise ValueError('SQL Server requires a valid mssql+pymssql URL') from None
        if url.drivername != 'mssql+pymssql' or not url.host or not url.database:
            raise ValueError('SQL Server requires a mssql+pymssql URL with host and database')
        if url.query:
            # Driver behavior, credentials and timeouts must remain explicit.
            raise ValueError('SQL Server URL query options are unsupported; use deployment settings')
        if engine_factory is None:
            engine_factory = sqlalchemy.create_engine
        # FreeTDS reads TLS policy from its process-wide configuration. Use a
        # bundled certificate-verifying default unless deployment selects one.
        tls_config = (settings.freetds_config_file or os.environ.get('FREETDSCONF')
                      or os.environ.get('FREETDS')
                      or str(files('cpea.resources').joinpath('database/freetds.conf')))
        if not Path(tls_config).is_file():
            raise ValueError('FreeTDS configuration file does not exist')
        os.environ['FREETDSCONF'] = tls_config
        try:
            self._engine = engine_factory(url, poolclass=sqlalchemy.pool.NullPool,
                pool_reset_on_return=None, pool_pre_ping=False, echo=False, hide_parameters=True,
                connect_args={
                    'login_timeout': settings.connect_timeout_seconds,
                    'timeout': settings.query_timeout_seconds,
                    'autocommit': True, 'charset': 'UTF-8', 'tds_version': '7.4',
                    'encryption': 'require', 'read_only': True,
                })
        except ImportError:
            raise ValueError('SQL Server requires the sqlserver extra (SQLAlchemy and pymssql)') from None
        except Exception:
            raise ValueError('SQL Server engine configuration failed') from None
        self.settings = settings
        self.datasource_id = datasource_id
        self.allowed_views = frozenset(allowed_views)
        self.max_rows = max_rows

    def __call__(self, datasource: str, sql: str):
        if datasource != self.datasource_id:
            raise ValueError('SQL Server datasource binding mismatch')
        validate_generated_sql(sql, self.allowed_views)
        connection = cursor = None
        try:
            # Raw DBAPI execution preserves the exact approved SQL, including
            # percent characters, and avoids SQLAlchemy SQL rewriting.
            connection = self._engine.raw_connection()
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [column[0] for column in cursor.description]
            rows = [list(row) for row in cursor.fetchmany(self.max_rows + 1)]
            return columns, rows
        except Exception:
            # Driver messages can contain SQL, server names and credentials.
            raise SQLServerExecutionError('SQL Server query failed') from None
        finally:
            # Try both releases even when cursor.close itself fails.
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass
