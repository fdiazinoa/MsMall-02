from pathlib import Path


def test_learned_adjustments_include_country_holidays():
    repo = Path(__file__).resolve().parents[1]
    dashboard = (repo / "components" / "BigDataDashboard.tsx").read_text(encoding="utf-8")

    assert "prediction.drivers.holiday_adjustment.observations > 0" in dashboard
    assert "event_type: 'COUNTRY_HOLIDAY'" in dashboard
    assert "event_type_label: 'Feriados nacionales'" in dashboard
    assert "...prediction.drivers.holiday_adjustment" in dashboard


def test_learned_adjustments_empty_state_requires_no_holidays_or_events():
    repo = Path(__file__).resolve().parents[1]
    dashboard = (repo / "components" / "BigDataDashboard.tsx").read_text(encoding="utf-8")

    assert "prediction.drivers.holiday_adjustment.observations === 0" in dashboard
    assert "&& !prediction.drivers.event_adjustments.length" in dashboard
    assert "Todavía no hay feriados o eventos históricos coincidentes con ventas" in dashboard
