"""All writes/restores in this module use a disposable local PostgreSQL cluster."""
import json
import subprocess
import zipfile
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.differential_backup_service import (
    DifferentialBackupService, DifferentialSelectionError, normalized_schema_hash,
)
from services.database_backup_service import DatabaseBackupUnavailable
from services.import_backup_service import BackupSizeExceeded
from test_database_backup import local_postgres
from test_import_backup import api, MALL, OTHER_MALL, LOCAL, FOREIGN


@pytest.fixture
def service(local_postgres, monkeypatch):
    monkeypatch.setenv('ENABLE_DATABASE_BACKUPS', 'true')
    monkeypatch.setenv('ENABLE_DIFFERENTIAL_BACKUPS', 'true')
    monkeypatch.setenv('BACKUP_DATABASE_URL', local_postgres)
    migration = next((Path(__file__).parents[1] / 'supabase/migrations').glob('*_database_backup_differential.sql'))
    with psycopg.connect(local_postgres) as conn:
        conn.execute('DROP SCHEMA IF EXISTS msmall_backup CASCADE')
        for role in ('anon', 'authenticated', 'service_role'):
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (role,)).fetchone():
                conn.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        conn.execute(migration.read_text())
    return DifferentialBackupService()


def archive(service, mode='base', mall=MALL, **kwargs):
    result = service.generate_snapshot(mode, mall, max_bytes=kwargs.pop('max_bytes', 5_000_000),
        on_progress=lambda _: None, check_active=kwargs.pop('check_active', lambda: None), **kwargs)
    with result.file, zipfile.ZipFile(result.file) as bundle:
        return {name: bundle.read(name) for name in bundle.namelist()}


def restore(dsn, content, *, succeeds=True):
    result = subprocess.run(['psql', '--dbname', dsn, '-X', '-v', 'ON_ERROR_STOP=1'], input=content, capture_output=True)
    if succeeds:
        assert result.returncode == 0, result.stderr.decode()
    else:
        assert result.returncode != 0
    return result


