import asyncio
import importlib
import sys
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
