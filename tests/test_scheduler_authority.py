import asyncio
import importlib
import sys
from datetime import datetime, timezone
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
    main = _load_main(monkeypatch, ENABLE_API_SCHEDULER="false", ENABLE_EMAIL_SCHEDULER="false")
    created = []

    def _fake_create_task(coro):
        created.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", _fake_create_task)
    asyncio.run(main.startup_event())

    assert created == []


def test_api_startup_starts_scheduler_when_flag_enabled(monkeypatch):
    main = _load_main(monkeypatch, ENABLE_API_SCHEDULER="true", ENABLE_EMAIL_SCHEDULER="false")
    created = []

    def _fake_create_task(coro):
        created.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", _fake_create_task)
    asyncio.run(main.startup_event())

    assert len(created) == 1
    assert created[0].cr_code.co_name == "scheduler_loop"


def test_api_email_scheduler_calls_missing_days_scheduler_with_logger_keyword(monkeypatch):
    main = _load_main(monkeypatch, EMAIL_SCHEDULER_POLL_SECONDS="30")
    calls = []
    sleeps = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) > 1:
            raise asyncio.CancelledError()

    async def _fake_to_thread(fn, *args, **kwargs):
        calls.append((fn, args, kwargs))
        return {"executed": False, "reason": "no_due_schedules", "runs": []}

    sentinel_supabase = object()
    monkeypatch.setattr(main, "supabase", sentinel_supabase)
    monkeypatch.setattr(main.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(main.asyncio, "to_thread", _fake_to_thread)

    try:
        asyncio.run(main.email_scheduler_loop())
    except asyncio.CancelledError:
        pass

    assert calls
    fn, args, kwargs = calls[0]
    assert fn is main.run_missing_days_email_scheduler
    assert args == (sentinel_supabase,)
    assert kwargs == {"logger": main.logger}


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


def test_schedule_due_at_defaults_missing_specific_time(monkeypatch):
    worker = _load_worker(monkeypatch)
    now = datetime(2026, 3, 7, 8, 35, tzinfo=timezone.utc)
    local = {"frecuencia_cron": "hora_especifica", "hora_especifica": None}

    assert worker._schedule_due_at(local, now) == datetime(2026, 3, 7, 8, 0, tzinfo=timezone.utc)


def test_worker_specific_schedule_uses_dominican_timezone_for_utc_server(monkeypatch):
    worker = _load_worker(monkeypatch, WORKER_TIMEZONE="America/Santo_Domingo")
    local = {
        "frecuencia_cron": "hora_especifica",
        "hora_especifica": "10:00:00",
        "ultima_ejecucion": None,
    }

    utc_now = datetime(2026, 6, 1, 10, 1, tzinfo=ZoneInfo("UTC"))
    local_now = utc_now.astimezone(worker._worker_timezone())
    assert worker._schedule_due_at(local, local_now) is None

    utc_after_local_slot = datetime(2026, 6, 1, 14, 1, tzinfo=ZoneInfo("UTC"))
    local_after_slot = utc_after_local_slot.astimezone(worker._worker_timezone())
    assert worker._schedule_due_at(local, local_after_slot) == datetime(
        2026, 6, 1, 10, 0, tzinfo=ZoneInfo("America/Santo_Domingo")
    )


def test_worker_ignores_generic_tz_env_for_specific_schedule(monkeypatch):
    worker = _load_worker(monkeypatch, TZ="UTC")
    local = {
        "frecuencia_cron": "hora_especifica",
        "hora_especifica": "13:00:00",
        "ultima_ejecucion": None,
    }

    assert worker._worker_timezone().key == "America/Santo_Domingo"
    early_local_now = datetime(2026, 6, 1, 13, 3, tzinfo=ZoneInfo("UTC")).astimezone(worker._worker_timezone())
    due_local_now = datetime(2026, 6, 1, 17, 3, tzinfo=ZoneInfo("UTC")).astimezone(worker._worker_timezone())

    assert worker._schedule_due_at(local, early_local_now) is None
    assert worker._schedule_due_at(local, due_local_now) == datetime(
        2026, 6, 1, 13, 0, tzinfo=ZoneInfo("America/Santo_Domingo")
    )


def test_worker_honors_explicit_worker_timezone(monkeypatch):
    worker = _load_worker(monkeypatch, WORKER_TIMEZONE="UTC", TZ="America/Santo_Domingo")

    assert worker._worker_timezone().key == "UTC"


def test_worker_timezone_falls_back_to_dominican_timezone(monkeypatch):
    worker = _load_worker(monkeypatch, WORKER_TIMEZONE="Invalid/Timezone", TZ="UTC")

    assert worker._worker_timezone().key == "America/Santo_Domingo"


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


def test_worker_now_local_defaults_to_santo_domingo(monkeypatch):
    worker = _load_worker(monkeypatch)

    assert worker._now_local().tzinfo == ZoneInfo("America/Santo_Domingo")


def test_mark_local_status_can_release_without_closing_schedule_slot(monkeypatch):
    worker = _load_worker(monkeypatch)
    updates = []

    class _UpdateQuery:
        def update(self, payload):
            updates.append(payload)
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name):
            assert name == "locales"
            return _UpdateQuery()

    monkeypatch.setattr(worker, "supabase", _FakeSupabase())

    asyncio.run(worker.mark_local_status("local-1", "IDLE", update_last_execution=False))

    assert updates == [{"processing_status": "IDLE"}]


