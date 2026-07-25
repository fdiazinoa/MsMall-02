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
