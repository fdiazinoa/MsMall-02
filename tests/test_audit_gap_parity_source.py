from pathlib import Path


def test_sales_gap_backend_uses_shared_date_loader_for_global_and_individual_modes():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    assert "from services.sales_gap_service import (" in main_py
    assert "dates_by_local = load_actual_sales_dates_by_local(" in main_py
    assert "s_actual = dates_by_local.get(sid, set())" in main_py
    assert "actual_dates = load_actual_sales_dates_for_local(" in main_py

    email_service = (repo / "services" / "missing_days_email_service.py").read_text(encoding="utf-8")
    export_service = (repo / "services" / "export_service.py").read_text(encoding="utf-8")
    assert "missing_dates = load_missing_sales_dates_for_local(" in email_service
    assert "expected_dates = expected_sales_dates(fecha_inicio, fecha_fin)" in export_service
    assert "sales_df['fecha_norm'] = sales_df['fecha'].apply(normalize_sales_date)" in export_service


def test_sales_gap_global_mode_ignores_inactive_stores():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")
    export_service = (repo / "services" / "export_service.py").read_text(encoding="utf-8")

    assert "select('id, nombre, rubro, activo').eq('mall_id', current_mall)" in main_py
    assert "stores = [row for row in (stores_resp.data or []) if _is_store_active(row)]" in main_py
    assert "select('id, nombre, rubro, activo').eq('mall_id', mall_id)" in export_service
    assert "stores = [row for row in (stores_query.execute().data or []) if row.get('activo') is not False]" in export_service
