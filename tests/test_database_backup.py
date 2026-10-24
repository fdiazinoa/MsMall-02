"""All PostgreSQL integration runs use a disposable local UNIX-socket cluster."""
import io
import json
import os
import shutil
import subprocess
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.database_backup_service import DatabaseBackupService, DatabaseBackupUnavailable, Table, scope_predicates, table_order
from services.import_backup_service import BackupSizeExceeded, GeneratedBackup
from test_import_backup import api, MALL, OTHER_MALL, LOCAL, FOREIGN


def test_default_is_disabled_without_connecting(monkeypatch):
    monkeypatch.delenv('ENABLE_DATABASE_BACKUPS', raising=False)
    monkeypatch.delenv('BACKUP_DATABASE_URL', raising=False)
    with pytest.raises(DatabaseBackupUnavailable):
        DatabaseBackupService(connect=lambda *_a, **_k: pytest.fail('must not connect')).generate(
            'mall', MALL, max_bytes=1000, on_progress=lambda _: None, check_active=lambda: None)


def test_unknown_tables_are_not_exported_and_cycles_fail_closed():
    tables = {'malls': Table('malls', ['id'], []), 'locales': Table('locales', ['id', 'mall_id'], []),
              'global_secrets': Table('global_secrets', ['id', 'secret'], []),
              'unknown': Table('unknown', ['id'], [])}
    assert set(scope_predicates(tables, MALL)) == {'malls', 'locales'}
    tables['a'] = Table('a', ['id'], [('parent', 'b', 'id')])
    tables['b'] = Table('b', ['id'], [('parent', 'a', 'id')])
    with pytest.raises(DatabaseBackupUnavailable, match='ciclo'):
        table_order(tables, ['a', 'b'])


def test_api_platform_is_global_only_and_mall_admin_needs_membership(api, monkeypatch):
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: True)
    monkeypatch.setattr(api.main, 'database_backup_ready', lambda: True)
    api.access['role'] = 'admin'
    response = api.client.post('/api/v1/export/import-backup/database/platform', headers={'X-Mall-Id': MALL})
    assert response.status_code == 404
    caps = api.client.get('/api/v1/export/import-backup/database/capabilities', headers={'X-Mall-Id': MALL}).json()
    assert caps == {'enabled': True, 'mall': True, 'platform': False}
    response = api.client.post('/api/v1/export/import-backup/database/mall', headers={'X-Mall-Id': OTHER_MALL})
    assert response.status_code == 403
    assert not api.db.writes


@pytest.mark.parametrize('scope', ['mall'])
def test_global_admin_receives_zip_with_private_headers(api, monkeypatch, scope):
    api.access['email'] = next(iter(api.main.SYSTEM_ADMIN_EMAILS))
    calls = []
    def generate(_self, requested_scope, mall, **kwargs):
        calls.append((requested_scope, mall))
        return GeneratedBackup(io.BytesIO(b'zip-content'), 0, [])
    monkeypatch.setattr(api.main, 'database_backup_ready', lambda: True)
    monkeypatch.setattr(api.main.DatabaseBackupService, 'generate', generate)
    response = api.client.post('/api/v1/export/import-backup/database/' + scope, headers={'X-Mall-Id': MALL})
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/zip'
    assert response.headers['cache-control'] == 'no-store'
    assert calls == [(scope, MALL)]


def test_backup_view_permission_alone_does_not_enable_sql(api, monkeypatch):
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: False)
    assert api.client.post('/api/v1/export/import-backup/database/mall', headers={'X-Mall-Id': MALL}).status_code == 403
    api.access['permissions'] = {}
    assert api.client.get('/api/v1/export/import-backup/database/capabilities', headers={'X-Mall-Id': MALL}).status_code == 403


