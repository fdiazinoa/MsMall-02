import asyncio
import copy
import httpx
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

import main
from services.client_portal_service import MAX_BYTES, parse_upload, prepare_import

USER = '10000000-0000-0000-0000-000000000001'
OTHER = '10000000-0000-0000-0000-000000000002'
LOCAL = '20000000-0000-0000-0000-000000000001'
MALL = '30000000-0000-0000-0000-000000000001'
CSV = b'Invoice,Date,Gross,Tax,Net\n001,2026-11-16,118,18,100\n'
MAPPING = dict(zip(('factura_numero', 'fecha_venta', 'total_bruto', 'total_impuestos', 'total_neto'), ('Invoice', 'Date', 'Gross', 'Tax', 'Net')))


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters, self.action, self.payload, self.conflict = [], 'select', None, None
        self.maximum = None

    def select(self, *args, **kwargs): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self
    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self
    def order(self, *args, **kwargs): return self
    def limit(self, count): self.maximum = count; return self
    def insert(self, payload): self.action = 'insert'; self.payload = payload; return self
    def update(self, payload): self.action = 'update'; self.payload = payload; return self
    def delete(self): self.action = 'delete'; return self
    def upsert(self, payload, on_conflict=None):
        self.action = 'upsert'; self.payload = payload; self.conflict = on_conflict; return self

    def execute(self):
        data = self.db.rows.setdefault(self.table, [])
        matched = [row for row in data if all(predicate(row) for predicate in self.filters)]
        if self.action in ('insert', 'upsert'):
            payload = self.payload if isinstance(self.payload, list) else [self.payload]
            for row in payload:
                conflict = self.conflict.split(',') if self.conflict else ['id']
                previous = next((old for old in data if all(k in row and old.get(k) == row[k] for k in conflict)), None)
                if previous and self.action == 'insert': raise RuntimeError('unique violation')
                if previous: previous.update(copy.deepcopy(row))
                else: data.append(copy.deepcopy(row))
            matched = payload
        elif self.action == 'update':
            for row in matched: row.update(copy.deepcopy(self.payload))
        elif self.action == 'delete':
            self.db.rows[self.table] = [row for row in data if row not in matched]
        return SimpleNamespace(data=copy.deepcopy(matched[:self.maximum] if self.maximum is not None else matched))


class DB:
    def __init__(self):
        self.rows = {
            'locales': [{'id': LOCAL, 'mall_id': MALL, 'nombre': 'Local asignado', 'codigo_interno': 'L001', 'activo': True}],
            'client_portal_grants': [{'user_id': USER, 'local_id': LOCAL}],
        }
    def table(self, name): return Query(self, name)


class ASGIClient:
    def request(self, method, path, **kwargs):
        async def invoke():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://testserver') as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(invoke())
    def post(self, path, **kwargs): return self.request('POST', path, **kwargs)
    def get(self, path, **kwargs): return self.request('GET', path, **kwargs)


@pytest.fixture
def portal(monkeypatch):
    db = DB()
    monkeypatch.setenv('CLIENT_PORTAL_ENABLED', 'true')
    monkeypatch.setattr(main, 'supabase', db)
    main.app.dependency_overrides[main.get_current_user_id] = lambda: USER
    try:
        yield ASGIClient(), db
    finally:
        main.app.dependency_overrides.clear()


def post(client, endpoint, raw=CSV, filename='ventas.csv', **extra):
    return client.post('/api/v1/portal/' + endpoint, files={'file': (filename, raw)},
        data={'local_id': LOCAL, 'mapping': json.dumps(MAPPING), **extra})


def test_full_csv_flow_validation_has_no_writes_and_retry_is_idempotent(portal):
    client, db = portal
    result = post(client, 'analyze').json()
    assert result['headers'] == ['Invoice', 'Date', 'Gross', 'Tax', 'Net']
    assert result['row_count'] == 1
    validation = post(client, 'validate').json()
    assert validation['valid'], validation
    assert not db.rows.get('ventas')
    request_id = str(uuid4())
    response = post(client, 'import', request_id=request_id)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'success', response.text
    assert len(db.rows['ventas']) == 1
    sale = db.rows['ventas'][0]
    assert sale['local_id'] == LOCAL and sale['mall_id'] == MALL
    assert sale['factura_no'] == '001' and sale['total_bruto'] == 118
    assert post(client, 'import', request_id=request_id).json()['status'] == 'success'
    assert len(db.rows['ventas']) == 1
    assert post(client, 'analyze').json()['saved']['mapping'] == MAPPING
    assert client.get('/api/v1/portal/history', params={'local_id': LOCAL}).json()[0]['status'] == 'success'
    assert db.rows['logs_carga'][0]['local_id'] == LOCAL


