from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
import services.missing_days_email_service as email
import services.audit_status_service as status
from services.sales_gap_service import expected_sales_dates


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.single = False
    def select(self, *a): return self
    def eq(self, *a): return self
    def order(self, *a, **kw): return self
    def limit(self, *a): return self
    def range(self, *a): return self
    def maybe_single(self):
        self.single = True
        return self
    def execute(self):
        return SimpleNamespace(data=self.rows[0] if self.single else self.rows)


class Client:
    def __init__(self, threshold=4, logs=None):
        self.threshold = threshold
        self.logs = logs or []
    def rpc(self, name, params):
        assert name == 'audit_annual_status'
        latest = next((row['fecha_hora'] for row in self.logs if (row.get('records_processed') or 0) > 0), None)
        return Query([{'local_id': 'local', 'ultima_importacion_datos': latest, 'dias_reportados': 1}])
    def table(self, name):
        return Query({
            'system_health': [{'value': str(self.threshold)}],
            'malls': [{'nombre': 'Mall prueba'}],
            'locales': [{'id': 'local', 'nombre': 'Local', 'email': 'local@example.com', 'activo': True}],
            'logs_carga': self.logs,
        }[name])


@pytest.mark.parametrize('mode', ['missing_days_audit', 'missing_days_audit_consolidated'])
@pytest.mark.parametrize('threshold,missing,sent', [(4, 0, 0), (4, 1, 0), (4, 3, 0), (4, 4, 1), (2, 1, 0), (2, 2, 1)])
def test_both_emails_respect_mall_threshold(monkeypatch, mode, threshold, missing, sent):
    monkeypatch.setattr(email, 'load_missing_days_details_for_local', lambda *a, **kw: [{'fecha': '2026-08-10'}] * missing)
    monkeypatch.setattr(email, 'load_actual_sales_dates_by_local', lambda *a, **kw: {})
    monkeypatch.setattr(email, 'load_resend_sender_config', lambda *a: {'from_email': 'test@mercasend.net', 'from_name': 'Test'})
    monkeypatch.setattr(email, 'load_annual_audit_status', lambda *a, **kw: [{'audit_year': 2026, 'dias_faltantes_anio': 8, 'ultima_importacion_datos': None}])
    calls = []
    result = email.send_missing_days_emails_for_mall(Client(threshold), {'mall_id': 'mall', 'notification_type': mode, 'cc_emails': ['admin@example.com'], 'send_only_with_gaps': False}, send_email=lambda *a, **kw: calls.append(a) or {'id': 'test'}, now=datetime(2026, 8, 20, tzinfo=timezone.utc))
    assert result['sent'] == sent
    assert len(calls) == sent
    assert result['fecha_fin'] == '2026-08-18'  # midnight UTC is previous evening in Santo Domingo


def test_annual_status_uses_import_timestamp_and_ignores_empty_import(monkeypatch):
    client = Client(logs=[{'fecha_hora': '2026-01-04T12:00:00Z', 'records_processed': 0}, {'fecha_hora': '2026-01-03T12:00:00Z', 'records_processed': 5}])
    row = status.load_annual_audit_status(client, 'mall', [{'id': 'local', 'nombre': 'Local'}], datetime(2026, 1, 4, 12, tzinfo=timezone.utc))[0]
    assert row['ultima_importacion_datos'] == '2026-01-03T12:00:00Z'
    assert row['dias_faltantes_anio'] == 2
    assert row['audit_year'] == 2026


def test_no_imports_and_first_day_of_year(monkeypatch):
    row = status.load_annual_audit_status(Client(), 'mall', [{'id': 'local', 'nombre': 'Local'}], datetime(2026, 1, 1, 12, tzinfo=timezone.utc))[0]
    assert row['dias_faltantes_anio'] == 0
    assert 'Sin ventas reportadas' in status.annual_audit_text(row)


def test_current_day_is_excluded_from_expected_dates():
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo('America/Santo_Domingo')).date()
    yesterday = today - timedelta(days=1)
    assert expected_sales_dates(yesterday.isoformat(), today.isoformat()) == {yesterday.isoformat()}
    assert expected_sales_dates(today.isoformat(), today.isoformat()) == set()


def test_annual_status_uses_one_summary_rpc_without_downloading_invoices():
    class SummaryClient:
        def rpc(self, name, params):
            assert params['p_start'] == '2026-01-01'
            assert params['p_end'] == '2026-01-03'
            assert params['p_local_ids'] == ['local']
            return Query([{'local_id': 'local', 'ultima_importacion_datos': None, 'dias_reportados': 2}])
    row = status.load_annual_audit_status(SummaryClient(), 'mall', [{'id': 'local', 'nombre': 'Local'}], datetime(2026, 1, 4, 12, tzinfo=timezone.utc))[0]
    assert row['dias_faltantes_anio'] == 1


def test_missing_summary_is_an_error_instead_of_reporting_no_sales():
    class EmptyClient:
        def rpc(self, *args): return Query([])
    with pytest.raises(ValueError):
        status.load_annual_audit_status(EmptyClient(), 'mall', [{'id': 'local', 'nombre': 'Local'}])


def test_last_import_can_be_from_a_previous_year():
    class PreviousYearClient:
        def rpc(self, *args):
            return Query([{'local_id': 'local', 'ultima_importacion_datos': '2025-12-31T12:00:00Z', 'dias_reportados': 0}])
    row = status.load_annual_audit_status(PreviousYearClient(), 'mall', [{'id': 'local', 'nombre': 'Local'}], datetime(2026, 1, 4, 12, tzinfo=timezone.utc))[0]
    assert row['ultima_importacion_datos'] == '2025-12-31T12:00:00Z'
    assert '31/12/2025' in status.annual_audit_text(row)
    assert row['audit_year'] == 2026
    assert row['dias_faltantes_anio'] == 3
