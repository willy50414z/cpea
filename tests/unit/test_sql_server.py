from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace

import pytest

from cpea.bootstrap import AssistantRuntime
from cpea.config.database import SQLServerSettings, SQLServerConfigurationError
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.database.sql_server import SQLServerExecutor, SQLServerExecutionError
from tests.support import dependencies, QUESTION, VIEW


class Driver:
    def __init__(self, fail=None, barrier=None):
        self.fail = fail
        self.barrier = barrier
        self.calls = []
        self.connections = []
        self.engine_calls = []

    def create_engine(self, url, **kwargs):
        self.engine_calls.append((url, kwargs))
        if self.fail == "engine":
            raise RuntimeError("PWD=top-secret")
        return SimpleNamespace(raw_connection=lambda: self.connect(
            url.render_as_string(hide_password=False), **kwargs["connect_args"]))

    def connect(self, secret, **kwargs):
        self.calls.append((secret, kwargs))
        if self.fail == 'connect':
            raise RuntimeError('PWD=top-secret')
        driver = self
        class Cursor:
            description = [('倉庫',), ('數量',)]
            closed = False
            sql = None
            executions = 0
            def execute(self, sql):
                self.executions += 1
                self.sql = sql
                if driver.barrier:
                    driver.barrier.wait(timeout=5)
                if driver.fail == 'execute':
                    raise TimeoutError('PWD=top-secret')
            def fetchmany(self, size):
                self.size = size
                if driver.fail == 'fetch':
                    raise RuntimeError('PWD=top-secret')
                return [[self.sql, i] for i in range(size)]
            def close(self):
                self.closed = True
                if driver.fail == 'cursor_close':
                    raise RuntimeError('PWD=top-secret')
        class Connection:
            closed = False
            def cursor(self):
                if driver.fail == 'cursor':
                    raise RuntimeError('PWD=top-secret')
                self.created_cursor = Cursor()
                return self.created_cursor
            def close(self):
                self.closed = True
                if driver.fail == 'connection_close':
                    raise RuntimeError('PWD=top-secret')
        connection = Connection()
        self.connections.append(connection)
        return connection


def adapter(driver, view=VIEW):
    return SQLServerExecutor(SQLServerSettings('mssql+pymssql://user:top-secret@server.example/actual-db', 7, 19),
                             'logical-binding', {view}, 2, engine_factory=driver.create_engine)


def test_settings_priority_blanks_and_secrets(tmp_path, monkeypatch):
    names = ['CPEA_DATABASE_URL', 'CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS',
             'CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS', 'CPEA_ENV_FILE']
    for name in names:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / '.env'
    env.write_text('CPEA_DATABASE_URL=PWD=file-secret\n'
                   'CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS=8\n'
                   'CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS=25\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert not AssistantSettings.from_env().sqlserver.enabled
    from_file = AssistantSettings.from_env(env)
    assert from_file.sqlserver.connect_timeout_seconds == 8
    assert 'file-secret' not in repr(from_file)
    monkeypatch.setenv(names[0], '')
    monkeypatch.setenv(names[1], '')
    monkeypatch.setenv(names[2], '12')
    settings = AssistantSettings.from_env(env).sqlserver
    assert not settings.enabled
    assert settings.connect_timeout_seconds == 5
    assert settings.query_timeout_seconds == 12
    monkeypatch.setenv(names[0], 'PWD=process-secret')
    assert AssistantSettings.from_env(env).sqlserver.connection_string == 'PWD=process-secret'
    env.write_text('CPEA_DATASOURCE_ID=file-binding\n', encoding='utf-8')
    monkeypatch.setenv('CPEA_DATASOURCE_ID', '')
    assert AssistantSettings.from_env(env).datasource_id is None
    monkeypatch.setenv('CPEA_DATASOURCE_ID', 'process-binding')
    assert AssistantSettings.from_env(env).datasource_id == 'process-binding'


@pytest.mark.parametrize('name', ['CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS', 'CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS'])
@pytest.mark.parametrize('value', ['0', '-1', 'nan', '1.5', 'PWD=secret'])
def test_invalid_timeouts(name, value, monkeypatch):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError) as exc:
        AssistantSettings.from_env()
    assert value not in str(exc.value) or value in ['0', '-1', '1.5']


@pytest.mark.parametrize('sql', [
    'DELETE FROM gms2.v_inventory', 'SELECT * FROM other.secret',
    'SELECT * INTO stolen FROM gms2.v_inventory',
    'SELECT * FROM gms2.v_inventory; SELECT 1',
    'SELECT * FROM gms2.v_inventory, other.secret',
    'SELECT * FROM gms2.v_inventory UNION SELECT * FROM other.secret',
    'SELECT * FROM gms2.v_inventory JOIN gms2.v_inventory b ON 1=1',
])
def test_policy_rejection_before_connect(sql):
    driver = Driver()
    with pytest.raises(ValueError):
        adapter(driver)('logical-binding', sql)
    assert driver.calls == []


