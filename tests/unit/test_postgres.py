from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from cpea.bootstrap import AssistantRuntime, ProjectRuntimes
from cpea.application.services.sql_execution import SQLExecutionError
from cpea.config.database import DatabaseConfigurationError, DatabaseSettings, SQLServerSettings
from cpea.config.settings import AssistantSettings
from cpea.domain.models import HavingFilter, QueryFilter, QueryPlan
from cpea.infrastructure.database.postgres import PostgreSQLExecutor, PostgreSQLExecutionError
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import validate_generated_sql
from tests.support import dependencies, QUESTION, VIEW
from tests.unit.test_sql_server import Driver


URL = 'postgresql://user:top-secret@server.example/actual-db'


@pytest.mark.parametrize('url,dialect', [
    ('', 'mssql'), (URL, 'postgresql'),
    (URL.replace('postgresql:', 'postgresql+psycopg:'), 'postgresql'),
    ('mssql+pymssql://user:secret@host/db', 'mssql'),
])
def test_adapter_dialect_is_inferred_from_url(url, dialect):
    assert DatabaseSettings(url).resolved_dialect == dialect
    assert 'top-secret' not in repr(DatabaseSettings(url))


def test_generic_settings_priority_and_explicit_blanks(tmp_path, monkeypatch):
    names = ('CPEA_DATABASE_URL', 'CPEA_DATABASE_DIALECT',
             'CPEA_DATABASE_CONNECT_TIMEOUT_SECONDS', 'CPEA_DATABASE_QUERY_TIMEOUT_SECONDS',
             'CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS', 'CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS')
    for name in names:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / '.env'
    path.write_text(f'CPEA_DATABASE_URL={URL}\nCPEA_DATABASE_CONNECT_TIMEOUT_SECONDS=7\n'
                    'CPEA_DATABASE_QUERY_TIMEOUT_SECONDS=19\n', encoding='utf-8')
    config = AssistantSettings.from_env(path).database_settings
    assert config.resolved_dialect == 'postgresql' and config.connect_timeout_seconds == 7
    assert config.query_timeout_seconds == 19
    monkeypatch.setenv('CPEA_DATABASE_URL', 'mssql+pymssql://u:p@host/db')
    assert AssistantSettings.from_env(path).database_settings.resolved_dialect == 'mssql'
    monkeypatch.setenv('CPEA_DATABASE_URL', '')
    config = AssistantSettings.from_env(path).database_settings
    assert not config.enabled
    monkeypatch.setenv('CPEA_DATABASE_DIALECT', 'postgresql')
    assert AssistantSettings.from_env(path).database_settings.resolved_dialect == 'postgresql'
    monkeypatch.setenv('CPEA_DATABASE_QUERY_TIMEOUT_SECONDS', '0')
    with pytest.raises(ValueError, match='CPEA_DATABASE_QUERY_TIMEOUT_SECONDS'):
        AssistantSettings.from_env(path)


@pytest.mark.parametrize('url,dialect,code', [
    ('not-a-url:top-secret', 'auto', 'driver_unsupported'),
    ('PWD=top-secret', 'auto', 'invalid_url'),
    (URL, 'mssql', 'dialect_mismatch'),
])
def test_invalid_selection_omits_secrets(url, dialect, code):
    with pytest.raises(DatabaseConfigurationError) as error:
        DatabaseSettings(url, dialect=dialect).resolved_dialect
    assert error.value.code == 'database_' + code
    assert 'top-secret' not in str(error.value)


@pytest.mark.parametrize('failure', [None, 'connect', 'cursor', 'execute', 'fetch', 'cursor_close', 'connection_close'])
def test_read_only_timeouts_bounding_one_execution_and_cleanup(failure):
    driver = Driver(failure)
    executor = PostgreSQLExecutor(DatabaseSettings(URL, 7, 19), 'binding', {VIEW}, 2, connect=driver.connect)
    assert not driver.calls
    sql = 'SELECT "仓库名称" FROM "gms2"."v_inventory" LIMIT 2'
    if failure in (None, 'cursor_close', 'connection_close'):
        columns, rows = executor('binding', sql)
        assert columns == ['倉庫', '數量'] and len(rows) == 3
    else:
        with pytest.raises(PostgreSQLExecutionError) as error:
            executor('binding', sql)
        assert 'top-secret' not in str(error.value) and error.value.__suppress_context__
    assert driver.calls == [(URL, {'connect_timeout': 7, 'autocommit': False,
        'options': '-c default_transaction_read_only=on -c standard_conforming_strings=on -c statement_timeout=19000',
        'client_encoding': 'UTF8'})]
    for connection in driver.connections:
        assert connection.closed and connection.read_only is True
        if hasattr(connection, 'created_cursor'):
            assert connection.created_cursor.closed and connection.created_cursor.executions <= 1
            if hasattr(connection.created_cursor, 'size'):
                assert connection.created_cursor.size == 3


