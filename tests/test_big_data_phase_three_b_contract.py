from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260729190139_big_data_phase_3b_scenarios.sql"
)


def test_phase_three_b_has_authenticated_simulation_and_workflow_contracts():
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    api = (ROOT / "api.ts").read_text(encoding="utf-8")
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(
        encoding="utf-8"
    )
    service = (
        ROOT / "services" / "big_data_phase_three_b_service.py"
    ).read_text(encoding="utf-8")

    assert '@router.post("/intelligence/phase-three-b/simulate")' in router
    assert '@router.get("/intelligence/phase-three-b/scenarios")' in router
    assert '@router.post("/intelligence/phase-three-b/scenarios")' in router
    assert (
        '@router.patch("/intelligence/phase-three-b/scenarios/{scenario_id}/status")'
        in router
    )
    assert (
        '@router.patch("/intelligence/phase-three-b/actions/{action_id}/status")'
        in router
    )
    assert "BigDataPhaseThreeService(self.supabase).prediction" in service
    assert '"BIG_DATA_FORECAST"' in router
    assert "_require_big_data_manager(mall_id, user)" in router
    assert "simulateBigDataScenario" in api
    assert "createBigDataScenario" in api
    assert "updateBigDataScenarioActionStatus" in api
    assert "Simular una decisión comercial" in dashboard
    assert "Plan de acción" in dashboard
    assert "no es venta comprometida" in dashboard


def test_phase_three_b_storage_is_private_mall_scoped_and_indexed():
    migration = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.big_data_scenarios" in migration
    assert "create table public.big_data_scenario_actions" in migration
    assert "mall_id uuid not null references public.malls" in migration
    assert "enable row level security" in migration
    assert "force row level security" in migration
    assert "from public, anon, authenticated" in migration
    assert "to service_role" in migration
    assert "big_data_scenarios_mall_created_idx" in migration
    assert "big_data_scenario_actions_scenario_status_idx" in migration


def test_phase_three_b_does_not_claim_causality_or_query_raw_sales():
    service = (
        ROOT / "services" / "big_data_phase_three_b_service.py"
    ).read_text(encoding="utf-8")

    assert "no demuestra causalidad" in service
    assert 'table("ventas")' not in service
    assert ".limit(MAX_SCENARIOS)" in service
    assert ".limit(MAX_ACTIONS)" in service
