import asyncio
import io
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

import main
from services import copilot_reports_service as reports


class Query:
    def __init__(self, rows, cap=500):
        self.rows = list(rows)
        self.cap = cap
        self.columns = '*'
        self.bounds = (0, 499)
    def select(self, columns):
        self.columns = columns
        return self
    def eq(self, k, v):
        self.rows = [r for r in self.rows if r.get(k) == v]
        return self
    def gte(self, k, v):
        self.rows = [r for r in self.rows if r.get(k, '') >= v]
        return self
    def lt(self, k, v):
        self.rows = [r for r in self.rows if r.get(k, '') < v]
        return self
    def order(self, k):
        self.rows.sort(key=lambda r: str(r.get(k, '')))
        return self
    def range(self, a, b):
        self.bounds = a, b
        return self
    def execute(self):
        a, b = self.bounds
        return SimpleNamespace(data=self.rows[a:min(b+1, a+self.cap)])


class Client:
    def __init__(self, data, cap=500):
        self.data, self.cap = data, cap
    def table(self, name):
        return Query(self.data.get(name, []), self.cap)


MALL = {'id': 'a', 'nombre': 'Agora Mall SQD'}


@pytest.mark.parametrize('prompt,kind', [
    ('Ayudarme a crear un reporte con el log de errores que te voy a facilitar para identificar causas', 'errores'),
    ('reporte descargable en formato excel de todas las conexiones de importación FTP', 'conexiones'),
    ('reporte con locales que han fallado al cargar o realizado cargas parciales últimos 7 días de agora mall center', 'cargas_fallidas'),
    ('locales del cubo que les falta ventas con rojo suave para exportar en excel o csv', 'cubo_faltantes'),
])
def test_four_user_commands(prompt, kind):
    assert reports.report_intent(prompt)['type'] == kind
    assert reports.report_intent(prompt)['format'] == 'xlsx'


def test_legacy_questions_stay_with_existing_copilot():
    assert reports.report_intent('Resumen de ventas recientes') is None
    assert reports.report_intent('Excel de ventas recientes') is None


def test_period_is_seven_complete_days_and_validates_dates():
    assert reports.period('últimos 7 días', now=datetime(2026, 9, 15)) == ('2026-09-08', '2026-09-14')
    assert reports.period('2026-09-01 al 2026-09-10') == ('2026-09-01', '2026-09-10')
    with pytest.raises(HTTPException): reports.period('', '2026-09-15', '2026-09-01')
    with pytest.raises(HTTPException): reports.period('', '2026-09-15', None)


def test_named_mall_is_checked_against_permissions():
    checks = []
    client = Client({'malls': [MALL, {'id': 'b', 'nombre': 'Sambil'}]})
    def access(ctx, mall_id): checks.append(mall_id)
    assert reports.resolve_mall(client, 'b', 'reporte de agora mall center', {}, access) == MALL
    assert checks == ['b', 'a']
    def deny(ctx, mall_id):
        if mall_id == 'a': raise HTTPException(403, 'denied')
    with pytest.raises(HTTPException): reports.resolve_mall(client, 'b', 'reporte de agora mall center', {}, deny)
    with pytest.raises(HTTPException): reports.resolve_mall(client, 'b', 'reporte de desconocido mall', {}, access)


def test_connections_are_complete_with_low_server_cap_and_do_not_leak_secrets():
    rows = [{'id': str(i), 'mall_id': 'a', 'nombre': f'Local {i}', 'sftp_host': 'https://host?token=SECRET', 'mapping_config': {'fecha': 'date', 'api_key': 'SECRET'}, 'sftp_pass': 'PASSWORD'} for i in range(1101)]
    rows.append({'id': 'other', 'mall_id': 'b', 'nombre': 'PRIVATE', 'sftp_host': 'host'})
    definition = reports.build_report(Client({'locales': rows}, cap=70), {'type': 'conexiones'}, MALL, '')
    assert len(definition['rows']) == 1101
    assert len(definition['headers']) == 8
    assert 'SECRET' not in json.dumps(definition)
    assert 'PASSWORD' not in json.dumps(definition)
    assert 'PRIVATE' not in json.dumps(definition)


def test_database_failure_is_not_an_empty_report():
    class Broken:
        def table(self, name): raise RuntimeError('unavailable')
    with pytest.raises(RuntimeError): reports.build_report(Broken(), {'type': 'conexiones'}, MALL, '')


def test_error_analysis_does_not_invent_fields_and_redacts_secrets():
    logs = reports.supplied_logs('fecha;hora;local;error\n2026-09-15;08:00;Tienda;timeout token=SECRET')
    rows = reports.log_rows(logs)
    assert rows[0][:3] == ['2026-09-15', '08:00', 'Tienda']
    assert 'SECRET' not in rows[0][3]
    assert rows[0][4].startswith('Posible')
    unstructured = reports.log_rows(reports.supplied_logs('unknown failure'))
    assert unstructured[0][:3] == ['No indicada', 'No indicada', 'No indicado']
    with pytest.raises(HTTPException): reports.supplied_logs('')


