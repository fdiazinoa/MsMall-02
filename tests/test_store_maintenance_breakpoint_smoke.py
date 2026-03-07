from pathlib import Path


def test_store_maintenance_exposes_breakpoint_field_with_hint():
    repo = Path(__file__).resolve().parents[1]
    store_maintenance = (repo / "components" / "StoreMaintenance.tsx").read_text(encoding="utf-8")

    assert "breakpoint_venta: ''" in store_maintenance
    assert "Breakpoint de Venta" in store_maintenance
    assert "Umbral contractual" in store_maintenance
    assert "Si el contrato no usa breakpoint, dejelo vacio." in store_maintenance
    assert "breakpoint_venta: parseOptionalNumber(newStore.breakpoint_venta)" in store_maintenance