def test_postgres_connections_are_isolated_between_queries():
    driver = Driver(barrier=Barrier(2))
    executor = PostgreSQLExecutor(DatabaseSettings(URL), 'binding', {VIEW}, 2, connect=driver.connect)
    queries = ['SELECT "A" FROM gms2.v_inventory LIMIT 2', 'SELECT "B" FROM gms2.v_inventory LIMIT 2']
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda sql: executor('binding', sql), queries))
    assert len(driver.connections) == 2
    assert [result[1][0][0] for result in results] == queries
    assert all(c.closed and c.created_cursor.closed for c in driver.connections)


@pytest.mark.parametrize('url,code', [
    ('postgresql://u:top-secret@host', 'host_or_database_missing'),
    ('postgresql://u:top-secret@host:invalid/db', 'invalid_url'),
    (URL + '?options=-c+default_transaction_read_only%3Doff', 'query_options_unsupported'),
    (URL + '?host=other-host', 'query_options_unsupported'),
])
def test_invalid_url_rejected_before_connection(url, code):
    driver = Driver()
    with pytest.raises(DatabaseConfigurationError) as error:
        PostgreSQLExecutor(DatabaseSettings(url), 'binding', {VIEW}, 2, connect=driver.connect)
    assert error.value.code == 'database_' + code
    assert 'top-secret' not in str(error.value) and not driver.calls


def test_psycopg_driver_alias_and_tls_options_are_preserved():
    driver = Driver()
    url = URL.replace('postgresql:', 'postgresql+psycopg:') + '?sslmode=verify-full&sslrootcert=%2Fca.pem'
    executor = PostgreSQLExecutor(DatabaseSettings(url), 'binding', {VIEW}, 2, connect=driver.connect)
    executor('binding', 'SELECT * FROM gms2.v_inventory LIMIT 2')
    assert driver.calls[0][0] == URL + '?sslmode=verify-full&sslrootcert=%2Fca.pem'


@pytest.mark.parametrize('sql', [
    'DELETE FROM gms2.v_inventory', 'SELECT * FROM other.secret LIMIT 2',
    'SELECT * FROM "gms2.v_inventory" LIMIT 2',
    'SELECT * FROM "GMS2"."v_inventory" LIMIT 2',
    'SELECT * FROM gms2.v_inventory; SELECT 1',
    'SELECT * FROM gms2.v_inventory, other.secret',
    'SELECT * FROM gms2.v_inventory UNION SELECT * FROM other.secret',
    'SELECT * FROM gms2.v_inventory FOR UPDATE',
])
def test_policy_rejection_and_binding_happen_before_connect(sql):
    driver = Driver()
    executor = PostgreSQLExecutor(DatabaseSettings(URL), 'binding', {VIEW}, 2, connect=driver.connect)
    with pytest.raises(ValueError):
        executor('binding', sql)
    with pytest.raises(ValueError, match='binding'):
        executor('other', 'SELECT * FROM gms2.v_inventory LIMIT 2')
    assert not driver.calls


def test_postgres_compilation_escaping_grouping_having_and_limit(tmp_path):
    _, catalog, *_ = dependencies(tmp_path)
    columns = catalog.views()[0].policy['columns']
    columns['仓库名称']['capabilities'].append('order_by')
    columns['库存数量']['capabilities'].append('filter')
    plan = QueryPlan(supported=True, source_views=[VIEW], select_columns=['仓库名称', '库存数量'],
        aggregations={'库存数量': 'sum'}, group_by=['仓库名称'], order_by=['仓库名称'],
        order_directions={'仓库名称': 'desc'}, filters=[QueryFilter(column='品号', operator='IN', value=["O'Reilly", '王%'])],
        having=[HavingFilter(column='库存数量', aggregation='sum', operator='>', value=2)], limit=10)
    sql = compile_single_view(plan, catalog, max_rows=3, dialect='postgresql')
    assert sql == ('SELECT "仓库名称", SUM("库存数量") AS "库存数量" FROM "gms2"."v_inventory"'
        ' WHERE "品号" IN (\'O\'\'Reilly\', \'王%\') GROUP BY "仓库名称"'
        ' HAVING SUM("库存数量") > 2 ORDER BY "仓库名称" DESC LIMIT 3')
    validate_generated_sql(sql, {VIEW}, dialect='postgresql')


def test_missing_psycopg_has_safe_installation_diagnostic(monkeypatch):
    import cpea.infrastructure.database.postgres as module
    monkeypatch.setattr(module, 'import_module', lambda name: (_ for _ in ()).throw(ImportError('top-secret')))
    with pytest.raises(ValueError, match='postgres extra') as error:
        PostgreSQLExecutor(DatabaseSettings(URL), 'binding', {VIEW}, 2)
    assert 'top-secret' not in str(error.value)


