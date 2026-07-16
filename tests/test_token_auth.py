import asyncio
import os
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import jwt

from routers.token_auth import (
    InMemoryTokenStore,
    TokenService,
    _hash_token as token_auth_hash_token,
    create_router,
    get_token_service,
)
from services.exporter_sales_promotion_service import build_sales_dedup_key


class ASGITestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def _request(self, method, path, **kwargs):
        async def _run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(_run())

    def post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

    def get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def put(self, path, **kwargs):
        return self._request("PUT", path, **kwargs)


class _FakeSupabaseTable:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self._payload = None

    def insert(self, payload):
        self._payload = payload
        return self

    def execute(self):
        rows = self.supabase.tables.setdefault(self.table_name, [])
        payload = dict(self._payload or {})
        rows.append(payload)
        return SimpleNamespace(data=[payload])


class _FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, table_name):
        return _FakeSupabaseTable(self, table_name)


def build_test_client(supabase_client=None):
    os.environ.setdefault("MSMALL_TOKEN_JWT_SECRET", "test-secret-123")
    app = FastAPI()
    store = InMemoryTokenStore()
    svc = TokenService(store=store, supabase_client=supabase_client)
    app.include_router(create_router())
    app.dependency_overrides[get_token_service] = lambda: svc
    return ASGITestClient(app), svc, store


def bootstrap_manage_token(client, svc, store):
    pair = svc._issue_pair(
        mall_id="mall-1",
        local_id=None,
        token_type="app",
        scopes=["tokens:manage", "app:read", "app:write"],
        created_by="tester",
        service_account_id=None,
        request=None,
    )
    return pair["access_token"]


def test_exporter_issue_use_refresh_revoke_flow():
    client, svc, store = build_test_client()
    admin_access = bootstrap_manage_token(client, svc, store)

    sa = client.post(
        "/service-accounts",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"mall_id": "mall-1", "local_id": "local-1", "token_type": "exporter", "scopes": ["export:write", "mapping:read"]},
    )
    assert sa.status_code == 200, sa.text
    sa_json = sa.json()

    issue = client.post(
        "/auth/token",
        json={"token_type": "exporter", "client_id": sa_json["client_id"], "client_secret": sa_json["client_secret"]},
    )
    assert issue.status_code == 200, issue.text
    pair = issue.json()

    ok = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
        json={"mall_id": "mall-1", "local_id": "local-1", "rows": []},
    )
    assert ok.status_code == 200

    bad = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
        json={"mall_id": "mall-1", "local_id": "local-999", "rows": []},
    )
    assert bad.status_code == 403

    refreshed = client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    new_pair = refreshed.json()

    old_refresh = client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert old_refresh.status_code == 401

    revoke = client.post(
        "/auth/revoke",
        headers={"Authorization": f"Bearer {new_pair['access_token']}"},
        json={"reason": "test"},
    )
    assert revoke.status_code == 200

    reused = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {new_pair['access_token']}"},
        json={"mall_id": "mall-1", "local_id": "local-1"},
    )
    assert reused.status_code == 401


def test_non_expiring_access_policy_survives_refresh_rotation():
    _client, svc, store = build_test_client()
    pair = svc._issue_pair(
        mall_id="mall-1",
        local_id="local-1",
        token_type="exporter",
        scopes=["export:write"],
        created_by="tester",
        service_account_id=None,
        request=None,
        access_never_expires=True,
    )

    original = store.get_token_by_id(pair["token_id"])
    assert original["access_never_expires"] is True
    assert original["access_expires_at"].startswith("9999-12-31")
    assert "exp" not in jwt.decode(pair["access_token"], options={"verify_signature": False})

    rotated_pair = svc.refresh(pair["refresh_token"], request=None)
    rotated = store.get_token_by_id(rotated_pair["token_id"])
    assert original["status"] == "revoked"
    assert rotated["access_never_expires"] is True
    assert rotated["access_expires_at"].startswith("9999-12-31")
    assert "exp" not in jwt.decode(rotated_pair["access_token"], options={"verify_signature": False})


