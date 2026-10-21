"""Shared, fail-closed quota reservations and renewable download leases."""

import logging
import threading
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class BackupPolicy(BaseModel):
    user_concurrency: int = Field(default=1, ge=1, le=10)
    mall_concurrency: int = Field(default=2, ge=1, le=50)
    min_interval_seconds: int = Field(default=60, ge=1, le=86400)
    user_daily_downloads: int = Field(default=10, ge=1, le=10000)
    max_file_mb: int = Field(default=50, ge=1, le=1000)
    user_daily_mb: int = Field(default=200, ge=1, le=100000)
    mall_daily_mb: int = Field(default=1000, ge=1, le=1000000)
    max_range_days: int = Field(default=90, ge=1, le=3660)


MESSAGES = {
    "frequency": "Espera antes de solicitar otro CSV.",
    "user_concurrency": "Ya tienes una descarga en curso.",
    "mall_concurrency": "El Mall alcanzó su límite de descargas simultáneas.",
    "daily_downloads": "Agotaste tus solicitudes de CSV disponibles para hoy.",
    "user_daily_bytes": "Agotaste tu cuota diaria de descarga.",
    "mall_daily_bytes": "El Mall agotó su cuota diaria de descarga.",
    "date_range": "El período supera el máximo de días permitido. Reduce el rango.",
    "lease_expired": "No se pudo mantener la reserva del backup. Inténtalo nuevamente.",
}


class BackupQuotaError(Exception):
    def __init__(self, reason: str = "unavailable", retry_after: int = 0):
        self.reason, self.retry_after = reason, retry_after
        self.status_code = 400 if reason == "date_range" else 503 if reason in {"unavailable", "lease_expired"} else 429
        message = MESSAGES.get(reason, "No se pudieron verificar las cuotas de backup. Reintenta en unos segundos.")
        if retry_after:
            message += f" Puedes reintentar en {retry_after} segundos."
        super().__init__(message)


class ImportBackupQuotaService:
    def __init__(self, db: Any, user_id: str, mall_id: str):
        self.db, self.user_id, self.mall_id = db, user_id, mall_id

    def call(self, action: str, **params) -> dict:
        try:
            result = self.db.rpc("import_backup_quota_control", {
                "p_action": action, "p_user_id": self.user_id, "p_mall_id": self.mall_id, **params,
            }).execute().data
            if not isinstance(result, dict) or not isinstance(result.get("quota"), dict):
                raise ValueError("Invalid quota response")
        except Exception as exc:
            raise BackupQuotaError(retry_after=20) from exc
        if not result.get("allowed"):
            logging.getLogger("msmall-api").info("Backup bloqueado usuario=%s mall=%s motivo=%s",
                                                  self.user_id, self.mall_id, result.get("reason"))
            raise BackupQuotaError(result.get("reason") or "unavailable", int(result.get("retry_after") or 0))
        return result

    def status(self) -> dict:
        return self.call("status")["quota"]

    def configure(self, policy: BackupPolicy) -> dict:
        return self.call("configure", p_policy=policy.model_dump())["quota"]

    def reserve(self, days: int):
        request_id = str(uuid4())
        result = self.call("reserve", p_request_id=request_id, p_days=days)
        return BackupLease(self, request_id, int(result["max_bytes"]))


class BackupLease:
    def __init__(self, service: ImportBackupQuotaService, request_id: str, max_bytes: int):
        self.service, self.request_id, self.max_bytes = service, request_id, max_bytes
        self.produced_bytes = 0
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._closed = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._heartbeat, daemon=True, name="backup-quota-lease")

    def start(self):
        self._thread.start()

    def _heartbeat(self):
        while not self._stop.wait(20):
            try:
                self.service.call("renew", p_request_id=self.request_id)
            except BackupQuotaError:
                self._lost.set()
                return

    def check(self):
        if self._lost.is_set():
            raise BackupQuotaError("lease_expired", 20)

    def progress(self, size: int):
        self.produced_bytes = size
        self.check()

    def prepare(self, size: int):
        self.check()
        self.service.call("prepare", p_request_id=self.request_id, p_bytes=size)

    def close(self, failed: bool = False):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1)
        try:
            self.service.call("fail" if failed else "finish", p_request_id=self.request_id, p_bytes=self.produced_bytes)
        except BackupQuotaError:
            # The DB will expire the lease and charge any unaccounted budget.
            logging.getLogger("msmall-api").warning("No se pudo cerrar la reserva de backup %s", self.request_id)
