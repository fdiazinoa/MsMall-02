import csv
import io
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.backup_restore_service import BackupRestoreService
from services.configuration_backup_service import ConfigurationBackupService, COLUMNS
from services.import_backup_service import ImportBackupService, CSV_COLUMNS
from test_import_backup import Database, Query, MALL, OTHER_MALL, LOCAL, sale, api


class RestoreQuery(Query):
    def upsert(self, payload, ignore_duplicates=False):
        assert ignore_duplicates is True
        self.payload, self.operation = payload, 'insert'
        return self

    def update(self, payload):
        self.payload, self.operation = payload, 'update'
        return self

    def is_(self, field, value):
        assert value == 'null'
        return self.eq(field, None)

    def execute(self):
        if self.payload is None:
            return super().execute()
        rows = self.db.rows.setdefault(self.table, [])
        if self.operation == 'insert':
            if any(r.get('id') == self.payload.get('id') for r in rows):
                return SimpleNamespace(data=[])
            rows.append(dict(self.payload))
            self.db.writes.append((self.table, self.payload))
            return SimpleNamespace(data=[dict(self.payload)])
        matches = [r for r in rows if all(r.get(field) == value for _, field, value in self.filters)]
        for row in matches:
            row.update(self.payload)
            self.db.writes.append((self.table, self.payload))
        return SimpleNamespace(data=matches)


class RestoreDB(Database):
    def table(self, name):
        return RestoreQuery(self, name)


def exported(source, kind):
    backup = (ImportBackupService(source).generate(MALL, '2026-01-01', '2026-01-31', [LOCAL])
              if kind == 'ventas' else ConfigurationBackupService(source).generate(MALL, kind, [LOCAL]))
    with backup.file:
        return backup.file.read()


def csv_bytes(kind, rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS if kind == 'ventas' else COLUMNS[kind])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def test_sales_roundtrip_preview_idempotence_and_preservation():
    source = Database([sale(factura_no='-001', total_neto='-100.00', metadata={'granularity': 'daily', 'archivo_origen': 'á.csv'})])
    content = exported(source, 'ventas')
    target = RestoreDB()
    service = BackupRestoreService(target)
    assert service.run(content, MALL, 'ventas')['pendientes'] == 1
    assert target.writes == []
    result = service.run(content, MALL, 'ventas', True)
    assert result['restaurados'] == 1 and not result['errores']
    restored = target.rows['ventas'][0]
    assert restored['factura_no'] == '-001'
    assert restored['total_neto'] == '-100.00'
    assert restored['metadata']['granularity'] == 'daily'
    assert restored['metadata']['archivo_origen'] == 'á.csv'
    assert service.run(content, MALL, 'ventas', True)['omitidos'] == 1
    assert len(target.rows['ventas']) == 1


def test_sales_natural_key_and_duplicates_inside_file():
    source = Database([sale(), sale(2)])
    target = RestoreDB([sale(3)])
    result = BackupRestoreService(target).run(exported(source, 'ventas'), MALL, 'ventas', True)
    assert result['omitidos'] == 2
    assert not target.writes


def test_locales_restore_before_sales_and_skip_existing_code():
    source = Database()
    source.rows['locales'][0]['nombre'] = '=Café, Norte\nPiso 1'
    target = RestoreDB()
    target.rows['locales'] = []
    content = exported(source, 'locales')
    service = BackupRestoreService(target)
    result = service.run(content, MALL, 'locales', True)
    assert result['restaurados'] == 1, result
    assert target.rows['locales'][0]['nombre'] == '=Café, Norte\nPiso 1'
    assert target.rows['locales'][0]['tipo_ejecucion'] == 'MANUAL'
    assert target.rows['locales'][0]['upsert_activo'] is False
    target.rows['locales'][0]['id'] = str(uuid4())
    assert service.run(content, MALL, 'locales', True)['omitidos'] == 1


