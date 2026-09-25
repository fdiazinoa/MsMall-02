from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_latest_import_rpc_is_lightweight_and_private():
    migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260925162500_add_audit_latest_imports_rpc.sql"
    ).read_text()
    assert "CREATE OR REPLACE FUNCTION public.audit_latest_imports" in migration
    assert "public.logs_carga" in migration
    assert "public.ventas" not in migration
    assert "SECURITY INVOKER" in migration
    assert "SET search_path = ''" in migration
    assert "FROM PUBLIC, anon, authenticated" in migration
    assert "TO service_role" in migration