def test_complete_and_differential_roundtrip_with_deletes_old_edits_and_mall_isolation(service, local_postgres):
    with psycopg.connect(local_postgres) as conn:
        conn.execute('''CREATE TABLE measurements (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, mall_id uuid,
            amount integer, doubled integer GENERATED ALWAYS AS (amount * 2) STORED, note text);
            CREATE TABLE composite_keys (mall_id uuid, code integer, note text, PRIMARY KEY (mall_id, code));''')
        conn.execute('''CREATE TABLE scenarios_comp (id uuid PRIMARY KEY,mall_id uuid,UNIQUE(id,mall_id));
            CREATE TABLE actions_comp (id uuid PRIMARY KEY,scenario_id uuid,mall_id uuid,note text,
              FOREIGN KEY(scenario_id,mall_id) REFERENCES scenarios_comp(id,mall_id) ON DELETE CASCADE);
            CREATE TABLE grants_comp (user_id uuid,local_id uuid REFERENCES locales(id),PRIMARY KEY(user_id,local_id));
            CREATE TABLE mappings_comp (id uuid PRIMARY KEY,user_id uuid,local_id uuid,note text,
              FOREIGN KEY(user_id,local_id) REFERENCES grants_comp(user_id,local_id) ON DELETE CASCADE);
            CREATE TABLE inherited_comp (id uuid PRIMARY KEY,scenario_id uuid,scenario_mall uuid,note text,
              FOREIGN KEY(scenario_id,scenario_mall) REFERENCES scenarios_comp(id,mall_id) ON DELETE CASCADE);''')
        scenario,foreign_scenario,actor=[str(uuid4()) for _ in range(3)]
        conn.execute('INSERT INTO scenarios_comp VALUES (%s,%s),(%s,%s)',(scenario,MALL,foreign_scenario,OTHER_MALL))
        conn.execute("INSERT INTO actions_comp VALUES (%s,%s,%s,'OWN_ACTION'),(%s,%s,%s,'FOREIGN_ACTION')",(str(uuid4()),scenario,MALL,str(uuid4()),foreign_scenario,OTHER_MALL))
        conn.execute('INSERT INTO grants_comp VALUES (%s,%s),(%s,%s)',(actor,LOCAL,actor,FOREIGN))
        conn.execute("INSERT INTO mappings_comp VALUES (%s,%s,%s,'OWN_MAPPING'),(%s,%s,%s,'FOREIGN_MAPPING')",(str(uuid4()),actor,LOCAL,str(uuid4()),actor,FOREIGN))
        conn.execute("INSERT INTO inherited_comp VALUES (%s,%s,%s,'OWN_INHERITED'),(%s,%s,%s,'FOREIGN_INHERITED'),(%s,NULL,NULL,'UNOWNED_NULL'),(%s,NULL,%s,'UNOWNED_PARTIAL')",(str(uuid4()),scenario,MALL,str(uuid4()),foreign_scenario,OTHER_MALL,str(uuid4()),str(uuid4()),MALL))
        conn.execute('INSERT INTO measurements (mall_id,amount,note) VALUES (%s,2,%s)', (MALL, 'BASE_GENERATED'))
        conn.execute('INSERT INTO composite_keys VALUES (%s,1,%s),(%s,2,%s)', (MALL, 'BASE_COMPOSITE', MALL, 'DELETE_COMPOSITE'))
    try:
        complete = archive(service)
        manifest = json.loads(complete['manifest.json'])
        base_id = manifest['base_id']
        assert set(complete) == {'schema.sql', 'data.sql', 'manifest.json'}
        assert 'FOREIGN_SALE' not in complete['data.sql'].decode()
        assert 'GLOBAL_SECRET' not in complete['data.sql'].decode()
        assert b'OWN_INHERITED' in complete['data.sql'] and b'OWN_MAPPING' in complete['data.sql']
        assert b'UNOWNED_' not in complete['data.sql'] and b'FOREIGN_' not in complete['data.sql']
        assert service.baseline(MALL)['id'] == base_id
        assert service.baseline(OTHER_MALL) is None
        with psycopg.connect(local_postgres) as conn:
            assert conn.execute("SELECT reltuples FROM pg_class WHERE oid='msmall_backup.row_fingerprints'::regclass").fetchone()[0]>0

        # No changes -> no source row payload in the differential, no schema replay.
        empty = archive(service, 'differential', base_id=base_id)
        assert set(empty) == {'data.sql', 'manifest.json'}
        assert b'OWN_LEGACY' not in empty['data.sql']
        assert b'FOREIGN_' not in empty['data.sql']

        with psycopg.connect(local_postgres) as conn:
            conn.execute("UPDATE ventas SET nota = 'UPDATED_OLD_DATE', fecha = '2020-01-01' WHERE local_id = %s", (LOCAL,))
            conn.execute("DELETE FROM relacionados WHERE nota = 'OWN_RELATED'")
            conn.execute("INSERT INTO otras VALUES (%s,%s,'NEW_OTHER')", (str(uuid4()), MALL))
            conn.execute("UPDATE measurements SET amount = 4, note = 'CHANGED_GENERATED' WHERE mall_id = %s", (MALL,))
            conn.execute("INSERT INTO measurements (mall_id,amount,note) VALUES (%s,5,'NEW_IDENTITY')", (MALL,))
            conn.execute("UPDATE composite_keys SET note = 'CHANGED_COMPOSITE' WHERE mall_id = %s AND code = 1", (MALL,))
            conn.execute('DELETE FROM composite_keys WHERE mall_id = %s AND code = 2', (MALL,))
            conn.execute("UPDATE inherited_comp SET note='UPDATED_INHERITED' WHERE note='OWN_INHERITED'")
            conn.execute("UPDATE actions_comp SET scenario_id=%s,mall_id=%s,note='FOREIGN_MOVED' WHERE note='OWN_ACTION'",(foreign_scenario,OTHER_MALL))
            conn.execute('DELETE FROM grants_comp WHERE local_id=%s',(LOCAL,))
        diff = archive(service, 'differential', base_id=base_id)
        assert b'UPDATED_OLD_DATE' in diff['data.sql']
        assert b'NEW_OTHER' in diff['data.sql']
        assert b'FOREIGN_' not in diff['data.sql'] and b'GLOBAL_SECRET' not in diff['data.sql']
        assert service.baseline(MALL)['id'] == base_id  # a differential never advances the base

        database = 'recovery_' + uuid4().hex
        with psycopg.connect(local_postgres, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        target = make_conninfo(local_postgres, dbname=database)
        try:
            with psycopg.connect(target) as conn:
                conn.execute('DROP SCHEMA public CASCADE')
            restore(target, complete['schema.sql'])
            restore(target, complete['data.sql'])
            # Preserve another Mall already present in the recovery environment.
            with psycopg.connect(target) as conn:
                conn.execute("INSERT INTO malls VALUES (%s,'FOREIGN_MALL')", (OTHER_MALL,))
                conn.execute("INSERT INTO locales VALUES (%s,%s,'FOREIGN_LOCAL')", (FOREIGN, OTHER_MALL))
            restore(target, diff['data.sql'])
            with psycopg.connect(target) as conn:
                assert conn.execute('SELECT nota,fecha::text FROM ventas WHERE local_id = %s', (LOCAL,)).fetchone() == ('UPDATED_OLD_DATE', '2020-01-01')
                assert conn.execute("SELECT count(*) FROM relacionados WHERE nota = 'OWN_RELATED'").fetchone()[0] == 0
                assert conn.execute("SELECT count(*) FROM otras WHERE nota = 'NEW_OTHER'").fetchone()[0] == 1
                assert conn.execute('SELECT amount,doubled FROM measurements ORDER BY id').fetchall() == [(4, 8), (5, 10)]
                assert conn.execute('SELECT code,note FROM composite_keys').fetchall() == [(1, 'CHANGED_COMPOSITE')]
                assert conn.execute('SELECT count(*) FROM mappings_comp').fetchone()[0]==0
                assert conn.execute('SELECT count(*) FROM grants_comp').fetchone()[0]==0
                assert conn.execute('SELECT count(*) FROM actions_comp').fetchone()[0]==0
                assert conn.execute('SELECT note FROM inherited_comp').fetchall()==[('UPDATED_INHERITED',)]
                assert conn.execute('SELECT nombre FROM locales WHERE id = %s', (FOREIGN,)).fetchone()[0] == 'FOREIGN_LOCAL'
            # Prevent a replay, chaining, or a differential applied without its matching full base.
            replay = restore(target, diff['data.sql'], succeeds=False)
            assert b'matching original full base' in replay.stderr
            with psycopg.connect(target) as conn:
                conn.execute("UPDATE msmall_restore.baselines SET base_id = %s, state = 'base'", (str(uuid4()),))
            restore(target, diff['data.sql'], succeeds=False)
        finally:
            with psycopg.connect(local_postgres, autocommit=True) as conn:
                conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))

        # Differentials remain relative to the complete, including a reversion to base values.
        with psycopg.connect(local_postgres) as conn:
            conn.execute("UPDATE ventas SET nota = 'OWN_LEGACY', fecha = '2026-01-10' WHERE local_id = %s", (LOCAL,))
        later = archive(service, 'differential', base_id=base_id)
        assert b'OWN_LEGACY' not in later['data.sql']
    finally:
        with psycopg.connect(local_postgres) as conn:
            conn.execute('DROP TABLE measurements, composite_keys, actions_comp, mappings_comp, inherited_comp, grants_comp, scenarios_comp')


