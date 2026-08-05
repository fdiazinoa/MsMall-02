import urllib.parse

from worker_importacion import (
    _map_studio_g_sale,
    _studio_g_probe_dates,
    _studio_g_date_range,
    fetch_studio_g_sales_detailed,
)
import pytest


def test_map_studio_g_sale_to_ventas_payload():
    config = {"id": "local-1", "mall_id": "mall-1"}
    row = {
        "IDTransaccion": 123,
        "NCF": "B0100000001",
        "Fecha": "2026-05-01T13:45:10",
        "Hora": "2026-05-01T13:45:10",
        "TotalBruto": 1000,
        "TotalImpuestos": "180.00",
        "TotalNeto": "1180.00",
    }

    mapped = _map_studio_g_sale(config, row, "AFB")

    assert mapped == {
        "local_id": "local-1",
        "mall_id": "mall-1",
        "fecha": "2026-05-01",
        "factura_no": "B0100000001",
        "comprobante": "B0100000001",
        "hora_transaccion": "13:45:10",
        "total_bruto": 1000.0,
        "total_impuestos": 180.0,
        "total_neto": 1180.0,
    }


def test_map_studio_g_sale_accepts_uppercase_api_fields():
    config = {"id": "local-1", "mall_id": "mall-1"}
    row = {
        "ID_TRANSACCION": 456,
        "NCF": "B0100000456",
        "FECHA": "2026-07-08T00:00:00",
        "HORA": "2026-07-08T15:20:30",
        "TOTALBRUTO": "2500.50",
        "TOTALIMPUESTOS": "450.09",
        "TOTALNETO": "2950.59",
    }

    mapped = _map_studio_g_sale(config, row, "AFB")

    assert mapped == {
        "local_id": "local-1",
        "mall_id": "mall-1",
        "fecha": "2026-07-08",
        "factura_no": "B0100000456",
        "comprobante": "B0100000456",
        "hora_transaccion": "15:20:30",
        "total_bruto": 2500.5,
        "total_impuestos": 450.09,
        "total_neto": 2950.59,
    }


def test_studio_g_date_range_uses_constants_for_history():
    config = {
        "constants_config": {
            "fecha_inicio": "2026-05-01",
            "fecha_fin": "2026-05-20",
        }
    }

    assert _studio_g_date_range(config) == ("2026-05-01", "2026-05-20")

def test_studio_g_date_range_uses_relative_modes(monkeypatch):
    import worker_importacion
    from datetime import datetime

    monkeypatch.setattr(worker_importacion, "_now_local", lambda: datetime(2026, 7, 8, 10, 0, 0))

    assert _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "yesterday"}}) == (
        "2026-07-07",
        "2026-07-07",
    )
    assert _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "current_month"}}) == (
        "2026-07-01",
        "2026-07-08",
    )
    assert _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "last_30_days"}}) == (
        "2026-06-09",
        "2026-07-08",
    )


def test_studio_g_custom_date_range_requires_dates():
    with pytest.raises(ValueError):
        _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "custom"}})


def test_studio_g_custom_date_range_normalizes_reversed_dates():
    config = {
        "constants_config": {
            "_studio_g_date_mode": "custom",
            "_studio_g_fecha_inicio": "2026-07-12",
            "_studio_g_fecha_fin": "2026-07-01",
        }
    }

    assert _studio_g_date_range(config) == ("2026-07-01", "2026-07-12")


def test_studio_g_range_500_falls_back_to_days_and_reports_failures(monkeypatch):
    import worker_importacion

    config = {
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "API",
        "sftp_host": "https://studio.example.test",
        "sftp_user": "client",
        "sftp_pass": "secret",
        "sftp_path": "AFB",
        "constants_config": {
            "_studio_g_date_mode": "custom",
            "_studio_g_fecha_inicio": "2026-07-11",
            "_studio_g_fecha_fin": "2026-07-13",
        },
    }
    calls = []
    monkeypatch.setattr(
        worker_importacion,
        "_studio_g_authorize",
        lambda config, constants: "token",
    )

    def fake_request(method, url, **kwargs):
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        start = params["FechaInicio"][0]
        end = params["FechaFin"][0]
        calls.append((start, end))
        if start != end or start == "2026-07-12":
            raise RuntimeError(
                'API HTTP 500: {"message":"error consultando ventas","status":"error"}'
            )
        return {
            "ventas": [{
                "IDTransaccion": start,
                "Fecha": f"{start}T10:00:00",
                "TotalBruto": 100,
                "TotalImpuestos": 18,
                "TotalNeto": 118,
            }]
        }

    monkeypatch.setattr(worker_importacion, "_api_json_request", fake_request)

    rows, source_name, failures = fetch_studio_g_sales_detailed(config)

    assert [row["fecha"] for row in rows] == ["2026-07-11", "2026-07-13"]
    assert source_name.endswith("(recuperacion diaria)")
    assert failures == [{
        "fecha": "2026-07-12",
        "error": 'API HTTP 500: {"message":"error consultando ventas","status":"error"}',
    }]
    assert calls == [
        ("2026-07-11", "2026-07-13"),
        ("2026-07-11", "2026-07-11"),
        ("2026-07-12", "2026-07-12"),
        ("2026-07-13", "2026-07-13"),
    ]