def test_database_errors_never_expose_connection_string(api, monkeypatch):
    api.access['email'] = next(iter(api.main.SYSTEM_ADMIN_EMAILS))
    monkeypatch.setattr(api.main, 'database_backup_ready', lambda: True)
    def fail(*_a, **_k):
        raise RuntimeError('postgres://user:secret-pass@private-host/db')
    monkeypatch.setattr(api.main.DatabaseBackupService, 'generate', fail)
    response = api.client.post('/api/v1/export/import-backup/database/mall', headers={'X-Mall-Id': MALL})
    assert response.status_code == 503
    assert 'secret-pass' not in response.text and 'private-host' not in response.text


@pytest.fixture(scope='module')
def local_postgres(tmp_path_factory):
    for binary in ('initdb', 'pg_ctl', 'pg_dump', 'pg_dumpall'):
        if not shutil.which(binary):
            pytest.skip('Local PostgreSQL binaries are required')
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        pytest.skip('initdb cannot run as root')
    root = tmp_path_factory.mktemp('sql-backup-local')
    # UNIX socket paths must stay below the OS path-length limit.
    import tempfile
    socket = tempfile.TemporaryDirectory(prefix='msmall-pg-')
    data = root / 'db'
    subprocess.run(['initdb', '-D', str(data), '-A', 'trust', '-U', 'postgres', '--no-locale', '--encoding=UTF8'], check=True, capture_output=True)
    subprocess.run(['pg_ctl', '-D', str(data), '-l', str(root / 'server.log'), '-o', f"-k {socket.name} -c listen_addresses='' -p 55467", '-w', 'start'], check=True, capture_output=True)
    dsn = f'host={socket.name} port=55467 dbname=postgres user=postgres'
    import psycopg
    try:
        with psycopg.connect(dsn) as conn:
            conn.execute('''
                CREATE TABLE malls (id uuid PRIMARY KEY, nombre text);
                CREATE TABLE locales (id uuid PRIMARY KEY, mall_id uuid REFERENCES malls(id), nombre text);
                CREATE TABLE ventas (id uuid PRIMARY KEY, local_id uuid REFERENCES locales(id), mall_id uuid, nota text);
                CREATE TABLE detalles (id uuid PRIMARY KEY, venta_id uuid REFERENCES ventas(id), nota text);
                CREATE TABLE otras (id uuid PRIMARY KEY, mall_id uuid, nota text);
                CREATE TABLE relacionados (id uuid PRIMARY KEY, detalle_id uuid REFERENCES detalles(id), otra_id uuid REFERENCES otras(id), nota text);
                CREATE TABLE global_secrets (id int PRIMARY KEY, secret text);
                CREATE SCHEMA storage;
                CREATE TABLE storage.buckets_vectors (id int);
                CREATE TABLE storage.vector_indexes (id int);
                INSERT INTO storage.buckets_vectors VALUES (999);
                INSERT INTO storage.vector_indexes VALUES (999);
                INSERT INTO global_secrets VALUES (1, 'GLOBAL_SECRET');
            ''')
            conn.execute('INSERT INTO malls VALUES (%s,%s),(%s,%s)', (MALL, 'Selected', OTHER_MALL, 'FOREIGN_MALL'))
            conn.execute('INSERT INTO locales VALUES (%s,%s,%s),(%s,%s,%s)', (LOCAL, MALL, 'Local', FOREIGN, OTHER_MALL, 'FOREIGN_LOCAL'))
            sale, foreign_sale, detail, foreign_detail, own_other, foreign_other = [str(uuid4()) for _ in range(6)]
            conn.execute('INSERT INTO ventas VALUES (%s,%s,NULL,%s),(%s,%s,%s,%s)', (sale, LOCAL, 'OWN_LEGACY', foreign_sale, FOREIGN, OTHER_MALL, 'FOREIGN_SALE'))
            conn.execute('INSERT INTO detalles VALUES (%s,%s,%s),(%s,%s,%s)', (detail, sale, 'OWN_DETAIL', foreign_detail, foreign_sale, 'FOREIGN_DETAIL'))
            conn.execute('INSERT INTO otras VALUES (%s,%s,%s),(%s,%s,%s)', (own_other, MALL, 'OWN_OTHER', foreign_other, OTHER_MALL, 'FOREIGN_OTHER'))
            conn.execute('INSERT INTO relacionados VALUES (%s,%s,%s,%s),(%s,%s,%s,%s)', (str(uuid4()), detail, own_other, 'OWN_RELATED', str(uuid4()), detail, foreign_other, 'CROSS_MALL_RELATED'))
        yield dsn
    finally:
        subprocess.run(['pg_ctl', '-D', str(data), '-m', 'immediate', '-w', 'stop'], check=True, capture_output=True)
        socket.cleanup()