def test_non_expiring_access_policy_survives_regeneration():
    client, svc, store = build_test_client()
    admin_access = bootstrap_manage_token(client, svc, store)
    permanent = svc._issue_pair(
        mall_id="mall-1",
        local_id="local-1",
        token_type="exporter",
        scopes=["export:write"],
        created_by="tester",
        service_account_id=None,
        request=None,
        access_never_expires=True,
    )

    regenerated = client.post(
        f"/tokens/{permanent['token_id']}/regenerate",
        headers={"Authorization": f"Bearer {admin_access}"},
    )

    assert regenerated.status_code == 200, regenerated.text
    regenerated_pair = regenerated.json()
    replacement = store.get_token_by_id(regenerated_pair["token_id"])
    assert store.get_token_by_id(permanent["token_id"])["status"] == "revoked"
    assert replacement["access_never_expires"] is True
    assert replacement["access_expires_at"].startswith("9999-12-31")
    assert "exp" not in jwt.decode(regenerated_pair["access_token"], options={"verify_signature": False})


def test_exporter_sync_ingest_writes_structured_load_log():
    fake_supabase = _FakeSupabase()
    client, svc, store = build_test_client(fake_supabase)
    store.local_codes[("mall-1", "local-1")] = "LOC-001"
    store.local_names[("mall-1", "local-1")] = "Zara"

    admin_access = bootstrap_manage_token(client, svc, store)
    sa = client.post(
        "/service-accounts",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"mall_id": "mall-1", "local_id": "local-1", "token_type": "exporter", "scopes": ["export:write", "mapping:read"]},
    )
    assert sa.status_code == 200, sa.text

    issue = client.post(
        "/auth/token",
        json={"token_type": "exporter", "client_id": sa.json()["client_id"], "client_secret": sa.json()["client_secret"]},
    )
    assert issue.status_code == 200, issue.text

    ingest = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {issue.json()['access_token']}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{
                "documento_numero": "FAC-1001",
                "documento_tipo": "factura",
                "fecha_venta": "2026-03-09",
                "hora_venta": "10:15:00",
                "total_bruto": 120,
                "total_impuesto": 18,
                "total_neto": 138,
            }],
            "meta": {
                "batch_id": "batch-web-001",
                "filename": "mall-demo-sync.json",
            },
        },
    )
    assert ingest.status_code == 200, ingest.text

    logs = fake_supabase.tables.get("logs_carga") or []
    assert len(logs) == 1
    assert logs[0]["canal"] == "WebService"
    assert logs[0]["local_nombre"] == "Zara"
    assert logs[0]["batch_id"] == "batch-web-001"
    assert logs[0]["records_processed"] == 1
    assert logs[0]["error_count"] == 0
    assert logs[0]["metadata"]["source"] == "exporter_sync_ingest"
    assert logs[0]["metadata"]["origin"] == "MsExportador"
    assert logs[0]["metadata"]["channel_family"] == "ERP_WEBSERVICE"

    events = fake_supabase.tables.get("operations_events") or []
    assert len(events) == 1
    assert events[0]["event_type"] == "WEBSERVICE_RECEIVED"
    assert events[0]["source"] == "MONITOR"
    assert events[0]["mall_id"] == "mall-1"
    assert events[0]["local_id"] == "local-1"
    assert events[0]["payload"]["canal"] == "WebService"


def test_exporter_token_handles_store_lookup_failure_without_500():
    client, svc, store = build_test_client()

    def _raise_lookup_error(_client_id):
        raise RuntimeError("relation \"service_accounts\" does not exist")

    store.find_service_account_by_client_id = _raise_lookup_error  # type: ignore[method-assign]

    issue = client.post(
        "/auth/token",
        json={"token_type": "exporter", "client_id": "msa_test", "client_secret": "secret"},
    )
    assert issue.status_code == 503, issue.text
    assert issue.json()["detail"] == "Autenticacion exporter temporalmente no disponible"