@pytest.mark.parametrize('value,literal', [(1, 'TRUE'), (0, 'FALSE'), ('true', 'TRUE'), ('false', 'FALSE')])
def test_postgres_boolean_filters_use_native_literals(tmp_path, value, literal):
    _, catalog, *_ = dependencies(tmp_path)
    catalog.views()[0].policy['columns']['品号']['type'] = 'boolean'
    plan = QueryPlan(supported=True, source_views=[VIEW], select_columns=['品号'],
                    filters=[QueryFilter(column='品号', operator='=', value=value)])
    assert f'WHERE "品号" = {literal} LIMIT' in compile_single_view(plan, catalog, dialect='postgresql')


def test_generation_only_postgres_needs_no_driver_or_executor(tmp_path, monkeypatch):
    import cpea.infrastructure.database.postgres as module
    from cpea.interfaces.web.ui import SessionGate, single_question_updates
    monkeypatch.setattr(module, 'import_module', lambda name: pytest.fail('must not import database driver'))
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    runtime = AssistantRuntime(replace(settings, database=DatabaseSettings(dialect='postgresql')),
        catalog=catalog, llm=llm, retriever=retriever, context_packer=packer, datasource_id='binding')
    try:
        frames = list(single_question_updates(runtime, QUESTION, SessionGate()))
        assert frames[-1].state == 'completed' and frames[-1].sql.endswith(' LIMIT 2')
        assert '未執行查詢' in frames[-1].messages[-1]['content']
        assert runtime.executor is None
    finally:
        runtime.close()


def test_web_projects_select_different_adapters_from_their_own_env(tmp_path, monkeypatch):
    from tests.support import write_profile
    import psycopg
    driver = Driver()
    monkeypatch.setattr(psycopg, 'connect', driver.connect)
    for project, url in [('gms2', 'mssql+pymssql://u:p@host/db'), ('retail', URL)]:
        root = write_profile(tmp_path / project, profile_id=project)
        (root / '.env').write_text(f'CPEA_DATABASE_URL={url}\n', encoding='utf-8')
    projects = ProjectRuntimes(tmp_path)
    try:
        from cpea.infrastructure.database.sql_server import SQLServerExecutor
        assert isinstance(projects.get('gms2').executor, SQLServerExecutor)
        assert isinstance(projects.get('retail').executor, PostgreSQLExecutor)
        assert projects.get('retail').executor.datasource_id == 'retail'
        assert projects.get('gms2').executor.datasource_id == 'gms2'
        assert not driver.calls
    finally:
        projects.close()


def test_project_evaluation_keeps_postgres_dialect_without_loading_driver(tmp_path, monkeypatch):
    from cpea.config.projects import resolve_project
    from evaluations.project_runner import _runtime_for_project
    from tests.support import write_profile
    import cpea.infrastructure.database.postgres as module
    monkeypatch.setattr(module, 'import_module', lambda name: pytest.fail('must not import database driver'))
    root = write_profile(tmp_path / 'retail')
    (root / '.env').write_text(f'CPEA_DATABASE_URL={URL}\n', encoding='utf-8')
    runtime = _runtime_for_project(resolve_project('retail', projects_root=tmp_path, require_cases=False))
    try:
        assert runtime.settings.database_settings.resolved_dialect == 'postgresql'
        assert not runtime.settings.database_settings.enabled and runtime.executor is None
        assert not runtime.settings.sqlserver.enabled
    finally:
        runtime.close()


@pytest.mark.parametrize('legacy', [False, True])
def test_runtime_automatically_selects_postgres_and_revalidates_its_sql(tmp_path, monkeypatch, legacy):
    import psycopg
    driver = Driver()
    monkeypatch.setattr(psycopg, 'connect', driver.connect)
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    settings = (replace(settings, sqlserver=SQLServerSettings(URL)) if legacy else
                replace(settings, database=DatabaseSettings(URL)))
    runtime = AssistantRuntime(settings, catalog=catalog, llm=llm, retriever=retriever,
        context_packer=packer, datasource_id='binding')
    try:
        assert isinstance(runtime.executor, PostgreSQLExecutor) and not driver.calls
        result = runtime.execute(QUESTION)
        assert result.attempts == 1 and result.rows_truncated
        assert result.generation.sql.endswith(' LIMIT 2') and 'TOP' not in result.generation.sql
        assert driver.connections[0].created_cursor.sql == result.generation.sql
        forged = result.generation.model_copy(update={'sql': compile_single_view(
            result.generation.query_plan, catalog, request=QUESTION, max_rows=2)})
        with pytest.raises(SQLExecutionError, match='approved query plan'):
            runtime.execution_agent().execute_generation(forged, 'binding', request=QUESTION)
        assert len(driver.calls) == 1
    finally:
        runtime.close()
