"""Real PostgreSQL race/accounting tests, restricted to a disposable local DB.

BACKUP_QUOTA_TEST_DSN=postgresql://postgres@127.0.0.1:55437/msmall_backup_quota_test
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from services.import_backup_quota_service import ImportBackupQuotaService, BackupQuotaError


MALL = "10000000-0000-0000-0000-000000000001"
OTHER_MALL = "10000000-0000-0000-0000-000000000002"
USERS = [f"40000000-0000-0000-0000-{index:012d}" for index in range(1, 21)]
DSN = os.environ.get("BACKUP_QUOTA_TEST_DSN", "")


def sql(query):
    result = subprocess.run(["psql", DSN, "-qAt", "-v", "ON_ERROR_STOP=1"], input=query,
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def literal(value):
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + (json.dumps(value) if isinstance(value, dict) else str(value)).replace("'", "''") + "'"


def rpc(action="status", user=USERS[0], mall=MALL, **params):
    args = {"p_action": action, "p_user_id": user, "p_mall_id": mall, **params}
    return json.loads(sql("set role service_role; select public.import_backup_quota_control(" +
                          ",".join(f"{key} => {literal(value)}" for key, value in args.items()) + ");"))


def reserve(user=USERS[0], mall=MALL, **params):
    return rpc("reserve", user, mall, p_request_id=str(uuid4()), **params)


def clear_cooldown():
    sql("update public.import_backup_jobs set created_at = now() - interval '2 days';")


@pytest.fixture(scope="module", autouse=True)
def database_schema():
    if not DSN or not shutil.which("psql"):
        pytest.skip("Set BACKUP_QUOTA_TEST_DSN to a disposable local PostgreSQL database")
    parsed = urlparse(DSN)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/msmall_backup_quota_test", "Refusing to reset a non-test database"
    sql("""
        drop schema if exists public cascade; create schema public;
        drop schema if exists auth cascade; create schema auth;
        create table auth.users(id uuid primary key);
        create table public.malls(id uuid primary key);
        grant usage on schema public to service_role, anon, authenticated;
    """)
    migration = next((Path(__file__).parents[1] / "supabase/migrations").glob("*_import_backup_quotas.sql"))
    sql(migration.read_text())
    sql("insert into auth.users values " + ",".join(f"('{user}')" for user in USERS) + ";" +
        f"insert into public.malls values ('{MALL}'),('{OTHER_MALL}');")


@pytest.fixture(autouse=True)
def reset_accounting(database_schema):
    sql("truncate public.import_backup_jobs, public.import_backup_usage, public.import_backup_policy; insert into public.import_backup_policy(id) values (true);")


def test_defaults_and_available_quota():
    quota = rpc()["quota"]
    assert quota["user"]["downloads_remaining"] == 10
    assert quota["user"]["remaining_bytes"] == 200_000_000
    assert quota["mall"]["remaining_bytes"] == 1_000_000_000
    assert quota["limits"]["user_concurrency"] == 1
    assert quota["limits"]["mall_concurrency"] == 2
    assert quota["timezone"] == "America/Santo_Domingo"


def test_frequency_and_failed_attempts_are_counted():
    first = reserve()
    rpc("fail", p_request_id=first["request_id"], p_bytes=1234)
    blocked = reserve()
    assert not blocked["allowed"] and blocked["reason"] == "frequency"
    assert 0 < blocked["retry_after"] <= 60
    assert blocked["quota"]["user"]["downloads_used"] == 1
    assert blocked["quota"]["user"]["used_bytes"] == 1234


def test_concurrency_is_enforced_across_processes():
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(reserve, USERS[:12]))
    assert sum(item["allowed"] for item in results) == 2
    assert all(item["reason"] == "mall_concurrency" for item in results if not item["allowed"])
    quota = rpc()["quota"]
    assert quota["mall"]["active"] == 2
    assert quota["mall"]["reserved_bytes"] == 100_000_000


def test_same_user_cannot_evade_concurrency_by_changing_malls():
    assert reserve()["allowed"]
    clear_cooldown()
    result = reserve(mall=OTHER_MALL)
    assert not result["allowed"] and result["reason"] == "user_concurrency"


def test_simultaneous_requests_from_one_user_consume_one_slot_and_one_attempt():
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(item["allowed"] for item in results) == 1
    assert rpc()["quota"]["user"]["downloads_used"] == 1


def test_daily_attempts_remain_consumed_after_failure_and_across_malls():
    rpc("configure", p_policy={"user_daily_downloads": 2})
    first = reserve()
    rpc("fail", p_request_id=first["request_id"])
    clear_cooldown()
    second = reserve(mall=OTHER_MALL)
    rpc("fail", mall=OTHER_MALL, p_request_id=second["request_id"])
    clear_cooldown()
    result = reserve()
    assert not result["allowed"] and result["reason"] == "daily_downloads"
    assert result["quota"]["user"]["downloads_remaining"] == 0


def test_volume_reservation_prevents_other_users_from_overspending_mall_quota():
    rpc("configure", p_policy={"user_daily_mb": 1, "mall_daily_mb": 1})
    first = reserve()
    assert first["max_bytes"] == 1_000_000
    rpc("prepare", p_request_id=first["request_id"], p_bytes=900_000)
    second = reserve(USERS[1])
    assert second["max_bytes"] == 100_000
    rpc("prepare", USERS[1], p_request_id=second["request_id"], p_bytes=100_000)
    rpc("finish", p_request_id=first["request_id"])
    rpc("finish", USERS[1], p_request_id=second["request_id"])
    result = reserve(USERS[2])
    assert not result["allowed"] and result["reason"] == "mall_daily_bytes"
    assert result["quota"]["mall"]["used_bytes"] == 1_000_000


def test_prepare_charges_actual_bytes_but_holds_concurrency_until_stream_finishes():
    first = reserve()
    prepared = rpc("prepare", p_request_id=first["request_id"], p_bytes=100)
    assert prepared["quota"]["user"]["remaining_bytes"] == 199_999_900
    assert prepared["quota"]["user"]["reserved_bytes"] == 0
    assert prepared["quota"]["user"]["active"] == 1
    finished = rpc("finish", p_request_id=first["request_id"], p_bytes=100)
    assert finished["quota"]["user"]["active"] == 0
    rpc("finish", p_request_id=first["request_id"], p_bytes=100)
    assert rpc()["quota"]["user"]["used_bytes"] == 100


def test_crashed_generation_expires_and_charges_reserved_budget():
    first = reserve()
    sql("update public.import_backup_jobs set expires_at = now() - interval '1 second';")
    quota = rpc()["quota"]
    assert quota["user"]["active"] == 0
    assert quota["user"]["reserved_bytes"] == 0
    assert quota["user"]["used_bytes"] == first["max_bytes"]
    assert not rpc("renew", p_request_id=first["request_id"])["allowed"]


def test_expired_stream_is_not_charged_twice():
    first = reserve()
    rpc("prepare", p_request_id=first["request_id"], p_bytes=100)
    sql("update public.import_backup_jobs set expires_at = now() - interval '1 second';")
    assert rpc()["quota"]["user"]["used_bytes"] == 100


def test_lease_can_renew_but_cannot_prepare_more_than_reserved():
    first = reserve()
    assert rpc("renew", p_request_id=first["request_id"])["allowed"]
    with pytest.raises(subprocess.CalledProcessError):
        rpc("prepare", p_request_id=first["request_id"], p_bytes=first["max_bytes"] + 1)
    assert rpc()["quota"]["user"]["reserved_bytes"] == first["max_bytes"]


def test_day_rollover_does_not_refund_an_in_flight_job_into_the_new_day():
    first = reserve()
    sql("update public.import_backup_usage set quota_day = quota_day - 1; update public.import_backup_jobs set quota_day = quota_day - 1;")
    quota = rpc()["quota"]
    assert quota["user"]["downloads_used"] == 0
    assert quota["user"]["active"] == 1
    rpc("fail", p_request_id=first["request_id"], p_bytes=100)
    assert rpc()["quota"]["user"]["used_bytes"] == 0
    assert sql("select used_bytes from public.import_backup_usage where scope='user' and quota_day < (now() at time zone 'America/Santo_Domingo')::date;") == "100"


def test_policy_changes_preserve_consumption_and_range_is_enforced():
    first = reserve()
    rpc("fail", p_request_id=first["request_id"], p_bytes=100)
    result = rpc("configure", p_policy={"user_daily_mb": 300, "max_range_days": 30})
    assert result["quota"]["user"]["remaining_bytes"] == 299_999_900
    clear_cooldown()
    assert reserve(p_days=31)["reason"] == "date_range"
    with pytest.raises(subprocess.CalledProcessError):
        rpc("configure", p_policy={"user_concurrency": 0})


def test_anon_and_authenticated_cannot_read_or_mutate_quota_accounting():
    for role in ("anon", "authenticated"):
        for table in ("import_backup_policy", "import_backup_usage", "import_backup_jobs"):
            assert sql(f"select has_table_privilege('{role}','public.{table}','select,insert,update,delete');") == "f"
        assert sql(f"select has_function_privilege('{role}','public.import_backup_quota_control(text,uuid,uuid,uuid,bigint,integer,jsonb)','execute');") == "f"
    assert sql("select bool_and(relrowsecurity) from pg_class where relname in ('import_backup_policy','import_backup_usage','import_backup_jobs');") == "t"


class PostgresQuotaDB:
    def rpc(self, _name, params):
        def execute():
            args = params.copy()
            action = args.pop("p_action")
            user = args.pop("p_user_id")
            mall = args.pop("p_mall_id")
            return SimpleNamespace(data=rpc(action, user, mall, **args))
        return SimpleNamespace(execute=execute)


def test_python_service_observes_shared_state_after_recreation():
    first = ImportBackupQuotaService(PostgresQuotaDB(), USERS[0], MALL).reserve(1)
    try:
        recreated = ImportBackupQuotaService(PostgresQuotaDB(), USERS[0], OTHER_MALL)
        assert recreated.status()["user"]["downloads_used"] == 1
        with pytest.raises(BackupQuotaError) as error:
            recreated.reserve(1)
        assert error.value.status_code == 429 and error.value.retry_after > 0
    finally:
        first.close(failed=True)


def test_http_download_enforces_real_quota_and_releases_reservation_on_size_error(monkeypatch):
    import main
    from test_import_backup import Database, ASGIClient, sale

    class DB(Database, PostgresQuotaDB):
        pass

    db = DB([sale()])
    access = {"user_id": USERS[0], "role": "auditor", "permissions": {"sales_reports": {"view": True}}}

    async def context(_):
        return access

    monkeypatch.setattr(main, "supabase", db)
    monkeypatch.setattr(main, "_get_access_context", context)
    monkeypatch.setattr(main, "_get_user_mall_ids", lambda _: [MALL])
    monkeypatch.setitem(main.app.dependency_overrides, main.get_current_user_id, lambda: USERS[0])
    client = ASGIClient(main.app)
    headers = {"X-Mall-Id": MALL}
    body = {"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31"}
    quota = client.get("/api/v1/export/import-backup/quota", headers=headers)
    assert quota.status_code == 200 and not quota.json()["can_configure"]
    first = client.post("/api/v1/export/import-backup/csv", json=body, headers=headers)
    assert first.status_code == 200
    denied = client.post("/api/v1/export/import-backup/csv", json=body, headers=headers)
    assert denied.status_code == 429 and int(denied.headers["retry-after"]) > 0
    quota = client.get("/api/v1/export/import-backup/quota", headers=headers).json()["quota"]
    assert quota["user"]["downloads_remaining"] == 9
    assert quota["user"]["used_bytes"] == len(first.content)
    assert quota["user"]["active"] == quota["user"]["reserved_bytes"] == 0
    assert client.request("PUT", "/api/v1/export/import-backup/settings", headers=headers, json={}).status_code == 403
    access["role"] = "admin"
    access["has_role_assignment"] = True
    updated = client.request("PUT", "/api/v1/export/import-backup/settings", headers=headers, json={"max_file_mb": 1})
    assert updated.status_code == 200 and updated.json()["quota"]["limits"]["max_file_mb"] == 1
    assert updated.json()["quota"]["user"]["used_bytes"] == len(first.content)
    clear_cooldown()
    db.rows["ventas"][0]["factura_no"] = "X" * 1_000_000
    oversized = client.post("/api/v1/export/import-backup/csv", json=body, headers=headers)
    assert oversized.status_code == 413
    quota = client.get("/api/v1/export/import-backup/quota", headers=headers).json()["quota"]
    assert quota["user"]["downloads_remaining"] == 8
    assert quota["user"]["active"] == quota["user"]["reserved_bytes"] == 0
    assert quota["user"]["used_bytes"] >= len(first.content)


def test_mid_stream_disconnect_closes_file_and_releases_slot(monkeypatch):
    import asyncio
    import io
    import main
    from services.import_backup_service import GeneratedBackup

    lease = ImportBackupQuotaService(PostgresQuotaDB(), USERS[0], MALL).reserve(1)
    lease.prepare(100)
    lease.produced_bytes = 100
    file = io.BytesIO(b"x" * 100)
    response = main.BackupQuotaResponse(GeneratedBackup(file, 1, []), lease)

    async def send(_message):
        raise OSError("Client disconnected")

    async def receive():
        return {"type": "http.disconnect"}

    async def run():
        try:
            await response({"type": "http", "method": "GET", "asgi": {"spec_version": "2.4"}}, receive, send)
        except BaseException:
            pass

    asyncio.run(run())
    assert file.closed
    quota = rpc()["quota"]
    assert quota["user"]["active"] == quota["user"]["reserved_bytes"] == 0
    assert quota["user"]["used_bytes"] == 100