def test_exporter_token_rejects_misconfigured_service_account_without_500():
    client, svc, store = build_test_client()
    client_secret = "super-secret"

    def _misconfigured_service_account(_client_id):
        return {
            "id": "sa-1",
            "status": "active",
            "token_type": "exporter",
            "client_secret_hash": token_auth_hash_token(client_secret),
            "mall_id": "mall-1",
            "local_id": None,
            "scopes": ["export:write"],
        }

    store.find_service_account_by_client_id = _misconfigured_service_account  # type: ignore[method-assign]

    issue = client.post(
        "/auth/token",
        json={"token_type": "exporter", "client_id": "msa_test", "client_secret": client_secret},
    )
    assert issue.status_code == 400, issue.text
    assert issue.json()["detail"] == "Service account exporter incompleta (id/mall_id/local_id)"


def test_exporter_token_missing_jwt_secret_returns_503_without_persisting_token():
    client, svc, store = build_test_client()
    client_secret = "super-secret"

    def _valid_service_account(_client_id):
        return {
            "id": "sa-1",
            "status": "active",
            "token_type": "exporter",
            "client_secret_hash": token_auth_hash_token(client_secret),
            "mall_id": "mall-1",
            "local_id": "local-1",
            "scopes": ["export:write"],
        }

    store.find_service_account_by_client_id = _valid_service_account  # type: ignore[method-assign]

    prev_msmall_secret = os.environ.pop("MSMALL_TOKEN_JWT_SECRET", None)
    prev_jwt_secret = os.environ.pop("JWT_SECRET", None)
    try:
        issue = client.post(
            "/auth/token",
            json={"token_type": "exporter", "client_id": "msa_test", "client_secret": client_secret},
        )
    finally:
        if prev_msmall_secret is not None:
            os.environ["MSMALL_TOKEN_JWT_SECRET"] = prev_msmall_secret
        if prev_jwt_secret is not None:
            os.environ["JWT_SECRET"] = prev_jwt_secret

    assert issue.status_code == 503, issue.text
    assert issue.json()["detail"] == "Emision de token exporter temporalmente no disponible"
    assert len(store.api_tokens) == 0


def test_bulk_revoke_local_and_mall():
    client, svc, store = build_test_client()
    admin_access = bootstrap_manage_token(client, svc, store)
    t1 = svc._issue_pair(mall_id="mall-1", local_id="local-1", token_type="exporter", scopes=["export:write"], created_by="x", service_account_id=None, request=None)
    t2 = svc._issue_pair(mall_id="mall-1", local_id="local-2", token_type="exporter", scopes=["export:write"], created_by="x", service_account_id=None, request=None)
    t3 = svc._issue_pair(mall_id="mall-2", local_id="local-3", token_type="exporter", scopes=["export:write"], created_by="x", service_account_id=None, request=None)

    r1 = client.post("/auth/revoke/local", headers={"Authorization": f"Bearer {admin_access}"}, json={"mall_id": "mall-1", "local_id": "local-1"})
    assert r1.status_code == 200
    assert r1.json()["revoked_count"] >= 1

    a1 = client.post("/api/v1/exporter/sync/ingest", headers={"Authorization": f"Bearer {t1['access_token']}"}, json={"mall_id": "mall-1", "local_id": "local-1"})
    assert a1.status_code == 401
    a2 = client.post("/api/v1/exporter/sync/ingest", headers={"Authorization": f"Bearer {t2['access_token']}"}, json={"mall_id": "mall-1", "local_id": "local-2"})
    assert a2.status_code == 200

    r2 = client.post("/auth/revoke/mall", headers={"Authorization": f"Bearer {admin_access}"}, json={"mall_id": "mall-1"})
    assert r2.status_code == 200
    a2b = client.post("/api/v1/exporter/sync/ingest", headers={"Authorization": f"Bearer {t2['access_token']}"}, json={"mall_id": "mall-1", "local_id": "local-2"})
    assert a2b.status_code == 401
    a3 = client.post("/api/v1/exporter/sync/ingest", headers={"Authorization": f"Bearer {t3['access_token']}"}, json={"mall_id": "mall-2", "local_id": "local-3"})
    assert a3.status_code == 200


