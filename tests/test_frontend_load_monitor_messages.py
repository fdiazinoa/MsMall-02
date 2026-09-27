from pathlib import Path


def test_load_monitor_uses_operational_messages():
    repo = Path(__file__).resolve().parents[1]
    helper = (repo / "utils" / "loadLogMessages.ts").read_text(encoding="utf-8")
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")
    import_manager = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    expected_messages = [
        "Archivo nuevo no encontrado.",
        "Archivo leido con 0 datos.",
        "El archivo no cumple con la estructura requerida.",
        "Error al insertar informacion.",
        "Campo invalido.",
        "Datos incompletos en el registro.",
        "Periodo cerrado para importacion.",
    ]
    for message in expected_messages:
        assert message in helper

    assert "Diagnostico" in monitor
    assert "Accion recomendada" in monitor
    assert "describeLoadLog" in monitor
    assert "describeLoadLog" in import_manager


def test_successful_insertion_message_is_not_classified_as_database_error():
    repo = Path(__file__).resolve().parents[1]
    helper = (repo / "utils" / "loadLogMessages.ts").read_text(encoding="utf-8")

    assert "if (status === 'error' && (" in helper
    assert "if (status === 'exito')" in helper
    assert "Este registro historico no conserva las estadisticas" in helper
    assert "zeroDataReason === 'headers_only'" in helper
    assert "zeroDataReason === 'all_rows_rejected'" in helper


def test_load_monitor_requests_latest_1000_without_date_filter():
    repo = Path(__file__).resolve().parents[1]
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")

    assert "const LOAD_MONITOR_MAX_LOGS = 1000" in monitor
    assert "limit: LOAD_MONITOR_MAX_LOGS" in monitor
    assert "dateRange" not in monitor
    assert 'type="date"' not in monitor
    assert "Math.min(Math.trunc(options.limit), 1000)" in api_ts