def test_importers_restore_once_without_enabling_or_overwriting():
    source = Database()
    source.rows['locales'][0].update(sftp_protocol='API', sftp_host='https://example.test', sftp_port=443,
        tipo_ejecucion='AUTOMATICO', mapping_config={'fecha': 'Date'}, constants_config={'provider': 'invupos'})
    content = exported(source, 'importadores')
    target = RestoreDB()
    service = BackupRestoreService(target)
    assert service.run(content, MALL, 'importadores', True)['restaurados'] == 1
    local = target.rows['locales'][0]
    assert local['tipo_ejecucion'] == 'MANUAL'
    assert local['mapping_config'] == {'fecha': 'Date'}
    local['sftp_pass'] = 'existing-secret'
    assert service.run(content, MALL, 'importadores', True)['omitidos'] == 1
    assert local['sftp_pass'] == 'existing-secret'


def test_mixed_invalid_rows_block_all_writes_and_foreign_mall():
    # Export rejects NaN itself; build an invalid CSV from the valid backup.
    content = exported(Database([sale(), sale(2, fecha='2026-01-02')]), 'ventas')
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    rows[1]['mall_id'] = OTHER_MALL
    target = RestoreDB()
    result = BackupRestoreService(target).run(csv_bytes('ventas', rows), MALL, 'ventas', True)
    assert result['errores'] and not result['applied'] and not target.writes
    rows[1]['mall_id'] = MALL
    rows[1]['total_neto'] = 'NaN'
    assert BackupRestoreService(target).run(csv_bytes('ventas', rows), MALL, 'ventas', True)['errores']
    assert not target.writes


def test_missing_parent_and_wrong_headers_and_oversize():
    target = RestoreDB()
    target.rows['locales'] = []
    service = BackupRestoreService(target)
    assert service.run(exported(Database([sale()]), 'ventas'), MALL, 'ventas', True)['errores']
    with pytest.raises(ValueError, match='columnas'):
        service.run(b'nombre\nEjemplo\n', MALL, 'ventas')
    with pytest.raises(ValueError, match='5 MB'):
        service.run(b'x' * (5 * 1024 * 1024 + 1), MALL, 'ventas')


def test_restore_api_rejects_non_admin(api, monkeypatch):
    main, client, db = api.main, api.client, api.db
    monkeypatch.setattr(main, '_ensure_backup_mall_access', lambda *_: False)
    response = client.post('/api/v1/export/import-backup/restore/ventas', files={'file': ('backup.csv', b'')}, headers={'X-Mall-Id': MALL})
    assert response.status_code == 403
    assert not db.writes


def test_erp_receiver_restored_disabled_and_not_duplicated():
    source = Database()
    source.rows['exporter_webservice_configs'] = [dict(id=str(uuid4()), mall_id=MALL, local_id=LOCAL,
        enabled=True, contract_type='msmall_sales_v1', default_granularity='daily',
        allow_transaction=True, allow_daily=True, strict_validation=True)]
    target = RestoreDB()
    service = BackupRestoreService(target)
    content = exported(source, 'webservice')
    result = service.run(content, MALL, 'webservice', True)
    assert result['restaurados'] == 1, result
    assert target.rows['exporter_webservice_configs'][0]['enabled'] is False
    assert service.run(content, MALL, 'webservice', True)['omitidos'] == 1


def test_shared_ftp_restore_with_empty_credentials_and_idempotence():
    source = Database()
    source.rows['remote_connections'] = [dict(id=str(uuid4()), mall_id=MALL, nombre='SFTP común',
        protocolo='SFTP', host='sftp.example.test', puerto=22, ruta_base='./', usuario='secret-user', password='secret-pass')]
    backup = ConfigurationBackupService(source).generate(MALL, 'ftp', None)
    with backup.file:
        content = backup.file.read()
    target = RestoreDB()
    service = BackupRestoreService(target)
    result = service.run(content, MALL, 'ftp', True)
    assert result['restaurados'] == 1, result
    assert target.rows['remote_connections'][0]['password'] == ''
    assert target.rows['remote_connections'][0]['usuario'] == ''
    assert service.run(content, MALL, 'ftp', True)['omitidos'] == 1


