from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_one_uses_core_license_and_one_frontend_contract():
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    api = (ROOT / "api.ts").read_text(encoding="utf-8")
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    endpoint_start = router.index('@router.get("/intelligence/phase-one")')
    endpoint_end = router.index('@router.get("/stores/{local_id}/profile")')
    endpoint = router[endpoint_start:endpoint_end]

    assert "_context(mall_id, start_date, end_date, user)" in endpoint
    assert "_capability_context" not in endpoint
    assert "BigDataPhaseOneService(db).intelligence" in endpoint
    assert "getBigDataPhaseOne" in api
    assert "ApiService.getBigDataPhaseOne" in dashboard
    assert "getBigDataDashboard" not in dashboard
    assert "getBigDataExecutiveSummary" not in dashboard


def test_phase_one_is_intelligence_first_not_a_dashboard_clone():
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    assert "Calendario de comportamiento" in dashboard
    assert "Anomalías por investigar" in dashboard
    assert "Movimientos explicados" in dashboard
    assert "Calidad y trazabilidad" in dashboard
    assert "Patrón semanal" in dashboard
    assert 'label="Ventas netas"' not in dashboard
    assert 'label="Registros de venta"' not in dashboard
    assert "Ranking de locales" not in dashboard
    assert "Ventas por categoría" not in dashboard


def test_phase_one_uses_compact_progressive_disclosure_tabs():
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    assert "INTELLIGENCE_TABS" in dashboard
    assert 'role="tablist"' in dashboard
    assert "activeTab === 'summary'" in dashboard
    assert "activeTab === 'calendar'" in dashboard
    assert "activeTab === 'anomalies'" in dashboard
    assert "activeTab === 'quality'" in dashboard
    assert "anomalyView === 'pending'" in dashboard
    assert "anomalyView === 'explained'" in dashboard
    assert "min-h-[72px]" in dashboard


def test_anomalies_use_comparable_list_and_open_detail_sheet():
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    assert "<table" in dashboard
    assert "visibleAnomalyRows" in dashboard
    assert "Mayor impacto" in dashboard
    assert "Todas las direcciones" in dashboard
    assert "Ver ficha" in dashboard
    assert 'aria-label="Ficha de anomalía"' in dashboard
    assert "Locales contribuyentes" in dashboard
    assert "Por explicar" in dashboard
    assert "Venta real del mall" in dashboard
    assert "Referencia histórica" in dashboard
    assert "Diferencia vs. referencia" in dashboard
    assert "Principal local asociado" in dashboard
    assert "Explicar movimiento" in dashboard
    assert "expected_impact: anomaly.direction" in dashboard
    assert "contributor.impact_share_percent.toFixed(1)" in dashboard
    assert "Confianza analítica" in dashboard
    assert "closeOnEscape" in dashboard
    assert "anomalyCopy" not in dashboard


def test_partial_month_calendar_aligns_from_the_first_visible_date():
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )

    assert "visibleCalendar[0]?.weekday ?? 0" in dashboard
    assert 'safeDate(`${selectedMonth}-01`).getDay()' not in dashboard


def test_phase_one_queries_are_batched_and_bounded():
    service = (
        ROOT / "services" / "big_data_phase_one_service.py"
    ).read_text(encoding="utf-8")

    assert '.eq("grain", "mall")' in service
    assert '.eq("grain", "local")' in service
    assert ".limit(500)" in service
    assert ".limit(10000)" in service
    assert ".limit(2000)" in service
    assert "for local_id in" not in service.split("class BigDataPhaseOneService", 1)[1]


def test_calendar_event_table_is_private_multi_mall_and_indexed():
    migration = next(
        (ROOT / "supabase" / "migrations").glob("*_big_data_calendar_events.sql")
    ).read_text(encoding="utf-8")

    assert "mall_id uuid not null references public.malls(id)" in migration
    assert "enable row level security" in migration
    assert "revoke all on table public.big_data_calendar_events from anon, authenticated" in migration
    assert "grant select, insert, update, delete" in migration
    assert "big_data_calendar_events_active_range_idx" in migration
