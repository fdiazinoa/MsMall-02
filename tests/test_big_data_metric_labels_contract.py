from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unvalidated_row_count_is_not_presented_as_transactions():
    source = (ROOT / "components" / "BigDataDashboard.tsx").read_text(encoding="utf-8")

    assert 'label="Registros de venta"' in source
    assert 'label="Transacciones"' not in source
    assert "Promedio por registro" in source
