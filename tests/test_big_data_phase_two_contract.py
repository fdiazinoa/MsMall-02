from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_two_exposes_one_authenticated_diagnostic_contract():
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    api = (ROOT / "api.ts").read_text(encoding="utf-8")
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    assert '@router.get("/intelligence/phase-two/stores/{local_id}")' in router
    assert "_context(mall_id, start_date, end_date, user)" in router
    assert "BigDataPhaseTwoService(db).diagnostic" in router
    assert "ApiService.getBigDataPhaseTwoDiagnostic" in dashboard
    assert "Abrir diagnóstico 360°" in dashboard
    assert 'aria-label="Diagnóstico 360 del local"' in dashboard
    assert "Evidencia de importación" in dashboard
    assert "Comparación de categoría" in dashboard


def test_phase_two_supabase_reads_are_mall_scoped_and_bounded():
    service = (ROOT / "services" / "big_data_phase_two_service.py").read_text(
        encoding="utf-8"
    )

    assert '.eq("mall_id", mall_id)' in service
    assert '.eq("local_id", local_id)' in service
    assert ".limit(MAX_MALL_LOCALS)" in service
    assert ".limit(DIAGNOSTIC_WINDOW_DAYS)" in service
    assert ".limit(MAX_PEER_ROWS)" in service
    assert ".limit(MAX_IMPORT_LOGS)" in service
    assert '.select("*")' not in service
    assert "ventas" not in service


def test_phase_two_reuses_existing_tables_without_a_schema_migration():
    service = (ROOT / "services" / "big_data_phase_two_service.py").read_text(
        encoding="utf-8"
    )

    for table in (
        "big_data_daily_aggregates",
        "local_commercial_classifications",
        "commercial_taxonomy",
        "logs_carga",
    ):
        assert f'table("{table}")' in service