def test_missing_cross_mall_stale_base_schema_changes_and_quota_rollback(service, local_postgres):
    complete = archive(service)
    base_id = json.loads(complete['manifest.json'])['base_id']
    for mall, base in [(MALL, str(uuid4())), (OTHER_MALL, base_id)]:
        with pytest.raises(DifferentialSelectionError, match='no existe'):
            archive(service, 'differential', mall=mall, base_id=base)
    with pytest.raises(BackupSizeExceeded):
        archive(service, max_bytes=1)
    assert service.baseline(MALL)['id'] == base_id
    def cancel():
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        archive(service, check_active=cancel)
    assert service.baseline(MALL)['id'] == base_id
    with pytest.raises(RuntimeError, match='cancelled'):
        archive(service, on_ready=lambda _size: cancel())
    assert service.baseline(MALL)['id'] == base_id
    with psycopg.connect(local_postgres) as locking:
        locking.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ('msmall-differential:' + MALL,))
        with pytest.raises(DatabaseBackupUnavailable, match='Ya se está generando'):
            archive(service)
    with psycopg.connect(local_postgres) as conn:
        conn.execute('ALTER TABLE ventas ADD COLUMN changed_schema text')
    try:
        with pytest.raises(DifferentialSelectionError, match='esquema cambió'):
            archive(service, 'differential', base_id=base_id)
    finally:
        with psycopg.connect(local_postgres) as conn:
            conn.execute('ALTER TABLE ventas DROP COLUMN changed_schema')
    new_base = json.loads(archive(service)['manifest.json'])['base_id']
    assert new_base != base_id
    with pytest.raises(DifferentialSelectionError, match='no existe'):
        archive(service, 'differential', base_id=base_id)
    with psycopg.connect(local_postgres) as conn:
        assert conn.execute('SELECT count(*) FROM msmall_backup.baselines WHERE mall_id = %s', (MALL,)).fetchone()[0] == 1
        for role in ('anon', 'authenticated', 'service_role'):
            assert not conn.execute("SELECT has_schema_privilege(%s,'msmall_backup','USAGE')", (role,)).fetchone()[0]


