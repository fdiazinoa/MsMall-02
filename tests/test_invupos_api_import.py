import urllib.parse
from pathlib import Path

import main
import worker_importacion as worker


def _config():
    return {
        "id": "local-food-shack",
        "mall_id": "mall-santiago-center",
        "nombre": "THE FOOD SHACK",
        "sftp_protocol": "API",
        "sftp_host": "https://api6.invupos.com/invuApiPos/index.php",
        "sftp_pass": "test-api-key",
        "sftp_path": "citas/viewAll",
        "constants_config": {"provider": "invupos"},
    }


def test_invupos_fetch_uses_apikey_header_and_documented_route(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return []

    monkeypatch.setattr(worker, "_webservice_json_request", fake_request)

    rows, source_name, rejected = worker.fetch_invupos_sales(_config())

    assert rows == []
    assert rejected == 0
    assert source_name == "InvuPOS citas/viewAll"
    assert captured["method"] == "GET"
    assert captured["headers"] == {"APIKEY": "test-api-key"}
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query) == {
        "r": ["citas/viewAll"]
    }


def test_invupos_maps_nested_sale_to_msmall_contract():
    row = {
        "numeroOrden": "ORD-42",
        "estado": "FACTURADA",
        "fechaFactura": "2026-08-28T14:35:20-04:00",
        "factura": {"numero": "B0200000042", "ncf": "B0200000042"},
        "totales": {
            "subtotal": "1,000.00",
            "impuestos": "180.00",
            "total": "1,180.00",
        },
    }

    mapped = worker._map_invupos_sale(_config(), row)

    assert mapped == {
        "local_id": "local-food-shack",
        "mall_id": "mall-santiago-center",
        "fecha": "2026-08-28",
        "factura_no": "B0200000042",
        "comprobante": "B0200000042",
        "hora_transaccion": "14:35:20",
        "total_bruto": 1000.0,
        "total_impuestos": 180.0,
        "total_neto": 1180.0,
    }


def test_invupos_uses_order_as_invoice_fallback_and_ignores_cancelled_sales():
    sale = {
        "idOrden": 77,
        "status": "PAGADA",
        "created_at": "2026-08-27 20:10:00",
        "total": 590,
        "tax": 90,
    }
    cancelled = {**sale, "idOrden": 78, "estado": "ANULADA"}

    assert worker._map_invupos_sale(_config(), sale)["factura_no"] == "INVUPOS-77"
    assert worker._map_invupos_sale(_config(), sale)["total_bruto"] == 500
    assert worker._map_invupos_sale(_config(), cancelled) is None


def test_invupos_provider_routes_through_dedicated_import(monkeypatch):
    received = []
    monkeypatch.setattr(
        worker,
        "process_invupos_api",
        lambda config, write_load_log=True: received.append((config, write_load_log)) or {"ok": True},
    )

    result = worker.process_webservice_import(_config(), write_load_log=False)

    assert result == {"ok": True}
    assert received[0][1] is False
    assert worker.api_provider_name(_config()) == "invupos"


def test_main_builds_invupos_preview_config_and_labels_virtual_file():
    request = main.RemoteRequest(
        protocolo="API",
        provider="invupos",
        host="https://api6.invupos.com/invuApiPos/index.php",
        password="test-api-key",
        ruta="citas/viewAll",
        tipo_archivo="JSON",
    )

    config = main._api_config_from_remote_request(request)
    virtual = main._list_remote_files_sync(request)

    assert config["constants_config"]["provider"] == "invupos"
    assert config["sftp_pass"] == "test-api-key"
    assert virtual["items"][0]["nombre"] == "INVUPOS_API"


def test_import_manager_exposes_invupos_without_date_controls():
    source = (Path(__file__).resolve().parents[1] / "components" / "ImportManager.tsx").read_text(
        encoding="utf-8"
    )

    assert '<option value="invupos">InvuPOS</option>' in source
    assert "https://api6.invupos.com/invuApiPos/index.php" in source
    assert "APIKEY de InvuPOS" in source
    assert "selectedApiProvider !== 'invupos'" in source
