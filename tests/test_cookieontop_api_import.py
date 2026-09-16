from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from services import cookieontop_service as service
import worker_importacion as worker

CONFIG = {'id': 'local-1', 'mall_id': 'mall-1', 'sftp_host': service.ENDPOINT,
          'sftp_pass': 'test-secret', 'sftp_path': '', 'sftp_protocol': 'API',
          'constants_config': {'provider': 'cookieontop'}}
ROW = {'Id_Transaccion': 9911, 'NCF': 'B0200009713', 'numSerie': 1,
       'Fecha': '2026-09-15', 'Hora': '11:03:24', 'Tasa': 1,
       'totalBruto': '635.59', 'totalImpuestos': '114.41', 'totalNeto': '750.00'}


def mock_api(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(service.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.parametrize('row', [ROW, {k.lower(): v for k, v in ROW.items()}])
def test_maps_live_and_documented_case_without_using_customer_as_invoice(row):
    mapped = service.map_sale(CONFIG, row)
    assert mapped['factura_no'] == 'COOKIEONTOP-9911'
    assert mapped['comprobante'] == ROW['NCF']
    assert mapped['total_neto'] == 750
    assert mapped['hora_transaccion'] == '11:03:24'
    assert mapped['local_id'] == 'local-1'
    assert service.map_sale(CONFIG, {**row, 'Tasa': 60})['total_neto'] == 45000


@pytest.mark.parametrize('patch', [{'Id_Transaccion': None}, {'totalNeto': None}, {'Tasa': 0}, {'totalBruto': 'NaN'}, {'Fecha': 'bad'}])
def test_invalid_invoice_is_not_silently_lost_or_zeroed(patch):
    with pytest.raises(ValueError):
        service.map_sale(CONFIG, {**ROW, **patch})


def test_bearer_day_and_no_tpv(monkeypatch):
    def handler(request):
        assert request.headers['Authorization'] == 'Bearer test-secret'
        assert dict(request.url.params) == {'fecha': '2026-09-15'}
        assert request.url.host == 'api.citrus.com.do'
        return httpx.Response(200, json=[ROW, ROW])
    mock_api(monkeypatch, handler)
    rows, source = service.fetch_sales(CONFIG, '2026-09-15', '2026-09-15')
    assert len(rows) == 1
    assert source == 'CookieOnTop 2026-09-15..2026-09-15'


def test_range_splits_only_on_explicit_record_limit(monkeypatch):
    calls = []
    def handler(request):
        params = dict(request.url.params)
        calls.append(params)
        assert params['idTpv'] == '7'
        if 'FechaDesde' in params:
            assert params['FechaHasta'] == '2026-09-16'
            return httpx.Response(400, json={'mensaje': 'El rango contiene 10001 registros y el máximo es 10000.'})
        return httpx.Response(200, json=[ROW] if params['fecha'] == '2026-09-15' else [])
    mock_api(monkeypatch, handler)
    rows, _ = service.fetch_sales({**CONFIG, 'sftp_path': '7'}, '2026-09-15', '2026-09-16')
    assert len(rows) == 1 and len(calls) == 3


@pytest.mark.parametrize('status,body,success', [
    (200, [], True), (404, {'mensaje': 'No se encontraron ventas para el periodo'}, True),
    (404, {'mensaje': 'ID TPV no existe'}, False), (404, {}, False),
    (401, {'secret': 'test-secret'}, False), (429, {}, False), (500, {}, False),
    (200, {'ventas': [ROW]}, False), (302, {}, False),
])
def test_empty_and_errors_never_report_false_success_or_leak_token(monkeypatch, status, body, success):
    mock_api(monkeypatch, lambda request: httpx.Response(status, json=body))
    if success:
        assert service.fetch_sales(CONFIG, '2026-09-15', '2026-09-15')[0] == []
    else:
        with pytest.raises((RuntimeError, ValueError)) as exc:
            service.fetch_sales(CONFIG, '2026-09-15', '2026-09-15')
        assert 'test-secret' not in str(exc.value)


@pytest.mark.parametrize('patch', [{'sftp_host': 'https://other.example/ventas'}, {'sftp_path': '-1'}, {'sftp_pass': ''}])
def test_bad_configuration_never_sends_request(monkeypatch, patch):
    mock_api(monkeypatch, lambda req: pytest.fail('must not send credentials'))
    with pytest.raises(ValueError):
        service.fetch_sales({**CONFIG, **patch}, '2026-09-15', '2026-09-15')


def test_rejects_out_of_period_and_conflicting_duplicate(monkeypatch):
    for rows in [[{**ROW, 'Fecha': '2026-09-16'}], [ROW, {**ROW, 'totalNeto': 800}]]:
        mock_api(monkeypatch, lambda request: httpx.Response(200, json=rows))
        with pytest.raises(ValueError):
            service.fetch_sales(CONFIG, '2026-09-15', '2026-09-15')
        monkeypatch.undo()


def test_default_queries_previous_local_day(monkeypatch):
    monkeypatch.setattr(worker, '_now_local', lambda: datetime(2026, 9, 16, 0, 15))
    monkeypatch.setattr(worker, 'fetch_cookieontop_records', lambda config, start, end: (start, end))
    assert worker.fetch_cookieontop_sales(CONFIG) == ('2026-09-15', '2026-09-15')


def test_worker_routes_and_reprocessing_is_idempotent(monkeypatch):
    mapped = service.map_sale(CONFIG, ROW)
    monkeypatch.setattr(worker, 'fetch_cookieontop_sales', lambda c: ([mapped], 'CookieOnTop test'))
    inserted = []
    class Query:
        def upsert(self, rows, **kwargs):
            assert kwargs == {'on_conflict': 'local_id,fecha,factura_no', 'ignore_duplicates': True}
            self.rows = [r for r in rows if r not in inserted]
            inserted.extend(self.rows)
            return self
        def execute(self):
            return SimpleNamespace(data=self.rows)
    monkeypatch.setattr(worker, 'supabase', SimpleNamespace(table=lambda name: Query()))
    monkeypatch.setattr(worker, 'insert_load_log', lambda *a, **k: pytest.fail('log deferred'))
    first = worker.process_webservice_import(CONFIG, write_load_log=False)
    again = worker.process_webservice_import(CONFIG, write_load_log=False)
    assert first['records_processed'] == 1 and again['records_processed'] == 0
    assert again['duplicate_skipped'] == 1
    assert first['provider'] == 'cookieontop'


def test_api_test_preview_and_virtual_file(monkeypatch):
    import main
    received = []
    monkeypatch.setattr(main, 'fetch_cookieontop_sales', lambda c: received.append(c) or ([ROW], 'CookieOnTop'))
    req = main.RemoteRequest(protocolo='API', host=service.ENDPOINT, usuario='', password='test-secret', ruta='', provider='cookieontop')
    assert main._test_remote_connection_sync(req)['status'] == 'success'
    assert main._api_preview_rows(req) == [ROW]
    assert main._list_remote_files_sync(req)['items'][0]['nombre'] == 'COOKIEONTOP_API'
    assert all(c['constants_config']['provider'] == 'cookieontop' for c in received)


def test_worker_preserves_partial_batch_progress_and_logs_error(monkeypatch):
    rows = [service.map_sale(CONFIG, {**ROW, 'Id_Transaccion': i + 1}) for i in range(501)]
    monkeypatch.setattr(worker, 'fetch_cookieontop_sales', lambda c: (rows, 'CookieOnTop test'))
    monkeypatch.setattr(worker, 'supabase', object())
    calls = []
    def insert(batch):
        calls.append(batch)
        if len(calls) == 2:
            raise RuntimeError('database unavailable')
        return SimpleNamespace(data=batch)
    monkeypatch.setattr(worker, '_upsert_sales_ignoring_duplicates', insert)
    logs = []
    monkeypatch.setattr(worker, 'insert_load_log', lambda *args, **kwargs: logs.append((args, kwargs)))
    monkeypatch.setattr(worker, 'run_local_risk_analysis_if_possible', lambda *a, **k: None)
    result = worker.process_cookieontop_api(CONFIG)
    assert result['status'] == 'partial' and result['records_processed'] == 500
    assert result['failed_files'] == 1
    assert logs[0][0][2] == 'parcial' and logs[0][1]['records_processed'] == 500


def test_fetch_failure_does_not_insert_and_is_logged(monkeypatch):
    def fail(config):
        raise RuntimeError('CookieOnTop HTTP 401: token invalido o revocado')
    monkeypatch.setattr(worker, 'fetch_cookieontop_sales', fail)
    monkeypatch.setattr(worker, '_upsert_sales_ignoring_duplicates', lambda rows: pytest.fail('no writes'))
    logs = []
    monkeypatch.setattr(worker, 'insert_load_log', lambda *a, **kw: logs.append(kw))
    result = worker.process_cookieontop_api(CONFIG)
    assert result['status'] == 'error' and not result['ok']
    assert logs[0]['error_count'] == 1