def test_without_primary_key_and_missing_migration_fail_closed(service, local_postgres):
    with psycopg.connect(local_postgres) as conn:
        conn.execute('CREATE TABLE no_key (mall_id uuid, value text)')
    try:
        with pytest.raises(DatabaseBackupUnavailable, match='clave primaria'):
            archive(service)
    finally:
        with psycopg.connect(local_postgres) as conn:
            conn.execute('DROP TABLE no_key')
    with psycopg.connect(local_postgres) as conn:
        conn.execute('DROP SCHEMA msmall_backup CASCADE')
    with pytest.raises(DatabaseBackupUnavailable, match='migración'):
        service.baseline(MALL)


def test_flag_defaults_off_without_connecting(monkeypatch):
    monkeypatch.delenv('ENABLE_DIFFERENTIAL_BACKUPS', raising=False)
    with pytest.raises(DatabaseBackupUnavailable, match='no está habilitada'):
        DifferentialBackupService(connect=lambda *_a, **_k: pytest.fail('must not connect')).baseline(MALL)


def test_random_pg_dump_tokens_are_not_schema_changes():
    assert normalized_schema_hash(b'\\restrict aaa\nCREATE TABLE a();\n\\unrestrict aaa') == normalized_schema_hash(b'\\restrict bbb\nCREATE TABLE a();\n\\unrestrict bbb')
    assert normalized_schema_hash(b'CREATE TABLE a();') != normalized_schema_hash(b'CREATE TABLE b();')


def test_file_ceiling_migration_preserves_configured_limits(local_postgres):
    from services.import_backup_quota_service import BackupPolicy
    assert BackupPolicy().max_file_mb == 50
    assert BackupPolicy(max_file_mb=5000).max_file_mb == 5000
    with pytest.raises(ValueError):
        BackupPolicy(max_file_mb=5001)
    migration = next((Path(__file__).parents[1] / 'supabase/migrations').glob('*_database_backup_file_ceiling.sql'))
    with psycopg.connect(local_postgres) as conn:
        conn.execute('CREATE TABLE import_backup_policy (max_file_mb int DEFAULT 50 CHECK (max_file_mb BETWEEN 1 AND 1000))')
        conn.execute('INSERT INTO import_backup_policy DEFAULT VALUES')
        conn.execute(migration.read_text())
        assert conn.execute('SELECT max_file_mb FROM import_backup_policy').fetchone()[0] == 50
        conn.execute('UPDATE import_backup_policy SET max_file_mb = 5000')
        assert conn.execute('SELECT max_file_mb FROM import_backup_policy').fetchone()[0] == 5000
        # This fixture's table is disposable; leave the rest of the module's schema unchanged.
        conn.execute('DROP TABLE import_backup_policy')


