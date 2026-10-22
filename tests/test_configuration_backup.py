import csv
import io
import json

import pytest

from services.configuration_backup_service import ConfigurationBackupService
from services.import_backup_service import BackupSizeExceeded, InvalidBackupSelection
from test_import_backup import Database, MALL, OTHER_MALL, LOCAL, INACTIVE, FOREIGN, api


def read(db, kind, ids=None, **options):
    backup = ConfigurationBackupService(db).generate(MALL, kind, ids, **options)
    try:
        content = backup.file.read().decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(content))), content
    finally:
        backup.file.close()


def configured_db():
    db = Database()
    for index, row in enumerate(db.rows['locales']):
        row.update(sftp_protocol=['SFTP', 'API', 'WEBSERVICE'][index], sftp_host='example.test',
                   sftp_pass='private-connection-password', sftp_user='private-login',
                   constants_config={'provider': 'example', 'nested': {'api_key': 'private-api-key', 'timeout': 30},
                                     'headers': {'Authorization': 'private-header'},
                                     'endpoint': 'https://user:private-url-password@host.test/data?access_token=private-query#secret'},
                   mapping_config={'fecha': 'Fecha', 'total_bruto': 'Importe'})
    db.rows['remote_connections'] = [
        {'id': 'connection-1', 'mall_id': MALL, 'nombre': 'FTP compartido', 'protocolo': 'FTP', 'password': 'private-shared-password'},
        {'id': 'connection-2', 'mall_id': OTHER_MALL, 'nombre': 'foreign-connection', 'protocolo': 'FTP'},
    ]
    db.rows['exporter_webservice_configs'] = [
        {'id': 'receiver-1', 'mall_id': MALL, 'local_id': LOCAL, 'enabled': False, 'contract_type': 'msmall_sales_v1'},
        {'id': 'receiver-2', 'mall_id': OTHER_MALL, 'local_id': FOREIGN, 'enabled': True},
    ]
    return db


def test_snapshots_partition_modules_and_omit_credentials_at_all_depths():
    db = configured_db()
    for kind in ('locales', 'importadores', 'ftp', 'webservice'):
        rows, content = read(db, kind)
        assert rows and all(row['mall_id'] == MALL for row in rows)
        assert 'private-' not in content and 'foreign-' not in content
        assert 'sftp_pass' not in content and 'sftp_user' not in content
        assert all(row['fecha_backup'] for row in rows)
        assert not any(q.table == 'ventas' for q in db.queries)
    rows, _ = read(db, 'importadores')
    assert [r['local_id'] for r in rows] == [INACTIVE]
    constants = json.loads(rows[0]['constants_config'])
    assert constants == {'endpoint': 'https://host.test/data', 'nested': {'timeout': 30}, 'provider': 'example'}
    rows, _ = read(db, 'ftp')
    assert {r['tipo_configuracion'] for r in rows} == {'importador_local', 'conexion_compartida'}
    rows, _ = read(db, 'webservice')
    assert [r['tipo_configuracion'] for r in rows] == ['receptor_erp']


def test_selection_excludes_other_stores_and_shared_connections_and_rejects_cross_mall():
    db = configured_db()
    rows, _ = read(db, 'ftp', [INACTIVE])
    assert rows == []
    for ids in ([], [FOREIGN]):
        with pytest.raises(InvalidBackupSelection):
            read(db, 'locales', ids)


def test_snapshot_size_cap_progress_cancellation_and_csv_injection():
    db = configured_db()
    db.rows['locales'][0]['nombre'] = '=HYPERLINK("https://bad.test")'
    progress = []
    rows, _ = read(db, 'locales', [LOCAL], on_progress=progress.append)
    assert rows[0]['nombre'].startswith("'")
    assert progress == sorted(progress) and len(progress) > 1
    with pytest.raises(BackupSizeExceeded):
        read(db, 'locales', max_bytes=200)
    def cancelled():
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        read(db, 'locales', check_active=cancelled)


def test_snapshot_pages_and_batches_locales():
    db = configured_db()
    db.rows['locales'] = [{'id': f'{i:036d}', 'mall_id': MALL, 'nombre': str(i)} for i in range(1001)]
    rows, _ = read(db, 'locales')
    assert len(rows) == 1001 and len({r['id'] for r in rows}) == 1001
    assert all(len(values) <= 100 for q in db.queries for op, field, values in q.filters if op == 'in')


def test_api_checks_module_permission_mall_and_accounts_for_one_snapshot(api, monkeypatch):
    def request(kind='locales', mall=MALL, ids=None):
        return api.client.post(f'/api/v1/export/import-backup/configuration/{kind}/csv',
                               headers={'X-Mall-Id': mall}, json={'local_ids': ids})
    assert request().status_code == 403
    api.access['permissions']['stores'] = {'view': True}
    assert request(mall=OTHER_MALL).status_code == 403
    assert request(ids=[FOREIGN]).status_code == 400
    assert request(kind='unknown').status_code == 404
    calls = []
    original = api.main.ImportBackupQuotaService
    monkeypatch.setattr(api.main, 'ImportBackupQuotaService', lambda *args: type('Quota', (), {
        'reserve': lambda self, days: (calls.append(days), original(*args).reserve(days))[1]})())
    response = request(ids=[LOCAL])
    assert response.status_code == 200 and calls == [1]
    assert 'backup_locales_' in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    assert int(response.headers['content-length']) == len(response.content)
    assert api.db.writes[-1][1]['accion'] == 'backup_configuracion_generado'
    assert request(kind='ftp').status_code == 403
    api.access['permissions']['imports'] = {'view': True}
    assert request(kind='webservice').status_code == 403
