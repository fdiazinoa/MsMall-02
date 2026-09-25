from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gap_endpoint_uses_tenant_aggregate_and_worker_pool():
    source = (ROOT / "main.py").read_text()
    endpoint = source[source.index('@app.get("/api/v1/auditoria/brechas-ventas")'):]
    assert "def get_sales_gaps(" in endpoint[:300]
    assert "async def get_sales_gaps(" not in endpoint[:300]
    assert "mall_id=current_mall" in endpoint


def test_frontend_does_not_couple_summary_to_annual_status():
    api = (ROOT / "api.ts").read_text()
    component = (ROOT / "components" / "SalesReport.tsx").read_text()
    get_report = api[api.index("async getSalesReport("):api.index("async getSaleDetails(")]
    assert "Promise.all" not in get_report
    assert "getAnnualAuditStatus" in get_report
    assert "retryOnTimeout: false" in get_report
    assert "auditStatus={annualAuditStatus}" in component


def test_frontend_loads_audit_details_only_after_user_action():
    component = (ROOT / "components" / "SalesReport.tsx").read_text()
    automatic_effects = component[component.index("useEffect(() => {"):]
    assert "onAuditLocal={auditLocal}" in component
    assert "Auditar local" in component
    assert "ApiService.getAnnualAuditStatus(currentMall.id, localId" in component
    assert "fetchData(controller.signal)" not in automatic_effects


def test_migration_aggregates_sales_dates_and_keeps_rpc_private():
    migration = (ROOT / "supabase" / "migrations" / "20260925123000_optimize_sales_audit_queries.sql").read_text()
    assert "CREATE OR REPLACE FUNCTION public.audit_sales_dates" in migration
    assert "GROUP BY v.local_id, v.fecha" in migration
    assert "REVOKE ALL ON FUNCTION public.audit_sales_dates" in migration
    assert "GRANT EXECUTE ON FUNCTION public.audit_sales_dates" in migration
    assert "TO service_role" in migration
