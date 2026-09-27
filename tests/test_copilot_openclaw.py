import json

import pytest
from fastapi import HTTPException

import main


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]


def test_openclaw_endpoint_accepts_https_and_private_railway_http():
    assert main._openclaw_chat_endpoint("https://gateway.example/openclaw") == (
        "https://gateway.example/openclaw/v1/chat/completions"
    )
    assert main._openclaw_chat_endpoint("http://openclaw.railway.internal:18789/v1") == (
        "http://openclaw.railway.internal:18789/v1/chat/completions"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://gateway.example/openclaw",
        "ftp://gateway.example/openclaw",
        "https://user:password@gateway.example/openclaw",
        "https://gateway.example/openclaw?token=secret",
    ],
)
def test_openclaw_endpoint_rejects_unsafe_urls(url):
    with pytest.raises(HTTPException) as error:
        main._openclaw_chat_endpoint(url)
    assert error.value.status_code == 503


def test_openclaw_call_is_stateless_and_contains_only_scoped_context(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": "**Estado**\n- Todo bien"}}]})

    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen)
    answer = main._call_openclaw_copilot(
        "https://gateway.example/openclaw",
        "gateway-secret",
        "openclaw:msmall",
        {"mall": {"id": "mall-a", "nombre": "Mall A"}, "ventas_recientes": {"total": 10}},
        "Resume las ventas",
        [main.CopilotChatMessage(role="assistant", content="Respuesta previa")],
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))
    assert answer.startswith("**Estado**")
    assert request.full_url == "https://gateway.example/openclaw/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer gateway-secret"
    assert request.get_header("X-openclaw-agent-id") == "msmall"
    assert payload["model"] == "openclaw:msmall"
    assert payload["stream"] is False
    assert "user" not in payload
    assert "x-openclaw-session-key" not in {key.lower() for key in request.headers}
    assert "mall-a" in payload["messages"][-1]["content"]
    assert "mall-b" not in payload["messages"][-1]["content"]
    assert captured["timeout"] == 60


def test_openclaw_status_requires_url_and_token_from_environment(monkeypatch):
    values = {
        main.COPILOT_PROVIDER_KEY: "openclaw",
        main.COPILOT_ENABLED_KEY: "true",
        main.COPILOT_OPENCLAW_MODEL_KEY: "openclaw:msmall",
    }
    monkeypatch.setattr(main, "_get_system_health_value", lambda key: values.get(key))
    monkeypatch.setenv(main.OPENCLAW_GATEWAY_URL_ENV, "https://gateway.example/openclaw")
    monkeypatch.setenv(main.OPENCLAW_GATEWAY_TOKEN_ENV, "secret")

    status = main._copilot_config_status()
    assert status["provider"] == "openclaw"
    assert status["gateway_configured"] is True
    assert status["api_key_configured"] is True
    assert status["available"] is True
    assert "secret" not in json.dumps(status)

    monkeypatch.delenv(main.OPENCLAW_GATEWAY_TOKEN_ENV)
    assert main._copilot_config_status()["available"] is False


def test_openclaw_secret_cannot_be_saved_in_supabase(monkeypatch):
    writes = []
    monkeypatch.setattr(main, "_upsert_system_health_value_sync", lambda *args: writes.append(args))

    with pytest.raises(HTTPException) as error:
        main._save_copilot_settings(
            main.CopilotSettingsRequest(
                enabled=True,
                provider="openclaw",
                model="openclaw:msmall",
                api_key="must-not-be-stored",
            )
        )

    assert error.value.status_code == 400
    assert writes == []


def test_openclaw_cannot_target_the_privileged_main_agent(monkeypatch):
    writes = []
    monkeypatch.setattr(main, "_upsert_system_health_value_sync", lambda *args: writes.append(args))

    with pytest.raises(HTTPException) as error:
        main._save_copilot_settings(
            main.CopilotSettingsRequest(
                enabled=True,
                provider="openclaw",
                model="openclaw:main",
            )
        )

    assert error.value.status_code == 400
    assert writes == []


def test_provider_routes_openclaw_without_reading_database_secret(monkeypatch):
    monkeypatch.setenv(main.OPENCLAW_GATEWAY_URL_ENV, "https://gateway.example/openclaw")
    monkeypatch.setenv(main.OPENCLAW_GATEWAY_TOKEN_ENV, "gateway-secret")
    monkeypatch.setattr(
        main,
        "_get_system_health_value",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not read an OpenClaw token from Supabase")),
    )
    captured = {}

    def fake_call(*args):
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(main, "_call_openclaw_copilot", fake_call)
    result = main._call_copilot_provider(
        {"provider": "openclaw", "model": "openclaw:msmall"},
        {"mall": {"id": "mall-a"}},
        "hola",
        [],
    )

    assert result == "ok"
    assert captured["args"][:3] == (
        "https://gateway.example/openclaw",
        "gateway-secret",
        "openclaw:msmall",
    )
