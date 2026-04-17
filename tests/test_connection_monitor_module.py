import asyncio
import importlib
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import paramiko
from fastapi import HTTPException

from services.connection_monitor_service import (
    ConnectionMonitorService,
    RetryPolicyBlocked,
    classify_connection_error,
)


class _FakeResponse:
    def __init__(self, data=None):
        self.data = data


class _TableQuery:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self._filters = []
        self._order = None
        self._limit = None
        self._mode = "select"
        self._payload = None
        self._single = False
        self._maybe_single = False

    def select(self, *_args, **_kwargs):
        if self._mode not in {"insert", "update", "upsert", "delete"}:
            self._mode = "select"
        return self

    def order(self, column, desc=False):
        self._order = (column, bool(desc))
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def eq(self, key, value):
        self._filters.append(("eq", key, value))
        return self

    def gte(self, key, value):
        self._filters.append(("gte", key, value))
        return self

    def lte(self, key, value):
        self._filters.append(("lte", key, value))
        return self

    def lt(self, key, value):
        self._filters.append(("lt", key, value))
        return self

    def in_(self, key, values):
        self._filters.append(("in", key, list(values)))
        return self

    def is_(self, key, value):
        self._filters.append(("is", key, value))
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def upsert(self, payload):
        self._mode = "upsert"
        self._payload = payload
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def _cmp(self, left, right, op):
        # Values in tests are ISO strings, plain strings, ints or None.
        if left is None:
            return False
        if op == "gte":
            return left >= right
        if op == "lte":
            return left <= right
        if op == "lt":
            return left < right
        return False

    def _apply_filters(self, rows):
        result = list(rows)
        for op, key, value in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(key) == value]
            elif op == "in":
                result = [r for r in result if r.get(key) in value]
            elif op == "is":
                if str(value).lower() == "null":
                    result = [r for r in result if r.get(key) is None]
                else:
                    result = [r for r in result if r.get(key) is value]
            elif op in {"gte", "lte", "lt"}:
                result = [r for r in result if self._cmp(r.get(key), value, op)]
        return result

    def _new_id(self, prefix):
        rows = self.supabase.tables.setdefault(self.table_name, [])
        return f"{prefix}{len(rows) + 1}"

    def execute(self):
        rows = self.supabase.tables.setdefault(self.table_name, [])
        filtered = self._apply_filters(rows)

        if self._mode == "select":
            data = [dict(r) for r in filtered]
            if self._order:
                col, desc = self._order
                data = sorted(data, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._limit is not None:
                data = data[: self._limit]
            if self._single:
                if not data:
                    raise RuntimeError("No rows")
                return _FakeResponse(dict(data[0]))
            if self._maybe_single:
                return _FakeResponse(dict(data[0]) if data else None)
            return _FakeResponse(data)

        if self._mode == "insert":
            payload = dict(self._payload or {})
            if self.table_name == "remote_connections" and not payload.get("id"):
                payload["id"] = self._new_id("rc")
            if self.table_name == "connection_runs" and not payload.get("id"):
                payload["id"] = self._new_id("run")
            if self.table_name == "retry_attempts" and not payload.get("id"):
                payload["id"] = self._new_id("ra")
            if self.table_name == "system_audit_logs" and not payload.get("id"):
                payload["id"] = self._new_id("audit")
            rows.append(payload)
            if self._single:
                return _FakeResponse(dict(payload))
            return _FakeResponse([dict(payload)])

        if self._mode == "update":
            updated = []
            for row in rows:
                if row in filtered:
                    row.update(dict(self._payload or {}))
                    updated.append(dict(row))
            if self._single:
                if not updated:
                    raise RuntimeError("No rows")
                return _FakeResponse(updated[0])
            return _FakeResponse(updated)

        if self._mode == "upsert":
            payload = dict(self._payload or {})
            key = payload.get("key")
            matched = None
            if key is not None:
                for row in rows:
                    if row.get("key") == key:
                        matched = row
                        break
            if matched is not None:
                matched.update(payload)
                return _FakeResponse([dict(matched)])
            rows.append(payload)
            return _FakeResponse([dict(payload)])

        if self._mode == "delete":
            deleted = [dict(r) for r in filtered]
            self.supabase.tables[self.table_name] = [r for r in rows if r not in filtered]
            return _FakeResponse(deleted)

        return _FakeResponse([])


class _FakeSupabase:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, table_name):
        return _TableQuery(self, table_name)