def test_studio_g_probe_dates_cover_large_range():
    from datetime import date

    assert _studio_g_probe_dates(date(2026, 7, 1), 30) == [
        "2026-07-01",
        "2026-07-08",
        "2026-07-15",
        "2026-07-23",
        "2026-07-30",
    ]


def test_studio_g_does_not_split_network_or_single_day_failures(monkeypatch):
    import worker_importacion

    config = {
        "sftp_host": "https://studio.example.test",
        "sftp_user": "client",
        "sftp_pass": "secret",
        "sftp_path": "AFB",
        "constants_config": {
            "_studio_g_date_mode": "custom",
            "_studio_g_fecha_inicio": "2026-07-11",
            "_studio_g_fecha_fin": "2026-07-13",
        },
    }
    calls = []
    monkeypatch.setattr(
        worker_importacion,
        "_studio_g_authorize",
        lambda config, constants: "token",
    )

    def fail_network(method, url, **kwargs):
        calls.append(url)
        raise RuntimeError("<urlopen error [Errno 113] No route to host>")

    monkeypatch.setattr(worker_importacion, "_api_json_request", fail_network)

    with pytest.raises(RuntimeError, match="No route to host"):
        fetch_studio_g_sales_detailed(config)

    assert len(calls) == 1


def test_studio_g_daily_fallback_fails_when_no_day_can_be_queried(monkeypatch):
    import worker_importacion

    config = {
        "sftp_host": "https://studio.example.test",
        "sftp_user": "client",
        "sftp_pass": "secret",
        "sftp_path": "AFB",
        "constants_config": {
            "_studio_g_date_mode": "custom",
            "_studio_g_fecha_inicio": "2026-07-11",
            "_studio_g_fecha_fin": "2026-07-12",
        },
    }
    calls = []
    monkeypatch.setattr(
        worker_importacion,
        "_studio_g_authorize",
        lambda config, constants: "token",
    )

    def fail_sales_query(method, url, **kwargs):
        calls.append(url)
        raise RuntimeError(
            'API HTTP 500: {"message":"error consultando ventas","status":"error"}'
        )

    monkeypatch.setattr(worker_importacion, "_api_json_request", fail_sales_query)

    with pytest.raises(RuntimeError, match="autenticacion fue correcta"):
        fetch_studio_g_sales_detailed(config)

    assert len(calls) == 3


def test_studio_g_global_outage_stops_after_representative_probes(monkeypatch):
    import worker_importacion

    config = {
        "sftp_host": "https://studio.example.test",
        "sftp_user": "client",
        "sftp_pass": "secret",
        "sftp_path": "AFB",
        "constants_config": {
            "_studio_g_date_mode": "custom",
            "_studio_g_fecha_inicio": "2026-07-01",
            "_studio_g_fecha_fin": "2026-07-30",
        },
    }
    calls = []
    monkeypatch.setattr(
        worker_importacion,
        "_studio_g_authorize",
        lambda config, constants: "token",
    )

    def fail_sales_query(method, url, **kwargs):
        calls.append(url)
        raise RuntimeError(
            'API HTTP 500: {"message":"error consultando ventas","status":"error"}'
        )

    monkeypatch.setattr(worker_importacion, "_api_json_request", fail_sales_query)

    with pytest.raises(RuntimeError, match="5 fecha\\(s\\) representativa"):
        fetch_studio_g_sales_detailed(config)

    assert len(calls) == 6


