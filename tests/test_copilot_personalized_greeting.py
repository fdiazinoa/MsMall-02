from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_widget_greets_authenticated_user_in_active_mall():
    source = (ROOT / "components" / "CopilotWidget.tsx").read_text(encoding="utf-8")

    assert source.index("user?.nombre,") < source.index("user?.nombre_completo")
    assert "session?.user?.user_metadata?.full_name" in source
    assert "'usuario msmall'" in source
    assert "¡Hola, ${displayName}!" in source
    assert "${currentMall?.nombre || 'el mall seleccionado'}" in source
    assert "setMessages(mallId ? [greeting] : [])" in source


def test_widget_keeps_quick_prompts_until_user_starts_conversation():
    source = (ROOT / "components" / "CopilotWidget.tsx").read_text(encoding="utf-8")

    assert "!messages.some((message) => message.role === 'user')" in source
    assert "ApiService.sendCopilotMessage(mallId, question, messages, token" in source


def test_widget_does_not_expose_ai_provider_in_header():
    source = (ROOT / "components" / "CopilotWidget.tsx").read_text(encoding="utf-8")

    assert "{currentMall?.nombre || 'Mall seleccionado'} · {providerName}" not in source
    assert "if (status.provider === 'openclaw') return 'OpenClaw'" not in source
