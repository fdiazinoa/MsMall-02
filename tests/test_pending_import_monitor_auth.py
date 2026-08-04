import asyncio
import importlib
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
MONITOR_SOURCE = ROOT / "railway-functions" / "pending-import-monitor" / "index.tsx"


def _load_main(monkeypatch, token: str = ""):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("PENDING_IMPORT_MONITOR_TOKEN", token)
    for module_name in ("main", "worker_importacion"):
        if module_name in sys.modules:
            del sys.modules[module_name]
    import main  # type: ignore
    return importlib.reload(main)


def _request(app, token=None):
    async def _run():
        headers = {"X-MsMall-Internal-Token": token} if token else {}
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/v1/remote/execute-manual/internal",
                headers=headers,
                json={"config_id": "local-1", "filename": "ventas.csv"},
            )

    return asyncio.run(_run())


def test_internal_monitor_endpoint_requires_dedicated_secret(monkeypatch):
    secret = "m" * 48
    main = _load_main(monkeypatch, secret)

    assert _request(main.app).status_code == 401
    assert _request(main.app, "wrong-token").status_code == 401


def test_internal_monitor_endpoint_passes_internal_context(monkeypatch):
    secret = "m" * 48
    main = _load_main(monkeypatch, secret)
    captured = {}

    async def _fake_execute(req, operator_ctx=None, exporter_ctx=None, internal_ctx=None):
        captured.update({
            "config_id": req.config_id,
            "operator_ctx": operator_ctx,
            "exporter_ctx": exporter_ctx,
            "internal_ctx": internal_ctx,
        })
        return {"status": "success"}

    monkeypatch.setattr(main, "_execute_manual_endpoint_impl", _fake_execute)
    response = _request(main.app, secret)

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert captured["config_id"] == "local-1"
    assert captured["operator_ctx"] is None
    assert captured["exporter_ctx"] is None
    assert captured["internal_ctx"]["source"] == "pending_import_monitor"


def test_internal_monitor_endpoint_fails_closed_when_server_secret_is_missing(monkeypatch):
    main = _load_main(monkeypatch, "")

    response = _request(main.app, "m" * 48)

    assert response.status_code == 503
    assert "no configurada" in response.json()["detail"]


def test_monitor_source_uses_internal_endpoint_and_records_worker_response():
    source = MONITOR_SOURCE.read_text(encoding="utf-8")

    assert 'requiredEnv("WORKER_API_URL")' in source
    assert 'requiredEnv("PENDING_IMPORT_MONITOR_TOKEN")' in source
    assert "/v1/remote/execute-manual/internal" in source
    assert '"X-MsMall-Internal-Token": PENDING_IMPORT_MONITOR_TOKEN' in source
    assert "Authorization: `Bearer ${SUPABASE_KEY}`" not in source
    assert "response.status" in source
    assert "await response.text()" in source
    assert "[outcome=${result.status}]" in source


def test_successful_import_reactivates_only_suspended_local(monkeypatch):
    main = _load_main(monkeypatch)
    calls = []

    class _FakeSensitiveOps:
        def reactivate_local_processing(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(main, "_sensitive_ops_service", lambda: _FakeSensitiveOps())

    main._reactivate_local_after_success(
        {
            "id": "local-suspended",
            "processing_status": "SUSPENDED_AUTH_ERROR",
            "consecutive_failures": 5,
        },
        source="pending_import_monitor",
    )
    main._reactivate_local_after_success(
        {"id": "local-idle", "processing_status": "IDLE", "consecutive_failures": 0},
        source="manual_remote_import",
    )

    assert len(calls) == 1
    assert calls[0]["local_id"] == "local-suspended"
    assert calls[0]["operator_ctx"]["role"] == "admin"
    assert calls[0]["audit_metadata"] == {
        "source": "pending_import_monitor",
        "automatic_reactivation": True,
    }
