from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_period_metrics_rpc_uses_sales_fecha_and_invoker_security():
    sql = (_repo_root() / "get_metricas_periodo.sql").read_text(encoding="utf-8")

    assert "v.fecha_venta" not in sql
    assert "v.fecha >= fecha_inicio_param" in sql
    assert "v.fecha <= fecha_fin_param" in sql
    assert "SECURITY DEFINER" not in sql
    assert "SECURITY INVOKER" in sql


def test_insights_do_not_use_placeholder_occupancy_costs():
    repo = _repo_root()
    main_py = (repo / "main.py").read_text(encoding="utf-8")
    rpc_sql = (repo / "create_insights_rpcs.sql").read_text(encoding="utf-8")
    combined = f"{main_py}\n{rpc_sql}"

    assert "renta_fija = 2500" not in combined
    assert "gastos_comunes = 600" not in combined
    assert "costos = 3000" not in combined
    assert "3000::numeric" not in combined
    assert "renta_fija, porcentaje_variable, porciento_renta" in main_py
    assert "cost_source = 'sin_configuracion'" in rpc_sql


def test_smart_insights_passes_mall_and_period_context():
    repo = _repo_root()
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")
    smart_insights = (repo / "components" / "SmartInsights.tsx").read_text(encoding="utf-8")

    assert "type InsightsContext" in api_ts
    assert "if (context.mallId) searchParams.set('mall_id', context.mallId);" in api_ts
    assert "if (context.startDate) searchParams.set('start_date', context.startDate);" in api_ts
    assert "if (context.endDate) searchParams.set('end_date', context.endDate);" in api_ts
    assert "ApiService.getBenchmarking(selectedLocalId, insightsContext)" in smart_insights
    assert "ApiService.getHeatmap(selectedLocalId, insightsContext)" in smart_insights
    assert "ApiService.getEfficiency(selectedLocalId, insightsContext)" in smart_insights
    assert "ApiService.getRanking(metric, currentMall?.id, insightsContext)" in smart_insights
