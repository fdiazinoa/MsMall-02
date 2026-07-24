from datetime import datetime, timezone

from services.missing_days_email_service import (
    build_missing_days_email_html,
    missing_days_email_period,
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
