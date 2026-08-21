import json
import ssl
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path

import worker_importacion as worker


def _suba_config():
    return {
        "id": "local-suba",
        "mall_id": "mall-1",
        "nombre": "SUBA",
        "sftp_protocol": "WEBSERVICE",
        "sftp_host": "https://example.test/api/external/v1/invoices",
        "sftp_pass": "stored-bearer-token",
        "file_type": "JSON",
        "mapping_config": {
            "fecha_venta": "invoiceDate",
            "total_bruto": "totals.grandTotal",
        },
        "constants_config": {
            "local_codigo": "IMP-67140",
            "_webservice_page_param": "page",
            "_webservice_start_page": "1",
            "_webservice_max_pages": "50",
        },
    }


def test_generic_webservice_uses_saved_bearer_token_and_paginates(monkeypatch):
    requests = []

    def fake_fetch(url, token, timeout_seconds):
        page = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["page"][0])
        requests.append((page, token, timeout_seconds))
        if page == 1:
            return {"invoices": [{"invoiceNumber": "A-1"}]}
        if page == 2:
            return {"invoices": [{"invoiceNumber": "A-2"}]}
        return {"invoices": []}

    monkeypatch.setattr(worker, "_fetch_webservice_json", fake_fetch)

    records, fetched_pages, last_url = worker.fetch_generic_webservice_records(_suba_config())

    assert [row["invoiceNumber"] for row in records] == ["A-1", "A-2"]
    assert fetched_pages == 2
    assert urllib.parse.parse_qs(urllib.parse.urlparse(last_url).query)["page"] == ["3"]
    assert requests == [
        (1, "stored-bearer-token", 45),
        (2, "stored-bearer-token", 45),
        (3, "stored-bearer-token", 45),
    ]


def test_generic_webservice_adds_configured_moving_date_range(monkeypatch):
    config = _suba_config()
    config["constants_config"].update(
        {
            "_webservice_start_date_param": "start_date",
            "_webservice_end_date_param": "end_date",
            "_webservice_date_mode": "yesterday",
        }
    )
    requested_urls = []

    def fake_fetch(url, _token, _timeout_seconds):
        requested_urls.append(url)
        return {"data": []}

    monkeypatch.setattr(worker, "_now_local", lambda: datetime(2026, 8, 20, 12, 0, 0))
    monkeypatch.setattr(worker, "_fetch_webservice_json", fake_fetch)

    worker.fetch_generic_webservice_records(config)

    query = urllib.parse.parse_qs(urllib.parse.urlparse(requested_urls[0]).query)
    assert query["page"] == ["1"]
    assert query["start_date"] == ["2026-08-19"]
    assert query["end_date"] == ["2026-08-19"]


def test_generic_webservice_authenticates_dynamically_and_sends_page_size(monkeypatch):
    config = _suba_config()
    config.update({
        "sftp_user": "agora",
        "sftp_pass": "provider-secret",
        "sftp_host": "https://provider.example/Malala/ventas",
    })
    config["constants_config"].update({
        "_webservice_auth_url": "https://provider.example/Malala/auth/token",
        "_webservice_auth_username_field": "username",
        "_webservice_auth_secret_field": "clientSecret",
        "_webservice_auth_token_path": "token",
        "_webservice_start_date_param": "fechaInicio",
        "_webservice_end_date_param": "fechaFin",
        "_webservice_page_size_param": "pageSize",
        "_webservice_page_size": "1000",
        "_webservice_data_path": "data",
    })
    auth_requests = []
    sales_requests = []

    def fake_json_request(method, url, **kwargs):
        auth_requests.append((method, url, kwargs.get("body"), kwargs.get("timeout_seconds")))
        return {"token": "short-lived-jwt", "expiresIn": 3600}

    def fake_fetch(url, token, timeout_seconds):
        sales_requests.append((url, token, timeout_seconds))
        return {"data": []}

    monkeypatch.setattr(worker, "_webservice_json_request", fake_json_request)
    monkeypatch.setattr(worker, "_fetch_webservice_json", fake_fetch)
    monkeypatch.setattr(worker, "_now_local", lambda: datetime(2026, 8, 21, 12, 0, 0))

    records, fetched_pages, last_url = worker.fetch_generic_webservice_records(config)

    assert records == []
    assert fetched_pages == 0
    assert auth_requests == [(
        "POST",
        "https://provider.example/Malala/auth/token",
        {"username": "agora", "clientSecret": "provider-secret"},
        45,
    )]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(last_url).query)
    assert query == {
        "fechaInicio": ["2026-08-20"],
        "fechaFin": ["2026-08-20"],
        "page": ["1"],
        "pageSize": ["1000"],
    }
    assert sales_requests == [(last_url, "short-lived-jwt", 45)]


