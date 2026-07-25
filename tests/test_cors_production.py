import asyncio
import importlib
import sys

import httpx


def _load_main(monkeypatch, **env):
    # Prevent local .env credentials from creating external connections in tests.
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    if "main" in sys.modules:
        module = importlib.reload(sys.modules["main"])
    else:
        import main as module  # type: ignore
        module = importlib.reload(module)
    return module


def _request(app, method: str, url: str, **kwargs) -> httpx.Response:
    async def _run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(_run())


def test_cors_production_does_not_return_wildcard(monkeypatch):
    main = _load_main(
        monkeypatch,
        APP_ENV="production",
        CORS_ALLOW_ORIGINS="https://msmall.vercel.app, https://admin.tudominio.com",
    )

    response = _request(
        main.app,
        "GET",
        "/",
        headers={"Origin": "https://msmall.vercel.app"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://msmall.vercel.app"
    assert response.headers.get("access-control-allow-origin") != "*"


def test_cors_allows_only_this_project_vercel_previews(monkeypatch):
    main = _load_main(monkeypatch, APP_ENV="production")

    preview = _request(
        main.app,
        "GET",
        "/",
        headers={"Origin": "https://msmall-6ovf0rwyg-felix-diaz-s-projects.vercel.app"},
    )
    foreign = _request(
        main.app,
        "GET",
        "/",
        headers={"Origin": "https://untrusted-project.vercel.app"},
    )

    assert preview.headers.get("access-control-allow-origin") == "https://msmall-6ovf0rwyg-felix-diaz-s-projects.vercel.app"
    assert foreign.headers.get("access-control-allow-origin") is None
