import asyncio
import os

from fastapi import FastAPI
import httpx

from routers.token_auth import (
    InMemoryTokenStore,
    TokenService,
    create_router,
    get_token_service,
)


class ASGITestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def post(self, path, **kwargs):
        async def _run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
                return await client.post(path, **kwargs)
        return asyncio.run(_run())


def build_test_client():
    os.environ.setdefault("MSMALL_TOKEN_JWT_SECRET", "test-secret-123")
    app = FastAPI()
    store = InMemoryTokenStore()
    svc = TokenService(store=store)
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