def test_studio_g_partial_result_is_logged_with_failed_dates(monkeypatch):
    import worker_importacion

    logs = []
    monkeypatch.setattr(
        worker_importacion,
        "fetch_studio_g_sales_detailed",
        lambda config: (
            [{"fecha": "2026-07-11"}],
            "Studio G AFB 2026-07-11..2026-07-13 (recuperacion diaria)",
            [{"fecha": "2026-07-12", "error": "API HTTP 500"}],
        ),
    )
    monkeypatch.setattr(
        worker_importacion,
        "_insert_studio_g_sales",
        lambda config, rows: (1, 0),
    )
    monkeypatch.setattr(
        worker_importacion,
        "insert_load_log",
        lambda *args, **kwargs: logs.append((args, kwargs)),
    )
    monkeypatch.setattr(
        worker_importacion,
        "run_local_risk_analysis_if_possible",
        lambda *args, **kwargs: None,
    )

    result = worker_importacion.process_studio_g_api({
        "id": "local-1",
        "mall_id": "mall-1",
        "nombre": "STUDIO G",
    })

    assert result["ok"] is True
    assert result["status"] == "partial"
    assert result["records_processed"] == 1
    assert result["failed_dates"] == ["2026-07-12"]
    assert result["details"][0]["tipo"] == "studio_g_date_error"
    assert logs[0][0][2] == "parcial"
    assert logs[0][1]["error_count"] == 1
    assert logs[0][1]["metadata"]["fallback_strategy"] == "daily"


def test_automatic_studio_g_config_routes_through_api_import(monkeypatch):
    import worker_importacion

    received = []
    monkeypatch.setattr(
        worker_importacion,
        "process_webservice_import",
        lambda config: received.append(config) or {"ok": True, "total_pending": 1},
    )
    config = {
        "id": "local-1",
        "nombre": "Studio G",
        "sftp_protocol": "API",
        "tipo_ejecucion": "AUTOMATICO",
        "frecuencia_cron": "cada_hora",
    }

    result = worker_importacion.process_local_files(config)

    assert result["ok"] is True
    assert received == [config]


def test_studio_g_preview_uses_history_before_sample(monkeypatch):
    import main

    calls = []
    historical_row = {
        "fecha": "2026-05-01",
        "factura_no": "B0100000001",
        "comprobante": "B0100000001",
        "hora_transaccion": "13:45:10",
        "total_bruto": 1000,
        "total_impuestos": 180,
        "total_neto": 1180,
    }

    def fake_fetch(config):
        constants = config["constants_config"]
        calls.append((constants["_studio_g_fecha_inicio"], constants["_studio_g_fecha_fin"]))
        return ([historical_row] if len(calls) == 2 else []), "Studio G test"

    monkeypatch.setattr(main, "fetch_studio_g_sales", fake_fetch)
    monkeypatch.setattr(main, "STUDIO_G_PREVIEW_HISTORY_DAYS", 120)

    rows = main._studio_g_preview_rows(
        main.RemoteRequest(
            protocolo="API",
            host="https://studio.example.test",
            usuario="user",
            password="secret",
            ruta="AFB",
            tipo_archivo="JSON",
        )
    )

    assert rows == [historical_row]
    assert len(calls) == 2
    assert calls[0][0] == calls[0][1]
    assert calls[1][0] < calls[1][1]


def test_studio_g_preview_continues_when_current_day_query_fails(monkeypatch):
    import main

    calls = []
    historical_row = {"fecha": "2026-07-11", "factura_no": "F-1"}

    def fake_fetch(config):
        calls.append(config["constants_config"])
        if len(calls) == 1:
            raise RuntimeError(
                'API HTTP 500: {"message":"error consultando ventas","status":"error"}'
            )
        return [historical_row], "Studio G history"

    monkeypatch.setattr(main, "fetch_studio_g_sales", fake_fetch)

    rows = main._studio_g_preview_rows(
        main.RemoteRequest(
            protocolo="API",
            host="https://studio.example.test",
            usuario="user",
            password="secret",
            ruta="AFB",
            tipo_archivo="JSON",
        )
    )

    assert rows == [historical_row]
    assert len(calls) == 2


