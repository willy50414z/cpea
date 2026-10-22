"""Select the executor using the same dialect as the compiler."""
from dataclasses import replace


def create_executor(settings, datasource_id, allowed_views):
    database = settings.database_settings
    if database.resolved_dialect == 'postgresql':
        from cpea.infrastructure.database.postgres import PostgreSQLExecutor
        return PostgreSQLExecutor(database, datasource_id, allowed_views, settings.max_rows)
    from cpea.infrastructure.database.sql_server import SQLServerExecutor
    sqlserver = replace(settings.sqlserver, connection_string=database.connection_string,
        connect_timeout_seconds=database.connect_timeout_seconds,
        query_timeout_seconds=database.query_timeout_seconds)
    return SQLServerExecutor(sqlserver, datasource_id, allowed_views, settings.max_rows)
