import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

import main


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _AuditTable:
    def __init__(self):
        self.payload = None

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        return _Result([self.payload])


class _AuthAdmin:
    def __init__(self, user):
        self.user = user

    def get_user_by_id(self, user_id):
        return {"user": {**self.user, "id": user_id}}


class _Auth:
    def __init__(self, user, reset_error=None):
        self.admin = _AuthAdmin(user)
        self.reset_error = reset_error
        self.reset_calls = []

    def reset_password_for_email(self, email, options):
        self.reset_calls.append((email, options))
        if self.reset_error:
            raise self.reset_error


class _FakeSupabase:
    def __init__(self, user, reset_error=None):
        self.auth = _Auth(user, reset_error)
        self.audit = _AuditTable()

    def table(self, name):
        assert name == "system_audit_logs"
        return self.audit


def test_admin_sends_password_recovery_and_records_audit(monkeypatch):
    fake = _FakeSupabase({"email": "USER@EXAMPLE.COM"})
    monkeypatch.setattr(main, "supabase", fake)
    monkeypatch.setattr(
        main,
        "PASSWORD_RECOVERY_REDIRECT_URL",
        "https://msmall.vercel.app/?password_recovery=1",
    )

    result = asyncio.run(
        main.admin_send_password_recovery("target-user", {"user_id": "admin-user"})
    )

    assert fake.auth.reset_calls == [
        (
            "user@example.com",
            {"redirect_to": "https://msmall.vercel.app/?password_recovery=1"},
        )
    ]
    assert result["target_user_id"] == "target-user"
    assert fake.audit.payload["usuario_id"] == "admin-user"
    assert fake.audit.payload["accion"] == "USER_PASSWORD_RECOVERY_REQUESTED"
    assert fake.audit.payload["metadata"]["target_user_id"] == "target-user"


def test_admin_password_recovery_maps_rate_limit_without_leaking_provider_error(monkeypatch):
    fake = _FakeSupabase(
        {"email": "user@example.com"},
        reset_error=RuntimeError("email rate limit exceeded: provider-internal-detail"),
    )
    monkeypatch.setattr(main, "supabase", fake)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            main.admin_send_password_recovery("target-user", {"user_id": "admin-user"})
        )

    assert exc_info.value.status_code == 429
    assert "Espera un minuto" in exc_info.value.detail
    assert "provider-internal-detail" not in exc_info.value.detail
    assert fake.audit.payload is None


def test_admin_password_recovery_rejects_user_without_email(monkeypatch):
    fake = _FakeSupabase({"email": ""})
    monkeypatch.setattr(main, "supabase", fake)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            main.admin_send_password_recovery("target-user", {"user_id": "admin-user"})
        )

    assert exc_info.value.status_code == 404
    assert fake.auth.reset_calls == []


def test_frontend_exposes_self_service_and_admin_recovery_flows():
    repo = Path(__file__).resolve().parents[1]
    app = (repo / "App.tsx").read_text(encoding="utf-8")
    auth_provider = (repo / "context" / "AuthProvider.tsx").read_text(encoding="utf-8")
    recovery_screen = (repo / "components" / "PasswordRecovery.tsx").read_text(encoding="utf-8")
    user_management = (repo / "components" / "UserManagement.tsx").read_text(encoding="utf-8")
    api = (repo / "api.ts").read_text(encoding="utf-8")

    assert "¿Olvidaste tu contraseña?" in app
    assert "ForgotPasswordScreen" in app
    assert "ResetPasswordScreen" in app
    assert "event === 'PASSWORD_RECOVERY'" in auth_provider
    assert "supabase.auth.resetPasswordForEmail" in auth_provider
    assert "supabase.auth.updateUser" in auth_provider
    assert "scope: 'global'" in auth_provider
    assert "Si el correo pertenece a una cuenta de MsMall" in recovery_screen
    assert "La nueva contraseña debe tener al menos 8 caracteres." in recovery_screen
    assert "ApiService.sendUserPasswordRecovery" in user_management
    assert "Enviar recuperación" in user_management
    assert "/password-recovery`" in api
