from worker_importacion import _map_studio_g_sale, _studio_g_date_range
import pytest


def test_map_studio_g_sale_to_ventas_payload():
    config = {"id": "local-1", "mall_id": "mall-1"}
    row = {
        "IDTransaccion": 123,
        "NCF": "B0100000001",
        "Fecha": "2026-05-01T13:45:10",
        "Hora": "2026-05-01T13:45:10",
        "TotalBruto": 1000,
        "TotalImpuestos": "180.00",
        "TotalNeto": "1180.00",
    }

    mapped = _map_studio_g_sale(config, row, "AFB")

    assert mapped == {
        "local_id": "local-1",
        "mall_id": "mall-1",
        "fecha": "2026-05-01",
        "factura_no": "B0100000001",
        "comprobante": "B0100000001",
        "hora_transaccion": "13:45:10",
        "total_bruto": 1000.0,
        "total_impuestos": 180.0,
        "total_neto": 1180.0,
    }


def test_studio_g_date_range_uses_constants_for_history():
    config = {
        "constants_config": {
            "fecha_inicio": "2026-05-01",
            "fecha_fin": "2026-05-20",
        }
    }

    assert _studio_g_date_range(config) == ("2026-05-01", "2026-05-20")


def test_studio_g_date_range_uses_relative_modes(monkeypatch):
    import worker_importacion
    from datetime import datetime

    monkeypatch.setattr(worker_importacion, "_now_local", lambda: datetime(2026, 7, 8, 10, 0, 0))

    assert _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "yesterday"}}) == (
        "2026-07-07",
        "2026-07-07",
    )
    assert _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "current_month"}}) == (
        "2026-07-01",
        "2026-07-08",
    )
    assert _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "last_30_days"}}) == (
        "2026-06-09",
        "2026-07-08",
    )


def test_studio_g_custom_date_range_requires_dates():
    with pytest.raises(ValueError):
        _studio_g_date_range({"constants_config": {"_studio_g_date_mode": "custom"}})