def _issue_exporter_access_for_local(client, svc, store, mall_id: str, local_id: str) -> str:
    admin_access = bootstrap_manage_token(client, svc, store)
    sa = client.post(
        "/service-accounts",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"mall_id": mall_id, "local_id": local_id, "token_type": "exporter", "scopes": ["export:write"]},
    )
    assert sa.status_code == 200, sa.text
    sa_json = sa.json()
    issue = client.post(
        "/auth/token",
        json={"token_type": "exporter", "client_id": sa_json["client_id"], "client_secret": sa_json["client_secret"]},
    )
    assert issue.status_code == 200, issue.text
    return issue.json()["access_token"]


def test_exporter_sync_ingest_transaction_persists_and_dedups():
    client, svc, store = build_test_client()
    store.local_codes[("mall-1", "local-1")] = "CLI-001"
    access_token = _issue_exporter_access_for_local(client, svc, store, "mall-1", "local-1")

    payload = {
        "mall_id": "mall-1",
        "local_id": "local-1",
        "rows": [
            {
                "factura_numero": "F-1001",
                "fecha_venta": "2026-02-26",
                "hora_venta": "10:20:30",
                "total_bruto": "100.00",
                "total_impuestos": "19.00",
                "total_neto": "81.00",
            }
        ],
        "meta": {"granularity": "transaction", "batch_id": "b1", "chunk_index": 1, "chunk_total": 1},
    }
    r1 = client.post("/api/v1/exporter/sync/ingest", headers={"Authorization": f"Bearer {access_token}"}, json=payload)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1["accepted"] is True
    assert j1["codigo_cliente"] == "CLI-001"
    assert j1["inserted"] == 1
    assert j1["updated"] == 0
    assert j1["ventas_inserted"] == 1
    assert j1["ventas_updated"] == 0

    rows_after_first = store.list_exporter_ingest_rows()
    assert len(rows_after_first) == 1
    assert rows_after_first[0]["documento_numero"] == "F-1001"
    assert rows_after_first[0]["documento_tipo"] == "factura"
    assert rows_after_first[0]["codigo_cliente"] == "CLI-001"
    sales_after_first = store.list_sales_rows()
    assert len(sales_after_first) == 1
    assert sales_after_first[0]["factura_no"] == "F-1001"
    assert sales_after_first[0]["fecha"] == "2026-02-26"
    assert sales_after_first[0]["hora_transaccion"] == "10:20:30"
    assert sales_after_first[0]["total_impuestos"] == 19.0
    assert sales_after_first[0]["metadata"]["source"] == "exporter_webservice"

    payload["rows"][0]["total_neto"] = "82.00"
    r2 = client.post("/api/v1/exporter/sync/ingest", headers={"Authorization": f"Bearer {access_token}"}, json=payload)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2["inserted"] == 0
    assert j2["updated"] == 1
    assert j2["ventas_inserted"] == 0
    assert j2["ventas_updated"] == 1

    rows_after_second = store.list_exporter_ingest_rows()
    assert len(rows_after_second) == 1
    assert rows_after_second[0]["total_neto"] == 82.0
    sales_after_second = store.list_sales_rows()
    assert len(sales_after_second) == 1
    assert sales_after_second[0]["total_neto"] == 82.0


