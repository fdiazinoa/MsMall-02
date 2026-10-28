import urllib.parse
import pytest
import worker_importacion as worker


def config():
    return {"id": "ego-local", "mall_id": "megacentro", "sftp_protocol": "API",
            "sftp_host": "https://egord.ddns.net/api/Ventas/ConsultarVentasPlazas",
            "sftp_user": "authorized-equipment", "sftp_pass": "test-jwt", "sftp_path": "TPV-TEST",
            "constants_config": {"provider": "ventas_plazas", "_api_date_mode": "custom",
                                 "_api_fecha_inicio": "2026-10-01", "_api_fecha_fin": "2026-10-27"}}


@pytest.mark.parametrize("wrapped", [False, True])
def test_contract_and_mapping(monkeypatch, wrapped):
    sale = {"ID_TRANSACCION": "42", "NCF": "", "NUMSERIE": "130", "FECHA": "2026-10-01",
            "HORA": "10:30:00", "TOTALBRUTO": 100, "TOTALIMPUESTOS": 18, "TOTALNETO": 118,
            "TASA": "18"}
    def request(method, url, **kwargs):
        assert method == "GET"
        assert urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) == {
            "idTpv": ["TPV-TEST"], "fechaDesde": ["20261001"], "fechaHasta": ["20261027"]}
        assert kwargs["headers"] == {"Authorization": "Bearer test-jwt", "X-Equipment-Id": "authorized-equipment", "Content-Type": "application/json"}
        return {"ventas": [sale]} if wrapped else [sale]
    monkeypatch.setattr(worker, "_api_json_request", request)
    rows, source = worker.fetch_ventas_plazas_sales(config())
    assert rows[0]["factura_no"] == "PLAZAS-TPV-TEST-42"
    assert rows[0]["local_id"] == "ego-local"
    assert rows[0]["total_neto"] == 118
    assert "Ventas Plazas" in source


@pytest.mark.parametrize("field", ["sftp_user", "sftp_pass", "sftp_path"])
def test_required_credentials(field):
    cfg = config()
    cfg[field] = ""
    with pytest.raises(ValueError, match="requiere"):
        worker.fetch_ventas_plazas_sales(cfg)


@pytest.mark.parametrize("response", [{}, {"ventas": {}}, ["bad"], [{"NCF": "A"}]])
def test_invalid_response_is_failure(monkeypatch, response):
    monkeypatch.setattr(worker, "_api_json_request", lambda *a, **k: response)
    with pytest.raises(RuntimeError):
        worker.fetch_ventas_plazas_sales(config())


def test_dispatch(monkeypatch):
    monkeypatch.setattr(worker, "process_ventas_plazas_api", lambda *a, **k: {"ok": True})
    assert worker.api_provider_name(config()) == "ventas_plazas"
    assert worker.process_webservice_import(config()) == {"ok": True}


def test_remote_preview_config():
    from main import RemoteRequest, _api_config_from_remote_request
    request = RemoteRequest(host=config()["sftp_host"], usuario="equipment", password="jwt", ruta="TPV", protocolo="API", provider="ventas_plazas")
    cfg = _api_config_from_remote_request(request, "2026-10-01", "2026-10-27")
    assert worker.api_provider_name(cfg) == "ventas_plazas"
    assert cfg["sftp_user"] == "equipment"


def test_preview_and_connection_use_plazas(monkeypatch):
    import main
    calls = []
    def fetch(cfg):
        calls.append(cfg)
        return [{"factura_no": "B01"}], "Ventas Plazas"
    monkeypatch.setattr(main, "fetch_ventas_plazas_sales", fetch)
    request = main.RemoteRequest(host=config()["sftp_host"], usuario="equipment", password="jwt", ruta="TPV", protocolo="API", provider="ventas_plazas")
    assert main._api_preview_rows(request) == [{"factura_no": "B01"}]
    assert calls[0]["constants_config"]["provider"] == "ventas_plazas"


def test_list_response_only_enabled_for_plazas(monkeypatch):
    import io
    class Response(io.BytesIO):
        status = 200
    monkeypatch.setattr(worker.urllib.request, "urlopen", lambda *a, **k: Response(b'[]'))
    assert worker._api_json_request("GET", "https://example.test", allow_list=True) == []
    with pytest.raises(RuntimeError, match="objeto JSON"):
        worker._api_json_request("GET", "https://example.test")
