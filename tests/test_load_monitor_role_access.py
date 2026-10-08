import asyncio
from types import SimpleNamespace

import httpx
import pytest
import main


def request(method, url):
    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url)
    return asyncio.run(run())


@pytest.mark.parametrize(
    "permissions,mall_id,status",
    [
        ({"monitor": {"view": True}}, "mall-demo", 200),
        ({"monitor": {"view": False}}, "mall-demo", 403),
        ({"monitor": {"create": True}}, "mall-demo", 403),
        ({"stores": {"view": True}}, "mall-demo", 403),
        ({"monitor": {"view": True}}, "mall-other", 403),
    ],
)
def test_demo_role_reads_only_authorized_mall_logs(monkeypatch, permissions, mall_id, status):
    context = {"user_id": "demo-user", "role": "rol_demo", "email": "demo@example.test", "permissions": permissions}
    calls = []

    async def get_context(_user_id):
        return context

    def list_logs(**kwargs):
        kwargs["ensure_operator_can_access_mall"](kwargs["operator_ctx"], kwargs["mall_id"])
        calls.append(kwargs["mall_id"])
        return [{"id": "load-1", "mall_id": "mall-demo", "archivo": "ventas2026.txt"}]

    monkeypatch.setattr(main, "_get_access_context", get_context)
    monkeypatch.setattr(main, "_get_user_mall_ids", lambda _user_id: ["mall-demo"])
    monkeypatch.setattr(main, "_sensitive_ops_service", lambda: SimpleNamespace(list_load_logs=list_logs))
    main.app.dependency_overrides[main.get_current_user_id] = lambda: "demo-user"
    try:
        response = request("GET", f"/api/v1/load-logs?mall_id={mall_id}")
        assert response.status_code == status
        if status == 200:
            assert response.json()[0]["archivo"] == "ventas2026.txt"
            assert calls == ["mall-demo"]
        else:
            assert calls == []
        # Monitor view does not grant destructive or unrelated audit access.
        assert request("DELETE", "/api/v1/load-logs?mall_id=mall-demo").status_code == 403
        with pytest.raises(main.HTTPException) as denied:
            asyncio.run(main.require_audit_read_access(user_id="demo-user"))
        assert denied.value.status_code == 403
    finally:
        main.app.dependency_overrides.pop(main.get_current_user_id, None)


@pytest.mark.parametrize("role", ["admin", "it", "auditor"])
def test_existing_audit_roles_keep_load_log_access(monkeypatch, role):
    context = {"role": role, "permissions": {}}
    async def get_context(_user_id):
        return context
    monkeypatch.setattr(main, "_get_access_context", get_context)
    assert asyncio.run(main.require_load_logs_read_access(user_id="existing-user")) is context
