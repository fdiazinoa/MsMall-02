import asyncio
import importlib
import sys
from datetime import datetime, timezone
from types import SimpleNamespace


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


def test_schedule_due_at_respects_specific_minute_and_last_attempt(monkeypatch):
    worker = _load_worker(monkeypatch)
    now = datetime(2026, 3, 7, 8, 35, tzinfo=timezone.utc)
    local = {"frecuencia_cron": "hora_especifica", "hora_especifica": "08:30"}

    due_at = worker._schedule_due_at(local, now)

    assert due_at == datetime(2026, 3, 7, 8, 30, tzinfo=timezone.utc)

    local["ultima_ejecucion"] = "2026-03-07T08:31:00+00:00"
    assert worker._schedule_due_at(local, now) is None


def test_run_worker_async_only_enqueues_due_locals(monkeypatch):
    worker = _load_worker(monkeypatch)
    queued = []
    now = datetime(2026, 3, 7, 8, 35, tzinfo=timezone.utc)

    async def _fake_cleanup_zombies():
        return None

    async def _fake_update_heartbeat():
        return None

    async def _fake_update_cron_success():
        return None

    async def _fake_clear_cron_error():
        return None

    async def _fake_process_local_safe(local, _global_sem, _host_sem, due_at=None):
        queued.append((local["id"], due_at.isoformat() if due_at else None))

    class _LocalesQuery:
        def __init__(self, data):
            self._data = data

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=self._data)

    class _FakeSupabase:
        def __init__(self, data):
            self._data = data

        def table(self, name):
            assert name == "locales"
            return _LocalesQuery(self._data)

    monkeypatch.setattr(worker, "_now_local", lambda: now)
    monkeypatch.setattr(worker, "_stable_offset_minutes", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(worker, "cleanup_zombies", _fake_cleanup_zombies)
    monkeypatch.setattr(worker, "update_heartbeat", _fake_update_heartbeat)
    monkeypatch.setattr(worker, "update_cron_success", _fake_update_cron_success)
    monkeypatch.setattr(worker, "clear_cron_error", _fake_clear_cron_error)
    monkeypatch.setattr(worker, "process_local_safe", _fake_process_local_safe)
    monkeypatch.setattr(
        worker,
        "supabase",
        _FakeSupabase([
            {
                "id": "hourly-1",
                "nombre": "Hourly",
                "mall_id": "mall-1",
                "tipo_ejecucion": "AUTOMATICO",
                "processing_status": "IDLE",
                "frecuencia_cron": "cada_hora",
            },
            {
                "id": "specific-1",
                "nombre": "Specific",
                "mall_id": "mall-1",
                "tipo_ejecucion": "AUTOMATICO",
                "processing_status": "IDLE",
                "frecuencia_cron": "hora_especifica",
                "hora_especifica": "08:30",
            },
            {
                "id": "specific-skip",
                "nombre": "SpecificSkip",
                "mall_id": "mall-1",
                "tipo_ejecucion": "AUTOMATICO",
                "processing_status": "IDLE",
                "frecuencia_cron": "hora_especifica",
                "hora_especifica": "08:30",
                "ultima_ejecucion": "2026-03-07T08:31:00+00:00",
            },
            {
                "id": "future-1",
                "nombre": "Future",
                "mall_id": "mall-1",
                "tipo_ejecucion": "AUTOMATICO",
                "processing_status": "IDLE",
                "frecuencia_cron": "hora_especifica",
                "hora_especifica": "09:00",
            },
        ]),
    )

    asyncio.run(worker.run_worker_async())

    assert [local_id for local_id, _due_at in queued] == ["hourly-1", "specific-1"]