def generate_local(monkeypatch, dsn, scope='mall', max_bytes=5_000_000):
    # The DSN is always this test cluster; no environment-provided remote DSN is used.
    monkeypatch.setenv('ENABLE_DATABASE_BACKUPS', 'true')
    monkeypatch.setenv('BACKUP_DATABASE_URL', dsn)
    return DatabaseBackupService().generate(scope, MALL, max_bytes=max_bytes, on_progress=lambda _: None, check_active=lambda: None)


def test_real_local_mall_archive_is_scoped_and_replayable(local_postgres, monkeypatch):
    backup = generate_local(monkeypatch, local_postgres)
    with backup.file, zipfile.ZipFile(backup.file) as bundle:
        assert set(bundle.namelist()) == {'schema.sql', 'data.sql', 'manifest.json'}
        data = bundle.read('data.sql').decode()
        assert 'OWN_LEGACY' in data and 'OWN_DETAIL' in data and 'OWN_RELATED' in data
        assert 'FOREIGN_' not in data and 'CROSS_MALL' not in data and 'GLOBAL_SECRET' not in data
        manifest = json.loads(bundle.read('manifest.json'))
        assert manifest['scope'] == 'mall'
        assert 'global_secrets' in manifest['excluded_public_tables']
        import psycopg
        from psycopg import sql
        with psycopg.connect(local_postgres) as conn:
            # Replay only on an empty duplicate schema in the disposable cluster.
            conn.execute('CREATE SCHEMA restored')
            for statement in [
                'CREATE TABLE restored.malls (LIKE public.malls INCLUDING ALL)',
                'CREATE TABLE restored.locales (LIKE public.locales INCLUDING ALL)',
                'CREATE TABLE restored.ventas (LIKE public.ventas INCLUDING ALL)',
                'CREATE TABLE restored.detalles (LIKE public.detalles INCLUDING ALL)',
                'CREATE TABLE restored.otras (LIKE public.otras INCLUDING ALL)',
                'CREATE TABLE restored.relacionados (LIKE public.relacionados INCLUDING ALL)',
            ]:
                conn.execute(statement)
            conn.execute('ALTER TABLE restored.locales ADD FOREIGN KEY (mall_id) REFERENCES restored.malls(id)')
            conn.execute('ALTER TABLE restored.ventas ADD FOREIGN KEY (local_id) REFERENCES restored.locales(id)')
            conn.execute('ALTER TABLE restored.detalles ADD FOREIGN KEY (venta_id) REFERENCES restored.ventas(id)')
            conn.execute('ALTER TABLE restored.relacionados ADD FOREIGN KEY (detalle_id) REFERENCES restored.detalles(id)')
            conn.execute('ALTER TABLE restored.relacionados ADD FOREIGN KEY (otra_id) REFERENCES restored.otras(id)')
        # psql consumes COPY text including quotes, tabs and nulls correctly.
        replay = subprocess.run(['psql', '--dbname', local_postgres, '-X', '-v', 'ON_ERROR_STOP=1'], input=data.replace('COPY public.', 'COPY restored.'), text=True, capture_output=True)
        assert replay.returncode == 0, replay.stderr
        with psycopg.connect(local_postgres) as conn:
            assert conn.execute('SELECT count(*) FROM restored.ventas').fetchone()[0] == 1


