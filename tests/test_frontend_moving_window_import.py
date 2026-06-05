from pathlib import Path


def test_import_manager_exposes_moving_window_flag():
    repo = Path(__file__).resolve().parents[1]
    component = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    assert "movingWindowModeKey = '_moving_window_mode'" in component
    assert "Archivo de ventana móvil" in component
    assert "Los documentos ya cargados se omiten" in component
