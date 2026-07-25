from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_big_data_migration_is_additive_and_has_required_contracts():
    sql = (ROOT / "20260724_big_data_sprint_1.sql").read_text(encoding="utf-8").lower()
    for required in (
        "mall_feature_flags", "big_data_daily_aggregates", "big_data_monthly_aggregates",
        "big_data_refresh_queue", "big_data_watermarks", "validate_mall_access",
        "big_data_mall_summary", "big_data_category_distribution", "enqueue_big_data_refresh",
    ):
        assert required in sql
    assert "drop table" not in sql
    assert "alter table public.ventas" not in sql
    assert "big_data_core" in sql


def test_big_data_is_worker_driven_and_visible_only_through_feature_flag():
    worker = (ROOT / "worker_importacion.py").read_text(encoding="utf-8")
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "components" / "BigDataDashboard.tsx").read_text(encoding="utf-8")
    assert "process_pending_refreshes" in worker
    assert "_require_core" in router
    assert "BIG_DATA_CORE" in router
    assert "Big Data" in dashboard


def test_big_data_does_not_query_legacy_sales_from_http_router():
    router = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")
    assert 'table("ventas")' not in router
    assert "big_data_daily_aggregates" in router
