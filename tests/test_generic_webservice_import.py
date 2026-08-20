import json
import urllib.error
import urllib.parse
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


def test_generic_webservice_sends_saved_date_range_on_every_page(monkeypatch):
    config = _suba_config()
    config["sftp_host"] = "https://example.test/api/external/v1/invoices?tenant=agora"
    config["constants_config"].update({
        "_webservice_date_mode": "custom",
        "_webservice_start_date": "2026-08-01",
        "_webservice_end_date": "2026-08-20",
        "_webservice_start_date_param": "start_date",
        "_webservice_end_date_param": "end_date",
    })
    requests = []

    def fake_fetch(url, _token, _timeout_seconds):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        requests.append(query)
        return [{"invoiceNumber": "A-1"}] if query["page"] == ["1"] else []

    monkeypatch.setattr(worker, "_fetch_webservice_json", fake_fetch)

    records, fetched_pages, _ = worker.fetch_generic_webservice_records(config)

    assert records == [{"invoiceNumber": "A-1"}]
    assert fetched_pages == 1
    assert requests == [
        {
            "tenant": ["agora"],
            "start_date": ["2026-08-01"],
            "end_date": ["2026-08-20"],
            "page": ["1"],
        },
        {
            "tenant": ["agora"],
            "start_date": ["2026-08-01"],
            "end_date": ["2026-08-20"],
            "page": ["2"],
        },
    ]


def test_generic_webservice_empty_response_reports_requested_range(monkeypatch):
    config = _suba_config()
    config["constants_config"].update({
        "_webservice_date_mode": "custom",
        "_webservice_start_date": "2026-08-01",
        "_webservice_end_date": "2026-08-20",
    })
    monkeypatch.setattr(worker, "fetch_generic_webservice_records", lambda _config: ([], 0, "https://example.test"))

    result = worker.process_webservice_import(config, write_load_log=False)

    assert result["ok"] is True
    assert result["records_received"] == 0
    assert result["message"] == "El proveedor WebService devolvió 0 registros para el rango 2026-08-01 al 2026-08-20."


def test_generic_webservice_none_date_mode_preserves_unfiltered_requests(monkeypatch):
    config = _suba_config()
    config["constants_config"]["_webservice_date_mode"] = "none"
    requests = []
    monkeypatch.setattr(
        worker,
        "_fetch_webservice_json",
        lambda url, _token, _timeout: requests.append(url) or [],
    )

    worker.fetch_generic_webservice_records(config)

    assert urllib.parse.parse_qs(urllib.parse.urlparse(requests[0]).query) == {"page": ["1"]}


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


def test_generic_webservice_explains_cloudflare_525(monkeypatch):
    def fail_with_525(_config):
        raise urllib.error.HTTPError(
            url="https://example.test/api/invoices?page=1",
            code=525,
            msg=None,
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(worker, "fetch_generic_webservice_records", fail_with_525)

    result = worker.process_webservice_import(_suba_config(), write_load_log=False)

    assert result["ok"] is False
    assert result["status"] == "error"
    assert "HTTP 525" in result["message"]
    assert "credencial no llegó a validarse" in result["message"]
    assert "<none>" not in result["message"].lower()


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
    assert "Periodo de consulta WebService" in manager
    assert "const webserviceDateModeKey = '_webservice_date_mode'" in manager
    assert "const webserviceStartDateKey = '_webservice_start_date'" in manager
    assert "const webserviceEndDateKey = '_webservice_end_date'" in manager


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


def test_api_connection_test_explains_cloudflare_525(monkeypatch):
    import main

    def fail_with_525(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://example.test/api/invoices?page=1",
            code=525,
            msg=None,
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(main, "fetch_generic_webservice_records", fail_with_525)
    request = main.RemoteRequest(
        protocolo="WEBSERVICE",
        host="https://example.test/api/invoices",
        puerto=443,
        password="stored-bearer-token",
        ruta=".",
        tipo_archivo="JSON",
    )

    result = main._test_remote_connection_sync(request)

    assert result["status"] == "error"
    assert "HTTP 525" in result["message"]
    assert "credencial no llegó a validarse" in result["message"]
    assert "<none>" not in result["message"].lower()
