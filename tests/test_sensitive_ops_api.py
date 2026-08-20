import asyncio
import importlib
import sys
from types import SimpleNamespace

import httpx
from fastapi import HTTPException

from services.sensitive_ops_service import SensitiveOpsService


def _load_main(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  # type: ignore
    return importlib.reload(main)


def _request(app, method: str, url: str, **kwargs) -> httpx.Response:
    async def _run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(_run())


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

    def delete(self):
        self._mode = "delete"
        return self

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
        return result

    def execute(self):
        rows = self.supabase.tables.setdefault(self.table_name, [])
        filtered = self._apply_filters(rows)

        if self._mode == "select":
            data = filtered
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
            return _FakeResponse([dict(r) for r in data])

        if self._mode == "insert":
            payload = dict(self._payload or {})
            if self.table_name == "remote_connections" and not payload.get("id"):
                payload["id"] = f"rc{len(rows) + 1}"
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

        if self._mode == "delete":
            deleted = [r for r in rows if r in filtered]
            self.supabase.tables[self.table_name] = [r for r in rows if r not in filtered]
            return _FakeResponse([dict(r) for r in deleted])

        return _FakeResponse([])


class _FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, table_name):
        return _TableQuery(self, table_name)


def _tenant_guard(operator_ctx, mall_id):
    if operator_ctx.get("role") == "admin":
        return
    allowed = set(operator_ctx.get("allowed_malls") or [])
    if mall_id not in allowed:
        raise HTTPException(status_code=403, detail="No tienes permisos para operar sobre este mall.")


def test_sensitive_service_masks_passwords_and_enforces_tenant():
    fake_db = _FakeSupabase({
        "remote_connections": [{
            "id": "rc1",
            "mall_id": "mall-a",
            "nombre": "Main SFTP",
            "protocolo": "SFTP",
            "host": "sftp.example.com",
            "puerto": 22,
            "usuario": "demo",
            "password": "supersecret123",
            "ruta_base": "/inbox",
            "created_at": "2026-01-01T00:00:00Z",
        }],
        "system_audit_logs": [],
    })
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    service = SensitiveOpsService(fake_db, logger)

    rows = service.list_remote_connections(
        mall_id="mall-a",
        operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
        ensure_operator_can_access_mall=_tenant_guard,
    )
    assert len(rows) == 1
    assert rows[0]["password"] == ""
    assert rows[0]["password_masked"] != ""
    assert "supersecret123" not in str(rows[0])

    try:
        service.list_remote_connections(
            mall_id="mall-a",
            operator_ctx={"user_id": "u2", "role": "auditor", "allowed_malls": ["mall-b"]},
            ensure_operator_can_access_mall=_tenant_guard,
        )
        assert False, "expected tenant denial"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_remote_connections_endpoint_redacts_password(monkeypatch):
    main = _load_main(monkeypatch)

    class _Svc:
        def create_remote_connection(self, **_kwargs):
            return {
                "id": "rc1",
                "mall_id": "mall-a",
                "nombre": "Conn",
                "protocolo": "SFTP",
                "host": "host",
                "puerto": 22,
                "usuario": "demo",
                "password": "",
                "password_masked": "su***23",
                "has_password": True,
                "ruta_base": ".",
                "created_at": "2026-01-01T00:00:00Z",
            }

    main.app.dependency_overrides[main.require_it_or_admin_access] = lambda: {"user_id": "u1", "role": "it"}
    monkeypatch.setattr(main, "_sensitive_ops_service", lambda: _Svc())

    try:
        res = _request(main.app, "POST", "/api/v1/remote-connections", json={
            "mall_id": "mall-a",
            "nombre": "Conn",
            "protocolo": "SFTP",
            "host": "host",
            "puerto": 22,
            "usuario": "demo",
            "password": "secret",
            "ruta_base": ".",
        })
    finally:
        main.app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["password"] == ""
    assert body["has_password"] is True
    assert body["password_masked"]
    assert "secret" not in res.text


def test_load_logs_cleanup_requires_it_or_admin(monkeypatch):
    main = _load_main(monkeypatch)

    async def _deny():
        raise HTTPException(status_code=403, detail="forbidden")

    main.app.dependency_overrides[main.require_it_or_admin_access] = _deny
    try:
        res = _request(main.app, "DELETE", "/api/v1/load-logs?mall_id=mall-a")
    finally:
        main.app.dependency_overrides.clear()

    assert res.status_code == 403