def test_real_local_platform_has_roles_and_all_malls(local_postgres, monkeypatch):
    backup = generate_local(monkeypatch, local_postgres, 'platform')
    with backup.file, zipfile.ZipFile(backup.file) as bundle:
        assert set(bundle.namelist()) == {'schema.sql', 'data.sql', 'roles.sql', 'manifest.json'}
        data = bundle.read('data.sql').decode()
        assert 'FOREIGN_SALE' in data and 'GLOBAL_SECRET' in data
        assert 'COPY storage.buckets_vectors' not in data and 'COPY storage.vector_indexes' not in data
        assert json.loads(bundle.read('manifest.json'))['mall_id'] is None


def test_real_local_quota_failure_returns_no_partial_archive(local_postgres, monkeypatch):
    with pytest.raises(BackupSizeExceeded):
        generate_local(monkeypatch, local_postgres, max_bytes=50)


def test_schema_and_data_share_snapshot_only_on_local_cluster(local_postgres, monkeypatch):
    import psycopg
    monkeypatch.setenv('ENABLE_DATABASE_BACKUPS', 'true')
    monkeypatch.setenv('BACKUP_DATABASE_URL', local_postgres)
    service = DatabaseBackupService()
    original = service._command

    def command(argv, path, *args):
        original(argv, path, *args)
        if path.name == 'schema.sql':
            with psycopg.connect(local_postgres) as conn:
                conn.execute("INSERT INTO global_secrets VALUES (2, 'AFTER_SNAPSHOT')")
    service._command = command
    backup = service.generate('platform', MALL, max_bytes=5_000_000, on_progress=lambda _: None, check_active=lambda: None)
    with backup.file, zipfile.ZipFile(backup.file) as bundle:
        assert b'AFTER_SNAPSHOT' not in bundle.read('data.sql')


def test_process_canceled_on_quota_or_deadline(tmp_path):
    import sys
    import time
    def stop():
        raise BackupSizeExceeded('quota')
    with pytest.raises(BackupSizeExceeded):
        DatabaseBackupService()._command([sys.executable, '-c', 'import time; time.sleep(10)'],
            tmp_path / 'out', dict(os.environ), stop, time.monotonic() + 30)


def test_dsn_is_not_passed_as_process_argument(local_postgres, monkeypatch):
    monkeypatch.setenv('ENABLE_DATABASE_BACKUPS', 'true')
    monkeypatch.setenv('BACKUP_DATABASE_URL', local_postgres)
    service = DatabaseBackupService()
    original = service._command
    def inspect_command(argv, path, env, *args):
        assert local_postgres not in str(argv)
        assert 'BACKUP_DATABASE_URL' not in str(argv)
        assert env['PGUSER'] == 'postgres'
        assert env['PGDATABASE'] == 'postgres'
        return original(argv, path, env, *args)
    service._command = inspect_command
    backup = service.generate('platform', MALL, max_bytes=5_000_000, on_progress=lambda _: None, check_active=lambda: None)
    backup.file.close()


def test_platform_download_removed_even_for_global_admin(api, monkeypatch):
    api.access['email'] = next(iter(api.main.SYSTEM_ADMIN_EMAILS))
    monkeypatch.setattr(api.main, 'database_backup_ready', lambda: True)
    monkeypatch.setattr(api.main.DatabaseBackupService, 'generate', lambda *_a, **_k: pytest.fail('Platform generation must not run'))
    response = api.client.post('/api/v1/export/import-backup/database/platform', headers={'X-Mall-Id': MALL})
    assert response.status_code == 404
    caps = api.client.get('/api/v1/export/import-backup/database/capabilities', headers={'X-Mall-Id': MALL}).json()
    assert caps['platform'] is False
    assert caps['mall'] is True
