from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services import missing_days_email_service as email_service


class _Query:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self.filters = []
        self.single = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        self.single = True
        return self

    def upsert(self, payload, **_kwargs):
        self.supabase.upserts.append((self.table_name, payload))
        return self

    def delete(self):
        return self

    def execute(self):
        rows = self.supabase.rows.get(self.table_name, [])
        if self.table_name == "system_health" and not self.supabase.return_health_rows:
            rows = []
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        if self.single:
            return SimpleNamespace(data=rows[0] if rows else None)
        return SimpleNamespace(data=rows)


class _Supabase:
    def __init__(self):
        self.rows = {
            "malls": [{"id": "mall-1", "nombre": "Mall Demo"}],
            "locales": [
                {
                    "id": "local-1",
                    "nombre": "Local Uno",
                    "codigo_interno": "L001",
                    "activo": True,
                    "mall_id": "mall-1",
                    "email": "local@example.com",
                },
                {
                    "id": "local-2",
                    "nombre": "Local Dos",
                    "codigo_interno": "L002",
                    "activo": True,
                    "mall_id": "mall-1",
                    "email": "otro@example.com",
                },
            ],
            "system_health": [],
        }
        self.upserts = []
        self.return_health_rows = False

    def table(self, table_name):
        return _Query(self, table_name)

    def rpc(self, function_name, params):
        assert function_name == "claim_system_health_slot"
        self.upserts.append(("system_health_claim", {
            "key": params["p_key"],
            "value": params["p_slot"],
        }))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=True))


def test_consolidated_email_sends_once_to_admins_and_ignores_local_emails(monkeypatch):
    monkeypatch.setattr(
        email_service,
        "load_missing_days_details_for_local",
        lambda _client, *, local_id, **_kwargs: (
            [{"fecha": "2026-05-09"}, {"fecha": "2026-05-10"}]
            if local_id == "local-1"
            else [{"fecha": "2026-05-10"}]
        ),
    )
    monkeypatch.setattr(
        email_service,
        "load_resend_sender_config",
        lambda *_args, **_kwargs: {
            "from_email": "notificaciones@mercasend.net",
            "from_name": "MSMALL",
        },
    )
    sent = []

    def fake_send(to_email, subject, text_body, html_body, cc_emails, **_kwargs):
        sent.append({
            "to": to_email,
            "cc": cc_emails,
            "subject": subject,
            "text": text_body,
            "html": html_body,
        })
        return {"id": "resend-consolidated-1"}

    result = email_service.send_missing_days_emails_for_mall(
        _Supabase(),
        {
            "mall_id": "mall-1",
            "notification_type": email_service.MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE,
            "lookback_days": 2,
            "send_only_with_gaps": True,
            "cc_emails": ["admin@example.com", "audit@example.com"],
        },
        send_email=fake_send,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
    )

    assert len(sent) == 1
    assert sent[0]["to"] == "admin@example.com"
    assert sent[0]["cc"] == ["audit@example.com"]
    assert "local@example.com" not in str(sent)
    assert "otro@example.com" not in str(sent)
    assert "3 dias faltantes" in sent[0]["html"]
    assert result["sent"] == 1
    assert result["failed"] == 0


def test_scheduler_uses_independent_slots_for_each_mode():
    assert email_service._system_health_key("mall-1", "LAST_SLOT") == "MDE_SLOT:mall-1"
    assert email_service._system_health_key(
        "mall-1",
        "LAST_SLOT",
        email_service.MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE,
    ) == "MDE_SLOT:mall-1:CONSOLIDATED"


def test_scheduler_skips_when_another_worker_claimed_the_slot(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    supabase = _Supabase()
    supabase.rows["email_notification_settings"] = [{
        "mall_id": "mall-1",
        "notification_type": email_service.MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE,
        "enabled": True,
        "weekdays": [0],
        "send_time": "10:00",
    }]
    sent = []

    def unclaimed_rpc(function_name, params):
        assert function_name == "claim_system_health_slot"
        assert params["p_slot"] == "2026-05-11T10:00"
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=False))

    supabase.rpc = unclaimed_rpc
    result = email_service.run_missing_days_email_scheduler(
        supabase,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
        send_email=lambda *_args, **_kwargs: sent.append(True),
    )

    assert result["executed"] is False
    assert result["runs"][0]["reason"] == "already_claimed_for_slot"
    assert sent == []


def test_frontend_and_api_keep_consolidated_mode_contract():
    repo = Path(__file__).resolve().parents[1]
    component = (repo / "components" / "ResendMessagingAdmin.tsx").read_text(encoding="utf-8")
    api = (repo / "api.ts").read_text(encoding="utf-8")
    types = (repo / "types.ts").read_text(encoding="utf-8")

    assert "Consolidar locales" in component
    assert "missing_days_audit_consolidated" in component
    assert "notification_type=${encodeURIComponent(notificationType)}" in api
    assert "missing_days_audit_consolidated" in types
