from datetime import datetime, timezone
from types import SimpleNamespace

from services import copilot_scheduled_tasks_service as scheduled


class _ReadQuery:
    def __init__(self, rows):
        self.rows = list(rows)
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

    def execute(self):
        rows = self.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return SimpleNamespace(data=(rows[0] if rows else None) if self.single else rows)


class _ReportSupabase:
    def __init__(self):
        self.tables = {
            "malls": [{"id": "mall-1", "nombre": "Agora Mall"}],
            "locales": [
                {"id": "local-1", "nombre": "Sin Ventas", "codigo_interno": "L001", "activo": True, "mall_id": "mall-1"},
                {"id": "local-2", "nombre": "Con Ventas", "codigo_interno": "L002", "activo": True, "mall_id": "mall-1"},
                {"id": "local-other", "nombre": "Otro Mall", "codigo_interno": "X001", "activo": True, "mall_id": "mall-2"},
            ],
            "system_health": [],
        }

    def table(self, name):
        return _ReadQuery(self.tables.get(name, []))


def test_parser_understands_variable_days_and_local_time():
    parsed = scheduled.parse_copilot_schedule_request(
        "Mañana a las 10:30 a. m. envíame los locales con 10 días consecutivos sin registrar ventas",
        user_email="audit@example.com",
        now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
    )

    assert parsed is not None
    assert parsed["consecutive_days"] == 10
    assert parsed["lookback_days"] == 10
    assert parsed["recipient_email"] == "audit@example.com"
    assert parsed["scheduled_for_local"].startswith("2026-09-28T10:30:00")
    assert parsed["timezone"] == "America/Santo_Domingo"


def test_parser_understands_days_written_as_words_and_defaults_to_eight():
    parsed = scheduled.parse_copilot_schedule_request(
        "Mañana mándame por correo las tiendas con quince días sin ventas",
        user_email="audit@example.com",
        now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
    )

    assert parsed is not None
    assert parsed["consecutive_days"] == 15
    assert parsed["scheduled_for_local"].startswith("2026-09-28T08:00:00")


def test_parser_understands_a_natural_mandate_without_fixed_word_order():
    parsed = scheduled.parse_copilot_schedule_request(
        "Programa para pasado mañana un correo con las tiendas que no han registrado ventas por 20 días",
        user_email="audit@example.com",
        now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
    )

    assert parsed is not None
    assert parsed["consecutive_days"] == 20
    assert parsed["scheduled_for_local"].startswith("2026-09-29T08:00:00")


def test_parser_understands_next_weekday_and_variable_days():
    parsed = scheduled.parse_copilot_schedule_request(
        "El próximo lunes a las 9 am envíame los locales que llevan 12 días sin ventas",
        user_email="audit@example.com",
        now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
    )

    assert parsed is not None
    assert parsed["consecutive_days"] == 12
    assert parsed["scheduled_for_local"].startswith("2026-09-28T09:00:00")


def test_parser_requests_a_date_for_an_incomplete_programming_mandate():
    try:
        scheduled.parse_copilot_schedule_request(
            "Programa un correo con los locales que llevan 8 días sin ventas",
            user_email="audit@example.com",
            now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
        )
    except ValueError as exc:
        assert "Indica cuándo" in str(exc)
    else:
        raise AssertionError("Expected an explicit clarification for the missing date")


def test_parser_leaves_immediate_email_request_to_existing_flow():
    assert scheduled.parse_copilot_schedule_request(
        "Envíame por correo los locales con 7 días sin registrar ventas",
        user_email="audit@example.com",
        now=datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc),
    ) is None


def test_report_is_scoped_to_mall_and_filters_exact_consecutive_window(monkeypatch):
    monkeypatch.setattr(
        scheduled,
        "load_actual_sales_dates_by_local",
        lambda _client, *, local_ids, **_kwargs: {
            "local-1": set(),
            "local-2": {"2026-09-26"},
        },
    )
    monkeypatch.setattr(
        scheduled,
        "load_resend_sender_config",
        lambda *_args: {"from_email": "notificaciones@mercasend.net", "from_name": "MSMALL"},
    )
    sent = []

    result = scheduled.send_consecutive_missing_sales_report(
        _ReportSupabase(),
        {
            "mall_id": "mall-1",
            "recipient_email": "audit@example.com",
            "timezone": "America/Santo_Domingo",
            "consecutive_days": 7,
        },
        send_email=lambda *args, **kwargs: sent.append((args, kwargs)) or {"id": "resend-1"},
        now=datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc),
    )

    assert result["locals_count"] == 1
    assert result["local_ids"] == ["local-1"]
    assert sent[0][0][0] == "audit@example.com"
    assert "Sin Ventas" in sent[0][0][3]
    assert "Con Ventas" not in sent[0][0][3]
    assert "Otro Mall" not in sent[0][0][3]


def test_report_sends_zero_findings_confirmation(monkeypatch):
    monkeypatch.setattr(
        scheduled,
        "load_actual_sales_dates_by_local",
        lambda _client, *, local_ids, fecha_inicio, fecha_fin: {
            local_id: scheduled.expected_sales_dates(fecha_inicio, fecha_fin)
            for local_id in local_ids
        },
    )
    monkeypatch.setattr(
        scheduled,
        "load_resend_sender_config",
        lambda *_args: {"from_email": "notificaciones@mercasend.net", "from_name": "MSMALL"},
    )
    sent = []

    result = scheduled.send_consecutive_missing_sales_report(
        _ReportSupabase(),
        {
            "mall_id": "mall-1",
            "recipient_email": "audit@example.com",
            "timezone": "America/Santo_Domingo",
            "consecutive_days": 10,
        },
        send_email=lambda *args, **kwargs: sent.append((args, kwargs)) or {"id": "resend-zero"},
        now=datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc),
    )

    assert result["locals_count"] == 0
    assert len(sent) == 1
    assert "No se encontraron locales" in sent[0][0][2]