def test_generic_webservice_treats_configured_404_as_empty(monkeypatch):
    config = _suba_config()
    config["constants_config"]["_webservice_empty_statuses"] = "404"
    calls = []

    def fake_fetch(url, token, timeout_seconds, empty_statuses):
        calls.append((url, token, timeout_seconds, empty_statuses))
        return {}

    monkeypatch.setattr(worker, "_fetch_webservice_json", fake_fetch)

    records, fetched_pages, _last_url = worker.fetch_generic_webservice_records(config)

    assert records == []
    assert fetched_pages == 0
    assert calls[0][3] == {404}


def test_webservice_json_request_returns_empty_for_configured_status(monkeypatch):
    error = urllib.error.HTTPError(
        "https://provider.example/ventas",
        404,
        "Not Found",
        {},
        None,
    )
    monkeypatch.setattr(worker.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    payload = worker._webservice_json_request(
        "GET",
        "https://provider.example/ventas",
        timeout_seconds=20,
        empty_statuses={404},
    )

    assert payload == {}


def test_generic_webservice_uses_verified_certifi_context(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"data": []}'

    def fake_urlopen(_request, *, timeout, context):
        captured["timeout"] = timeout
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr(worker.urllib.request, "urlopen", fake_urlopen)

    payload = worker._fetch_webservice_json("https://example.test/invoices", "secret", 20)

    assert payload == {"data": []}
    assert captured["timeout"] == 20
    assert captured["context"].verify_mode == ssl.CERT_REQUIRED
    assert captured["context"].check_hostname is True


def test_agalma_invoice_fields_map_to_sales_contract(monkeypatch):
    inserted = []

    class Result:
        data = [{"id": "inserted"}]

    monkeypatch.setattr(
        worker,
        "_filter_existing_sale_rows",
        lambda rows, line_numbers, _local_id: (rows, line_numbers, []),
    )
    monkeypatch.setattr(worker, "_atomic_duplicate_details", lambda *_args: [])

    def fake_upsert(rows):
        inserted.extend(rows)
        return Result()

    monkeypatch.setattr(worker, "_upsert_sales_ignoring_duplicates", fake_upsert)

    config = {
        "id": "local-agalma",
        "mall_id": "mall-agora",
        "nombre": "AGALMA",
        "file_type": "JSON",
        "mapping_config": {
            "factura_numero": "id",
            "fecha_venta": "emission_date",
            "total_bruto": "subtotal_taxable",
            "total_impuestos": "tax_amount",
            "total_neto": "total_amount",
        },
        "constants_config": {"_moving_window_mode": "true"},
    }
    invoice = {
        "id": 618,
        "emission_date": "2026-07-08",
        "subtotal_taxable": 283.9,
        "tax_amount": 51.1,
        "total_amount": 335,
    }

    count, errors, _stats = worker.process_file_logic(config, "AGALMA.json", json.dumps([invoice]))

    assert count == 1
    assert errors == []
    assert inserted == [
        {
            "local_id": "local-agalma",
            "mall_id": "mall-agora",
            "fecha": "2026-07-08",
            "factura_no": "618",
            "total_bruto": 283.9,
            "total_impuestos": 51.1,
            "total_neto": 335.0,
        }
    ]


def test_malala_fields_map_to_sales_contract(monkeypatch):
    inserted = []

    class Result:
        data = [{"id": "inserted"}]

    monkeypatch.setattr(
        worker,
        "_filter_existing_sale_rows",
        lambda rows, line_numbers, _local_id: (rows, line_numbers, []),
    )
    monkeypatch.setattr(worker, "_atomic_duplicate_details", lambda *_args: [])
    monkeypatch.setattr(worker, "_upsert_sales_ignoring_duplicates", lambda rows: inserted.extend(rows) or Result())

    config = {
        "id": "local-malala",
        "mall_id": "mall-santiago",
        "nombre": "MALALA",
        "file_type": "JSON",
        "mapping_config": {
            "factura_numero": "ID_TRANSACCION",
            "fecha_venta": "FECHA",
            "total_bruto": "TOTALBRUTO",
            "total_impuestos": "TOTALIMPUESTOS",
            "total_neto": "TOTALNETO",
        },
        "constants_config": {"_moving_window_mode": "true"},
    }
    sale = {
        "ID_TRANSACCION": 1234,
        "FECHA": "2026-08-20",
        "HORA": "14:30:00",
        "TOTALBRUTO": 847.46,
        "TOTALIMPUESTOS": 152.54,
        "TOTALNETO": 1000,
    }

    count, errors, _stats = worker.process_file_logic(config, "MALALA.json", json.dumps([sale]))

    assert count == 1
    assert errors == []
    assert inserted == [{
        "local_id": "local-malala",
        "mall_id": "mall-santiago",
        "fecha": "2026-08-20",
        "factura_no": "1234",
        "total_bruto": 847.46,
        "total_impuestos": 152.54,
        "total_neto": 1000.0,
    }]


def test_webservice_protocol_routes_to_generic_import_without_duplicate_log(monkeypatch):
    monkeypatch.setattr(
        worker,
        "fetch_generic_webservice_records",
        lambda config: ([{"invoiceNumber": "A-1"}], 1, "https://example.test?page=1"),
    )
    processed = {}

    def fake_process(config, source_name, content):
        processed["config"] = config
        processed["source_name"] = source_name
        processed["rows"] = json.loads(content)
        return 1, [], {"moving_window_mode": True, "duplicate_skipped": 0}

    monkeypatch.setattr(worker, "process_file_logic", fake_process)
    monkeypatch.setattr(worker, "run_local_risk_analysis_if_possible", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "insert_load_log",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("manual flow must write one log only")),
    )

    result = worker.process_webservice_import(_suba_config(), write_load_log=False)

    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["canal"] == "WEBSERVICE"
    assert result["provider"] == "generic"
    assert result["records_processed"] == 1
    assert result["records_received"] == 1
    assert processed["source_name"] == "WEBSERVICE_1-1.json"
    assert processed["rows"] == [{"invoiceNumber": "A-1"}]
    assert processed["config"]["constants_config"]["_moving_window_mode"] is True