@pytest.mark.parametrize('changed', [
    {'fecha_venta': '2026-99-99'}, {'total_neto': 'Infinity'},
    {'local_id': str(uuid4())}, {'id_registro': 'invalid-id'},
    {'hora_transaccion': '99:99:99'}, {'tipo_registro': 'unknown'},
])
def test_invalid_sale_cells_rejected_before_writes(changed):
    content = exported(Database([sale()]), 'ventas')
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    rows[0].update(changed)
    target = RestoreDB()
    result = BackupRestoreService(target).run(csv_bytes('ventas', rows), MALL, 'ventas', True)
    assert result['errores'] and not target.writes


def test_row_limit_and_malformed_csv():
    service = BackupRestoreService(RestoreDB())
    row = dict.fromkeys(CSV_COLUMNS, '')
    with pytest.raises(ValueError, match='2,000'):
        service.run(csv_bytes('ventas', [row] * 2001), MALL, 'ventas')
    malformed = (','.join(CSV_COLUMNS) + '\n"unterminated').encode()
    with pytest.raises(csv.Error):
        service.run(malformed, MALL, 'ventas')


def test_restore_api_preview_apply_and_repeat(api, monkeypatch):
    target = RestoreDB()
    monkeypatch.setattr(api.main, 'supabase', target)
    monkeypatch.setattr(api.main, '_ensure_backup_mall_access', lambda *_: True)
    content = exported(Database([sale()]), 'ventas')
    url = '/api/v1/export/import-backup/restore/ventas'
    kwargs = dict(files={'file': ('backup.csv', content)}, headers={'X-Mall-Id': MALL})
    preview = api.client.post(url, **kwargs)
    assert preview.status_code == 200 and preview.json()['pendientes'] == 1
    assert not target.writes
    applied = api.client.post(url + '?apply=true', **kwargs)
    assert applied.status_code == 200 and applied.json()['restaurados'] == 1
    assert api.client.post(url + '?apply=true', **kwargs).json()['omitidos'] == 1


def test_restore_api_malformed_headers_and_no_backup_permission(api, monkeypatch):
    monkeypatch.setattr(api.main, '_ensure_backup_mall_access', lambda *_: True)
    url = '/api/v1/export/import-backup/restore/locales'
    kwargs = dict(files={'file': ('backup.csv', b'nombre\nEjemplo')}, headers={'X-Mall-Id': MALL})
    assert api.client.post(url, **kwargs).status_code == 422
    api.access['permissions'] = {}
    assert api.client.post(url, **kwargs).status_code == 403


def test_database_unique_conflict_is_skipped_and_retry_recovers_partial_failure():
    class Conflict(Exception):
        code = '23505'

    target = RestoreDB()
    base_table = target.table
    failures = [Conflict(), RuntimeError('sensitive backend details')]

    def table(name):
        query = base_table(name)
        original = query.execute

        def execute():
            if query.payload is not None and failures:
                raise failures.pop(0)
            return original()
        query.execute = execute
        return query

    target.table = table
    content = exported(Database([sale(), sale(2, factura_no='002')]), 'ventas')
    service = BackupRestoreService(target)
    first = service.run(content, MALL, 'ventas', True)
    assert first['omitidos'] == 1 and len(first['errores']) == 1
    assert 'sensitive' not in str(first)
    retry = service.run(content, MALL, 'ventas', True)
    assert retry['restaurados'] == 2 and not retry['errores']


def test_importer_duplicates_inside_csv_are_only_applied_once():
    source = Database()
    source.rows['locales'][0].update(sftp_protocol='API', sftp_host='https://example.test')
    rows = list(csv.DictReader(io.StringIO(exported(source, 'importadores').decode('utf-8-sig'))))
    target = RestoreDB()
    result = BackupRestoreService(target).run(csv_bytes('importadores', rows * 2), MALL, 'importadores', True)
    assert result['restaurados'] == 1 and result['omitidos'] == 1
