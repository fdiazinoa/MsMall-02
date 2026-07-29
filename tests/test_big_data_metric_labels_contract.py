from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_one_does_not_repeat_unvalidated_transaction_kpis():
    source = (ROOT / "components" / "BigDataDashboard.tsx").read_text(encoding="utf-8")

    assert 'label="Registros de venta"' not in source
    assert 'label="Transacciones"' not in source
    assert "Promedio por registro" not in source
    assert "Confiabilidad" in source
