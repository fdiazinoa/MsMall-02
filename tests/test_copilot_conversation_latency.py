import asyncio

import pytest
from fastapi import HTTPException

import main


@pytest.fixture
def chat(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_copilot_config_status", lambda: {
        "enabled": True, "available": True, "provider": "test", "model": "test",
    })
    monkeypatch.setattr(main, "_ensure_operator_can_access_mall", lambda *_: calls.append("access"))
    monkeypatch.setattr(main, "_build_copilot_context", lambda *_: calls.append("context") or {})
    monkeypatch.setattr(main, "_build_big_data_copilot_context", lambda *_: calls.append("big_data") or {})
    monkeypatch.setattr(main, "_call_copilot_provider", lambda *_: calls.append("provider") or "Respuesta operativa")

    def send(message, **kwargs):
        return asyncio.run(main.chat_with_copilot(
            main.CopilotChatRequest(mall_id="mall-1", message=message, **kwargs),
            {"user_id": "user-1", "email": "user@example.com", "role": "admin"},
        ))

    return send, calls


@pytest.mark.parametrize("message", [
    "Hola", " ¡HÓLA! 👋 ", "Buenos días", "Hola Copilot",
    "Muchas gracias", "¿Cómo estás?", "¿Qué puedes hacer?",
])
def test_conversation_skips_context_and_provider(chat, message):
    send, calls = chat
    result = send(message)
    assert result["answer"]
    assert result["provider"] == "deterministic"
    assert result["sources"] == []
    assert calls == ["access"]


@pytest.mark.parametrize("message", [
    "Hola, revisa las conexiones", "Cuántos locales tienen API",
    "¿Y los otros?", "Explícame ese error", "Gracias, revisa las cargas",
])
def test_mixed_operational_and_followup_messages_keep_live_context(chat, message):
    send, calls = chat
    assert send(message)["answer"] == "Respuesta operativa"
    assert calls == ["context", "provider"]


def test_big_data_keeps_its_context(chat):
    send, calls = chat
    send("¿Cómo van las ventas este mes?")
    assert calls == ["big_data", "provider"]


@pytest.mark.parametrize("extra", [
    {"log_text": "fallo de conexión"}, {"fecha_inicio": "2026-10-01"},
    {"fecha_fin": "2026-10-12"},
])
def test_greeting_with_operational_inputs_does_not_skip_context(chat, extra):
    send, calls = chat
    send("Hola", **extra)
    assert calls == ["context", "provider"]


def test_greeting_rejects_unauthorized_mall(chat, monkeypatch):
    send, calls = chat

    def deny(*_):
        raise HTTPException(403, "Sin acceso")

    monkeypatch.setattr(main, "_ensure_operator_can_access_mall", deny)
    with pytest.raises(HTTPException) as error:
        send("Hola")
    assert error.value.status_code == 403
    assert calls == []


def test_greeting_respects_disabled_copilot(chat, monkeypatch):
    send, calls = chat
    monkeypatch.setattr(main, "_copilot_config_status", lambda: {"enabled": False})
    with pytest.raises(HTTPException) as error:
        send("Hola")
    assert error.value.status_code == 503
    assert calls == []


def test_greeting_does_not_require_ai_provider(chat, monkeypatch):
    send, calls = chat
    monkeypatch.setattr(main, "_copilot_config_status", lambda: {
        "enabled": True, "available": False,
    })
    assert send("Hola")["provider"] == "deterministic"
    assert calls == ["access"]
