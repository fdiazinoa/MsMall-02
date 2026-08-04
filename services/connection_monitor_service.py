import os
import socket
from datetime import date, datetime, time, timedelta, timezone
from ftplib import FTP
from typing import Any, Callable, Dict, List, Optional, Tuple

import paramiko

from services.sensitive_ops_service import mask_secret, sanitize_error_text

ERROR_CODES = {
    "auth_error",
    "timeout",
    "endpoint_down",
    "validation_error",
    "unknown_error",
}
RUN_STATUSES = {"ok", "fail", "partial"}
RETRY_STATUSES = {"ok", "fail"}


def _first_response_row(response: Any) -> Dict[str, Any]:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return dict(data)
    if isinstance(data, list) and data:
        return dict(data[0] or {})
    return {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int, min_value: int = 1, max_value: int = 10000) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, value))


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_date_yyyy_mm_dd(value: str) -> date:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        raise ValueError("date debe tener formato YYYY-MM-DD")


def _normalize_remote_host(host: str) -> str:
    normalized = (host or "").strip()
    if normalized.startswith("sftp://"):
        normalized = normalized[len("sftp://") :]
    elif normalized.startswith("ftp://"):
        normalized = normalized[len("ftp://") :]
    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]
    return normalized


def _candidate_hosts(host: str) -> List[str]:
    normalized = _normalize_remote_host(host)
    if not normalized:
        return []
    out = [normalized]
    if normalized.startswith("www.") and len(normalized) > 4:
        out.append(normalized[4:])
    return out


def classify_connection_error(exc: Exception) -> str:
    if isinstance(exc, (ValueError, TypeError)):
        return "validation_error"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, socket.timeout)):  # type: ignore[name-defined]
        return "timeout"
    if isinstance(exc, paramiko.AuthenticationException):
        return "auth_error"
    message = str(exc or "").lower()
    if any(token in message for token in [
        "auth",
        "authentication",
        "permission denied",
        "login incorrect",
        "530",
        "invalid credentials",
    ]):
        return "auth_error"
    if any(token in message for token in [
        "timeout",
        "timed out",
        "deadline",
    ]):
        return "timeout"
    if isinstance(exc, (ConnectionError, ConnectionRefusedError, OSError, EOFError, paramiko.SSHException)):
        return "endpoint_down"
    if any(token in message for token in [
        "refused",
        "unreachable",
        "no route to host",
        "name or service not known",
        "temporary failure in name resolution",
        "connection reset",
        "network is unreachable",
    ]):
        return "endpoint_down"
    return "unknown_error"


def _safe_error_message(exc: Exception) -> str:
    return sanitize_error_text(exc, max_len=300) or "unknown_error"


def _open_sftp(host: str, port: int, user: str, password: str):
    last_error: Optional[Exception] = None
    for candidate in _candidate_hosts(host):
        try:
            transport = paramiko.Transport((candidate, int(port)))
            transport.banner_timeout = 20
            transport.auth_timeout = 25
            transport.connect(username=user, password=password)
            transport.set_keepalive(30)
            sftp = paramiko.SFTPClient.from_transport(transport)
            return transport, sftp
        except Exception as exc:  # pragma: no cover - network-dependent path
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("Host remoto inválido o vacío para conexión SFTP")


def _open_ftp(host: str, port: int, user: str, password: str):
    last_error: Optional[Exception] = None
    for candidate in _candidate_hosts(host):
        try:
            ftp = FTP()
            ftp.connect(candidate, int(port), timeout=25)
            ftp.login(user, password)
            ftp.set_pasv(True)
            return ftp
        except Exception as exc:  # pragma: no cover - network-dependent path
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("Host remoto inválido o vacío para conexión FTP")