@pytest.mark.parametrize('endpoint', ['analyze', 'validate', 'import'])
def test_other_client_and_revoked_grant_cannot_upload(portal, endpoint):
    client, db = portal
    db.rows['client_portal_grants'] = [{'user_id': OTHER, 'local_id': LOCAL}]
    response = post(client, endpoint, request_id=str(uuid4()))
    assert response.status_code == 403
    assert not db.rows.get('ventas')
    assert client.get('/api/v1/portal/local').status_code == 403
    assert client.get('/api/v1/portal/history', params={'local_id': LOCAL}).status_code == 403


def test_history_and_mapping_are_private_to_user(portal):
    client, db = portal
    db.rows['client_portal_uploads'] = [{'id': str(uuid4()), 'user_id': OTHER, 'local_id': LOCAL, 'status': 'success'}]
    assert client.get('/api/v1/portal/history', params={'local_id': LOCAL}).json() == []
    signature = parse_upload(CSV, 'ventas.csv')['signature']
    db.rows['client_portal_mappings'] = [{'user_id': OTHER, 'local_id': LOCAL, 'signature': signature, 'mapping': MAPPING}]
    assert post(client, 'analyze').json()['saved'] is None


@pytest.mark.parametrize('raw', [CSV.replace(b'118', b'NaN'), CSV.replace(b'2026-11-16', b'not-a-date'), CSV.replace(b'001,', b',')])
def test_invalid_file_is_rejected_without_writes(portal, raw):
    client, db = portal
    assert not post(client, 'validate', raw=raw).json()['valid']
    assert post(client, 'import', raw=raw, request_id=str(uuid4())).json()['status'] == 'invalid'
    assert not db.rows.get('ventas')
    assert not db.rows.get('client_portal_uploads')


def test_closed_period_blocks_portal(portal):
    client, db = portal
    db.rows['locales'][0]['fecha_corte_importacion'] = '2026-11-16'
    assert not post(client, 'validate').json()['valid']
    assert not db.rows.get('ventas')


def test_mapping_cannot_override_identity(portal):
    client, db = portal
    response = post(client, 'validate', mapping=json.dumps({**MAPPING, 'local_id': LOCAL}))
    assert response.status_code == 422
    assert not db.rows.get('ventas')


def test_flag_and_authentication_are_required(portal, monkeypatch):
    client, db = portal
    monkeypatch.delenv('CLIENT_PORTAL_ENABLED')
    assert client.get('/api/v1/portal/local').status_code == 404
    main.app.dependency_overrides.clear()
    assert client.get('/api/v1/portal/local').status_code in (401, 403)


def test_portal_account_cannot_access_internal_api(monkeypatch):
    user = SimpleNamespace(id=USER, app_metadata={'portal_client': True})
    monkeypatch.setattr(main, 'supabase', SimpleNamespace(auth=SimpleNamespace(get_user=lambda token: SimpleNamespace(user=user))))
    credential = HTTPAuthorizationCredentials(scheme='Bearer', credentials='test')
    for path in ('/api/v1/portal/local', '/api/v1/users/me/access'):
        assert main.get_current_user_id(credential, Request({'type': 'http', 'path': path, 'headers': []})) == USER
    with pytest.raises(HTTPException) as exc:
        main.get_current_user_id(credential, Request({'type': 'http', 'path': '/api/v1/admin/users', 'headers': []}))
    assert exc.value.status_code == 403


@pytest.mark.parametrize('suffix,content', [
    ('json', json.dumps([{'Invoice': '001', 'Date': '2026-11-16', 'Gross': 118, 'Tax': 18, 'Net': 100}]).encode()),
    ('html', b'<table><tr><th>Invoice</th><th>Date</th><th>Gross</th><th>Tax</th><th>Net</th></tr><tr><td>001</td><td>2026-11-16</td><td>118</td><td>18</td><td>100</td></tr></table>'),
])
def test_json_and_html_import_through_same_engine(portal, suffix, content):
    client, db = portal
    response = post(client, 'import', raw=content, filename='ventas.' + suffix, request_id=str(uuid4()))
    assert response.json()['status'] == 'success', response.text
    assert db.rows['ventas'][0]['total_neto'] == 100


