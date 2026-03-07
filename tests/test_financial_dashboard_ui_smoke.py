from pathlib import Path


def test_financial_dashboard_uses_ranked_ocr_and_projection_gap_views():
    repo = Path(__file__).resolve().parents[1]
    dashboard = (repo / "components" / "FinancialDashboard.tsx").read_text(encoding="utf-8")

    assert "Salud de Cartera por OCR" in dashboard
    assert "Watchlist de cartera" in dashboard
    assert "Potencial de Recaudación Variable" in dashboard
    assert "Gap vs Breakpoint" in dashboard
    assert "const proyeccion = ventaActual;" not in dashboard
    assert "projectionDelta" in dashboard
    assert "storesAboveBreakpoint" in dashboard
