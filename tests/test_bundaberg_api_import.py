import urllib.parse

import pytest

import worker_importacion
from worker_importacion import (
    _bundaberg_query_sales,
    _map_bundaberg_sale,
    fetch_bundaberg_sales,
    process_webservice_import,
)


def test_map_bundaberg_sale_to_ventas_payload():
    mapped = _map_bundaberg_sale(
        {"id": "local-1", "mall_id": "mall-1"},
        {
            "id_transaccion": 13,
            "ncf": "E320000000458",
            "numserie": 454,
            "fecha": "2026-06-17",
            "hora": "11:00:39",
            "totalbruto": "185.00",
            "totalimpuestos": "28.22",
            "totalneto": "156.78",
        },
        "8906",
    )

    assert mapped == {
        "local_id": "local-1",
        "mall_id": "mall-1",
        "fecha": "2026-06-17",
        "factura_no": "454",
        "comprobante": "E320000000458",
        "hora_transaccion": "11:00:39",
        "total_bruto": 185.0,
        "total_impuestos": 28.22,
        "total_neto": 156.78,
    }


def test_bundaberg_single_date_uses_documented_query(monkeypatch):
    received = []

    def fake_request(method, url, **kwargs):
        received.append((method, urllib.parse.urlsplit(url), kwargs))
        return {"cliente": "8906", "fecha": "2026-06-17", "ventas": []}

    monkeypatch.setattr(worker_importacion, "_api_json_request", fake_request)
    rows = _bundaberg_query_sales(
        {"sftp_host": "https://provider.example/api.php"},
        id_tpv="8906",
        api_key="private-key",
        fecha_inicio="2026-06-17",
        fecha_fin="2026-06-17",
        timeout=20,
    )

    assert rows == []
    method, parsed_url, kwargs = received[0]
    assert method == "GET"
    assert parsed_url.path == "/api.php"
    assert urllib.parse.parse_qs(parsed_url.query) == {
        "idTpv": ["8906"],
        "fecha": ["2026-06-17"],
        "apiKey": ["private-key"],
    }
    assert kwargs["timeout"] == 20


def test_bundaberg_range_uses_lower_camel_case_parameters(monkeypatch):
    received = []
    monkeypatch.setattr(
        worker_importacion,
        "_api_json_request",
        lambda method, url, **kwargs: received.append(url) or {"ventas": []},
    )

    _bundaberg_query_sales(
        {"sftp_host": "https://provider.example/api.php"},
        id_tpv="8906",
        api_key="private-key",
        fecha_inicio="2026-06-01",
        fecha_fin="2026-06-17",
        timeout=20,
    )

    params = urllib.parse.parse_qs(urllib.parse.urlsplit(received[0]).query)
    assert params["fechaInicio"] == ["2026-06-01"]
    assert params["fechaFin"] == ["2026-06-17"]
    assert "fecha" not in params


def test_bundaberg_preserves_required_trailing_slash(monkeypatch):
    received = []
    monkeypatch.setattr(
        worker_importacion,
        "_api_json_request",
        lambda method, url, **kwargs: received.append(url) or {"ventas": []},
    )

    _bundaberg_query_sales(
        {"sftp_host": "https://sibs2.com/api_agora_inv/"},
        id_tpv="8906",
        api_key="private-key",
        fecha_inicio="2026-08-04",
        fecha_fin="2026-08-04",
        timeout=20,
    )

    assert urllib.parse.urlsplit(received[0]).path == "/api_agora_inv/"


def test_bundaberg_empty_success_response_means_no_sales(monkeypatch):
    monkeypatch.setattr(worker_importacion, "_api_json_request", lambda *args, **kwargs: {})

    rows = _bundaberg_query_sales(
        {"sftp_host": "https://provider.example/api.php"},
        id_tpv="8906",
        api_key="private-key",
        fecha_inicio="2026-08-04",
        fecha_fin="2026-08-04",
        timeout=20,
    )

    assert rows == []


def test_api_json_request_accepts_whitespace_only_body(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"  \n\t "

    monkeypatch.setattr(worker_importacion.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    assert worker_importacion._api_json_request("GET", "https://provider.example/api.php") == {}


def test_api_json_request_reports_non_json_without_exposing_body(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"<html>provider failure with secret data</html>"

    monkeypatch.setattr(worker_importacion.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="no es JSON valido") as error:
        worker_importacion._api_json_request("GET", "https://provider.example/api.php")

    assert "secret data" not in str(error.value)


def test_fetch_bundaberg_sales_uses_secret_and_id_tpv(monkeypatch):
    received = []
    monkeypatch.setattr(
        worker_importacion,
        "_bundaberg_query_sales",
        lambda config, **kwargs: received.append(kwargs) or [],
    )

    rows, source = fetch_bundaberg_sales({
        "sftp_host": "https://provider.example/api.php",
        "sftp_pass": "private-key",
        "sftp_path": "8906",
        "constants_config": {
            "provider": "bundaberg",
            "_api_date_mode": "custom",
            "_api_fecha_inicio": "2026-06-01",
            "_api_fecha_fin": "2026-06-17",
        },
    })

    assert rows == []
    assert source == "Bundaberg 8906 2026-06-01..2026-06-17"
    assert received[0]["api_key"] == "private-key"
    assert received[0]["id_tpv"] == "8906"


def test_webservice_dispatches_bundaberg_provider(monkeypatch):
    received = []
    monkeypatch.setattr(
        worker_importacion,
        "process_bundaberg_api",
        lambda config, write_load_log=True: received.append((config, write_load_log)) or {"ok": True},
    )

    result = process_webservice_import({
        "sftp_protocol": "API",
        "sftp_host": "https://sibs2.com/api_facturacion/api_agora_bundaberg.php",
        "constants_config": {"provider": "bundaberg"},
    }, write_load_log=False)

    assert result == {"ok": True}
    assert received[0][1] is False


def test_bundaberg_connection_test_uses_selected_provider(monkeypatch):
    import main

    received = []
    monkeypatch.setattr(
        main,
        "fetch_bundaberg_sales",
        lambda config: received.append(config) or ([], "Bundaberg 8906"),
    )

    result = main._test_remote_connection_sync(main.RemoteRequest(
        protocolo="API",
        provider="bundaberg",
        host="https://sibs2.com/api_agora_inv/",
        password="private-key",
        ruta="8906",
        tipo_archivo="JSON",
    ))

    assert result["status"] == "success"
    assert "Bundaberg" in result["message"]
    assert received[0]["sftp_pass"] == "private-key"
    assert received[0]["sftp_path"] == "8906"
