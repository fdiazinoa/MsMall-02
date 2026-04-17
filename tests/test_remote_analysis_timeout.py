import importlib
import sys


def _load_main(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  # type: ignore
    return importlib.reload(main)


def test_remote_analysis_timeout_extends_for_json(monkeypatch):
    main = _load_main(monkeypatch)

    assert main._remote_analysis_timeout_seconds("ventas.json", "JSON") == 420.0
    assert main._remote_analysis_timeout_seconds("/remote/path/ventas.json", None) == 420.0


def test_remote_analysis_timeout_keeps_shorter_window_for_csv(monkeypatch):
    main = _load_main(monkeypatch)

    assert main._remote_analysis_timeout_seconds("ventas.csv", "CSV") == 180.0