def test_binding_rejection_before_connect():
    driver = Driver()
    with pytest.raises(ValueError):
        adapter(driver)('wrong', 'SELECT * FROM gms2.v_inventory')
    assert driver.calls == []


@pytest.mark.parametrize('failure', [None, 'connect', 'cursor', 'execute', 'fetch', 'cursor_close', 'connection_close'])
def test_timeouts_bounding_single_execute_and_cleanup(failure):
    driver = Driver(failure)
    if failure in [None, 'cursor_close', 'connection_close']:
        columns, rows = adapter(driver)('logical-binding', 'SELECT * FROM gms2.v_inventory')
        assert columns == ['倉庫', '數量'] and len(rows) == 3
    else:
        with pytest.raises(SQLServerExecutionError) as exc:
            adapter(driver)('logical-binding', 'SELECT * FROM gms2.v_inventory')
        assert 'top-secret' not in str(exc.value)
        assert exc.value.__suppress_context__
    assert len(driver.calls) == 1
    assert driver.calls[0][1] == {'login_timeout': 7, 'timeout': 19, 'autocommit': True,
        'charset': 'UTF-8', 'tds_version': '7.4', 'encryption': 'require', 'read_only': True}
    from sqlalchemy.pool import NullPool
    options = driver.engine_calls[0][1]
    assert options['poolclass'] is NullPool and options['pool_reset_on_return'] is None
    assert options['pool_pre_ping'] is False and options['echo'] is False and options['hide_parameters'] is True
    for conn in driver.connections:
        assert conn.closed
        if hasattr(conn, 'created_cursor'):
            assert conn.created_cursor.closed
            assert conn.created_cursor.executions <= 1
            if hasattr(conn.created_cursor, 'size'):
                assert conn.created_cursor.size == 3


def test_parallel_queries_own_connections():
    driver = Driver(barrier=Barrier(2))
    executor = adapter(driver)
    queries = ['SELECT [A] FROM gms2.v_inventory', 'SELECT [B] FROM gms2.v_inventory']
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda sql: executor('logical-binding', sql), queries))
    assert len(driver.connections) == 2
    assert [r[1][0][0] for r in results] == queries
    assert all(c.closed and c.created_cursor.closed for c in driver.connections)


def test_bootstrap_injection_generation_only_and_missing_driver(tmp_path, monkeypatch):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    configured = replace(settings, sqlserver=SQLServerSettings('mssql+pymssql://user:secret@server.example/actual-db'))
    fake = lambda d, s: ([], [])
    runtime = AssistantRuntime(configured, catalog=catalog, executor=fake, datasource_id='binding')
    assert runtime.executor is fake
    import cpea.infrastructure.database.sql_server as module
    monkeypatch.setattr(module, 'import_module', lambda name: (_ for _ in ()).throw(ImportError()))
    with pytest.raises(ValueError, match='binding'):
        AssistantRuntime(configured, catalog=catalog)
    with pytest.raises(ValueError, match='sqlserver extra'):
        AssistantRuntime(configured, catalog=catalog, datasource_id='binding')
    runtime = AssistantRuntime(settings, catalog=catalog, llm=llm, retriever=retriever, context_packer=packer)
    assert runtime.generate(QUESTION).supported


@pytest.mark.parametrize('view', [VIEW, 'alternative.v_inventory'])
def test_configured_profile_switch_and_no_startup_connection(tmp_path, monkeypatch, view):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path, view=view)
    driver = Driver()
    import cpea.infrastructure.database.sql_server as module
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, 'create_engine', driver.create_engine)
    configured = replace(settings, sqlserver=SQLServerSettings('mssql+pymssql://user:secret@server.example/actual-db'))
    runtime = AssistantRuntime(configured, catalog=catalog, llm=llm, retriever=retriever,
                               context_packer=packer, datasource_id='binding')
    assert driver.calls == []
    result = runtime.execute(QUESTION)
    assert result.attempts == 1 and result.rows_truncated and len(result.rows) == 2
    assert driver.calls[0][0] == configured.sqlserver.connection_string
    assert result.generation.query_trace.execution_attempts == 1
    assert runtime.executor.allowed_views == {view}


