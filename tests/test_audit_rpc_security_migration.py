from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_audit_rpc_search_path_is_pinned():
    migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260925161500_harden_sales_audit_function_search_path.sql"
    ).read_text()
    assert "ALTER FUNCTION public.audit_sales_dates" in migration
    assert "ALTER FUNCTION public.audit_sales_summary" in migration
    assert "ALTER FUNCTION public.audit_annual_status" in migration
    assert migration.count("SET search_path = ''") == 3
