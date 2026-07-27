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


def test_dashboard_frontend_keeps_compact_cards_and_total_below_donut():
    dashboard_source = (ROOT / "components" / "DashboardKPIs.tsx").read_text(encoding="utf-8")

    assert "h-[150px] xl:h-[165px]" in dashboard_source
    assert "min-w-0 space-y-3" in dashboard_source
    assert "border-t border-slate-100 pt-2" in dashboard_source
    assert "mode={businessTypeChartMode}" in dashboard_source
    assert "mode={rubroChartMode}" in dashboard_source

    chart_end = dashboard_source.index("</ResponsiveContainer>")
    total_footer = dashboard_source.index("border-t border-slate-100 pt-2")
    assert total_footer > chart_end