def test_api_enforces_flag_permissions_base_and_no_date_filters(api, monkeypatch):
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: True)
    monkeypatch.setattr(api.main, 'database_backup_ready', lambda: True)
    monkeypatch.setattr(api.main, 'differential_backup_ready', lambda: False)
    assert api.client.post('/api/v1/export/import-backup/database/mall?mode=base', headers={'X-Mall-Id': MALL}).status_code == 503
    monkeypatch.setattr(api.main, 'differential_backup_ready', lambda: True)
    monkeypatch.setattr(api.main.DifferentialBackupService, 'baseline', lambda _self, _mall: {'id': 'safe-base'})
    assert api.client.get('/api/v1/export/import-backup/database/baseline', headers={'X-Mall-Id': MALL}).json()['baseline']['id'] == 'safe-base'
    caps = api.client.get('/api/v1/export/import-backup/database/capabilities', headers={'X-Mall-Id': MALL}).json()
    assert caps['differential'] is True
    for query in ['mode=differential', 'mode=base&base_id='+str(uuid4()), 'mode=base&fecha_inicio=2026-01-01', 'mode=unknown']:
        assert api.client.post('/api/v1/export/import-backup/database/mall?'+query, headers={'X-Mall-Id': MALL}).status_code == 422
    api.access['permissions'] = {}
    assert api.client.get('/api/v1/export/import-backup/database/baseline', headers={'X-Mall-Id': MALL}).status_code == 403


def test_api_routes_snapshots_through_existing_quota_and_masks_unexpected_errors(api, monkeypatch):
    from services.import_backup_service import GeneratedBackup
    import io
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: True)
    monkeypatch.setattr(api.main, 'database_backup_ready', lambda: True)
    monkeypatch.setattr(api.main, 'differential_backup_ready', lambda: True)
    calls = []
    def generate(_self, mode, mall, **kwargs):
        calls.append((mode, mall, kwargs['base_id'], kwargs['max_bytes']))
        return GeneratedBackup(io.BytesIO(b'zip-content'), 0, [])
    monkeypatch.setattr(api.main.DifferentialBackupService, 'generate_snapshot', generate)
    response = api.client.post('/api/v1/export/import-backup/database/mall?mode=base', headers={'X-Mall-Id': MALL})
    assert response.status_code == 200
    assert calls[0][:3] == ('base', MALL, None) and calls[0][3] > 0
    assert response.headers['cache-control'] == 'no-store'
    def fail(*_a, **_k):
        raise ValueError('postgresql://user:secret@private-host/db')
    monkeypatch.setattr(api.main.DifferentialBackupService, 'generate_snapshot', fail)
    response = api.client.post('/api/v1/export/import-backup/database/mall?mode=differential&base_id='+str(uuid4()), headers={'X-Mall-Id': MALL})
    assert response.status_code == 503
    assert 'secret' not in response.text and 'private-host' not in response.text


def test_existing_archives_restore_after_source_fingerprints_are_purged(service, local_postgres):
    with psycopg.connect(local_postgres) as conn:
        original_notes = conn.execute('SELECT id,nota FROM ventas WHERE local_id=%s', (LOCAL,)).fetchall()
    complete = archive(service)
    base_id = json.loads(complete['manifest.json'])['base_id']
    with psycopg.connect(local_postgres) as conn:
        conn.execute("UPDATE ventas SET nota='AFTER_COMPLETE' WHERE local_id=%s", (LOCAL,))
    diff = archive(service, 'differential', base_id=base_id)
    with psycopg.connect(local_postgres) as conn:
        before = conn.execute('SELECT count(*) FROM ventas').fetchone()[0]
        assert conn.execute('SELECT count(*) FROM msmall_backup.row_fingerprints').fetchone()[0] > 0
        conn.execute('TRUNCATE TABLE msmall_backup.row_fingerprints')
        assert conn.execute('SELECT count(*) FROM msmall_backup.row_fingerprints').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM ventas').fetchone()[0] == before
    database = 'recovery_purged_' + uuid4().hex
    with psycopg.connect(local_postgres, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    target = make_conninfo(local_postgres, dbname=database)
    try:
        with psycopg.connect(target) as conn:
            conn.execute('DROP SCHEMA public CASCADE')
        restore(target, complete['schema.sql'])
        restore(target, complete['data.sql'])
        restore(target, diff['data.sql'])
        with psycopg.connect(target) as conn:
            assert conn.execute('SELECT nota FROM ventas WHERE local_id=%s', (LOCAL,)).fetchone()[0] == 'AFTER_COMPLETE'
            assert conn.execute("SELECT state FROM msmall_restore.baselines WHERE mall_id=%s", (MALL,)).fetchone()[0].startswith('differential:')
    finally:
        with psycopg.connect(local_postgres, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
            for sale_id, note in original_notes:
                conn.execute('UPDATE ventas SET nota=%s WHERE id=%s', (note, sale_id))