def test_studio_g_connection_test_validates_sales_query(monkeypatch):
    import main

    received = []
    monkeypatch.setattr(
        main,
        "fetch_studio_g_sales",
        lambda config: received.append(config) or (
            [{"fecha": "2026-07-29"}],
            "Studio G AFB",
        ),
    )

    result = main._test_remote_connection_sync(
        main.RemoteRequest(
            protocolo="API",
            host="https://studio.example.test",
            usuario="user",
            password="secret",
            ruta="AFB",
            tipo_archivo="JSON",
        )
    )

    assert result["status"] == "success"
    assert "consulta de ventas validada" in result["message"]
    assert received[0]["sftp_path"] == "AFB"
    constants = received[0]["constants_config"]
    assert constants["_studio_g_fecha_inicio"] == constants["_studio_g_fecha_fin"]
    assert received[0]["_webservice_timeout_seconds"] == "20"


def test_runtime_import_overrides_sync_constants_config():
    import main

    base_config = {
        "constants_config": {"_studio_g_date_mode": "current_month"},
        "constants": {"_studio_g_date_mode": "current_month"},
    }
    runtime_config = main.ImportConfigSchema(
        protocolo="API",
        constants={
            "_studio_g_date_mode": "custom",
            "_studio_g_fecha_inicio": "2026-05-01",
            "_studio_g_fecha_fin": "2026-05-31",
        },
    )

    merged = main._normalize_import_config_payload(
        main._apply_runtime_import_overrides(base_config, runtime_config)
    )

    assert merged["constants"]["_studio_g_date_mode"] == "custom"
    assert merged["constants_config"]["_studio_g_date_mode"] == "custom"
    assert merged["constants_config"]["_studio_g_fecha_inicio"] == "2026-05-01"


def test_studio_g_api_can_defer_load_log_to_manual_endpoint(monkeypatch):
    import worker_importacion

    logs = []
    monkeypatch.setattr(
        worker_importacion,
        "fetch_studio_g_sales_detailed",
        lambda config: (
            [{"fecha": "2026-07-01"}],
            "Studio G AFB 2026-07-01..2026-07-01",
            [],
        ),
    )
    monkeypatch.setattr(worker_importacion, "_insert_studio_g_sales", lambda config, rows: (1, 0))
    monkeypatch.setattr(worker_importacion, "insert_load_log", lambda *args, **kwargs: logs.append((args, kwargs)))
    monkeypatch.setattr(worker_importacion, "run_local_risk_analysis_if_possible", lambda *args, **kwargs: None)

    result = worker_importacion.process_studio_g_api(
        {"id": "local-1", "mall_id": "mall-1", "nombre": "STUDIO G"},
        write_load_log=False,
    )

    assert logs == []
    assert result["status"] == "success"
    assert result["canal"] == "API"
    assert result["source_name"] == "Studio G AFB 2026-07-01..2026-07-01"
    assert result["records_processed"] == 1


def test_manual_api_webservice_endpoint_owns_monitor_log_contract():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    assert "process_webservice_import, config_data, write_load_log=False" in main_py
    assert '"source": "manual_api_webservice_import"' in main_py
    assert "insert_load_log(" in main_py
    assert "trigger=\"manual_api_webservice_import\"" in main_py
    assert 'status_value == "partial"' in main_py
    assert '"failed_dates": result.get("failed_dates") or []' in main_py


def test_specific_schedule_persists_visible_default_time():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    api_source = (repo / "api.ts").read_text(encoding="utf-8")
    manager_source = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    assert "config.frecuencia === 'hora_especifica'" in api_source
    assert "(config.hora_especifica || '08:00')" in api_source
    assert "freq.id === 'hora_especifica'" in manager_source


def test_studio_g_api_configuration_is_available_in_import_manager():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    manager_source = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")
    types_source = (repo / "types.ts").read_text(encoding="utf-8")

    assert "'FTP' | 'SFTP' | 'LOCAL' | 'API'" in types_source
    assert '<option value="API">API REST</option>' in manager_source
    assert '<option value="studio_g">Studio G</option>' in manager_source
    assert "Autenticación Client Credentials" in manager_source
    assert "Periodo de consulta API" in manager_source
    assert "ID TPV" in manager_source
    assert "constants.provider = 'studio_g'" in manager_source
    assert "const closeProgressResult = () =>" in manager_source
    assert "Cerrar resultado" in manager_source
    assert "role=\"dialog\"" in manager_source
    assert "if (config.protocolo === 'API') return true" in manager_source
    assert "Consultar y Procesar API" in manager_source