@pytest.mark.parametrize('raw,name', [
    (b'<table><tr><td colspan="2">x</td></tr></table>', 'x.html'),
    (b'A,A\n1,2', 'x.csv'), (b'A,B\n1,2,3', 'x.csv'),
    (b'{"x":[{}],"y":[{}]}', 'x.json'), (b'[]', 'x.json'), (b'x', 'x.exe'),
])
def test_malformed_formats_are_explicitly_rejected(raw, name):
    with pytest.raises(ValueError): parse_upload(raw, name)


def test_multiple_html_tables_selection_and_no_execution():
    parsed = parse_upload(b'<script>alert(1)</script><table><tr><th>A</th></tr><tr><td>first</td></tr></table><table><tr><th>B</th></tr><tr><td>&lt;img src=x onerror=alert(1)&gt;</td></tr></table>', 'x.html', 1)
    assert len(parsed['tables']) == 2
    assert parsed['rows'][0]['B'] == '<img src=x onerror=alert(1)>'


def test_no_headers_json_flatten_and_european_amounts():
    parsed = parse_upload(b'001;2026-11-16;1.180,00;180,00;1.000,00', 'x.csv', has_header=False)
    mapping = dict(zip(MAPPING, parsed['headers']))
    content, _, errors = prepare_import(parsed, mapping, {'decimal_separator': ','}, {'nombre': 'Local', 'codigo_interno': 'L001'})
    assert not errors and '1180.00' in content
    assert parse_upload(b'[{"a":{"b":1}}]', 'x.json')['headers'] == ['a.b']


def test_file_size_limit():
    with pytest.raises(ValueError): parse_upload(b'x' * (MAX_BYTES + 1), 'x.csv')


def test_admin_portal_endpoints_require_internal_authorization(portal):
    client, db = portal
    # Use actual dependency chain for the privileged routes, with an unprivileged context.
    async def no_permissions(user_id):
        return {'user_id': USER, 'role': 'cliente', 'permissions': {}}
    original = main._get_access_context
    main._get_access_context = no_permissions
    try:
        for method, path, payload in [
            ('GET', '/api/v1/admin/portal/locals', None),
            ('POST', '/api/v1/admin/portal/grants', {'user_id': USER, 'local_id': LOCAL}),
            ('DELETE', '/api/v1/admin/portal/grants', {'user_id': USER, 'local_id': LOCAL}),
            ('POST', '/api/v1/admin/portal/clients', {'email': 'client@example.test', 'password': 'example-password', 'local_id': LOCAL}),
        ]:
            assert client.request(method, path, json=payload).status_code == 403
    finally:
        main._get_access_context = original


def test_inactive_local_and_wrong_mall_are_not_imported(portal):
    client, db = portal
    db.rows['locales'][0]['activo'] = False
    assert post(client, 'validate').status_code == 404
    assert client.get('/api/v1/portal/local').status_code == 404
    db.rows['locales'][0]['activo'] = True
    # Even with duplicate store codes in the mall, the assigned UUID wins.
    db.rows['locales'].append({**db.rows['locales'][0], 'id': str(uuid4())})
    assert post(client, 'import', request_id=str(uuid4())).json()['status'] == 'success'
    assert db.rows['ventas'][0]['local_id'] == LOCAL


def test_reused_request_id_cannot_process_changed_payload(portal):
    client, db = portal
    request_id = str(uuid4())
    assert post(client, 'import', request_id=request_id).json()['status'] == 'success'
    assert post(client, 'import', raw=CSV.replace(b'118', b'119'), request_id=request_id).status_code == 409
    assert len(db.rows['ventas']) == 1 and db.rows['ventas'][0]['total_bruto'] == 118


def test_staff_account_management_cannot_add_mall_access_to_portal_client(monkeypatch):
    user = SimpleNamespace(id=USER, email='client@example.test', app_metadata={'portal_client': True})
    monkeypatch.setattr(main, 'supabase', SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(get_user_by_id=lambda uid: SimpleNamespace(user=user)))))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.admin_assign_malls(USER, main.UserMallAssignment(mall_ids=[MALL]), {'user_id': OTHER}))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.admin_update_user(USER, main.AdminUpdateUserRequest(mall_ids=[MALL]), {'user_id': OTHER}))
    assert exc.value.status_code == 400


