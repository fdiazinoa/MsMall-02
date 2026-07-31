from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_three_a_exposes_one_authenticated_forecast_contract():
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    api = (ROOT / "api.ts").read_text(encoding="utf-8")
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    assert '@router.get("/intelligence/phase-three-a/prediction")' in router
    assert '_capability_context(mall_id, user, "BIG_DATA_FORECAST")' in router
    assert "BigDataPhaseThreeService(db).prediction" in router
    assert "getBigDataPhaseThreePrediction" in api
    assert "Próximos 7, 30 y 90 días" in dashboard
    assert "Venta diaria con límites de incertidumbre" in dashboard
    assert "BIG_DATA_FORECAST" in dashboard


def test_phase_three_a_reads_only_bounded_mall_aggregates_and_calendar_context():
    service = (ROOT / "services" / "big_data_phase_three_service.py").read_text(
        encoding="utf-8"
    )

    assert 'table("big_data_daily_aggregates")' in service
    assert 'table("big_data_calendar_events")' in service
    assert '.eq("mall_id", mall_id)' in service
    assert '.eq("grain", "mall")' in service
    assert ".limit(MAX_HISTORY_ROWS)" in service
    assert ".limit(MAX_CALENDAR_EVENTS)" in service
    assert '.select("*")' not in service
    assert 'table("ventas")' not in service
    assert "row_date <= as_of" in service


def test_phase_three_a_is_explainable_and_does_not_invent_event_lift():
    service = (ROOT / "services" / "big_data_phase_three_service.py").read_text(
        encoding="utf-8"
    )

    assert "MIN_CONTEXT_OBSERVATIONS = 2" in service
    assert "Mediana robusta por día de semana" in service
    assert '"applied": applied' in service
    assert "INTERVAL_Z_SCORE" in service
    assert "INSUFFICIENT_DATA" in service


def test_phase_three_a_reuses_existing_feature_flag_without_schema_migration():
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    manager = (ROOT / "components" / "MallManager.tsx").read_text(encoding="utf-8")
    migrations = list(ROOT.glob("**/*phase_three*.sql"))

    assert "BIG_DATA_FORECAST" in router
    assert "BIG_DATA_FORECAST" in manager
    assert migrations == []
