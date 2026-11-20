"""Client protocol/ZIP tests on local files; no production or Windows credentials."""
import base64
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest

from services.windows_backup_package_service import build_windows_package
from test_import_backup import api, MALL, OTHER_MALL

spec = importlib.util.spec_from_file_location('windows_backup_client', Path(__file__).parents[1] / 'scripts/windows-sql-backup/backup_client.py')
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)
KEY = 'sb_publishable_test_public_configuration'
BASE = str(uuid4())


def zip_bytes(mall=MALL, mode='base', base_id=BASE, generated='2026-11-19T06:00:00+00:00'):
    manifest = {'format': 'msmall-postgres-differential-v1', 'mall_id': mall,
                'mode': mode, 'base_id': base_id, 'export_id': str(uuid4()), 'generated_at': generated}
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('data.sql', 'BEGIN;\nCOMMIT;')
        if mode == 'base':
            archive.writestr('schema.sql', '-- schema')
    return content.getvalue(), manifest


@pytest.fixture
def client(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'mall_id': MALL, 'api_url': 'https://api.example/api/v1',
                               'supabase_url': 'https://auth.example', 'publishable_key': KEY}))
    return client_module.Client(path, tmp_path / 'backups')


class Response(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {} if length is None else {'Content-Length': str(length)}


def test_private_package_only_contains_public_configuration_and_selected_mall():
    with zipfile.ZipFile(io.BytesIO(build_windows_package(MALL, 'https://auth.example', KEY))) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {'config.json', 'backup_client.py', 'Instalar.ps1', 'LEEME.txt'}
        config = json.loads(archive.read('config.json'))
        assert config['mall_id'] == MALL and config['publishable_key'] == KEY
        assert set(config) == {'mall_id', 'supabase_url', 'publishable_key', 'api_url'}
        assert b'CryptProtectData' in archive.read('backup_client.py')
    for key in ('sb_secret_unsafe_key', 'a.' + base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip('=') + '.c'):
        with pytest.raises(ValueError, match='clave pública'):
            build_windows_package(MALL, 'https://auth.example', key)


def test_package_api_preserves_admin_and_mall_authorization(api, monkeypatch):
    monkeypatch.setattr(api.main, 'sql_weekly_quota_ready', lambda: True)
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: True)
    monkeypatch.setattr(api.main, 'SUPABASE_URL', 'https://auth.example')
    endpoint = '/api/v1/export/import-backup/database/windows-package'
    response = api.client.post(endpoint, headers={'X-Mall-Id': MALL}, json={'publishable_key': KEY})
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert json.loads(archive.read('config.json'))['mall_id'] == MALL
    assert api.client.post(endpoint, headers={'X-Mall-Id': OTHER_MALL}, json={'publishable_key': KEY}).status_code == 403
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: False)
    assert api.client.post(endpoint, headers={'X-Mall-Id': MALL}, json={'publishable_key': KEY}).status_code == 403


def test_cloud_schedule_cannot_be_enabled_when_server_flag_is_off(api, monkeypatch):
    monkeypatch.setattr(api.main, 'sql_weekly_quota_ready', lambda: True)
    monkeypatch.setattr(api.main, '_backup_is_admin', lambda _: True)
    monkeypatch.setattr(api.main, 'sql_cloud_automation_ready', lambda: False)
    response = api.client.request('PUT', '/api/v1/export/import-backup/database/schedule',
                                  headers={'X-Mall-Id': MALL}, json={'enabled': True, 'run_hour': 2})
    assert response.status_code == 409 and 'Windows' in response.json()['detail']
    assert not api.db.writes


def test_direct_download_validates_crc_and_manifest_without_cloud_storage(client, monkeypatch):
    data, manifest = zip_bytes()
    client.token = 'ordinary-user-token'
    calls = []
    def open_http(url, headers, payload):
        calls.append((url, headers, payload))
        return Response(data, len(data))
    monkeypatch.setattr(client_module, 'open_http', open_http)
    path, actual = client.download('base', '2026-11-19')
    assert path.read_bytes() == data and actual == manifest
    assert path.with_suffix('.sha256').exists()
    assert not list(client.root.glob('*.part'))
    assert len(calls) == 1 and calls[0][0].endswith('/database/mall?mode=base')
    assert calls[0][1] == {'Authorization': 'Bearer ordinary-user-token', 'X-Mall-Id': MALL}
    assert client.find_base(BASE)[0] == path


