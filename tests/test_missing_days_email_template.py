from datetime import datetime, timezone

from services.missing_days_email_service import (
    build_missing_days_email_html,
    missing_days_email_period,
    run_missing_days_email_scheduler,
    missing_days_schedule_slot,
    render_missing_days_template,
)


def test_missing_days_email_html_contains_alert_summary_and_days():
    html = build_missing_days_email_html(
        mall_name="Mall Demo",
        local_name="Local Demo",
        fecha_inicio="2026-05-01",
        fecha_fin="2026-05-10",
        missing_details=[
            {
                "fecha": "2026-05-05",
                "causa": "Procesado con Exito (Posible archivo vacio)",
                "log_id": "abc-123",
            },
            {
                "fecha": "2026-05-08",
                "causa": "Archivo no disponible en FTP",
            },
        ],
    )

    assert "Faltan ventas para 2 dias" in html
    assert "Local auditado:</strong> Local Demo" in html
    assert "Detalle de dias faltantes y auditoria de logs" in html
    assert "2026-05-05" in html
    assert "2026-05-08" in html
    assert "Log ID: #abc-123" in html


def test_missing_days_email_html_includes_configured_body_message():
    html = build_missing_days_email_html(
        mall_name="Mall Demo",
        local_name="Local Demo",
        fecha_inicio="2026-05-01",
        fecha_fin="2026-05-10",
        missing_details=[],
        body_message="Mensaje personalizado para el local.",
    )

    assert "Mensaje personalizado para el local." in html


def test_render_missing_days_template_replaces_known_variables_only():
    rendered = render_missing_days_template(
        "Hola {local_name}, faltan {missing_count} dias. {unknown}",
        {"local_name": "Local Demo", "missing_count": 3},
        "Default",
    )

    assert rendered == "Hola Local Demo, faltan 3 dias. {unknown}"


def test_missing_days_schedule_slot_uses_configured_local_time(monkeypatch):
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    settings = {
        "enabled": True,
        "weekdays": [0],
        "send_time": "10:00",
    }

    due, slot, reason = missing_days_schedule_slot(
        settings,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
    )

    assert due is True
    assert slot == "2026-05-11T10:00"
    assert reason == "due"


def test_missing_days_schedule_slot_waits_until_send_time(monkeypatch):
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    settings = {
        "enabled": True,
        "weekdays": [0],
        "send_time": "10:00",
    }

    due, slot, reason = missing_days_schedule_slot(
        settings,
        now=datetime(2026, 5, 11, 13, 59, tzinfo=timezone.utc),
    )

    assert due is False
    assert slot is None
    assert reason == "send_time_not_reached"


def test_missing_days_email_period_ends_on_previous_local_day(monkeypatch):
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")

    fecha_inicio, fecha_fin = missing_days_email_period(
        3,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
    )

    assert fecha_inicio == "2026-05-08"
    assert fecha_fin == "2026-05-10"


def test_missing_days_scheduler_sends_when_slot_is_due(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    sent = []

    class FakeQuery:
        def __init__(self, db, table_name):
            self.db = db
            self.table_name = table_name
            self.filters = {}
            self.upsert_payload = None

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def lte(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def range(self, *_args, **_kwargs):
            return self

        def maybe_single(self):
            return self

        def upsert(self, payload, **_kwargs):
            self.upsert_payload = payload
            return self

        def execute(self):
            if self.upsert_payload is not None:
                self.db.upserts.append((self.table_name, self.upsert_payload))
                return type("Response", (), {"data": [self.upsert_payload]})()
            if self.table_name == "email_notification_settings":
                return type("Response", (), {"data": self.db.settings})()
            if self.table_name == "system_health":
                return None
            if self.table_name == "malls":
                return type("Response", (), {"data": {"nombre": "Mall Demo"}})()
            if self.table_name == "locales":
                return type("Response", (), {"data": [{"id": "local-1", "nombre": "Local Demo", "email": "local@example.com"}]})()
            return type("Response", (), {"data": []})()

    class FakeSupabase:
        def __init__(self):
            self.settings = [{
                "mall_id": "mall-1",
                "notification_type": "missing_days_audit",
                "enabled": True,
                "weekdays": [0],
                "send_time": "10:00",
                "lookback_days": 1,
                "send_only_with_gaps": True,
                "cc_emails": [],
            }]
            self.upserts = []

        def table(self, table_name):
            return FakeQuery(self, table_name)

    def fake_send_email(to_email, subject, text_body, html_body, cc_emails, **kwargs):
        sent.append({
            "to": to_email,
            "subject": subject,
            "text": text_body,
            "html": html_body,
            "cc": cc_emails,
            "kwargs": kwargs,
        })
        return {"id": "resend-1"}

    db = FakeSupabase()
    result = run_missing_days_email_scheduler(
        db,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
        send_email=fake_send_email,
    )

    assert result["executed"] is True
    assert result["runs"][0]["sent"] == 1
    assert sent[0]["to"] == "local@example.com"
    assert "Local Demo" in sent[0]["subject"]
    assert any(payload["key"] == "MDE_SLOT:mall-1" for _table, payload in db.upserts)


def test_missing_days_scheduler_uses_admin_email_when_local_has_no_email(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MISSING_DAYS_EMAIL_TIMEZONE", "America/Santo_Domingo")
    sent = []

    class FakeQuery:
        def __init__(self, db, table_name):
            self.db = db
            self.table_name = table_name
            self.filters = {}
            self.upsert_payload = None

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def lte(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def range(self, *_args, **_kwargs):
            return self

        def maybe_single(self):
            return self

        def upsert(self, payload, **_kwargs):
            self.upsert_payload = payload
            return self

        def execute(self):
            if self.upsert_payload is not None:
                self.db.upserts.append((self.table_name, self.upsert_payload))
                return type("Response", (), {"data": [self.upsert_payload]})()
            if self.table_name == "email_notification_settings":
                return type("Response", (), {"data": self.db.settings})()
            if self.table_name == "system_health":
                return None
            if self.table_name == "malls":
                return type("Response", (), {"data": {"nombre": "Mall Demo"}})()
            if self.table_name == "locales":
                return type("Response", (), {"data": [{"id": "local-1", "nombre": "Local Sin Email", "email": ""}]})()
            return type("Response", (), {"data": []})()

    class FakeSupabase:
        def __init__(self):
            self.settings = [{
                "mall_id": "mall-1",
                "notification_type": "missing_days_audit",
                "enabled": True,
                "weekdays": [0],
                "send_time": "10:00",
                "lookback_days": 1,
                "send_only_with_gaps": True,
                "cc_emails": ["admin@example.com", "audit@example.com"],
            }]
            self.upserts = []

        def table(self, table_name):
            return FakeQuery(self, table_name)

    def fake_send_email(to_email, subject, text_body, html_body, cc_emails, **kwargs):
        sent.append({
            "to": to_email,
            "subject": subject,
            "text": text_body,
            "html": html_body,
            "cc": cc_emails,
            "kwargs": kwargs,
        })
        return {"id": "resend-1"}

    db = FakeSupabase()
    result = run_missing_days_email_scheduler(
        db,
        now=datetime(2026, 5, 11, 14, 1, tzinfo=timezone.utc),
        send_email=fake_send_email,
    )

    assert result["runs"][0]["sent"] == 1
    assert result["runs"][0]["results"][0]["recipient_source"] == "admin_fallback"
    assert sent[0]["to"] == "admin@example.com"
    assert sent[0]["cc"] == ["audit@example.com"]
    assert "Local Sin Email" in sent[0]["subject"]
