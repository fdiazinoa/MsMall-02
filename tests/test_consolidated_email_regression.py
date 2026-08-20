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


def test_missing_system_health_slot_is_treated_as_not_sent():
    class _NoContentQuery:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def maybe_single(self):
            return self

        def execute(self):
            return None

    class _NoContentSupabase:
        def table(self, table_name):
            assert table_name == "system_health"
            return _NoContentQuery()

    assert email_service._system_health_get(_NoContentSupabase(), "MDE_SLOT:new-mall") is None


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


def test_scheduler_records_failure_releases_slot_and_continues(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    supabase = _Supabase()
    supabase.rows["email_notification_settings"] = [
        {
            "mall_id": "mall-1",
            "notification_type": email_service.MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE,
            "enabled": True,
            "weekdays": [0],
            "send_time": "10:00",
        },
        {
            "mall_id": "mall-2",
            "notification_type": email_service.MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE,
            "enabled": True,
            "weekdays": [0],
            "send_time": "10:00",
        },
    ]
    released = []
    statuses = []

    monkeypatch.setattr(email_service, "_system_health_get", lambda *_args: None)
    monkeypatch.setattr(email_service, "_claim_system_health_slot", lambda *_args: True)
    monkeypatch.setattr(
        email_service,
        "_release_system_health_slot",
        lambda _client, key, slot: released.append((key, slot)),
    )
    monkeypatch.setattr(
        email_service,
        "_system_health_upsert",
        lambda _client, key, value: statuses.append((key, value)),
    )

    def fake_send(_client, settings, **_kwargs):
        if settings["mall_id"] == "mall-1":
            raise RuntimeError("Resend timeout")
        return {
            "status": "success",
            "mall_id": "mall-2",
            "fecha_inicio": "2026-05-04",
            "fecha_fin": "2026-05-10",
            "requested": 1,
            "sent": 1,
            "skipped": 0,
            "failed": 0,
            "results": [],
        }

    monkeypatch.setattr(email_service, "send_missing_days_emails_for_mall", fake_send)
    result = email_service.run_missing_days_email_scheduler(
        supabase,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
    )

    assert result["checked"] == 2
    assert result["failed"] == 1
    assert result["executed"] is True
    assert result["runs"][0]["reason"] == "send_failed"
    assert result["runs"][1]["sent"] == 1
    assert released == [
        ("MDE_SLOT:mall-1:CONSOLIDATED", "2026-05-11T10:00"),
    ]
    assert ("MDE_STATUS:mall-1:CONSOLIDATED", "error: Resend timeout") in statuses


def test_scheduler_retries_failed_delivery_for_both_modes(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    for notification_type, expected_key in [
        (email_service.MISSING_DAYS_NOTIFICATION_TYPE, "MDE_SLOT:mall-1"),
        (
            email_service.MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE,
            "MDE_SLOT:mall-1:CONSOLIDATED",
        ),
    ]:
        supabase = _Supabase()
        supabase.rows["email_notification_settings"] = [{
            "mall_id": "mall-1",
            "notification_type": notification_type,
            "enabled": True,
            "weekdays": [0],
            "send_time": "10:00",
        }]
        released = []
        monkeypatch.setattr(email_service, "_system_health_get", lambda *_args: None)
        monkeypatch.setattr(email_service, "_claim_system_health_slot", lambda *_args: True)
        monkeypatch.setattr(email_service, "_system_health_upsert", lambda *_args: None)
        monkeypatch.setattr(
            email_service,
            "_release_system_health_slot",
            lambda _client, key, slot: released.append((key, slot)),
        )
        monkeypatch.setattr(
            email_service,
            "send_missing_days_emails_for_mall",
            lambda *_args, **_kwargs: {
                "status": "partial",
                "mall_id": "mall-1",
                "fecha_inicio": "2026-05-04",
                "fecha_fin": "2026-05-10",
                "requested": 1,
                "sent": 0,
                "skipped": 0,
                "failed": 1,
                "results": [{"status": "failed", "reason": "Error enviando email."}],
            },
        )

        result = email_service.run_missing_days_email_scheduler(
            supabase,
            now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
        )

        assert result["failed"] == 1
        assert result["runs"][0]["retry_scheduled"] is True
        assert result["runs"][0]["error"] == "Error enviando email."
        assert released == [(expected_key, "2026-05-11T10:00")]


def test_frontend_and_api_keep_consolidated_mode_contract():
    repo = Path(__file__).resolve().parents[1]
    component = (repo / "components" / "ResendMessagingAdmin.tsx").read_text(encoding="utf-8")
    api = (repo / "api.ts").read_text(encoding="utf-8")
    types = (repo / "types.ts").read_text(encoding="utf-8")

    assert "Consolidar locales" in component
    assert "missing_days_audit_consolidated" in component
    assert "notification_type=${encodeURIComponent(notificationType)}" in api
    assert "missing_days_audit_consolidated" in types
