import asyncio
import importlib
import sys
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def _reset_module(module_name: str):
    if module_name in sys.modules:
        del sys.modules[module_name]


def _load_main(monkeypatch, **env):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _reset_module("main")
    _reset_module("worker_importacion")
    import main  # type: ignore
    return importlib.reload(main)


def _load_worker(monkeypatch, **env):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _reset_module("worker_importacion")
    import worker_importacion  # type: ignore
    return importlib.reload(worker_importacion)


def test_api_startup_does_not_start_scheduler_when_flag_disabled(monkeypatch):
    main = _load_main(monkeypatch, ENABLE_API_SCHEDULER="false")
    created = []

    def _fake_create_task(coro):
        created.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", _fake_create_task)
    asyncio.run(main.startup_event())

    assert created == []


def test_api_startup_starts_scheduler_when_flag_enabled(monkeypatch):
    main = _load_main(monkeypatch, ENABLE_API_SCHEDULER="true")
    created = []

    def _fake_create_task(coro):
        created.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", _fake_create_task)
    asyncio.run(main.startup_event())

    assert len(created) == 1
    assert created[0].cr_code.co_name == "scheduler_loop"


def test_worker_run_updates_heartbeat_on_smoke_cycle(monkeypatch):
    worker = _load_worker(monkeypatch)
    heartbeat_updates = []

    async def _fake_cleanup_zombies():
        return None

    async def _fake_upsert_system_health_value(key, value):
        heartbeat_updates.append((key, value))

    class _LocalesQuery:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name):
            assert name == "locales"
            return _LocalesQuery()

    monkeypatch.setattr(worker, "cleanup_zombies", _fake_cleanup_zombies)
    monkeypatch.setattr(worker, "_upsert_system_health_value", _fake_upsert_system_health_value)
    monkeypatch.setattr(worker, "supabase", _FakeSupabase())

    asyncio.run(worker.run_worker_async())

    keys = [k for k, _v in heartbeat_updates]
    assert "CRON_LAST_RUN" in keys
    assert "CRON_LAST_SUCCESS" in keys
    assert "CRON_LAST_ERROR" in keys


def test_worker_specific_schedule_waits_until_configured_minute(monkeypatch):
    worker = _load_worker(monkeypatch)
    now = datetime(2026, 6, 1, 8, 9, tzinfo=ZoneInfo("America/Santo_Domingo"))
    local = {
        "frecuencia_cron": "hora_especifica",
        "hora_especifica": "08:10:00",
        "ultima_ejecucion": None,
    }

    assert worker.should_run_scheduled_local(local, now) is False


def test_worker_specific_schedule_uses_dominican_timezone_for_utc_server(monkeypatch):
    worker = _load_worker(monkeypatch, WORKER_TIMEZONE="America/Santo_Domingo")
    utc_now = datetime(2026, 6, 1, 10, 1, tzinfo=ZoneInfo("UTC"))
    local = {
        "frecuencia_cron": "hora_especifica",
        "hora_especifica": "10:00:00",
        "ultima_ejecucion": None,
    }

    assert worker.should_run_scheduled_local(local, utc_now) is False

    utc_after_local_slot = datetime(2026, 6, 1, 14, 1, tzinfo=ZoneInfo("UTC"))
    assert worker.should_run_scheduled_local(local, utc_after_local_slot) is True


def test_worker_timezone_falls_back_to_dominican_timezone(monkeypatch):
    worker = _load_worker(monkeypatch, WORKER_TIMEZONE="Invalid/Timezone", TZ="UTC")

    assert worker._worker_timezone().key == "America/Santo_Domingo"


def test_worker_specific_schedule_runs_once_after_slot(monkeypatch):
    worker = _load_worker(monkeypatch)
    now = datetime(2026, 6, 1, 8, 30, tzinfo=ZoneInfo("America/Santo_Domingo"))
    local = {
        "frecuencia_cron": "hora_especifica",
        "hora_especifica": "08:10:00",
        "ultima_ejecucion": None,
    }

    assert worker.should_run_scheduled_local(local, now) is True

    local["ultima_ejecucion"] = "2026-06-01T08:12:00-04:00"
    assert worker.should_run_scheduled_local(local, now) is False


def test_worker_hourly_schedule_uses_current_slot(monkeypatch):
    worker = _load_worker(monkeypatch)
    now = datetime(2026, 6, 1, 15, 25, tzinfo=ZoneInfo("America/Santo_Domingo"))

    assert worker.should_run_scheduled_local({
        "frecuencia_cron": "cada_hora",
        "ultima_ejecucion": "2026-06-01T14:59:00-04:00",
    }, now) is True

    assert worker.should_run_scheduled_local({
        "frecuencia_cron": "cada_hora",
        "ultima_ejecucion": "2026-06-01T15:01:00-04:00",
    }, now) is False


def test_worker_two_hour_schedule_uses_even_hour_slot(monkeypatch):
    worker = _load_worker(monkeypatch)
    now = datetime(2026, 6, 1, 15, 25, tzinfo=ZoneInfo("America/Santo_Domingo"))

    assert worker.should_run_scheduled_local({
        "frecuencia_cron": "cada_2_horas",
        "ultima_ejecucion": "2026-06-01T13:59:00-04:00",
    }, now) is True

    assert worker.should_run_scheduled_local({
        "frecuencia_cron": "cada_2_horas",
        "ultima_ejecucion": "2026-06-01T14:01:00-04:00",
    }, now) is False
