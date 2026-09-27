import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main


class _InsertQuery:
    def __init__(self, rows):
        self.rows = rows
        self.payload = None

    def insert(self, payload):
        self.payload = dict(payload)
        self.rows.append(self.payload)
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": "task-1", **(self.payload or {})}])


class _InsertSupabase:
    def __init__(self):
        self.rows = []

    def table(self, name):
        assert name == "copilot_scheduled_tasks"
        return _InsertQuery(self.rows)


def test_schedule_draft_rejects_an_external_recipient(monkeypatch):
    monkeypatch.setattr(main, "_ensure_operator_can_access_mall", lambda *_args: None)

    with pytest.raises(HTTPException) as exc:
        main._build_copilot_schedule_draft(
            {
                "task_type": "missing_sales_consecutive",
                "recipient_email": "other@example.com",
                "scheduled_for": "2030-01-02T12:00:00+00:00",
                "scheduled_for_local": "2030-01-02T08:00:00-04:00",
                "timezone": "America/Santo_Domingo",
                "lookback_days": 10,
                "consecutive_days": 10,
                "instruction": "mañana envíame el reporte",
            },
            "mall-1",
            {"user_id": "user-1", "email": "owner@example.com", "role": "auditor"},
        )

    assert exc.value.status_code == 400
    assert "usuario autenticado" in str(exc.value.detail)


def test_schedule_confirmation_persists_fixed_owner_mall_and_recipient(monkeypatch):
    fake_supabase = _InsertSupabase()
    monkeypatch.setattr(main, "supabase", fake_supabase)
    monkeypatch.setattr(main, "_ensure_operator_can_access_mall", lambda *_args: None)
    main._COPILOT_SCHEDULE_DRAFTS["draft-1"] = {
        "mall_id": "mall-1",
        "mall_name": "Agora Mall",
        "owner_id": "user-1",
        "owner_email": "owner@example.com",
        "recipient_email": "owner@example.com",
        "task_type": "missing_sales_consecutive",
        "scheduled_for": "2030-01-02T12:00:00+00:00",
        "scheduled_for_local": "2030-01-02T08:00:00-04:00",
        "timezone": "America/Santo_Domingo",
        "lookback_days": 10,
        "consecutive_days": 10,
        "instruction": "Mañana envíame los locales con 10 días sin ventas",
        "idempotency_key": "idem-1",
        "expires_at_epoch": 4102444800,
    }

    result = asyncio.run(main.confirm_copilot_schedule(
        main.CopilotScheduleConfirmRequest(mall_id="mall-1", draft_id="draft-1"),
        {"user_id": "user-1", "email": "owner@example.com", "role": "auditor"},
    ))

    assert result["status"] == "scheduled"
    assert result["consecutive_days"] == 10
    assert fake_supabase.rows[0]["mall_id"] == "mall-1"
    assert fake_supabase.rows[0]["created_by"] == "user-1"
    assert fake_supabase.rows[0]["recipient_email"] == "owner@example.com"
    assert "draft-1" not in main._COPILOT_SCHEDULE_DRAFTS


def test_scheduled_tasks_migration_is_service_role_only():
    sql = Path("supabase/migrations/20260927225123_copilot_scheduled_tasks.sql").read_text()

    assert "enable row level security" in sql.lower()
    assert "revoke all on table public.copilot_scheduled_tasks from anon, authenticated" in sql.lower()
    assert "grant all on table public.copilot_scheduled_tasks to service_role" in sql.lower()
