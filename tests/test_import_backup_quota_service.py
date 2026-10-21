from types import SimpleNamespace

import pytest

from services.import_backup_quota_service import BackupQuotaError, BackupLease, ImportBackupQuotaService, BackupPolicy
from services.import_backup_service import BackupSizeExceeded, ImportBackupService
from test_import_backup import Database, MALL, sale


def test_unavailable_quota_storage_is_fail_closed():
    with pytest.raises(BackupQuotaError) as error:
        ImportBackupQuotaService(object(), "user", "mall").reserve(1)
    assert error.value.status_code == 503


def test_malformed_quota_response_is_not_an_unlimited_fallback():
    db = SimpleNamespace(rpc=lambda *_: SimpleNamespace(execute=lambda: SimpleNamespace(data=[])))
    with pytest.raises(BackupQuotaError):
        ImportBackupQuotaService(db, "user", "mall").status()


def test_lease_close_is_idempotent_even_if_two_cleanup_paths_run():
    calls = []
    lease = BackupLease(SimpleNamespace(call=lambda action, **args: calls.append((action, args))), "request", 1000)
    lease.progress(123)
    lease.close(failed=True)
    lease.close()
    assert calls == [("fail", {"p_request_id": "request", "p_bytes": 123})]


def test_lost_lease_blocks_generation_and_streaming():
    lease = BackupLease(None, "request", 1000)
    lease._lost.set()
    with pytest.raises(BackupQuotaError):
        lease.check()


def test_csv_maximum_is_enforced_on_encoded_bytes_before_delivery():
    db = Database([sale()])
    original = ImportBackupService(db).generate(MALL, "2026-01-01", "2026-01-31", None)
    with original.file:
        size = len(original.file.read())
    exact = ImportBackupService(db).generate(MALL, "2026-01-01", "2026-01-31", None, max_bytes=size)
    exact.file.close()
    progress = []
    with pytest.raises(BackupSizeExceeded):
        ImportBackupService(db).generate(MALL, "2026-01-01", "2026-01-31", None, max_bytes=size - 1, on_progress=progress.append)
    assert sum(progress) < size


def test_tiny_remaining_quota_cannot_even_write_a_bom():
    with pytest.raises(BackupSizeExceeded):
        ImportBackupService(Database()).generate(MALL, "2026-01-01", "2026-01-31", None, max_bytes=1)


def test_missing_migration_returns_503_from_api_without_querying_sales(monkeypatch):
    import main
    from test_import_backup import ASGIClient

    db = Database([sale()])

    async def context(_):
        return {"user_id": "user", "role": "admin", "permissions": {"import_backup": {"view": True}}}

    monkeypatch.setattr(main, "supabase", db)
    monkeypatch.setattr(main, "_get_access_context", context)
    monkeypatch.setattr(main, "_get_user_mall_ids", lambda _: [MALL])
    monkeypatch.setitem(main.app.dependency_overrides, main.get_current_user_id, lambda: "user")
    client = ASGIClient(main.app)
    response = client.post("/api/v1/export/import-backup/csv", headers={"X-Mall-Id": MALL},
                           json={"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31"})
    assert response.status_code == 503 and response.headers["retry-after"] == "20"
    assert not any(query.table == "ventas" for query in db.queries)


def test_editable_admin_hint_cannot_change_global_policy_or_bypass_mall_membership(monkeypatch):
    import main
    monkeypatch.setattr(main, "supabase", Database())
    monkeypatch.setattr(main, "_get_user_mall_ids", lambda _: [MALL])
    context = {"user_id": "user", "role": "admin", "has_role_assignment": False}
    assert not main._backup_can_configure(context)
    assert not main._ensure_backup_mall_access(context, MALL)
    with pytest.raises(main.HTTPException) as error:
        main._ensure_backup_mall_access(context, "other-mall")
    assert error.value.status_code == 403


def test_server_assigned_admin_can_configure_global_policy(monkeypatch):
    import main
    assert main._backup_can_configure({"role": "admin", "has_role_assignment": True})
    db = Database()
    db.rows["profiles"] = [{"id": "admin-user", "role": "admin"}]
    monkeypatch.setattr(main, "supabase", db)
    assert main._backup_can_configure({"user_id": "admin-user", "role": "admin", "has_role_assignment": False})


@pytest.mark.parametrize("field,value", [("max_file_mb", 0), ("user_concurrency", -1), ("mall_daily_mb", None), ("user_daily_downloads", 1.5)])
def test_invalid_policy_is_rejected(field, value):
    with pytest.raises(ValueError):
        BackupPolicy(**{field: value})
