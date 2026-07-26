from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_frontend_uses_small_store_projection_and_preserves_data_while_refreshing():
    api_source = (ROOT / "api.ts").read_text(encoding="utf-8")
    dashboard_source = (ROOT / "components" / "DashboardKPIs.tsx").read_text(encoding="utf-8")

    assert ".select('id,mall_id,nombre,rubro,tipo_negocio')" in api_source
    assert "ApiService.getDashboardStores(currentMall.id)" in dashboard_source
    assert "setRefreshing(true)" in dashboard_source
    assert "Actualizando…" in dashboard_source
    assert "setDates(draftDates)" in dashboard_source
