from pathlib import Path


def test_sales_gap_backend_uses_shared_date_loader_for_global_and_individual_modes():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    assert "def _load_actual_dates_for_local(target_local_id: str) -> Set[str]:" in main_py
    assert "s_actual = _load_actual_dates_for_local(sid)" in main_py
    assert "actual_dates = _load_actual_dates_for_local(local_id)" in main_py


def test_sales_gap_global_mode_ignores_inactive_stores():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")
    export_service = (repo / "services" / "export_service.py").read_text(encoding="utf-8")

    assert "select('id, nombre, rubro, activo').eq('mall_id', current_mall)" in main_py
    assert "stores = [row for row in (stores_resp.data or []) if _is_store_active(row)]" in main_py
    assert "select('id, nombre, rubro, activo').eq('mall_id', mall_id)" in export_service
    assert "stores = [row for row in (stores_query.execute().data or []) if row.get('activo') is not False]" in export_service
