import importlib
import io
import stat as stat_module
import sys
from types import SimpleNamespace


def _load_worker(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if "worker_importacion" in sys.modules:
        del sys.modules["worker_importacion"]
    import worker_importacion  # type: ignore
    return importlib.reload(worker_importacion)


class _FakeFile:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class _FakeSFTP:
    def __init__(self, files):
        self.files = dict(files)
        self.renames = []

    def stat(self, path):
        return SimpleNamespace(st_mode=stat_module.S_IFDIR)

    def listdir_attr(self, path):
        return [
            SimpleNamespace(
                filename=name,
                st_mode=stat_module.S_IFREG,
                st_mtime=1,
                st_size=len(content),
            )
            for name, content in self.files.items()
        ]

    def open(self, path, _mode):
        filename = path.split("/")[-1]
        return _FakeFile(self.files[filename])

    def rename(self, old_path, new_path):
        old_name = old_path.split("/")[-1]
        new_name = new_path.split("/")[-1]
        self.renames.append((old_name, new_name))
        self.files[new_name] = self.files.pop(old_name)

    def close(self):
        return None


class _FakeSSH:
    def close(self):
        return None


def test_worker_marks_error_when_no_insert_is_confirmed(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_sftp = _FakeSFTP({"ventas_20260301.json": b'{"rows":[]}'})

    monkeypatch.setattr(worker, "connect_with_retries", lambda connector, attempts=3, base_delay=2: connector())
    monkeypatch.setattr(worker, "get_sftp_client", lambda *args, **kwargs: (_FakeSSH(), fake_sftp))
    monkeypatch.setattr(worker, "process_file_logic", lambda config, filename, content: (0, []))
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: None)

    worker.process_local_files({
        "nombre": "Cafe Santo Domingo",
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "SFTP",
        "sftp_host": "example.com",
        "sftp_port": 22,
        "sftp_user": "demo",
        "sftp_pass": "secret",
        "sftp_path": ".",
        "file_type": "JSON",
        "accion_post_procesado": "RENOMBRAR_BACKUP",
        "prefijo_backup": "MS02_",
    })

    assert fake_sftp.renames == [("ventas_20260301.json", "ERR_ventas_20260301.json")]


def test_worker_marks_success_with_pr_prefix_after_confirmed_insert(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_sftp = _FakeSFTP({"ventas_20260301.json": b'{"rows":[{"ok":true}]}'})

    monkeypatch.setattr(worker, "connect_with_retries", lambda connector, attempts=3, base_delay=2: connector())
    monkeypatch.setattr(worker, "get_sftp_client", lambda *args, **kwargs: (_FakeSSH(), fake_sftp))
    monkeypatch.setattr(worker, "process_file_logic", lambda config, filename, content: (12, []))
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: None)

    worker.process_local_files({
        "nombre": "Cafe Santo Domingo",
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "SFTP",
        "sftp_host": "example.com",
        "sftp_port": 22,
        "sftp_user": "demo",
        "sftp_pass": "secret",
        "sftp_path": ".",
        "file_type": "JSON",
        "accion_post_procesado": "RENOMBRAR_BACKUP",
        "prefijo_backup": "MS02_",
    })

    assert fake_sftp.renames == [("ventas_20260301.json", "PR_ventas_20260301.json")]


def test_worker_strips_legacy_custom_prefix_when_building_standard_marker(monkeypatch):
    worker = _load_worker(monkeypatch)

    assert worker._build_marked_filename(
        "MS02_ventas_20260301.json",
        worker.AUTO_SUCCESS_PREFIX,
        ("MS02_",),
    ) == "PR_ventas_20260301.json"
