from datetime import datetime, timedelta
from types import SimpleNamespace

from services.load_log_service import build_load_log_payload


def test_load_log_timestamp_is_timezone_aware_utc():
    payload = build_load_log_payload(
        local_nombre="LC Waikiki",
        archivo="DailySales.csv",
        estado="exito",
        mensaje="ok",
    )

    timestamp = datetime.fromisoformat(payload["fecha_hora"])

    assert timestamp.utcoffset() == timedelta(0)


def test_remote_file_order_defaults_to_oldest(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    import worker_importacion as worker

    files = [
        SimpleNamespace(filename="new.csv", st_mtime=30),
        SimpleNamespace(filename="old.csv", st_mtime=10),
        SimpleNamespace(filename="middle.csv", st_mtime=20),
    ]

    worker._sort_sftp_pending_files(files, {"constants_config": {}})

    assert [item.filename for item in files] == ["old.csv", "middle.csv", "new.csv"]


def test_remote_file_order_can_prioritize_newest_snapshot(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    import worker_importacion as worker

    config = {"constants_config": {"_remote_file_order": "newest"}}
    sftp_files = [
        SimpleNamespace(filename="old.csv", st_mtime=10),
        SimpleNamespace(filename="new.csv", st_mtime=30),
        SimpleNamespace(filename="middle.csv", st_mtime=20),
    ]
    ftp_files = ["DailySales_2026-07-14.csv", "DailySales_2026-08-20.csv"]

    worker._sort_sftp_pending_files(sftp_files, config)
    worker._sort_ftp_pending_files(ftp_files, config)

    assert [item.filename for item in sftp_files] == ["new.csv", "middle.csv", "old.csv"]
    assert ftp_files == ["DailySales_2026-08-20.csv", "DailySales_2026-07-14.csv"]