def test_list_load_logs_falls_back_to_legacy_rows_when_primary_empty():
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "loc-1", "mall_id": "mall-a", "nombre": "Subway"},
        ],
        "logs_carga": [
            {
                "id": "log-legacy-1",
                "mall_id": None,
                "local_id": None,
                "local_nombre": "Subway",
                "archivo": "ventas.csv",
                "estado": "exito",
                "mensaje": "Carga exitosa",
                "fecha_hora": "2026-02-24T10:00:00Z",
            }
        ],
    })
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    service = SensitiveOpsService(fake_db, logger)

    rows = service.list_load_logs(
        operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
        ensure_operator_can_access_mall=_tenant_guard,
        mall_id="mall-a",
        limit=50,
    )

    assert len(rows) == 1
    assert rows[0]["id"] == "log-legacy-1"


def test_reactivate_local_processing_resets_status_and_failures():
    fake_db = _FakeSupabase({
        "locales": [
            {
                "id": "loc-1",
                "mall_id": "mall-a",
                "nombre": "AGE",
                "processing_status": "SUSPENDED_AUTH_ERROR",
                "consecutive_failures": 5,
            }
        ],
        "system_audit_logs": [],
    })
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    service = SensitiveOpsService(fake_db, logger)

    result = service.reactivate_local_processing(
        local_id="loc-1",
        operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
        ensure_operator_can_access_mall=_tenant_guard,
    )

    assert result["status"] == "success"
    assert result["local"]["processing_status"] == "IDLE"
    assert result["local"]["consecutive_failures"] == 0
    assert fake_db.tables["locales"][0]["processing_status"] == "IDLE"
    assert fake_db.tables["locales"][0]["consecutive_failures"] == 0
    assert fake_db.tables["system_audit_logs"]
    assert fake_db.tables["system_audit_logs"][0]["accion"] == "LOCAL_REACTIVATE_PROCESSING"


def test_list_load_logs_merges_primary_and_legacy_rows():
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "loc-1", "mall_id": "mall-a", "nombre": "Subway"},
        ],
        "logs_carga": [
            {
                "id": "log-new-1",
                "mall_id": "mall-a",
                "local_id": "loc-1",
                "local_nombre": "Subway",
                "archivo": "nuevo.csv",
                "estado": "exito",
                "mensaje": "Carga estructurada",
                "fecha_hora": "2026-03-01T10:00:00Z",
            },
            {
                "id": "log-legacy-1",
                "mall_id": None,
                "local_id": None,
                "local_nombre": "Subway",
                "archivo": "legacy.csv",
                "estado": "error",
                "mensaje": "Carga legacy",
                "fecha_hora": "2026-02-27T10:00:00Z",
            },
        ],
    })
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    service = SensitiveOpsService(fake_db, logger)

    rows = service.list_load_logs(
        operator_ctx={"user_id": "u1", "role": "it", "allowed_malls": ["mall-a"]},
        ensure_operator_can_access_mall=_tenant_guard,
        mall_id="mall-a",
        limit=50,
    )

    assert [row["id"] for row in rows] == ["log-new-1", "log-legacy-1"]


def test_load_logs_endpoint_accepts_mall_query_without_current_mall_dependency(monkeypatch):
    main = _load_main(monkeypatch)

    class _Svc:
        def list_load_logs(self, **kwargs):
            assert kwargs["mall_id"] == "mall-a"
            assert kwargs["start_date"] is None
            assert kwargs["end_date"] is None
            assert kwargs["limit"] == 200
            return [{
                "id": "log1",
                "fecha_hora": "2026-02-24T10:00:00Z",
                "local_nombre": "Subway",
                "archivo": "ventas.csv",
                "estado": "exito",
                "mensaje": "ok",
                "detalles": [],
            }]

    main.app.dependency_overrides[main.require_audit_read_access] = lambda: {"user_id": "u1", "role": "auditor"}
    monkeypatch.setattr(main, "_sensitive_ops_service", lambda: _Svc())

    try:
        res = _request(
            main.app,
            "GET",
            "/api/v1/load-logs?mall_id=mall-a&limit=200",
        )
    finally:
        main.app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "log1"
