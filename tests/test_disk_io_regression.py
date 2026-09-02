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
    assert "query = query.or(`fecha.gt.${lastDate},and(fecha.eq.${lastDate},id.gt.${lastId})`);" in api_ts
    assert "query.range(page * pageSize" not in api_ts


def test_sales_cube_uses_daily_aggregates_for_large_ranges_and_surfaces_errors():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")
    sales_cube = (repo / "components" / "SalesCube.tsx").read_text(encoding="utf-8")

    assert "sales_rows = fetch_sales_cube_daily_aggregates(" in main_py
    assert 'select_fields=(\n                    "id,local_id,fecha,total_bruto,total_neto,total_impuestos"' in main_py
    assert "parseErrorDetail(response" in api_ts
    assert 'setError(err?.message || "No se pudo generar el cubo de ventas.")' in sales_cube