def test_failure_report_filters_period_mall_and_includes_partial():
    logs = [{'id': str(i), 'mall_id': 'a', 'fecha_hora': '2026-09-10T08:00:00-04:00', 'local_nombre': f'L{i}', 'estado': state, 'mensaje': 'detail'} for i, state in enumerate(['error', 'parcial', 'exito'])]
    logs += [{'id': 'x', 'mall_id': 'b', 'fecha_hora': '2026-09-10T08:00:00-04:00', 'estado': 'error'}, {'id': 'old', 'mall_id': 'a', 'fecha_hora': '2026-08-01T08:00:00-04:00', 'estado': 'error'}]
    definition = reports.build_report(Client({'logs_carga': logs}), {'type': 'cargas_fallidas'}, MALL, '', '2026-09-08', '2026-09-14')
    assert len(definition['rows']) == 2
    assert {r[3] for r in definition['rows']} == {'error', 'parcial'}


def test_cube_missing_cells_are_red_and_csv_marks_gaps(monkeypatch):
    client = Client({'locales': [{'id': 'l1', 'mall_id': 'a', 'nombre': '=HYPERLINK("evil")'}, {'id': 'l2', 'mall_id': 'a', 'nombre': 'Inactive', 'activo': False}]})
    def actual(client, **kwargs):
        assert kwargs['local_ids'] == ['l1']
        return {'l1': {'2026-09-10'}}  # A recorded zero-sale day is still present.
    monkeypatch.setattr(reports, 'load_actual_sales_dates_by_local', actual)
    definition = reports.build_report(client, {'type': 'cubo_faltantes'}, MALL, '', '2026-09-10', '2026-09-11')
    assert definition['rows'][0][1:] == [1, 'FALTAN VENTAS', 'CON VENTAS', 'SIN VENTAS']
    workbook = load_workbook(io.BytesIO(main._build_copilot_excel(definition)))
    sheet = workbook.active
    row = next(r for r in sheet if r[0].value == "'=HYPERLINK(\"evil\")")
    assert row[4].fill.fgColor.rgb == '00FEE2E2'
    assert row[3].fill.fgColor.rgb != '00FEE2E2'
    assert row[0].data_type == 's'
    csv = reports.csv_bytes(definition).decode('utf-8-sig')
    assert 'SIN VENTAS' in csv and "'=HYPERLINK" in csv


def test_operational_download_is_private_and_rechecks_mall(monkeypatch):
    monkeypatch.setattr(main, '_COPILOT_DOWNLOADS', {'id': {'owner_id': 'owner', 'mall_id': 'a', 'expires_at_epoch': 99999999999, 'content': b'test', 'mime_type': 'text/csv', 'filename': 'report.csv'}})
    with pytest.raises(HTTPException): asyncio.run(main.download_copilot_report('id'))
    with pytest.raises(HTTPException): asyncio.run(main.download_copilot_operational_report('id', {'user_id': 'other'}))
    def deny(ctx, mall): raise HTTPException(403, 'denied')
    monkeypatch.setattr(main, '_ensure_operator_can_access_mall', deny)
    with pytest.raises(HTTPException): asyncio.run(main.download_copilot_operational_report('id', {'user_id': 'owner'}))


def test_chat_routes_exports_without_using_llm_or_sample_context(monkeypatch):
    monkeypatch.setattr(main, '_copilot_config_status', lambda: {'enabled': True, 'api_key_configured': False})
    monkeypatch.setattr(main, 'supabase', Client({'malls': [MALL], 'locales': []}))
    monkeypatch.setattr(main, '_ensure_operator_can_access_mall', lambda ctx, mid: None)
    def forbidden(*args): raise AssertionError('must not query sampled context or LLM')
    monkeypatch.setattr(main, '_build_copilot_context', forbidden)
    monkeypatch.setattr(main, '_call_copilot_provider', forbidden)
    result = asyncio.run(main.chat_with_copilot(main.CopilotChatRequest(mall_id='a', message='Exportar conexiones de importación FTP en Excel'), {'user_id': 'u', 'role': 'admin'}))
    assert result['attachments'][0]['row_count'] == 0
    assert '/operational-download/' in result['attachments'][0]['download_url']
    assert result['provider'] == 'deterministic'


def test_download_succeeds_only_for_owner_and_expires(monkeypatch):
    monkeypatch.setattr(main, '_COPILOT_DOWNLOADS', {'id': {'owner_id': 'owner', 'mall_id': 'a', 'expires_at_epoch': 99999999999, 'content': b'test', 'mime_type': 'text/csv', 'filename': 'report.csv'}})
    checks = []
    monkeypatch.setattr(main, '_ensure_operator_can_access_mall', lambda ctx, mid: checks.append(mid))
    async def download():
        response = await main.download_copilot_operational_report('id', {'user_id': 'owner'})
        assert response.headers['cache-control'] == 'no-store'
        return b''.join([part async for part in response.body_iterator])
    assert asyncio.run(download()) == b'test'
    assert checks == ['a']
    main._COPILOT_DOWNLOADS['id']['expires_at_epoch'] = 1
    with pytest.raises(HTTPException): asyncio.run(download())


def test_connection_export_requires_it_or_admin():
    with pytest.raises(HTTPException) as error:
        main._prepare_operational_report(None, {'role': 'auditor'}, {'type': 'conexiones'})
    assert error.value.status_code == 403


def test_stale_log_input_does_not_override_connection_command():
    assert reports.report_intent('Excel de conexiones FTP', 'old log')['type'] == 'conexiones'
