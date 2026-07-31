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


def test_dashboard_frontend_uses_compact_modern_charts_and_readable_currency():
    dashboard_source = (ROOT / "components" / "DashboardKPIs.tsx").read_text(encoding="utf-8")

    assert "min-w-0 space-y-3" in dashboard_source
    assert "mode={businessTypeChartMode}" in dashboard_source
    assert "mode={rubroChartMode}" in dashboard_source
    assert "formatCompactCurrency" in dashboard_source
    assert "tickFormatter={(value) => compactFormat(Number(value))}" in dashboard_source
    assert "currencyDisplay: 'symbol'" in dashboard_source
    assert "DailySalesTooltip" in dashboard_source
    assert "moving_average_7" in dashboard_source
    assert "Composición del total por segmento" in dashboard_source
    assert "Participación y concentración acumulada" in dashboard_source
    assert "Acum. {cumulative.toFixed(1)}%" in dashboard_source
    assert "Ranking por venta neta" in dashboard_source
    assert "PieChart" not in dashboard_source
    assert "Últimos 7 días" not in dashboard_source