def _logger():
    return SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )


def _tenant_guard(operator_ctx, mall_id):
    if operator_ctx.get("role") == "admin":
        return
    allowed = set(operator_ctx.get("allowed_malls") or [])
    if mall_id not in allowed:
        raise HTTPException(status_code=403, detail="No tienes permisos para operar sobre este mall.")


def _request(app, method: str, url: str, **kwargs) -> httpx.Response:
    async def _run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(_run())


def _load_main(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  # type: ignore
    return importlib.reload(main)


def test_classify_connection_error_maps_expected_codes():
    assert classify_connection_error(ValueError("bad payload")) == "validation_error"
    assert classify_connection_error(TimeoutError("timed out")) == "timeout"
    assert classify_connection_error(paramiko.AuthenticationException("auth failed")) == "auth_error"
    assert classify_connection_error(OSError("connection refused")) == "endpoint_down"
    assert classify_connection_error(Exception("weird thing")) == "unknown_error"


def test_manual_retry_creates_run_and_retry_attempt_and_enforces_cooldown(monkeypatch):
    monkeypatch.setenv("RETRY_COOLDOWN_SECONDS", "300")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "3")
    fake_db = _FakeSupabase({
        "remote_connections": [{
            "id": "rc1",
            "mall_id": "mall-a",
            "nombre": "Conn",
            "protocolo": "SFTP",
            "host": "example.com",
            "puerto": 22,
            "usuario": "demo",
            "password": "supersecret",
        }],
        "connection_runs": [],
        "retry_attempts": [],
        "system_audit_logs": [],
    })
    svc = ConnectionMonitorService(fake_db, _logger())
    monkeypatch.setattr(svc, "_probe_connection", lambda conn: {
        "status": "fail",
        "error_code": "endpoint_down",
        "error_message": "connection refused",
        "started_at": "2026-02-24T02:00:00+00:00",
        "finished_at": "2026-02-24T02:00:01+00:00",
        "duration_ms": 1000,
    })

    out = svc.execute_manual_retry(
        connection_id="rc1",
        operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
        ensure_operator_can_access_mall=_tenant_guard,
    )
    assert out["run"]["status"] == "fail"
    assert out["retry_attempt"]["attempt_no"] == 1
    assert len(fake_db.tables["connection_runs"]) == 1
    assert len(fake_db.tables["retry_attempts"]) == 1

    try:
        svc.execute_manual_retry(
            connection_id="rc1",
            operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
            ensure_operator_can_access_mall=_tenant_guard,
        )
        assert False, "expected cooldown"
    except RetryPolicyBlocked as exc:
        assert exc.code == "cooldown_active"
        assert exc.retry_after_seconds > 0


