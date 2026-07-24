from pathlib import Path


def test_frontend_ai_risk_uses_snapshot_contract():
    repo = Path(__file__).resolve().parents[1]
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")
    smart_insights = (repo / "components" / "SmartInsights.tsx").read_text(encoding="utf-8")

    assert "data?.alerts" in api_ts
    assert "data?.summary" in api_ts
    assert "status: data?.status || 'error'" in api_ts

    assert "setAlertsSummary(alertsData.summary || null);" in smart_insights
    assert "alertsStatus === 'error' || alertsStatus === 'no_data'" in smart_insights
    assert "alert.display_type || String(alert.rule_code || alert.tipo_alerta || '').replace(/_/g, ' ')" in smart_insights
    assert "No hay una evaluación reciente del semáforo para este local." in smart_insights