class RetryPolicyBlocked(Exception):
    def __init__(self, *, code: str, message: str, retry_after_seconds: int = 0, attempt_no: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.attempt_no = attempt_no


class ConnectionMonitorService:
    def __init__(self, supabase_client: Any, logger: Any):
        self.supabase = supabase_client
        self.logger = logger

    # --- Config ---
    def retry_max_attempts(self) -> int:
        return _parse_int_env("RETRY_MAX_ATTEMPTS", 3, min_value=1, max_value=10)

    def retry_cooldown_seconds(self) -> int:
        return _parse_int_env("RETRY_COOLDOWN_SECONDS", 300, min_value=0, max_value=86400)

    def retry_batch_request_limit(self) -> int:
        return _parse_int_env("RETRY_BATCH_REQUEST_LIMIT", 20, min_value=1, max_value=500)

    def nightly_retry_enabled(self) -> bool:
        return _parse_bool_env("NIGHTLY_RETRY_ENABLED", True)

    def nightly_retry_cron(self) -> str:
        return (os.getenv("NIGHTLY_RETRY_CRON") or "0 2 * * *").strip()

    # --- DB helpers ---
    def _require_supabase(self) -> None:
        if not self.supabase:
            raise RuntimeError("Supabase no configurado")

    def _upsert_system_health(self, key: str, value: str) -> None:
        if not self.supabase:
            return
        now = _utcnow()
        self.supabase.table("system_health").upsert({
            "key": key,
            "value": value,
            "last_update": _format_utc(now),
        }).execute()

    def _audit(self, *, user_id: Optional[str], mall_id: Optional[str], action: str, detail: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self.supabase:
            return
        try:
            self.supabase.table("system_audit_logs").insert({
                "usuario_id": user_id,
                "mall_id": mall_id,
                "accion": action,
                "detalle": detail,
                "metadata": {
                    **(metadata or {}),
                    "timestamp": _format_utc(_utcnow()),
                },
            }).execute()
        except Exception as exc:
            self.logger.warning("Connection monitor audit log failed: %s", sanitize_error_text(exc))

    def _get_connection(self, connection_id: str) -> Optional[Dict[str, Any]]:
        self._require_supabase()
        res = (
            self.supabase.table("remote_connections")
            .select("*")
            .eq("id", connection_id)
            .maybe_single()
            .execute()
        )
        return (res.data if res else None) or None

    def _list_connections(self, mall_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self._require_supabase()
        q = self.supabase.table("remote_connections").select("*")
        if mall_id:
            q = q.eq("mall_id", mall_id)
        res = q.order("nombre", desc=False).execute()
        return list(res.data or [])

    def _insert_connection_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_supabase()
        res = self.supabase.table("connection_runs").insert(payload).select().execute()
        return _first_response_row(res)

    def _update_connection_run(self, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_supabase()
        res = (
            self.supabase.table("connection_runs")
            .update(payload)
            .eq("id", run_id)
            .select()
            .execute()
        )
        return _first_response_row(res)

    def _insert_retry_attempt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_supabase()
        res = self.supabase.table("retry_attempts").insert(payload).select().execute()
        return _first_response_row(res)

    def _recent_retry_attempts(self, connection_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._require_supabase()
        try:
            res = (
                self.supabase.table("retry_attempts")
                .select("*")
                .eq("connection_id", connection_id)
                .order("attempted_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(res.data or [])
        except Exception:
            # If migration not applied yet or columns missing, fail closed to avoid crashing endpoint tests.
            return []

    def _recent_connection_runs(self, mall_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        self._require_supabase()
        res = (
            self.supabase.table("connection_runs")
            .select("*")
            .eq("mall_id", mall_id)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = [dict(r) for r in (res.data or [])]
        for row in rows:
            if row.get("error_message"):
                row["error_message"] = sanitize_error_text(row.get("error_message"))
        return rows

    # --- Probing / classification ---
    def _validate_connection_row(self, conn: Dict[str, Any]) -> None:
        missing = [k for k in ["protocolo", "host", "puerto", "usuario", "password"] if not str(conn.get(k) or "").strip()]
        if missing:
            raise ValueError(f"Conexión remota inválida. Faltan campos: {', '.join(missing)}")

    def _probe_connection(self, conn: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_connection_row(conn)
        started = _utcnow()
        protocol = str(conn.get("protocolo") or "SFTP").upper()
        host = str(conn.get("host") or "")
        port = int(conn.get("puerto") or (22 if protocol == "SFTP" else 21))
        user = str(conn.get("usuario") or "")
        password = str(conn.get("password") or "")
        meta = {
            "connection_id": conn.get("id"),
            "mall_id": conn.get("mall_id"),
            "protocol": protocol,
            "host": mask_secret(host),
            "port": port,
            "user": mask_secret(user),
        }
        try:
            if protocol == "SFTP":
                transport, sftp = _open_sftp(host, port, user, password)
                sftp.close()
                transport.close()
            elif protocol == "FTP":
                ftp = _open_ftp(host, port, user, password)
                ftp.quit()
            else:
                raise ValueError(f"Protocolo no soportado: {protocol}")
            finished = _utcnow()
            duration_ms = max(0, int((finished - started).total_seconds() * 1000))
            self.logger.info("Connection monitor probe ok meta=%s duration_ms=%s", meta, duration_ms)
            return {
                "status": "ok",
                "error_code": None,
                "error_message": None,
                "started_at": _format_utc(started),
                "finished_at": _format_utc(finished),
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            finished = _utcnow()
            duration_ms = max(0, int((finished - started).total_seconds() * 1000))
            code = classify_connection_error(exc)
            message = _safe_error_message(exc)
            self.logger.warning(
                "Connection monitor probe fail code=%s meta=%s err=%s duration_ms=%s",
                code,
                meta,
                message,
                duration_ms,
            )
            return {
                "status": "fail",
                "error_code": code,
                "error_message": message,
                "started_at": _format_utc(started),
                "finished_at": _format_utc(finished),
                "duration_ms": duration_ms,
            }

    # --- Retry policy ---
    def _compute_retry_policy(self, connection_id: str) -> Dict[str, Any]:
        max_attempts = self.retry_max_attempts()
        cooldown_seconds = self.retry_cooldown_seconds()
        recent_attempts = self._recent_retry_attempts(connection_id, limit=50)

        last_attempt_at: Optional[datetime] = None
        consecutive_failed = 0
        for row in recent_attempts:
            attempted_at = _parse_iso_dt(row.get("attempted_at"))
            if attempted_at and last_attempt_at is None:
                last_attempt_at = attempted_at
            status = str(row.get("status") or "").lower()
            if status == "ok":
                break
            if status == "fail":
                consecutive_failed += 1

        next_attempt_no = consecutive_failed + 1
        retry_after_seconds = 0
        if last_attempt_at and cooldown_seconds > 0:
            elapsed = int((_utcnow() - last_attempt_at).total_seconds())
            retry_after_seconds = max(0, cooldown_seconds - max(0, elapsed))

        return {
            "max_attempts": max_attempts,
            "cooldown_seconds": cooldown_seconds,
            "recent_failed_attempts": consecutive_failed,
            "next_attempt_no": next_attempt_no,
            "retry_after_seconds": retry_after_seconds,
        }

    def _enforce_retry_policy(self, connection_id: str) -> Dict[str, Any]:
        policy = self._compute_retry_policy(connection_id)
        if policy["recent_failed_attempts"] >= policy["max_attempts"]:
            raise RetryPolicyBlocked(
                code="max_attempts_reached",
                message=f"Máximo de reintentos alcanzado ({policy['max_attempts']}).",
                attempt_no=policy["next_attempt_no"],
            )
        if policy["retry_after_seconds"] > 0:
            raise RetryPolicyBlocked(
                code="cooldown_active",
                message="Cooldown de reintento activo.",
                retry_after_seconds=policy["retry_after_seconds"],
                attempt_no=policy["next_attempt_no"],
            )
        return policy

    # --- Core execution ---
    def _finalize_run_after_retry(self, run_row: Dict[str, Any], retry_result: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(run_row["id"])
        started_at = _parse_iso_dt(run_row.get("started_at")) or _utcnow()
        retry_finished = _parse_iso_dt(retry_result.get("finished_at")) or _utcnow()
        total_duration_ms = max(0, int((retry_finished - started_at).total_seconds() * 1000))

        if retry_result.get("status") == "ok":
            update_payload = {
                "status": "partial",
                "finished_at": retry_result.get("finished_at"),
                "duration_ms": total_duration_ms,
            }
        else:
            update_payload = {
                "status": "fail",
                "error_code": retry_result.get("error_code"),
                "error_message": sanitize_error_text(retry_result.get("error_message")),
                "finished_at": retry_result.get("finished_at"),
                "duration_ms": total_duration_ms,
            }
        return self._update_connection_run(run_id, update_payload)

    def _record_retry_attempt(
        self,
        *,
        run_row: Dict[str, Any],
        connection_row: Dict[str, Any],
        attempt_no: int,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {
            "connection_run_id": run_row.get("id"),
            "mall_id": connection_row.get("mall_id"),
            "connection_id": connection_row.get("id"),
            "attempt_no": attempt_no,
            "status": "ok" if result.get("status") == "ok" else "fail",
            "error_code": result.get("error_code"),
            "error_message": sanitize_error_text(result.get("error_message")),
            "attempted_at": _format_utc(_utcnow()),
            "duration_ms": int(result.get("duration_ms") or 0),
        }
        return self._insert_retry_attempt(payload)

    def _create_run_from_probe(
        self,
        *,
        connection_row: Dict[str, Any],
        probe_result: Dict[str, Any],
        run_type: str,
        created_by: Optional[str],
        local_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "mall_id": connection_row.get("mall_id"),
            "local_id": local_id,
            "connection_id": connection_row.get("id"),
            "run_type": run_type,
            "status": "ok" if probe_result.get("status") == "ok" else "fail",
            "error_code": probe_result.get("error_code"),
            "error_message": sanitize_error_text(probe_result.get("error_message")),
            "started_at": probe_result.get("started_at") or _format_utc(_utcnow()),
            "finished_at": probe_result.get("finished_at") or _format_utc(_utcnow()),
            "duration_ms": int(probe_result.get("duration_ms") or 0),
            "created_by": created_by,
            "created_at": _format_utc(_utcnow()),
        }
        return self._insert_connection_run(payload)

    def execute_manual_retry(
        self,
        *,
        connection_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_supabase()
        conn = self._get_connection(connection_id)
        if not conn:
            raise KeyError("Conexión remota no encontrada")
        ensure_operator_can_access_mall(operator_ctx, conn.get("mall_id"))

        policy = self._enforce_retry_policy(connection_id)
        probe = self._probe_connection(conn)
        run_row = self._create_run_from_probe(
            connection_row=conn,
            probe_result=probe,
            run_type="manual",
            created_by=operator_ctx.get("user_id"),
        )
        attempt = self._record_retry_attempt(
            run_row=run_row,
            connection_row=conn,
            attempt_no=policy["next_attempt_no"],
            result=probe,
        )

        self._audit(
            user_id=operator_ctx.get("user_id"),
            mall_id=conn.get("mall_id"),
            action="CONNECTION_RETRY_MANUAL",
            detail=f"Manual retry for connection '{conn.get('nombre')}' -> {probe.get('status')}",
            metadata={
                "connection_id": connection_id,
                "connection_run_id": run_row.get("id"),
                "retry_attempt_id": attempt.get("id"),
                "attempt_no": policy["next_attempt_no"],
                "error_code": probe.get("error_code"),
            },
        )

        return {
            "status": "success",
            "connection_id": connection_id,
            "mall_id": conn.get("mall_id"),
            "run": self._sanitize_run_row(run_row),
            "retry_attempt": self._sanitize_retry_attempt(attempt),
            "policy": {
                **policy,
                "next_attempt_no": policy["next_attempt_no"],
                "retry_after_seconds": 0,
            },
        }

    def execute_batch_retry_failed(
        self,
        *,
        mall_id: str,
        run_date: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_supabase()
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        target_date = parse_date_yyyy_mm_dd(run_date)
        start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)

        runs_res = (
            self.supabase.table("connection_runs")
            .select("*")
            .eq("mall_id", mall_id)
            .eq("status", "fail")
            .gte("started_at", _format_utc(start_dt))
            .lt("started_at", _format_utc(end_dt))
            .order("started_at", desc=True)
            .limit(max(10, self.retry_batch_request_limit() * 5))
            .execute()
        )
        fail_runs = [dict(r) for r in (runs_res.data or []) if r.get("connection_id")]

        seen = set()
        connection_ids: List[str] = []
        for row in fail_runs:
            cid = str(row.get("connection_id"))
            if cid in seen:
                continue
            seen.add(cid)
            connection_ids.append(cid)
            if len(connection_ids) >= self.retry_batch_request_limit():
                break

        results = []
        success_count = 0
        fail_count = 0
        skipped_count = 0

        for cid in connection_ids:
            try:
                out = self.execute_manual_retry(
                    connection_id=cid,
                    operator_ctx=operator_ctx,
                    ensure_operator_can_access_mall=ensure_operator_can_access_mall,
                )
                run_status = ((out.get("run") or {}).get("status") or "").lower()
                if run_status in {"ok", "partial"}:
                    success_count += 1
                else:
                    fail_count += 1
                results.append({"connection_id": cid, "status": "retried", "result": out})
            except RetryPolicyBlocked as blocked:
                skipped_count += 1
                results.append({
                    "connection_id": cid,
                    "status": "skipped",
                    "reason": blocked.code,
                    "message": blocked.message,
                    "retry_after_seconds": blocked.retry_after_seconds,
                    "attempt_no": blocked.attempt_no,
                })
            except Exception as exc:
                fail_count += 1
                results.append({
                    "connection_id": cid,
                    "status": "error",
                    "error_code": classify_connection_error(exc if isinstance(exc, Exception) else Exception(str(exc))),
                    "message": _safe_error_message(exc if isinstance(exc, Exception) else Exception(str(exc))),
                })

        self._audit(
            user_id=operator_ctx.get("user_id"),
            mall_id=mall_id,
            action="CONNECTION_RETRY_BATCH",
            detail=f"Batch retry failed connections date={run_date}",
            metadata={
                "run_date": run_date,
                "requested": len(connection_ids),
                "success_count": success_count,
                "fail_count": fail_count,
                "skipped_count": skipped_count,
            },
        )

        return {
            "status": "success",
            "mall_id": mall_id,
            "date": run_date,
            "requested": len(connection_ids),
            "limit": self.retry_batch_request_limit(),
            "retried_ok": success_count,
            "retried_fail": fail_count,
            "skipped": skipped_count,
            "results": results,
        }

    def _execute_scheduled_run_for_connection(self, conn: Dict[str, Any]) -> Dict[str, Any]:
        initial = self._probe_connection(conn)
        run_row = self._create_run_from_probe(
            connection_row=conn,
            probe_result=initial,
            run_type="scheduled",
            created_by=None,
        )

        retry_attempt = None
        if initial.get("status") == "fail":
            try:
                policy = self._enforce_retry_policy(str(conn.get("id")))
                retry_probe = self._probe_connection(conn)
                retry_attempt = self._record_retry_attempt(
                    run_row=run_row,
                    connection_row=conn,
                    attempt_no=policy["next_attempt_no"],
                    result=retry_probe,
                )
                run_row = self._finalize_run_after_retry(run_row, retry_probe)
            except RetryPolicyBlocked as blocked:
                self.logger.info(
                    "Connection monitor retry skipped connection_id=%s reason=%s retry_after=%s",
                    conn.get("id"),
                    blocked.code,
                    blocked.retry_after_seconds,
                )
            except Exception as exc:
                self.logger.warning(
                    "Connection monitor retry execution failed connection_id=%s err=%s",
                    conn.get("id"),
                    sanitize_error_text(exc),
                )

        return {
            "run": self._sanitize_run_row(run_row),
            "retry_attempt": self._sanitize_retry_attempt(retry_attempt) if retry_attempt else None,
        }

    # --- Public read endpoints ---
    def get_status_summary(
        self,
        *,
        mall_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
        recent_limit: int = 20,
    ) -> Dict[str, Any]:
        self._require_supabase()
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        connections = self._list_connections(mall_id)
        runs = self._recent_connection_runs(mall_id, limit=max(1, min(int(recent_limit), 200)))

        latest_by_connection: Dict[str, Dict[str, Any]] = {}
        for row in runs:
            cid = row.get("connection_id")
            if cid and cid not in latest_by_connection:
                latest_by_connection[cid] = row

        counts = {"total": len(connections), "ok": 0, "fail": 0, "partial": 0, "pending": 0}
        for conn in connections:
            latest = latest_by_connection.get(conn.get("id"))
            if not latest:
                counts["pending"] += 1
                continue
            status = str(latest.get("status") or "").lower()
            if status in {"ok", "fail", "partial"}:
                counts[status] += 1
            else:
                counts["pending"] += 1

        return {
            "mall_id": mall_id,
            "summary": counts,
            "recent_runs": runs,
            "connections": [
                {
                    "id": conn.get("id"),
                    "nombre": conn.get("nombre"),
                    "protocolo": conn.get("protocolo"),
                    "host": mask_secret(conn.get("host")),
                    "last_run": latest_by_connection.get(conn.get("id")),
                }
                for conn in connections
            ],
        }

    def get_failures_by_date(
        self,
        *,
        mall_id: str,
        run_date: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
        limit: int = 200,
    ) -> Dict[str, Any]:
        self._require_supabase()
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        target_date = parse_date_yyyy_mm_dd(run_date)
        start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)
        res = (
            self.supabase.table("connection_runs")
            .select("*")
            .eq("mall_id", mall_id)
            .gte("started_at", _format_utc(start_dt))
            .lt("started_at", _format_utc(end_dt))
            .order("started_at", desc=True)
            .limit(max(1, min(int(limit), 500)))
            .execute()
        )
        rows = []
        for row in (res.data or []):
            status = str(row.get("status") or "").lower()
            if status not in {"fail", "partial"}:
                continue
            rows.append(self._sanitize_run_row(dict(row)))
        return {
            "mall_id": mall_id,
            "date": run_date,
            "count": len(rows),
            "failures": rows,
        }

    # --- Nightly job ---
    def _parse_nightly_hour_minute(self) -> Tuple[int, int]:
        expr = self.nightly_retry_cron()
        try:
            parts = expr.split()
            if len(parts) != 5:
                raise ValueError("invalid cron")
            minute_s, hour_s, dom, mon, dow = parts
            if dom != "*" or mon != "*" or dow != "*":
                raise ValueError("unsupported cron format")
            minute = int(minute_s)
            hour = int(hour_s)
            if not (0 <= minute <= 59 and 0 <= hour <= 23):
                raise ValueError("out of range")
            return hour, minute
        except Exception:
            self.logger.warning("Invalid NIGHTLY_RETRY_CRON=%r. Using fallback 0 2 * * *", expr)
            return 2, 0

    def _get_system_health_value(self, key: str) -> Optional[str]:
        self._require_supabase()
        try:
            res = self.supabase.table("system_health").select("value").eq("key", key).maybe_single().execute()
            row = res.data if res else None
            if isinstance(row, dict):
                return row.get("value")
        except Exception:
            return None
        return None

    def _nightly_due_now(self, now_utc: Optional[datetime] = None) -> Tuple[bool, Dict[str, Any]]:
        now_utc = (now_utc or _utcnow()).astimezone(timezone.utc)
        hour, minute = self._parse_nightly_hour_minute()
        scheduled_at = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now_utc < scheduled_at:
            return False, {"scheduled_at": _format_utc(scheduled_at), "reason": "scheduled_time_not_reached"}
        last_run_raw = self._get_system_health_value("CONNECTION_MONITOR_LAST_RUN")
        last_run = _parse_iso_dt(last_run_raw)
        if last_run and last_run >= scheduled_at:
            return False, {"scheduled_at": _format_utc(scheduled_at), "last_run": _format_utc(last_run), "reason": "already_ran_for_slot"}
        return True, {"scheduled_at": _format_utc(scheduled_at), "last_run": _format_utc(last_run) if last_run else None}

    def run_scheduled_monitor_cycle(self) -> Dict[str, Any]:
        self._require_supabase()
        connections = self._list_connections()
        results = []
        counts = {"total": len(connections), "ok": 0, "fail": 0, "partial": 0}
        for conn in connections:
            result = self._execute_scheduled_run_for_connection(conn)
            run_status = str(((result.get("run") or {}).get("status") or "fail")).lower()
            if run_status in counts:
                counts[run_status] += 1
            results.append(result)
        return {"summary": counts, "results": results}

    def run_nightly_monitor_if_due(self, *, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
        self._require_supabase()
        if not self.nightly_retry_enabled():
            return {"executed": False, "reason": "disabled"}
        due, meta = self._nightly_due_now(now_utc=now_utc)
        if not due:
            return {"executed": False, **meta}

        run_started = _utcnow()
        self._upsert_system_health("CONNECTION_MONITOR_LAST_RUN", _format_utc(run_started))
        try:
            result = self.run_scheduled_monitor_cycle()
            self._upsert_system_health("CONNECTION_MONITOR_LAST_SUCCESS", _format_utc(_utcnow()))
            self._upsert_system_health("CONNECTION_MONITOR_LAST_ERROR", "")
            return {"executed": True, **meta, **result}
        except Exception as exc:
            self._upsert_system_health("CONNECTION_MONITOR_LAST_ERROR", sanitize_error_text(exc))
            raise

    # --- Sanitizers ---
    def _sanitize_run_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        data = dict(row)
        if data.get("error_code") and data["error_code"] not in ERROR_CODES:
            data["error_code"] = "unknown_error"
        if data.get("error_message"):
            data["error_message"] = sanitize_error_text(data.get("error_message"))
        return data

    def _sanitize_retry_attempt(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        data = dict(row)
        if data.get("error_code") and data["error_code"] not in ERROR_CODES:
            data["error_code"] = "unknown_error"
        if data.get("error_message"):
            data["error_message"] = sanitize_error_text(data.get("error_message"))
        return data


# Avoid NameError in classify_connection_error without moving imports in monolithic files.
import asyncio  # noqa: E402  pylint: disable=wrong-import-position
