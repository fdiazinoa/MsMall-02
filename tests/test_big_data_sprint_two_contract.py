from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sprint_two_is_separate_from_legacy_projection():
    service = read("services/big_data_sprint2_service.py")
    legacy = read("analytics.py")
    assert "big-data-forecast-v1" in service
    assert "from analytics" not in service
    assert "proyeccion_cierre_mes" in legacy


def test_all_new_flags_are_disabled_by_absence_and_mall_scoped():
    migration = read("20260724_big_data_sprint_2.sql")
    backend = read("main.py")
    assert "'BIG_DATA_OPERATIONS'" in migration
    assert '"BIG_DATA_OPERATIONS"' in backend
    assert "INSERT INTO public.mall_feature_flags" not in migration
    assert "requested_mall_id" in backend


def test_claim_rpc_uses_skip_locked_timeout_and_service_role_only():
    migration = read("20260724_big_data_sprint_2.sql")
    assert "FOR UPDATE OF event SKIP LOCKED" in migration
    assert "event.claimed_at < now()" in migration
    assert "claim_token = gen_random_uuid()" in migration
    assert "REVOKE ALL ON FUNCTION public.claim_operations_events" in migration
    assert "GRANT EXECUTE ON FUNCTION public.claim_operations_events" in migration
    assert "TO service_role" in migration


def test_worker_preserves_import_priority_and_safe_old_owner_completion():
    worker = read("worker_importacion.py")
    importer_position = worker.index("await asyncio.gather(*tasks)")
    deferred_position = worker.index("run_deferred_big_data_jobs()", importer_position)
    assert importer_position < deferred_position
    consumer = read("services/operations_agent_service.py")
    assert '.eq("claim_token", event.get("claim_token"))' in consumer
    assert "claim_operations_events" in consumer


def test_operations_contracts_are_real_and_paginated():
    router = read("routers/big_data.py")
    frontend = read("components/OperationsCenter.tsx")
    assert "/operations/items/{collection}" in router
    assert "limit: int = Query(25, ge=1, le=100)" in router
    assert "review_finding" in router
    assert "resolve_finding" in router
    assert "reopen_finding" in router
    assert "ApiService.getOperationsItems" in frontend
    assert "Observaciones" in frontend
    assert "Patrones" in frontend
    assert "addOperationsFindingComment" in frontend
    assert "mock" not in frontend.lower()


def test_multi_mall_components_clear_and_ignore_stale_responses():
    dashboard = read("components/BigDataDashboard.tsx")
    operations = read("components/OperationsCenter.tsx")
    for source in (dashboard, operations):
        assert "requestVersion" in source
        assert "currentMall?.id !== mallId" in source
    assert "setData(null)" in dashboard
    assert "ApiService.getBigDataPhaseOne" in dashboard
    assert "getBigDataExecutiveSummary" not in dashboard
    assert "setFindings([])" in operations


def test_big_data_copilot_uses_aggregates_and_has_deterministic_fallback():
    main = read("main.py")
    assert "_build_big_data_copilot_context" in main
    assert "BigDataSprint2Service(supabase).executive_summary" in main
    assert "_deterministic_big_data_answer" in main
    assert '"como van las ventas"' in main
    assert '"ventas este mes"' in main
    assert '"provider": provider' in main
    assert "big_data_aggregates" in main


def test_no_iot_scope_was_added():
    changed_sources = "\n".join(
        read(path)
        for path in (
            "services/big_data_sprint2_service.py",
            "services/operations_agent_service.py",
            "routers/big_data.py",
            "components/OperationsCenter.tsx",
        )
    ).lower()
    for forbidden in ("camera", "sensor", "occupancy", "heatmap"):
        assert forbidden not in changed_sources