@pytest.mark.parametrize('kind', ['truncated', 'foreign', 'wrong_base', 'crc'])
def test_incomplete_or_invalid_download_never_replaces_previous_full(client, monkeypatch, kind):
    original, _ = zip_bytes()
    old = client.root / 'base_original.zip'
    old.write_bytes(original)
    data, _ = zip_bytes(mall=OTHER_MALL if kind == 'foreign' else MALL,
                        base_id=str(uuid4()) if kind == 'wrong_base' else BASE, mode='differential')
    if kind == 'crc':
        data = bytearray(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo('data.sql')
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data[offset] ^= 0xff
        data = bytes(data)
    client.token = 'token'
    monkeypatch.setattr(client_module, 'open_http', lambda *_: Response(data, len(data) + (1 if kind == 'truncated' else 0)))
    with pytest.raises(Exception):
        client.download('differential', '2026-11-20', BASE)
    assert old.read_bytes() == original and not list(client.root.glob('*.part'))
    assert list(client.root.glob('*.zip')) == [old]


def test_daily_differential_uses_local_base_and_skips_verified_repeat(client, monkeypatch):
    data, _ = zip_bytes()
    (client.root / 'base_saved.zip').write_bytes(data)
    monkeypatch.setattr(client, 'api', lambda _: {'baseline': {'id': BASE}})
    calls = []
    monkeypatch.setattr(client, 'download', lambda *args: calls.append(args))
    client.run_backups('2026-11-20')
    assert calls == [('differential', '2026-11-20', BASE)]
    data, _ = zip_bytes(mode='differential')
    (client.root / 'differential_2026-11-20_saved.zip').write_bytes(data)
    client.run_backups('2026-11-20')
    assert len(calls) == 1
    (client.root / 'base_saved.zip').unlink()
    client.run_backups('2026-11-20')
    assert calls[-1] == ('base', '2026-11-20')


def test_new_server_base_monthly_rotation_and_local_day(client, monkeypatch):
    data, _ = zip_bytes(generated='2026-11-20T01:00:00Z')  # Nov 19 in Santo Domingo
    (client.root / 'base_saved.zip').write_bytes(data)
    monkeypatch.setattr(client, 'api', lambda _: {'baseline': {'id': BASE}})
    calls = []
    monkeypatch.setattr(client, 'download', lambda *args: calls.append(args))
    client.run_backups('2026-11-20')
    assert calls[-1] == ('differential', '2026-11-20', BASE)
    client.run_backups('2026-12-01')
    assert calls[-1] == ('base', '2026-12-01')
    monkeypatch.setattr(client, 'api', lambda _: {'baseline': {'id': str(uuid4())}})
    client.run_backups('2026-11-20')
    assert calls[-1] == ('base', '2026-11-20')


def test_rotated_session_is_saved_before_backup_api(client, monkeypatch):
    calls = []
    client.session.write_bytes(b'old-encrypted')
    monkeypatch.setattr(client_module, 'dpapi', lambda data, decrypt=False: b'old-refresh' if decrypt else b'new-encrypted')
    def http_json(url, headers, payload):
        assert url == 'https://auth.example/auth/v1/token?grant_type=refresh_token'
        assert payload == {'refresh_token': 'old-refresh'}
        assert headers == {'apikey': KEY}
        return {'access_token': 'new-access', 'refresh_token': 'new-refresh'}
    monkeypatch.setattr(client_module, 'http_json', http_json)
    def api_call(suffix):
        assert client.session.read_bytes() == b'new-encrypted'
        calls.append(suffix)
        return {'mall': True, 'enabled': True, 'differential': True}
    monkeypatch.setattr(client, 'api', api_call)
    client.authenticate()
    assert calls == ['/capabilities'] and client.token == 'new-access'


def test_https_only_and_redirects_do_not_transmit_bearer(client):
    with pytest.raises(client_module.ClientError):
        client_module.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example')
    config = client.config.copy()
    config['api_url'] = 'http://api.example'
    client.path.write_text(json.dumps(config))
    with pytest.raises(client_module.ClientError, match='HTTPS'):
        client_module.load_config(client.path)