def test_exporter_sync_ingest_daily_requires_resumen_id_when_no_documento():
    client, svc, store = build_test_client()
    store.local_codes[("mall-1", "local-1")] = "CLI-001"
    access_token = _issue_exporter_access_for_local(client, svc, store, "mall-1", "local-1")

    bad = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{"fecha_venta": "2026-02-26", "total_bruto": 1000, "total_impuesto": 190, "total_neto": 810}],
            "meta": {"granularity": "daily"},
        },
    )
    assert bad.status_code == 422

    ok = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{
                "fecha_venta": "2026-02-26",
                "total_bruto": 1000,
                "total_impuesto": 190,
                "total_neto": 810,
                "resumen_id": "local-1-2026-02-26",
                "cantidad_documentos": 12,
            }],
            "meta": {"granularity": "daily"},
        },
    )
    assert ok.status_code == 200, ok.text
    j = ok.json()
    assert j["granularity"] == "daily"
    assert j["inserted"] == 1
    assert j["ventas_inserted"] == 1
    assert j["ventas_updated"] == 0
    rows = store.list_exporter_ingest_rows()
    assert len(rows) == 1
    assert rows[0]["hora_venta"] is None
    assert rows[0]["resumen_id"] == "local-1-2026-02-26"
    sales_rows = store.list_sales_rows()
    assert len(sales_rows) == 1
    assert sales_rows[0]["factura_no"] == "WS-DAILY:local-1-2026-02-26"
    assert sales_rows[0].get("hora_transaccion") is None
    assert sales_rows[0]["metadata"]["granularity"] == "daily"


def test_exporter_sync_ingest_updates_existing_venta_row():
    client, svc, store = build_test_client()
    store.local_codes[("mall-1", "local-1")] = "CLI-001"
    existing_sale = {
        "id": "venta-1",
        "mall_id": "mall-1",
        "local_id": "local-1",
        "fecha": "2026-02-26",
        "factura_no": "F-1001",
        "hora_transaccion": "09:30:00",
        "total_bruto": 100.0,
        "total_impuestos": 19.0,
        "total_neto": 81.0,
        "metadata": {"source": "file_import"},
        "created_at": "2026-02-26T10:00:00+00:00",
        "updated_at": "2026-02-26T10:00:00+00:00",
    }
    store.sales_rows[build_sales_dedup_key(existing_sale)] = dict(existing_sale)
    access_token = _issue_exporter_access_for_local(client, svc, store, "mall-1", "local-1")

    response = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{
                "factura_numero": "F-1001",
                "fecha_venta": "2026-02-26",
                "hora_venta": "10:20:30",
                "total_bruto": 118.0,
                "total_impuestos": 18.0,
                "total_neto": 100.0,
            }],
            "meta": {"granularity": "transaction", "batch_id": "batch-ventas-1"},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ventas_inserted"] == 0
    assert payload["ventas_updated"] == 1
    sales_rows = store.list_sales_rows()
    assert len(sales_rows) == 1
    assert sales_rows[0]["factura_no"] == "F-1001"
    assert sales_rows[0]["total_bruto"] == 118.0
    assert sales_rows[0]["total_impuestos"] == 18.0
    assert sales_rows[0]["total_neto"] == 100.0
    assert sales_rows[0]["metadata"]["source"] == "exporter_webservice"


def test_exporter_sync_ingest_returns_promotion_error_detail():
    fake_supabase = _FakeSupabase()
    client, svc, store = build_test_client(fake_supabase)
    store.local_codes[("mall-1", "local-1")] = "CLI-001"
    access_token = _issue_exporter_access_for_local(client, svc, store, "mall-1", "local-1")

    def _raise_promotion_error(_rows):
        raise RuntimeError('column "factura_no" of relation "ventas" does not exist')

    store.promote_exporter_ingest_rows = _raise_promotion_error  # type: ignore[method-assign]

    response = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{
                "factura_numero": "F-1001",
                "fecha_venta": "2026-02-26",
                "hora_venta": "10:20:30",
                "total_bruto": 118.0,
                "total_impuestos": 18.0,
                "total_neto": 100.0,
            }],
            "meta": {"granularity": "transaction", "batch_id": "batch-error-1"},
        },
    )

    assert response.status_code == 500, response.text
    assert 'Error promoviendo ventas WebService a public.ventas' in response.json()["detail"]
    assert 'factura_no' in response.json()["detail"]

    logs = fake_supabase.tables.get("logs_carga") or []
    assert len(logs) == 1
    assert logs[0]["estado"] == "error"
    assert logs[0]["canal"] == "WebService"
    assert logs[0]["batch_id"] == "batch-error-1"
    assert logs[0]["metadata"]["origin"] == "MsExportador"

    events = fake_supabase.tables.get("operations_events") or []
    assert len(events) == 1
    assert events[0]["event_type"] == "WEBSERVICE_FAILED"
    assert events[0]["severity"] == "HIGH"
    assert events[0]["payload"]["metadata"]["channel_family"] == "ERP_WEBSERVICE"


