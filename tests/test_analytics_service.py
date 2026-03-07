from datetime import date, timedelta

from analytics_service import AnalyticsService


def _build_sales_rows():
    today = date.today()
    rows = []
    for offset in range(6, 1, -1):
        sale_date = today - timedelta(days=offset)
        for idx in range(10):
            rows.append({
                "fecha": sale_date.isoformat(),
                "total_bruto": 100.0,
                "factura_no": f"{offset}{idx:03d}",
                "hora_transaccion": f"10:{idx:02d}:00",
            })

    alert_date = today - timedelta(days=1)
    for idx in range(8):
        rows.append({
            "fecha": alert_date.isoformat(),
            "total_bruto": 15.0,
            "factura_no": f"A{idx:03d}",
            "hora_transaccion": f"11:{idx:02d}:00",
        })
    return rows


def test_analyze_local_detects_abrupt_drop_and_repeated_amounts(monkeypatch):
    service = AnalyticsService(supabase_client=object())
    monkeypatch.setattr(service, "_fetch_store", lambda local_id: {"id": local_id, "nombre": "Demo"})
    monkeypatch.setattr(service, "_fetch_sales_rows", lambda local_id, days=30: _build_sales_rows())

    snapshot = service.analyze_local("local-1")

    assert snapshot["status"] == "ok"
    assert snapshot["summary"]["risk_state"] == "HIGH"
    assert {alert["rule_code"] for alert in snapshot["alerts"]} >= {
        "BAJA_ANOMALA",
        "MONTO_REPETIDO_CONSECUTIVO",
    }


def test_analyze_local_returns_no_data_without_enough_history(monkeypatch):
    service = AnalyticsService(supabase_client=object())
    today = date.today().isoformat()
    monkeypatch.setattr(service, "_fetch_store", lambda local_id: {"id": local_id, "nombre": "Demo"})
    monkeypatch.setattr(service, "_fetch_sales_rows", lambda local_id, days=30: [
        {"fecha": today, "total_bruto": 120.0, "factura_no": "1", "hora_transaccion": "10:00:00"},
        {"fecha": today, "total_bruto": 130.0, "factura_no": "2", "hora_transaccion": "10:05:00"},
    ])

    snapshot = service.analyze_local("local-1")

    assert snapshot["status"] == "no_data"
    assert snapshot["summary"]["risk_state"] == "NO_DATA"


def test_get_alert_snapshot_uses_recent_stored_run_before_live_refresh(monkeypatch):
    service = AnalyticsService(supabase_client=object())
    run_at = date.today().isoformat() + "T10:00:00+00:00"
    monkeypatch.setattr(service, "_fetch_store", lambda local_id: {"id": local_id, "nombre": "Demo"})
    monkeypatch.setattr(service, "_load_recent_run", lambda local_id: {
        "local_id": local_id,
        "run_at": run_at,
        "detail": "Corrida reciente desde importacion automatica.",
    })
    monkeypatch.setattr(service, "_load_recent_alerts", lambda local_id: [{
        "id": "alert-1",
        "fecha_detectada": date.today().isoformat(),
        "tipo_alerta": "COMPORTAMIENTO_ATIPICO",
        "nivel_riesgo": "MEDIO",
        "mensaje": "[MONTO_REPETIDO_CONSECUTIVO] Se detectaron 5 facturas consecutivas por $10.00.",
    }])
    monkeypatch.setattr(
        service,
        "run_and_persist_local_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live refresh should not run")),
    )

    snapshot = service.get_alert_snapshot("local-1")

    assert snapshot["status"] == "ok"
    assert snapshot["source"] == "stored"
    assert snapshot["alerts"][0]["rule_code"] == "MONTO_REPETIDO_CONSECUTIVO"