def test_private_gms2_catalog_stays_external():
    from pathlib import Path
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    profile = Path(__file__).parents[2] / 'projects/gms2'
    if not profile.exists():
        pytest.skip('Private deployment profile is not present')
    catalog = SchemaCatalog(profile)
    driver = Driver()
    executor = SQLServerExecutor(SQLServerSettings('mssql+pymssql://user:secret@server.example/actual-db'), 'binding',
                               {v.name for v in catalog.views()}, 2, engine_factory=driver.create_engine)
    assert driver.calls == []
    executor('binding', 'SELECT * FROM gms2.v_inventory')
    assert driver.calls[0][0] == 'mssql+pymssql://user:secret@server.example/actual-db'


@pytest.mark.parametrize('raw,code', [
    ('PWD=top-secret', 'sqlserver_invalid_url'),
    ('postgresql://u:top-secret@host/db', 'sqlserver_driver_unsupported'),
    ('mssql+pyodbc://u:top-secret@host/db', 'sqlserver_driver_unsupported'),
    ('mssql+pymssql://u:top-secret@host', 'sqlserver_host_or_database_missing'),
    ('mssql+pymssql://u:top-secret@host/db?conn_properties=DELETE', 'sqlserver_query_options_unsupported'),
])
def test_connection_format_errors_have_safe_specific_codes(raw, code):
    driver = Driver()
    with pytest.raises(SQLServerConfigurationError) as error:
        SQLServerExecutor(SQLServerSettings(raw), 'binding', {VIEW}, 2,
                          engine_factory=driver.create_engine)
    assert error.value.code == code
    assert 'top-secret' not in str(error.value)
    assert not driver.engine_calls and not driver.calls


def test_invalid_url_and_configuration_errors_are_sanitized():
    driver = Driver()
    for raw in ['PWD=top-secret', 'postgresql://u:top-secret@host/db',
                'mssql+pyodbc://u:top-secret@host/db', 'mssql+pymssql://u:top-secret@host',
                'mssql+pymssql://u:top-secret@host/db?conn_properties=DELETE']:
        with pytest.raises(ValueError) as exc:
            SQLServerExecutor(SQLServerSettings(raw), 'binding', {VIEW}, 2,
                              engine_factory=driver.create_engine)
        assert 'top-secret' not in str(exc.value)
    assert not driver.engine_calls and not driver.calls
    driver.fail = 'engine'
    with pytest.raises(ValueError) as exc:
        adapter(driver)
    assert 'top-secret' not in str(exc.value)


def test_password_special_characters_and_percent_sql_are_preserved():
    from sqlalchemy.engine import URL
    secret = 'p@ss:word;{}%中文'
    url = URL.create('mssql+pymssql', username='user', password=secret,
                     host='server.example', port=1435, database='actual-db')
    driver = Driver()
    executor = SQLServerExecutor(SQLServerSettings(url.render_as_string(hide_password=False)),
        'binding', {VIEW}, 2, engine_factory=driver.create_engine)
    sql = "SELECT * FROM gms2.v_inventory WHERE [品号] LIKE N'%ZX100%'"
    executor('binding', sql)
    assert driver.engine_calls[0][0].password == secret
    assert driver.engine_calls[0][0].port == 1435
    assert driver.connections[0].created_cursor.sql == sql


def test_tls_default_and_explicit_process_config(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.delenv('FREETDS', raising=False)
    monkeypatch.delenv('FREETDSCONF', raising=False)
    driver = Driver()
    adapter(driver)
    import os
    config = Path(os.environ['FREETDSCONF']).read_text(encoding='utf-8')
    assert 'ca file = system' in config and 'check certificate hostname = yes' in config
    assert driver.engine_calls[0][1]['connect_args']['encryption'] == 'require'
    assert not driver.calls
    selected = str(tmp_path / 'deployment.conf')
    Path(selected).write_text('[global]\nca file = system\n', encoding='utf-8')
    monkeypatch.setenv('FREETDSCONF', selected)
    adapter(driver)
    assert os.environ['FREETDSCONF'] == selected


def test_env_file_resolves_freetds_config(tmp_path, monkeypatch):
    monkeypatch.delenv('FREETDSCONF', raising=False)
    monkeypatch.delenv('FREETDS', raising=False)
    (tmp_path / '.env').write_text('FREETDSCONF=certificates.conf\n', encoding='utf-8')
    settings = AssistantSettings.from_env(tmp_path / '.env')
    assert settings.sqlserver.freetds_config_file == str(tmp_path / 'certificates.conf')


def test_real_engine_factory_and_import_do_not_connect(tmp_path, monkeypatch):
    import pymssql
    monkeypatch.setattr(pymssql, 'connect', lambda *a, **k: pytest.fail('Startup connected to DB'))
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    settings = replace(settings, sqlserver=SQLServerSettings('mssql+pymssql://u:secret@server.example/db'))
    runtime = AssistantRuntime(settings, catalog=catalog, datasource_id='binding')
    from sqlalchemy.pool import NullPool
    assert isinstance(runtime.executor._engine.pool, NullPool)
