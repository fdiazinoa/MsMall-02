from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reclassification_uses_history_and_queues_only_affected_sale_days():
    migration = (ROOT / "20260725_big_data_reclassification_history.sql").read_text(
        encoding="utf-8"
    )
    assert "effective_from date" in migration
    assert "enqueue_big_data_reclassification" in migration
    assert "SELECT DISTINCT v.fecha::date AS sale_day" in migration
    assert "classification_baseline" in migration
    assert "idx_ventas_local_fecha" in (ROOT / "add_performance_indexes.sql").read_text(
        encoding="utf-8"
    )
    assert "ON public.local_commercial_classifications" in migration
    assert "ON public.ventas" not in migration


def test_refresh_uses_one_historical_category_per_sale_day():
    migration = (ROOT / "20260725_big_data_reclassification_history.sql").read_text(
        encoding="utf-8"
    )
    assert "LEFT JOIN LATERAL" in migration
    assert "history.category_id" in migration
    assert "effective_from, h.changed_at" in migration
    assert "LIMIT 1" in migration
    assert "DELETE FROM public.big_data_daily_aggregates" in migration
