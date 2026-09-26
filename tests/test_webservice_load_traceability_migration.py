from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260926132912_backfill_webservice_load_traceability.sql"
)


def test_historical_webservice_backfill_is_scoped_and_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "trim(m.nombre) = 'Santiago Center'" in sql
    assert "l.codigo_interno IN ('7', '13', '60', '106', '137', '139')" in sql
    assert "NOT EXISTS" in sql
    assert "existing.records_processed" in sql


def test_historical_webservice_backfill_is_explicitly_identified():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "historical_sales_backfill" in sql
    assert "'backfill', true" in sql
    assert "no representa una nueva transmisión WebService" in sql
    assert "max(v.created_at) AS latest_inserted_at" in sql
