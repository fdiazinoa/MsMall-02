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