def test_retry_max_attempts_limit(monkeypatch):
    monkeypatch.setenv("RETRY_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "2")
    fake_db = _FakeSupabase({
        "remote_connections": [{
            "id": "rc1", "mall_id": "mall-a", "nombre": "Conn", "protocolo": "SFTP",
            "host": "example.com", "puerto": 22, "usuario": "demo", "password": "pw",
        }],
        "connection_runs": [],
        "retry_attempts": [
            {"id": "ra1", "connection_id": "rc1", "attempt_no": 1, "status": "fail", "attempted_at": "2026-02-24T00:00:00+00:00"},
            {"id": "ra2", "connection_id": "rc1", "attempt_no": 2, "status": "fail", "attempted_at": "2026-02-24T01:00:00+00:00"},
        ],
        "system_audit_logs": [],
    })
    svc = ConnectionMonitorService(fake_db, _logger())
    monkeypatch.setattr(svc, "_probe_connection", lambda conn: (_ for _ in ()).throw(AssertionError("should not probe")))

    try:
        svc.execute_manual_retry(
            connection_id="rc1",
            operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
            ensure_operator_can_access_mall=_tenant_guard,
        )
        assert False, "expected max attempts"
    except RetryPolicyBlocked as exc:
        assert exc.code == "max_attempts_reached"


def test_scheduled_monitor_cycle_creates_connection_runs_and_retry_attempts(monkeypatch):
    monkeypatch.setenv("RETRY_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "3")
    fake_db = _FakeSupabase({
        "remote_connections": [
            {"id": "rc1", "mall_id": "mall-a", "nombre": "Conn1", "protocolo": "SFTP", "host": "h1", "puerto": 22, "usuario": "u", "password": "pw"},
            {"id": "rc2", "mall_id": "mall-a", "nombre": "Conn2", "protocolo": "SFTP", "host": "h2", "puerto": 22, "usuario": "u", "password": "pw"},
        ],
        "connection_runs": [],
        "retry_attempts": [],
        "system_audit_logs": [],
        "system_health": [],
    })
    svc = ConnectionMonitorService(fake_db, _logger())
    calls = {"rc1": 0, "rc2": 0}

    def _probe(conn):
        cid = conn["id"]
        calls[cid] += 1
        if cid == "rc1" and calls[cid] == 1:
            return {
                "status": "fail",
                "error_code": "endpoint_down",
                "error_message": "refused",
                "started_at": "2026-02-24T02:00:00+00:00",
                "finished_at": "2026-02-24T02:00:01+00:00",
                "duration_ms": 1000,
            }
        return {
            "status": "ok",
            "error_code": None,
            "error_message": None,
            "started_at": "2026-02-24T02:00:02+00:00",
            "finished_at": "2026-02-24T02:00:03+00:00",
            "duration_ms": 1000,
        }

    monkeypatch.setattr(svc, "_probe_connection", _probe)
    result = svc.run_scheduled_monitor_cycle()

    assert result["summary"]["total"] == 2
    assert result["summary"]["ok"] == 1
    assert result["summary"]["partial"] == 1
    assert len(fake_db.tables["connection_runs"]) == 2
    assert len(fake_db.tables["retry_attempts"]) == 1
    statuses = {r["id"]: r["status"] for r in fake_db.tables["connection_runs"]}
    assert "partial" in statuses.values()


def test_nightly_monitor_if_due_updates_system_health(monkeypatch):
    monkeypatch.setenv("NIGHTLY_RETRY_ENABLED", "true")
    monkeypatch.setenv("NIGHTLY_RETRY_CRON", "0 2 * * *")
    monkeypatch.setenv("RETRY_COOLDOWN_SECONDS", "0")
    fake_db = _FakeSupabase({
        "remote_connections": [
            {"id": "rc1", "mall_id": "mall-a", "nombre": "Conn1", "protocolo": "SFTP", "host": "h1", "puerto": 22, "usuario": "u", "password": "pw"},
        ],
        "connection_runs": [],
        "retry_attempts": [],
        "system_audit_logs": [],
        "system_health": [],
    })
    svc = ConnectionMonitorService(fake_db, _logger())
    monkeypatch.setattr(svc, "_probe_connection", lambda conn: {
        "status": "ok",
        "error_code": None,
        "error_message": None,
        "started_at": "2026-02-24T02:10:00+00:00",
        "finished_at": "2026-02-24T02:10:01+00:00",
        "duration_ms": 1000,
    })

    result = svc.run_nightly_monitor_if_due(now_utc=datetime(2026, 2, 24, 2, 10, tzinfo=timezone.utc))
    assert result["executed"] is True
    keys = {row["key"]: row["value"] for row in fake_db.tables["system_health"]}
    assert "CONNECTION_MONITOR_LAST_RUN" in keys
    assert "CONNECTION_MONITOR_LAST_SUCCESS" in keys
    assert "CONNECTION_MONITOR_LAST_ERROR" in keys


def test_tenant_isolation_denies_status_summary():
    fake_db = _FakeSupabase({"remote_connections": [], "connection_runs": []})
    svc = ConnectionMonitorService(fake_db, _logger())
    try:
        svc.get_status_summary(
            mall_id="mall-a",
            operator_ctx={"user_id": "u1", "role": "auditor", "allowed_malls": ["mall-b"]},
            ensure_operator_can_access_mall=_tenant_guard,
        )
        assert False, "expected tenant denial"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_connections_endpoints_status_failures_retry_and_rbac(monkeypatch):
    main = _load_main(monkeypatch)

    class _Svc:
        def get_status_summary(self, **_kwargs):
            return {
                "mall_id": "mall-a",
                "summary": {"total": 2, "ok": 1, "fail": 1, "partial": 0, "pending": 0},
                "recent_runs": [{"id": "run1", "mall_id": "mall-a", "run_type": "scheduled", "status": "fail", "started_at": "2026-02-24T00:00:00Z", "finished_at": "2026-02-24T00:00:01Z", "duration_ms": 1000, "created_at": "2026-02-24T00:00:01Z"}],
                "connections": [{"id": "rc1", "nombre": "Conn", "protocolo": "SFTP", "host": "ex***om", "last_run": None}],
            }

        def get_failures_by_date(self, **_kwargs):
            return {
                "mall_id": "mall-a",
                "date": "2026-02-24",
                "count": 1,
                "failures": [{"id": "run1", "mall_id": "mall-a", "run_type": "scheduled", "status": "fail", "error_code": "timeout", "error_message": "timeout", "started_at": "2026-02-24T00:00:00Z", "finished_at": "2026-02-24T00:00:01Z", "duration_ms": 1000, "created_at": "2026-02-24T00:00:01Z"}],
            }

        def execute_manual_retry(self, **_kwargs):
            return {
                "status": "success",
                "connection_id": "rc1",
                "mall_id": "mall-a",
                "run": {"id": "run2", "mall_id": "mall-a", "run_type": "manual", "status": "ok", "started_at": "2026-02-24T01:00:00Z", "finished_at": "2026-02-24T01:00:01Z", "duration_ms": 1000, "created_at": "2026-02-24T01:00:01Z"},
                "retry_attempt": {"id": "ra1", "attempt_no": 1, "status": "ok", "attempted_at": "2026-02-24T01:00:01Z", "duration_ms": 1000},
                "policy": {"max_attempts": 3, "cooldown_seconds": 300, "next_attempt_no": 1, "retry_after_seconds": 0},
            }

    main.app.dependency_overrides[main.require_audit_read_access] = lambda: {"user_id": "u1", "role": "auditor"}
    main.app.dependency_overrides[main.require_it_or_admin_access] = lambda: {"user_id": "u2", "role": "it"}
    monkeypatch.setattr(main, "_connection_monitor_service", lambda: _Svc())

    try:
        r_status = _request(main.app, "GET", "/api/v1/connections/status?mall_id=mall-a")
        r_fail = _request(main.app, "GET", "/api/v1/connections/failures?mall_id=mall-a&date=2026-02-24")
        r_retry = _request(main.app, "POST", "/api/v1/connections/rc1/retry")
    finally:
        main.app.dependency_overrides.clear()

    assert r_status.status_code == 200
    assert r_status.json()["summary"]["total"] == 2
    assert r_fail.status_code == 200
    assert r_fail.json()["failures"][0]["error_code"] == "timeout"
    assert r_retry.status_code == 200
    assert r_retry.json()["retry_attempt"]["attempt_no"] == 1

    # RBAC deny on write endpoint
    async def _deny_it():
        raise HTTPException(status_code=403, detail="forbidden")

    main.app.dependency_overrides[main.require_it_or_admin_access] = _deny_it
    try:
        r_denied = _request(main.app, "POST", "/api/v1/connections/rc1/retry")
    finally:
        main.app.dependency_overrides.clear()
    assert r_denied.status_code == 403


def test_retry_endpoint_returns_429_on_policy_block(monkeypatch):
    main = _load_main(monkeypatch)

    class _Svc:
        def execute_manual_retry(self, **_kwargs):
            raise RetryPolicyBlocked(code="cooldown_active", message="Cooldown activo", retry_after_seconds=123, attempt_no=2)

    main.app.dependency_overrides[main.require_it_or_admin_access] = lambda: {"user_id": "u1", "role": "it"}
    monkeypatch.setattr(main, "_connection_monitor_service", lambda: _Svc())

    try:
        res = _request(main.app, "POST", "/api/v1/connections/rc1/retry")
    finally:
        main.app.dependency_overrides.clear()

    assert res.status_code == 429
    detail = res.json()["detail"]
    assert detail["reason"] == "cooldown_active"
    assert detail["retry_after_seconds"] == 123
