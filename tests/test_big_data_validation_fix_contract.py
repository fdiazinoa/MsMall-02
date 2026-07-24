from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_validation_fix_requeues_both_sides_and_keeps_full_month_totals():
    sql = (ROOT / "20260724_big_data_sprint_1_validation_fix.sql").read_text(encoding="utf-8")

    assert "OLD.mall_id IS DISTINCT FROM NEW.mall_id" in sql
    assert "OLD.fecha IS DISTINCT FROM NEW.fecha" in sql
    assert "period_date >= affected_month_start" in sql
    assert "period_date < (affected_month_end + interval '1 month')::date" in sql


def test_validation_fix_claims_queue_rows_atomically_and_recovers_stalled_work():
    sql = (ROOT / "20260724_big_data_sprint_1_validation_fix.sql").read_text(encoding="utf-8")

    assert "claim_big_data_refresh_queue" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "interval '15 minutes'" in sql
    assert "claim_token = NULL" in sql


def test_worker_uses_atomic_claim_and_conditional_completion():
    source = (ROOT / "services" / "big_data_analytics_service.py").read_text(encoding="utf-8")

    assert 'rpc("claim_big_data_refresh_queue", {"p_limit": limit})' in source
    assert '.eq("claim_token", item["claim_token"])' in source