def test_worker_empty_ftp_slot_does_not_update_last_execution(monkeypatch):
    worker = _load_worker(monkeypatch)
    status_calls = []
    failure_resets = []

    async def _fake_mark_local_status(local_id, status, *, update_last_execution=True):
        status_calls.append((local_id, status, update_last_execution))

    def _fake_process_local_files(_local):
        return {
            "ok": True,
            "message": "Archivo nuevo no encontrado",
            "total_pending": 0,
            "processed_files": 0,
            "failed_files": 0,
            "details": [],
        }

    class _UpdateQuery:
        def update(self, payload):
            failure_resets.append(payload)
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name):
            assert name == "locales"
            return _UpdateQuery()

    monkeypatch.setattr(worker, "mark_local_status", _fake_mark_local_status)
    monkeypatch.setattr(worker, "process_local_files", _fake_process_local_files)
    monkeypatch.setattr(worker, "supabase", _FakeSupabase())

    asyncio.run(worker.process_local_safe(
        {
            "id": "local-1",
            "nombre": "Local Demo",
            "mall_id": "mall-1",
            "processing_status": "IDLE",
            "consecutive_failures": 0,
        },
        asyncio.Semaphore(1),
        asyncio.Semaphore(1),
    ))

    assert status_calls[0] == ("local-1", "BUSY", True)
    assert status_calls[-1] == ("local-1", "IDLE", False)
    assert failure_resets == [{"consecutive_failures": 0}]


def test_worker_failed_file_result_does_not_create_duplicate_system_log(monkeypatch):
    worker = _load_worker(monkeypatch)
    status_calls = []
    load_logs = []
    updates = []

    async def _fake_mark_local_status(local_id, status, *, update_last_execution=True):
        status_calls.append((local_id, status, update_last_execution))

    def _fake_process_local_files(_local):
        return {
            "ok": False,
            "message": "Lote completado: 0/1 archivos procesados.",
            "total_pending": 1,
            "processed_files": 0,
            "failed_files": 1,
            "details": [{"linea": 2, "error": "Datos incompletos"}],
        }

    class _UpdateQuery:
        def update(self, payload):
            updates.append(payload)
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name):
            assert name == "locales"
            return _UpdateQuery()

    monkeypatch.setattr(worker, "mark_local_status", _fake_mark_local_status)
    monkeypatch.setattr(worker, "process_local_files", _fake_process_local_files)
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: load_logs.append((args, kwargs)))
    monkeypatch.setattr(worker, "supabase", _FakeSupabase())

    asyncio.run(worker.process_local_safe(
        {
            "id": "local-1",
            "nombre": "Local Demo",
            "mall_id": "mall-1",
            "processing_status": "IDLE",
            "consecutive_failures": 0,
            "sftp_protocol": "SFTP",
        },
        asyncio.Semaphore(1),
        asyncio.Semaphore(1),
    ))

    assert load_logs == []
    assert updates == [{"consecutive_failures": 1}]
    assert status_calls[-1] == ("local-1", "IDLE", True)


def test_studio_g_api_failure_creates_load_log(monkeypatch):
    worker = _load_worker(monkeypatch)
    load_logs = []

    def _fake_fetch_studio_g_sales(_config):
        raise OSError(113, "No route to host")

    monkeypatch.setattr(worker, "fetch_studio_g_sales", _fake_fetch_studio_g_sales)
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: load_logs.append((args, kwargs)))

    result = worker.process_studio_g_api({
        "id": "studio-g-local",
        "nombre": "Studio G",
        "mall_id": "mall-agora",
        "sftp_protocol": "API",
    })

    assert result["ok"] is False
    assert "Fallo API Studio G" in result["message"]
    assert len(load_logs) == 1
    args, kwargs = load_logs[0]
    assert args[:4] == ("Studio G", "Studio G API", "error", result["message"])
    assert kwargs["canal"] == "API"
    assert kwargs["records_processed"] == 0
    assert kwargs["error_count"] == 1
    assert kwargs["metadata"]["source"] == "worker_studio_g_api"
    assert "No route to host" in kwargs["metadata"]["exception"]