def test_exporter_webservice_config_crud_endpoints():
    client, svc, store = build_test_client()
    admin_access = bootstrap_manage_token(client, svc, store)

    put = client.put(
        "/api/v1/exporter/configs/local-1",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={
            "mall_id": "mall-1",
            "enabled": True,
            "contract_type": "msmall_sales_v1",
            "default_granularity": "daily",
            "allow_transaction": False,
            "allow_daily": True,
            "strict_validation": True,
            "notes": "ERP via webservice",
        },
    )
    assert put.status_code == 200, put.text
    cfg = put.json()
    assert cfg["mall_id"] == "mall-1"
    assert cfg["local_id"] == "local-1"
    assert cfg["default_granularity"] == "daily"
    assert cfg["allow_transaction"] is False

    get_one = client.get(
        "/api/v1/exporter/configs/local-1",
        headers={"Authorization": f"Bearer {admin_access}"},
        params={"mall_id": "mall-1"},
    )
    assert get_one.status_code == 200, get_one.text
    assert get_one.json()["notes"] == "ERP via webservice"

    get_list = client.get(
        "/api/v1/exporter/configs",
        headers={"Authorization": f"Bearer {admin_access}"},
        params={"mall_id": "mall-1"},
    )
    assert get_list.status_code == 200, get_list.text
    rows = get_list.json()
    assert len(rows) == 1
    assert rows[0]["local_id"] == "local-1"


def test_exporter_sync_ingest_respects_webservice_config():
    client, svc, store = build_test_client()
    admin_access = bootstrap_manage_token(client, svc, store)
    store.local_codes[("mall-1", "local-1")] = "CLI-001"
    access_token = _issue_exporter_access_for_local(client, svc, store, "mall-1", "local-1")

    cfg_put = client.put(
        "/api/v1/exporter/configs/local-1",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={
            "mall_id": "mall-1",
            "enabled": True,
            "contract_type": "msmall_sales_v1",
            "default_granularity": "transaction",
            "allow_transaction": True,
            "allow_daily": False,
            "strict_validation": True,
        },
    )
    assert cfg_put.status_code == 200, cfg_put.text

    daily_blocked = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{
                "fecha_venta": "2026-02-26",
                "total_bruto": 1000,
                "total_impuesto": 190,
                "total_neto": 810,
                "resumen_id": "loc-1-2026-02-26",
            }],
            "meta": {"granularity": "daily"},
        },
    )
    assert daily_blocked.status_code == 422, daily_blocked.text

    tx_ok = client.post(
        "/api/v1/exporter/sync/ingest",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "mall_id": "mall-1",
            "local_id": "local-1",
            "rows": [{
                "factura_numero": "F-2001",
                "fecha_venta": "2026-02-26",
                "hora_venta": "09:15:00",
                "total_bruto": 200,
                "total_impuesto": 38,
                "total_neto": 162,
            }],
            "meta": {"batch_id": "cfgtest-1"},
        },
    )
    assert tx_ok.status_code == 200, tx_ok.text
    tx_json = tx_ok.json()
    assert tx_json["webservice_config_applied"] is True
    assert tx_json["granularity"] == "transaction"