def test_worker_dispatches_legacy_webservice_protocol(monkeypatch):
    monkeypatch.setattr(worker, "process_webservice_import", lambda config: {"ok": True, "protocol": config["sftp_protocol"]})

    result = worker.process_local_files({"sftp_protocol": "WEBSERVICE"})

    assert result == {"ok": True, "protocol": "WEBSERVICE"}


def test_import_manager_keeps_webservice_separate_from_provider_api():
    repo = Path(__file__).resolve().parents[1]
    manager = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")
    types_source = (repo / "types.ts").read_text(encoding="utf-8")

    assert "'API' | 'WEBSERVICE'" in types_source
    assert '<option value="WEBSERVICE">WebService JSON (Bearer token)</option>' in manager
    assert "editingConfig.protocolo === 'WEBSERVICE'" in manager
    assert "Token Bearer del WebService" in manager


def test_import_manager_exposes_suba_webservice_date_range_controls():
    repo = Path(__file__).resolve().parents[1]
    manager = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    assert "api.suba.do/api/external/v1/invoices" in manager
    assert "Periodo de consulta WebService" in manager
    assert "Por rango de fecha" in manager
    assert "Desde" in manager
    assert "Hasta" in manager
    assert "webserviceDateModeKey = '_webservice_date_mode'" in manager
    assert "webserviceStartDateKey = '_webservice_start_date'" in manager
    assert "webserviceEndDateKey = '_webservice_end_date'" in manager
    assert "webserviceStartDateParamKey = '_webservice_start_date_param'" in manager
    assert "webserviceEndDateParamKey = '_webservice_end_date_param'" in manager
    assert "Selecciona las fechas Desde y Hasta para consultar el WebService." in manager


def test_import_manager_supports_malala_dynamic_authentication():
    repo = Path(__file__).resolve().parents[1]
    manager = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    assert "isMalalaWebserviceConfig" in manager
    assert "https://clientes.proisa.com.do/Malala" in manager
    assert "Autenticación dinámica MALALA" in manager
    assert "_webservice_auth_url" in manager
    assert "_webservice_auth_secret_field: 'clientSecret'" in manager
    assert "_webservice_page_size_param: 'pageSize'" in manager
    assert "_webservice_empty_statuses: '404'" in manager


def test_api_connection_test_and_manual_listing_recognize_webservice(monkeypatch):
    import main

    monkeypatch.setattr(
        main,
        "fetch_generic_webservice_records",
        lambda config, max_pages_override=None: ([{"invoiceNumber": "A-1"}], 1, config["sftp_host"]),
    )
    request = main.RemoteRequest(
        protocolo="WEBSERVICE",
        host="https://example.test/api/invoices",
        puerto=443,
        password="stored-bearer-token",
        ruta=".",
        tipo_archivo="JSON",
    )

    connection = main._test_remote_connection_sync(request)
    files = main._list_remote_files({"protocolo": "WEBSERVICE"})

    assert connection["status"] == "success"
    assert "Registros detectados en la primera página: 1" in connection["message"]
    assert files[0]["nombre"] == "WEBSERVICE_API"
