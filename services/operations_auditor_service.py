from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


ACTIVE_STATUSES = {"OPEN", "ACKNOWLEDGED"}


class OperationsAuditorService:
    """Builds operational findings that feed MsMall Copilot and Operations Center."""

    def __init__(self, supabase_client: Any, logger: Optional[logging.Logger] = None):
        self.supabase = supabase_client
        self.logger = logger or logging.getLogger(__name__)

    def list_findings(
        self,
        mall_id: str,
        status: Optional[str] = "OPEN",
        severity: Optional[str] = None,
        source: Optional[str] = None,
        local_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        query = (
            self.supabase.table("operational_findings")
            .select("*")
            .eq("mall_id", mall_id)
            .order("detected_at", desc=True)
            .limit(max(1, min(int(limit or 100), 300)))
        )
        if status:
            query = query.eq("status", status.upper())
        if severity:
            query = query.eq("severity", severity.upper())
        if source:
            query = query.eq("source", source.upper())
        if local_id:
            query = query.eq("local_id", local_id)

        rows = query.execute().data or []
        last_run = self._last_run(mall_id)
        return {
            "findings": [self._normalize_row(row) for row in rows],
            "summary": self._summary(rows, last_run),
            "last_run": last_run,
        }

    def get_finding(self, mall_id: str, finding_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_ready()
        row = (
            self.supabase.table("operational_findings")
            .select("*")
            .eq("mall_id", mall_id)
            .eq("id", finding_id)
            .maybe_single()
            .execute()
        ).data
        return self._normalize_row(row) if row else None

    def acknowledge_finding(self, mall_id: str, finding_id: str, operator: str) -> Dict[str, Any]:
        return self._update_status(mall_id, finding_id, "ACKNOWLEDGED", operator)

    def resolve_finding(self, mall_id: str, finding_id: str, operator: str) -> Dict[str, Any]:
        return self._update_status(mall_id, finding_id, "RESOLVED", operator)

    def run_audit(self, mall_id: str, operator: Optional[str] = None, lookback_days: int = 7) -> Dict[str, Any]:
        self._ensure_ready()
        started = datetime.utcnow()
        started_epoch = time.time()
        errors: List[Dict[str, str]] = []
        created = 0
        updated = 0
        findings: List[Dict[str, Any]] = []

        try:
            locals_rows = self._load_locales(mall_id)
            active_locals = [row for row in locals_rows if self._is_active_local(row)]
            inactive_locals = [row for row in locals_rows if not self._is_active_local(row)]
            logs = self._load_recent_logs(mall_id, limit=250)
            file_dates = [
                parsed
                for parsed in (self._extract_file_date(log.get("archivo") or log.get("mensaje") or "") for log in logs)
                if parsed
            ]
            sales_dates = self._load_sales_dates(locals_rows, lookback_days, file_dates)

            findings.extend(self._audit_missing_days(mall_id, active_locals, sales_dates, lookback_days))
            findings.extend(self._audit_loads_without_sales(mall_id, logs, sales_dates))
            findings.extend(self._audit_error_rate(mall_id, logs))
            findings.extend(self._audit_workers(mall_id, active_locals, logs))
            findings.extend(self._audit_inactive_processing(mall_id, inactive_locals))
        except Exception as exc:  # pragma: no cover - defensive operational guard
            self.logger.exception("Operations Auditor failed while collecting evidence")
            errors.append({"stage": "collect", "message": str(exc)[:240]})

        seen: Set[str] = set()
        for finding in findings:
            fingerprint = str(finding.get("fingerprint") or "").strip()
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            try:
                existed = self._finding_exists(mall_id, fingerprint)
                self._upsert_finding(finding)
                if existed:
                    updated += 1
                else:
                    created += 1
            except Exception as exc:  # pragma: no cover - depends on remote DB behavior
                self.logger.warning("Operations Auditor could not save finding %s: %s", fingerprint, exc)
                errors.append({"stage": "persist", "fingerprint": fingerprint, "message": str(exc)[:240]})

        duration_ms = int((time.time() - started_epoch) * 1000)
        status = "completed_with_errors" if errors else "completed"
        run_row = {
            "mall_id": mall_id,
            "status": status,
            "started_at": started.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
            "findings_created": created,
            "findings_updated": updated,
            "errors": errors,
            "metadata": {
                "lookback_days": lookback_days,
                "findings_detected": len(seen),
            },
            "created_by": operator,
        }
        try:
            run_row = (self.supabase.table("operations_auditor_runs").insert(run_row).execute().data or [run_row])[0]
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Operations Auditor could not save run: %s", exc)

        return {
            "status": status,
            "mall_id": mall_id,
            "findings_created": created,
            "findings_updated": updated,
            "findings_detected": len(seen),
            "duration_ms": duration_ms,
            "errors": errors,
            "run": run_row,
        }

    def build_copilot_summary(self, mall_id: str, limit: int = 20) -> Dict[str, Any]:
        data = self.list_findings(mall_id=mall_id, status="OPEN", limit=limit)
        findings = data.get("findings") or []
        summary = data.get("summary") or {}
        critical = int(summary.get("by_severity", {}).get("CRITICAL") or 0)
        high = int(summary.get("by_severity", {}).get("HIGH") or 0)
        warning = int(summary.get("by_severity", {}).get("WARNING") or 0)
        if critical:
            health = "ROJO"
        elif high or warning:
            health = "AMARILLO"
        else:
            health = "VERDE"
        return {
            "health": health,
            "summary": summary,
            "last_run": data.get("last_run"),
            "open_findings": [
                {
                    "id": row.get("id"),
                    "local": row.get("local_name"),
                    "type": row.get("type"),
                    "severity": row.get("severity"),
                    "title": row.get("title"),
                    "description": row.get("description"),
                    "root_cause": row.get("root_cause"),
                    "recommendation": row.get("recommendation"),
                    "confidence": row.get("confidence"),
                    "source": row.get("source"),
                    "detected_at": row.get("detected_at"),
                    "evidence": row.get("evidence"),
                }
                for row in findings[:limit]
            ],
        }

    def _audit_missing_days(
        self,
        mall_id: str,
        locals_rows: List[Dict[str, Any]],
        sales_dates: Dict[str, Set[str]],
        lookback_days: int,
    ) -> List[Dict[str, Any]]:
        end_date = date.today()
        start_date = end_date - timedelta(days=max(1, lookback_days) - 1)
        expected = [(start_date + timedelta(days=offset)).isoformat() for offset in range(lookback_days)]
        findings = []
        for local in locals_rows:
            local_id = str(local.get("id") or "")
            if not local_id:
                continue
            actual = sales_dates.get(local_id, set())
            missing = [day for day in expected if day not in actual]
            if not missing:
                continue
            severity = "CRITICAL" if len(missing) >= lookback_days else "HIGH" if len(missing) >= 3 else "WARNING"
            findings.append(self._finding(
                mall_id=mall_id,
                local=local,
                finding_type="MISSING_DAYS",
                severity=severity,
                source="MISSING_DAYS",
                title=f"{local.get('nombre') or 'Local'} tiene dias sin informacion",
                description=f"Faltan {len(missing)} de {lookback_days} dias esperados en ventas recientes.",
                evidence={"fecha_inicio": start_date.isoformat(), "fecha_fin": end_date.isoformat(), "dias_faltantes": missing},
                root_cause="No hay ventas registradas para las fechas esperadas en el cubo.",
                recommendation="Validar el monitor de carga, el archivo recibido y reprocesar las fechas faltantes si aplica.",
                confidence=0.90,
                fingerprint=f"MISSING_DAYS:{local_id}:{start_date.isoformat()}:{end_date.isoformat()}",
            ))
        return findings

    def _audit_loads_without_sales(
        self,
        mall_id: str,
        logs: List[Dict[str, Any]],
        sales_dates: Dict[str, Set[str]],
    ) -> List[Dict[str, Any]]:
        findings = []
        for log in logs:
            local_id = str(log.get("local_id") or "")
            if not local_id:
                continue
            records = self._safe_int(log.get("records_processed")) or self._extract_records(log.get("mensaje"))
            state = str(log.get("estado") or "").lower()
            if state not in {"exito", "success", "ok"} or records <= 0:
                continue
            file_date = self._extract_file_date(log.get("archivo") or log.get("mensaje") or "")
            if not file_date:
                continue
            if file_date in sales_dates.get(local_id, set()):
                continue
            local = {"id": local_id, "nombre": log.get("local_nombre")}
            findings.append(self._finding(
                mall_id=mall_id,
                local=local,
                finding_type="LOAD_SUCCESS_BUT_SALES_MISSING",
                severity="HIGH",
                source=self._source_from_log(log),
                title=f"Carga exitosa sin ventas visibles para {log.get('local_nombre') or 'local'}",
                description="El monitor reporta registros cargados, pero el cubo no refleja ventas para la fecha del archivo.",
                evidence={
                    "archivo": log.get("archivo"),
                    "fecha_archivo": file_date,
                    "records_processed": records,
                    "fecha_hora": log.get("fecha_hora"),
                    "mensaje": log.get("mensaje"),
                },
                root_cause="Posible diferencia entre fecha del archivo, local asociado o persistencia final en ventas.",
                recommendation="Comparar el archivo importado contra ventas por local/fecha y revisar mapeo de local y fecha.",
                confidence=0.86,
                fingerprint=f"LOAD_SUCCESS_BUT_SALES_MISSING:{local_id}:{file_date}:{log.get('archivo') or ''}",
            ))
        return findings

    def _audit_error_rate(self, mall_id: str, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for log in logs:
            local_id = str(log.get("local_id") or "sin_local")
            bucket = grouped.setdefault(local_id, {"local": log.get("local_nombre"), "errors": 0, "total": 0, "samples": []})
            bucket["total"] += 1
            state = str(log.get("estado") or "").lower()
            error_count = self._safe_int(log.get("error_count"))
            if state in {"error", "parcial", "failed", "fail"} or error_count > 0:
                bucket["errors"] += 1
                if len(bucket["samples"]) < 4:
                    bucket["samples"].append({
                        "fecha_hora": log.get("fecha_hora"),
                        "archivo": log.get("archivo"),
                        "estado": log.get("estado"),
                        "mensaje": log.get("mensaje"),
                    })

        findings = []
        for local_id, bucket in grouped.items():
            if bucket["total"] < 3 or bucket["errors"] < 3:
                continue
            rate = bucket["errors"] / max(1, bucket["total"])
            if rate < 0.35:
                continue
            local = {"id": None if local_id == "sin_local" else local_id, "nombre": bucket.get("local")}
            findings.append(self._finding(
                mall_id=mall_id,
                local=local,
                finding_type="HIGH_ERROR_RATE",
                severity="CRITICAL" if rate >= 0.70 else "HIGH",
                source="WORKER",
                title=f"Alta tasa de errores en cargas de {bucket.get('local') or 'local sin identificar'}",
                description=f"{bucket['errors']} de {bucket['total']} eventos recientes presentan error o carga parcial.",
                evidence={"error_rate": round(rate, 2), "samples": bucket["samples"]},
                root_cause="Errores repetidos en estructura, conexion o validacion de archivos.",
                recommendation="Revisar credenciales/conexion y validar la estructura del archivo antes del siguiente ciclo.",
                confidence=0.82,
                fingerprint=f"HIGH_ERROR_RATE:{local_id}:{date.today().isoformat()}",
            ))
        return findings

    def _audit_workers(
        self,
        mall_id: str,
        locals_rows: List[Dict[str, Any]],
        logs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        last_log_by_local: Dict[str, str] = {}
        for log in logs:
            local_id = str(log.get("local_id") or "")
            if local_id and local_id not in last_log_by_local:
                last_log_by_local[local_id] = str(log.get("fecha_hora") or "")

        findings = []
        for local in locals_rows:
            local_id = str(local.get("id") or "")
            if not local_id:
                continue
            execution_mode = str(local.get("tipo_ejecucion") or local.get("execution_mode") or "").upper()
            has_import = bool(local.get("sftp_host") or local.get("upsert_activo") or execution_mode == "AUTOMATICO")
            if not has_import or execution_mode == "MANUAL":
                continue
            if last_log_by_local.get(local_id):
                continue
            findings.append(self._finding(
                mall_id=mall_id,
                local=local,
                finding_type="WORKER_NOT_EXECUTED",
                severity="WARNING",
                source="WORKER",
                title=f"Worker sin ejecucion reciente para {local.get('nombre') or 'local'}",
                description="No hay eventos recientes de carga para un local con importacion configurada.",
                evidence={"lookback_logs": len(logs), "ultima_ejecucion": local.get("ultima_ejecucion")},
                root_cause="El worker no ha registrado ejecuciones recientes para este local.",
                recommendation="Validar programacion, frecuencia y estado de la conexion remota.",
                confidence=0.70,
                fingerprint=f"WORKER_NOT_EXECUTED:{local_id}:{date.today().isoformat()}",
            ))
        return findings

    def _audit_inactive_processing(self, mall_id: str, locals_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        findings = []
        for local in locals_rows:
            local_id = str(local.get("id") or "")
            processing = str(local.get("processing_status") or "").upper()
            execution_mode = str(local.get("tipo_ejecucion") or "").upper()
            has_import = bool(local.get("sftp_host") or local.get("upsert_activo") or execution_mode == "AUTOMATICO")
            if not local_id or (processing != "BUSY" and not has_import):
                continue
            findings.append(self._finding(
                mall_id=mall_id,
                local=local,
                finding_type="LOCAL_INACTIVE_BUT_PROCESSING",
                severity="HIGH",
                source="WORKER",
                title=f"Local inactivo aun aparece con procesamiento configurado",
                description=f"{local.get('nombre') or 'Local'} esta inactivo, pero conserva senales de importacion o procesamiento.",
                evidence={"processing_status": local.get("processing_status"), "tipo_ejecucion": local.get("tipo_ejecucion"), "sftp_host": bool(local.get("sftp_host"))},
                root_cause="La baja operativa del local no detuvo por completo su importador.",
                recommendation="Desactivar la importacion FTP/SFTP y confirmar que el worker lo omite.",
                confidence=0.88,
                fingerprint=f"LOCAL_INACTIVE_BUT_PROCESSING:{local_id}",
            ))
        return findings

    def _load_locales(self, mall_id: str) -> List[Dict[str, Any]]:
        return (
            self.supabase.table("locales")
            .select("*")
            .eq("mall_id", mall_id)
            .order("nombre")
            .limit(500)
            .execute()
        ).data or []

    def _load_recent_logs(self, mall_id: str, limit: int = 250) -> List[Dict[str, Any]]:
        return (
            self.supabase.table("logs_carga")
            .select("*")
            .eq("mall_id", mall_id)
            .order("fecha_hora", desc=True)
            .limit(limit)
            .execute()
        ).data or []

    def _load_sales_dates(
        self,
        locals_rows: List[Dict[str, Any]],
        lookback_days: int,
        extra_dates: Optional[List[str]] = None,
    ) -> Dict[str, Set[str]]:
        local_ids = [str(row.get("id")) for row in locals_rows if row.get("id")]
        end_date = date.today()
        start_date = end_date - timedelta(days=max(1, lookback_days) - 1)
        for raw_date in extra_dates or []:
            try:
                parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
                if parsed < start_date:
                    start_date = parsed
                if parsed > end_date:
                    end_date = parsed
            except ValueError:
                continue
        dates_by_local: Dict[str, Set[str]] = {local_id: set() for local_id in local_ids}
        if not local_ids:
            return dates_by_local
        rows = (
            self.supabase.table("ventas")
            .select("local_id,fecha")
            .in_("local_id", local_ids)
            .gte("fecha", start_date.isoformat())
            .lte("fecha", end_date.isoformat())
            .limit(10000)
            .execute()
        ).data or []
        for row in rows:
            local_id = str(row.get("local_id") or "")
            normalized = self._normalize_date(row.get("fecha"))
            if local_id and normalized:
                dates_by_local.setdefault(local_id, set()).add(normalized)
        return dates_by_local

    def _last_run(self, mall_id: str) -> Optional[Dict[str, Any]]:
        try:
            return (
                self.supabase.table("operations_auditor_runs")
                .select("*")
                .eq("mall_id", mall_id)
                .order("started_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            ).data
        except Exception:
            return None

    def _finding_exists(self, mall_id: str, fingerprint: str) -> bool:
        row = (
            self.supabase.table("operational_findings")
            .select("id")
            .eq("mall_id", mall_id)
            .eq("fingerprint", fingerprint)
            .maybe_single()
            .execute()
        ).data
        return bool(row)

    def _upsert_finding(self, finding: Dict[str, Any]) -> None:
        now = datetime.utcnow().isoformat()
        payload = {**finding, "updated_at": now}
        payload.setdefault("detected_at", now)
        payload.setdefault("status", "OPEN")
        self.supabase.table("operational_findings").upsert(
            payload,
            on_conflict="mall_id,fingerprint",
        ).execute()

    def _update_status(self, mall_id: str, finding_id: str, status: str, operator: str) -> Dict[str, Any]:
        self._ensure_ready()
        payload: Dict[str, Any] = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
            "assigned_to": operator,
        }
        if status == "RESOLVED":
            payload["resolved_at"] = datetime.utcnow().isoformat()
        row = (
            self.supabase.table("operational_findings")
            .update(payload)
            .eq("mall_id", mall_id)
            .eq("id", finding_id)
            .execute()
        ).data
        if not row:
            raise ValueError("Finding not found")
        return self._normalize_row(row[0])

    def _finding(
        self,
        mall_id: str,
        local: Dict[str, Any],
        finding_type: str,
        severity: str,
        source: str,
        title: str,
        description: str,
        evidence: Dict[str, Any],
        root_cause: str,
        recommendation: str,
        confidence: float,
        fingerprint: str,
    ) -> Dict[str, Any]:
        return {
            "mall_id": mall_id,
            "local_id": local.get("id"),
            "local_name": local.get("nombre") or local.get("local_nombre"),
            "type": finding_type,
            "severity": severity,
            "title": title,
            "description": description,
            "evidence": evidence,
            "root_cause": root_cause,
            "recommendation": recommendation,
            "confidence": round(float(confidence), 2),
            "status": "OPEN",
            "source": source,
            "metadata": {},
            "fingerprint": fingerprint,
        }

    def _summary(self, rows: List[Dict[str, Any]], last_run: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        by_severity: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        affected_locals: Set[str] = set()
        for row in rows:
            severity = str(row.get("severity") or "INFO").upper()
            source = str(row.get("source") or "UNKNOWN").upper()
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_source[source] = by_source.get(source, 0) + 1
            if row.get("local_id"):
                affected_locals.add(str(row["local_id"]))
        return {
            "total_open": len(rows),
            "critical": by_severity.get("CRITICAL", 0),
            "high": by_severity.get("HIGH", 0),
            "warning": by_severity.get("WARNING", 0),
            "info": by_severity.get("INFO", 0),
            "affected_locals": len(affected_locals),
            "by_severity": by_severity,
            "by_source": by_source,
            "last_run_at": last_run.get("started_at") if last_run else None,
            "last_run_status": last_run.get("status") if last_run else None,
        }

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not row:
            return {}
        return {
            **row,
            "confidence": float(row.get("confidence") or 0),
            "evidence": row.get("evidence") or {},
            "metadata": row.get("metadata") or {},
            "notified_to": row.get("notified_to") or [],
        }

    def _ensure_ready(self) -> None:
        if not self.supabase:
            raise RuntimeError("Supabase no configurado.")

    @staticmethod
    def _is_active_local(row: Dict[str, Any]) -> bool:
        return row.get("activo") is not False

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_records(message: Any) -> int:
        text = str(message or "")
        match = re.search(r"(\d+)\s+registros?\s+(?:cargados?|procesados?)", text, re.I)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _normalize_date(value: Any) -> Optional[str]:
        if not value:
            return None
        text = str(value)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_file_date(text: str) -> Optional[str]:
        for match in re.finditer(r"(?<!\d)(\d{8})(?!\d)", str(text or "")):
            raw = match.group(1)
            candidates: List[Tuple[int, int, int]] = [
                (int(raw[4:8]), int(raw[2:4]), int(raw[0:2])),
                (int(raw[0:4]), int(raw[4:6]), int(raw[6:8])),
            ]
            for year, month, day in candidates:
                try:
                    return date(year, month, day).isoformat()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _source_from_log(log: Dict[str, Any]) -> str:
        metadata = log.get("metadata") if isinstance(log.get("metadata"), dict) else {}
        raw = str(log.get("canal") or log.get("source") or metadata.get("canal") or "").upper()
        if "WEBSERVICE" in raw:
            return "WEBSERVICE"
        if "SFTP" in raw:
            return "SFTP"
        if "FTP" in raw:
            return "FTP"
        return "WORKER"