def test_local_is_bound_to_login_and_client_cannot_select_another(portal):
    client, db = portal
    other_local = str(uuid4())
    db.rows['locales'].append({**db.rows['locales'][0], 'id': other_local, 'codigo_interno': 'L002'})
    assert client.get('/api/v1/portal/local', params={'local_id': other_local}).json()['id'] == LOCAL
    # Caller-supplied local_id is ignored: the server derives the local from the authenticated user.
    result = post(client, 'import', local_id=other_local, request_id=str(uuid4()))
    assert result.json()['status'] == 'success', result.text
    assert db.rows['ventas'][0]['local_id'] == LOCAL
    assert db.rows['client_portal_uploads'][0]['local_id'] == LOCAL


def test_ambiguous_legacy_grants_fail_closed(portal):
    client, db = portal
    db.rows['client_portal_grants'].append({'user_id': USER, 'local_id': str(uuid4())})
    assert client.get('/api/v1/portal/local').status_code == 403
    assert post(client, 'import', request_id=str(uuid4())).status_code == 403
    assert not db.rows.get('ventas')


def test_admin_creates_portal_only_account_with_one_bound_local(portal, monkeypatch):
    client, db = portal
    created = []
    async def admin_context(user_id):
        return {'user_id': OTHER, 'role': 'admin', 'permissions': {'users': {'create': True, 'update': True}}}
    monkeypatch.setattr(main, '_get_access_context', admin_context)
    def create_user(payload):
        created.append(payload)
        return SimpleNamespace(user=SimpleNamespace(id=OTHER, email=payload['email']))
    db.auth = SimpleNamespace(admin=SimpleNamespace(create_user=create_user))
    response = client.post('/api/v1/admin/portal/clients', json={'email': 'client@example.test', 'password': 'temporary-password', 'local_id': LOCAL})
    assert response.status_code == 200, response.text
    assert created[0]['app_metadata'] == {'portal_client': True}
    assert not created[0].get('user_metadata', {}).get('role')
    assert {'user_id': OTHER, 'local_id': LOCAL} in db.rows['client_portal_grants']
    assert not db.rows.get('usuarios_malls')


def test_admin_cannot_give_client_second_local_or_convert_staff_implicitly(portal, monkeypatch):
    client, db = portal
    async def admin_context(user_id):
        return {'user_id': OTHER, 'role': 'admin', 'permissions': {'users': {'update': True}}}
    monkeypatch.setattr(main, '_get_access_context', admin_context)
    db.auth = SimpleNamespace(admin=SimpleNamespace(get_user_by_id=lambda uid: SimpleNamespace(user=SimpleNamespace(app_metadata={'portal_client': True}))))
    assert client.post('/api/v1/admin/portal/grants', json={'user_id': USER, 'local_id': LOCAL}).status_code == 409
    db.auth.admin.get_user_by_id = lambda uid: SimpleNamespace(user=SimpleNamespace(app_metadata={}))
    assert client.post('/api/v1/admin/portal/grants', json={'user_id': OTHER, 'local_id': LOCAL}).status_code == 400


@pytest.mark.parametrize('role', ['admin', 'custom_role'])
def test_admin_portal_locals_only_returns_active_mall(portal, monkeypatch, role):
    client, db = portal
    other_mall = str(uuid4())
    other_local = str(uuid4())
    db.rows['locales'].extend([
        {**db.rows['locales'][0], 'id': other_local, 'mall_id': other_mall},
        {**db.rows['locales'][0], 'id': str(uuid4()), 'activo': False},
    ])
    async def access_context(user_id):
        return {'user_id': USER, 'role': role, 'permissions': {'users': {'update': True}}}
    monkeypatch.setattr(main, '_get_access_context', access_context)
    monkeypatch.setattr(main, '_get_user_mall_ids', lambda uid: [MALL, other_mall])
    response = client.get('/api/v1/admin/portal/locals', params={'mall_id': MALL})
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == [LOCAL]
    response = client.get('/api/v1/admin/portal/locals', params={'mall_id': other_mall})
    assert [row['id'] for row in response.json()] == [other_local]
    assert client.get('/api/v1/admin/portal/locals').status_code == 422


def test_admin_portal_locals_requires_access_to_requested_mall(portal, monkeypatch):
    client, db = portal
    async def access_context(user_id):
        return {'user_id': USER, 'role': 'custom_role', 'permissions': {'users': {'update': True}}}
    monkeypatch.setattr(main, '_get_access_context', access_context)
    monkeypatch.setattr(main, '_get_user_mall_ids', lambda uid: [MALL])
    response = client.get('/api/v1/admin/portal/locals', params={'mall_id': str(uuid4())})
    assert response.status_code == 403
