import stat
from pathlib import Path
from types import SimpleNamespace

import main


class _FakeSFTP:
    def __init__(self):
        self.closed = False

    def stat(self, path):
        if path == ".":
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_size=0)
        return SimpleNamespace(st_mode=stat.S_IFREG, st_size=4096)

    def lstat(self, path):
        return self.stat(path)

    def listdir(self, _path):
        return ["ERR_Ventas kryolan2026-06-25.txt"]

    def listdir_attr(self, _path):
        return [SimpleNamespace(
            filename="ERR_Ventas kryolan2026-06-25.txt",
            st_mode=stat.S_IFREG,
            st_size=0,
            st_mtime=1_752_000_000,
        )]

    def close(self):
        self.closed = True


class _FakeSSH:
    def close(self):
        pass


class _ReadableSFTP:
    def stat(self, _path):
        return SimpleNamespace(st_mode=stat.S_IFDIR)

    def listdir(self, _path):
        return ["Ventas 2026.CSV"]

    def open(self, path, _mode):
        assert path == "./Ventas 2026.CSV"
        from io import BytesIO
        return BytesIO(b"Fecha,Venta\n2026-08-04,100")


def test_sftp_listing_recovers_size_when_directory_metadata_reports_zero(monkeypatch):
    fake_sftp = _FakeSFTP()
    monkeypatch.setattr(main, "get_sftp_client", lambda *_args: (_FakeSSH(), fake_sftp))

    files = main._list_remote_files({
        "protocolo": "SFTP",
        "host": "example.test",
        "puerto": 22,
        "usuario": "user",
        "password": "secret",
        "ruta_remota": ".",
        "tipo_archivo": "TXT",
    })

    assert files[0]["nombre"] == "ERR_Ventas kryolan2026-06-25.txt"
    assert files[0]["tamano"] == 4096
    assert fake_sftp.closed is True


def test_saved_remote_listing_uses_database_secret_and_path():
    merged = main._build_remote_listing_config(
        {
            "id": "local-1",
            "host": "sftp.example.test",
            "password": "",
            "ruta_remota": ".",
        },
        {
            "id": "local-1",
            "sftp_protocol": "SFTP",
            "sftp_host": "sftp.example.test",
            "sftp_user": "saved-user",
            "sftp_pass": "saved-secret",
            "sftp_path": "/ventas/exportadas",
            "file_type": "TXT",
        },
    )

    assert merged["sftp_pass"] == "saved-secret"
    assert merged["sftp_path"] == "/ventas/exportadas"
    assert "password" not in merged
    assert "ruta_remota" not in merged


def test_sftp_download_resolves_current_server_filename_before_opening():
    payload, filename = main._download_sftp_file_bytes(
        _ReadableSFTP(),
        "ventas 2026.csv",
        "./",
    )

    assert filename == "Ventas 2026.CSV"
    assert payload.startswith(b"Fecha,Venta")


def test_frontend_remote_reads_send_local_id_and_do_not_retry_regular_500():
    source = (Path(__file__).resolve().parents[1] / "api.ts").read_text(encoding="utf-8")

    assert source.count("local_id: config.id || null") >= 3
    assert "local_id: localId || null" in source
    assert "[502, 503, 504].includes(response.status)" in source


def test_frontend_remote_listing_retries_network_failures_with_timeout():
    source = (Path(__file__).resolve().parents[1] / "api.ts").read_text(encoding="utf-8")
    start = source.index("async listRemoteFiles")
    end = source.index("async analyzeSingleFile", start)
    segment = source[start:end]

    assert "fetchJsonWithBaseFallback" in segment
    assert "'/remote/list-files'" in segment
    assert "{ timeoutMs: 40000 }" in segment
    assert "No se pudo consultar la ruta remota guardada." in segment


def test_manual_modal_shows_saved_route_and_listing_errors():
    source = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "ImportManager.tsx"
    ).read_text(encoding="utf-8")

    assert "Importación" in source
    assert "activeManualConfig?.nombre" in source
    assert "Ruta:" in source
    assert "manualLoadError" in source
    assert "No se pudo consultar la ruta remota" in source


def test_manual_batch_accepts_error_files_and_quoted_wildcard_masks():
    source = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "ImportManager.tsx"
    ).read_text(encoding="utf-8")

    assert "trimmed.startsWith('\"') && trimmed.endsWith('\"')" in source
    assert "filter((f) => !/^PR_/i.test(f.nombre))" in source
    assert "! /^(PR_|ERR_)" not in source
    assert "No reportado" in source


def test_manual_rename_uses_unique_target_when_backup_exists():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "existing_names = [item.filename for item in sftp.listdir_attr(target_dir)]" in source
    assert "build_unique_marked_filename(filename, prefix, existing_names)" in source

    renamed = main.build_unique_marked_filename(
        "ERR_Ventas kryolan2026-06-25.txt",
        "PR_",
        ["ERR_Ventas kryolan2026-06-25.txt", "PR_Ventas kryolan2026-06-25.txt"],
    )
    assert renamed.startswith("PR_Ventas kryolan2026-06-25_")
    assert renamed.endswith(".txt")
