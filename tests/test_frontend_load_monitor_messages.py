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

    assert "Causa probable" in monitor
    assert "Accion recomendada" in monitor
    assert "describeLoadLog" in monitor
    assert "describeLoadLog" in import_manager


def test_load_monitor_requests_latest_200_without_date_filter():
    repo = Path(__file__).resolve().parents[1]
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")

    assert "const LOAD_MONITOR_MAX_LOGS = 200" in monitor
    assert "limit: LOAD_MONITOR_MAX_LOGS" in monitor
    assert "dateRange" not in monitor
    assert 'type="date"' not in monitor
    assert "query.set('limit', String(options.limit))" in api_ts
