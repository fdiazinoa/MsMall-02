from pathlib import Path


def test_sales_import_does_not_run_exact_count_as_connection_warmup():
    main_py = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert 'table("ventas").select("count", count="exact")' not in main_py
    assert "Pre-warm Supabase connection / cache" not in main_py


def test_global_audit_uses_one_batched_sales_date_loader():
    main_py = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "dates_by_local = load_actual_sales_dates_by_local(" in main_py
    assert "s_actual = dates_by_local.get(sid, set())" in main_py


def test_hot_sales_read_paths_use_keyset_pagination():
    repo = Path(__file__).resolve().parents[1]
    dashboard_service = (repo / "services" / "dashboard_analytics_service.py").read_text(encoding="utf-8")
    export_service = (repo / "services" / "export_service.py").read_text(encoding="utf-8")
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")

    assert "sales = fetch_sales_rows_keyset(" in dashboard_service
    assert "return fetch_sales_rows_keyset(" in export_service
    assert "query = query.gt('id', lastId);" in api_ts
    assert "query.range(page * pageSize" not in api_ts
