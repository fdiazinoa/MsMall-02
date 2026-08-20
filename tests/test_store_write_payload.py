import pytest
from fastapi import HTTPException

import main


def test_blank_store_numeric_fields_are_normalized_to_null():
    payload = {
        "mts": "",
        "porciento_renta": "  ",
        "renta_fija": None,
        "breakpoint_venta": "",
        "porcentaje_variable": "",
        "piso": "P2-L01",
    }

    sanitized = main._sanitize_store_write_payload(payload)

    assert sanitized["piso"] == "P2-L01"
    for field in main.STORE_NUMERIC_FIELDS:
        assert sanitized[field] is None


def test_valid_store_numeric_fields_are_normalized_to_numbers():
    sanitized = main._sanitize_store_write_payload({
        "mts": "125.50",
        "porciento_renta": 5,
        "renta_fija": "1000",
        "breakpoint_venta": "25000.25",
        "porcentaje_variable": "7.5",
    })

    assert sanitized == {
        "mts": 125.5,
        "porciento_renta": 5.0,
        "renta_fija": 1000.0,
        "breakpoint_venta": 25000.25,
        "porcentaje_variable": 7.5,
    }


def test_invalid_store_numeric_field_returns_clear_validation_error():
    with pytest.raises(HTTPException) as exc_info:
        main._sanitize_store_write_payload({"mts": "cien"})

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "mts debe contener un número válido"


def test_inactivating_store_disables_automatic_processing():
    sanitized = main._sanitize_store_write_payload({
        "activo": False,
        "motivo_inactivacion": "  Fin de contrato  ",
        "upsert_activo": True,
    })

    assert sanitized["activo"] is False
    assert sanitized["upsert_activo"] is False
    assert sanitized["tipo_ejecucion"] == "MANUAL"
    assert sanitized["processing_status"] == "IDLE"
    assert sanitized["motivo_inactivacion"] == "Fin de contrato"
    assert sanitized["fecha_inactivacion"]


def test_reactivating_store_clears_inactivation_metadata():
    sanitized = main._sanitize_store_write_payload({
        "activo": True,
        "fecha_inactivacion": "2026-08-03",
        "motivo_inactivacion": "Fin de contrato",
    })

    assert sanitized["activo"] is True
    assert sanitized["fecha_inactivacion"] is None
    assert sanitized["motivo_inactivacion"] is None
