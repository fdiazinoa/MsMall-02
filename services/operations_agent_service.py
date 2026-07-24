from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


EVENT_IMPORT_COMPLETED = "FTP_IMPORT_COMPLETED"
EVENT_IMPORT_FAILED = "FTP_IMPORT_FAILED"
EVENT_SALES_IMPORTED = "SALES_IMPORTED"
EVENT_SALES_IMPORT_FAILED = "SALES_IMPORT_FAILED"
EVENT_WEBSERVICE_RECEIVED = "WEBSERVICE_RECEIVED"
EVENT_WEBSERVICE_FAILED = "WEBSERVICE_FAILED"
EVENT_MONITOR_ENTRY_CREATED = "MONITOR_ENTRY_CREATED"
EVENT_LOCAL_UPDATED = "LOCAL_UPDATED"
EVENT_LOCAL_ACTIVATED = "LOCAL_ACTIVATED"
EVENT_LOCAL_DEACTIVATED = "LOCAL_DEACTIVATED"

EVENT_PENDING = "PENDING"
EVENT_PROCESSING = "PROCESSING"
EVENT_PROCESSED = "PROCESSED"
EVENT_FAILED = "FAILED"
DEFAULT_DIGEST_MINUTES = 30


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _safe_int(value: Any) -> int:
    try:
        return int(float(str(value or 0)))
    except Exception:
        return 0


def _response_data(response: Any) -> List[Dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def _read_int_env(name: str, default: int, minimum: int = 1, maximum: int = 1440) -> int:
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _normalize_date(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    return None


def extract_file_date(text: Any) -> Optional[str]:
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


def infer_event_type_from_load_log(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    channel = str(payload.get("canal") or metadata.get("canal") or "").upper()
    status = str(payload.get("estado") or "").lower()
    records = _safe_int(payload.get("records_processed") or metadata.get("records_processed"))
    failed = status in {"error", "failed", "fail", "no_encontrado"} or _safe_int(payload.get("error_count") or metadata.get("error_count")) > 0

    if "WEBSERVICE" in channel:
        return EVENT_WEBSERVICE_FAILED if failed else EVENT_WEBSERVICE_RECEIVED
    if "FTP" in channel or "SFTP" in channel:
        return EVENT_IMPORT_FAILED if failed else EVENT_IMPORT_COMPLETED
    if records > 0 and not failed:
        return EVENT_SALES_IMPORTED
    if failed:
        return EVENT_SALES_IMPORT_FAILED
    return EVENT_MONITOR_ENTRY_CREATED


def should_publish_operations_event(payload: Dict[str, Any], event_type: str) -> bool:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    records = _safe_int(payload.get("records_processed") or metadata.get("records_processed"))
    errors = _safe_int(payload.get("error_count") or metadata.get("error_count"))
    reason = str(metadata.get("reason") or payload.get("reason") or "").strip().lower()
    filename = str(payload.get("archivo") or metadata.get("archivo") or "").strip().upper()

    if reason == "no_new_file" and records == 0 and errors == 0:
        return False
    if event_type == EVENT_IMPORT_COMPLETED and records == 0 and errors == 0 and filename in {"", "N/A"}:
        return False
    return True


def publish_operations_event(
    supabase_client: Any,
    *,
    mall_id: Optional[str],
    local_id: Optional[str],
    event_type: str,
    source: str,
    payload: Optional[Dict[str, Any]] = None,
    severity: str = "INFO",
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    if not supabase_client or not mall_id or not event_type:
        return None
    if not should_publish_operations_event(payload or {}, event_type):
        return None
    row = {
        "mall_id": mall_id,
        "local_id": local_id,
        "event_type": event_type,
        "source": source,
        "payload": payload or {},
        "severity": severity,
        "processing_status": EVENT_PENDING,
    }
    try:
        response = supabase_client.table("operations_events").insert(row).execute()
        return (_response_data(response) or [row])[0]
    except Exception as exc:
        if logger:
            logger.warning("Operations event publish skipped: %s", str(exc)[:220])
        return None


class OperationsAgentWorker:
    """Processes operations_events and turns them into operational intelligence."""

    def __init__(self, supabase_client: Any, logger: Optional[logging.Logger] = None):
        self.supabase = supabase_client
        self.logger = logger or logging.getLogger(__name__)

    def process_pending_events(self, limit: int = 50) -> Dict[str, Any]:
        self._ensure_ready()
        started = time.time()
        events_response = (
            self.supabase.table("operations_events")
            .select("*")
            .eq("processing_status", EVENT_PENDING)
            .order("created_at")
            .limit(max(1, min(limit, 200)))
            .execute()
        )
        events = _response_data(events_response)

        processed = 0
        failed = 0
        processed_malls: Set[str] = set()
        results = []
        for event in events:
            try:
                result = self.process_event(event)
                processed += 1
                if result.get("mall_id"):
                    processed_malls.add(str(result["mall_id"]))
                results.append(result)
            except Exception as exc:  # pragma: no cover - defensive worker guard
                failed += 1
                event_id = event.get("id")
                self.logger.exception("OperationsAgentWorker failed event=%s", event_id)
                self._mark_event_failed(event_id, str(exc))
                results.append({"event_id": event_id, "status": EVENT_FAILED, "error": str(exc)[:220]})

        digests = 0
        for mall_id in processed_malls:
            if self._should_refresh_digest(mall_id):
                self._refresh_digest(mall_id)
                digests += 1

        return {
            "status": "ok",
            "processed": processed,
            "failed": failed,
            "digests": digests,
            "duration_ms": int((time.time() - started) * 1000),
            "results": results,
        }

    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_ready()
        event_id = event.get("id")
        if event_id:
            self.supabase.table("operations_events").update({
                "processing_status": EVENT_PROCESSING,
            }).eq("id", event_id).execute()

        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = str(event.get("event_type") or "")
        mall_id = str(event.get("mall_id") or payload.get("mall_id") or "")
        local_id = str(event.get("local_id") or payload.get("local_id") or "") or None
        local = self._load_local(local_id) if local_id else {}
        findings: List[Dict[str, Any]] = []
        observations: List[Dict[str, Any]] = []
        patterns: List[Dict[str, Any]] = []

        if event_type in {EVENT_IMPORT_COMPLETED, EVENT_WEBSERVICE_RECEIVED, EVENT_SALES_IMPORTED, EVENT_MONITOR_ENTRY_CREATED}:
            findings.extend(self._audit_successful_load_event(mall_id, local, payload, event_type))
        if event_type in {EVENT_IMPORT_FAILED, EVENT_WEBSERVICE_FAILED, EVENT_SALES_IMPORT_FAILED}:
            findings.extend(self._audit_failed_load_event(mall_id, local, payload, event_type))
        if event_type in {EVENT_LOCAL_UPDATED, EVENT_LOCAL_DEACTIVATED, EVENT_LOCAL_ACTIVATED}:
            findings.extend(self._audit_local_update_event(mall_id, local, payload, event_type))

        for finding in findings:
            saved = self._upsert_finding(finding)
            finding_id = saved.get("id") if saved else None
            observations.append(self._create_observation(
                mall_id=mall_id,
                local_id=local_id,
                event_id=event_id,
                finding_id=finding_id,
                observation_type=finding.get("type") or event_type,
                observation=finding.get("description") or "",
                conclusion=finding.get("root_cause") or "",
                recommendation=finding.get("recommendation") or "",
                confidence=float(finding.get("confidence") or 0),
            ))
            if finding.get("type"):
                patterns.append(self._touch_pattern(
                    mall_id=mall_id,
                    local_id=local_id,
                    pattern_type=finding["type"],
                    pattern_name=finding.get("title") or finding["type"],
                    description=finding.get("description") or "",
                    confidence=float(finding.get("confidence") or 0),
                    metadata={"event_type": event_type, "source": event.get("source"), "payload": payload},
                ))

        if not observations:
            observations.append(self._create_observation(
                mall_id=mall_id,
                local_id=local_id,
                event_id=event_id,
                finding_id=None,
                observation_type=event_type,
                observation=self._describe_event(event, local),
                conclusion="No se detecto una anomalia accionable con la evidencia disponible.",
                recommendation="Mantener seguimiento desde Operations Center y Copilot.",
                confidence=0.65,
            ))

        if event_id:
            self.supabase.table("operations_events").update({
                "processing_status": EVENT_PROCESSED,
                "processed_at": utcnow_iso(),
                "processing_error": None,
            }).eq("id", event_id).execute()

        return {
            "event_id": event_id,
            "event_type": event_type,
            "mall_id": mall_id,
            "status": EVENT_PROCESSED,
            "findings": len(findings),
            "observations": len(observations),
            "patterns": len(patterns),
        }

    def _audit_successful_load_event(
        self,
        mall_id: str,
        local: Dict[str, Any],
        payload: Dict[str, Any],
        event_type: str,
    ) -> List[Dict[str, Any]]:
        local_id = str(local.get("id") or payload.get("local_id") or "")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        records = _safe_int(payload.get("records_processed") or metadata.get("records_processed"))
        file_date = payload.get("sale_date") or extract_file_date(payload.get("archivo") or payload.get("filename") or payload.get("mensaje") or "")
        if not local_id or not file_date or records <= 0:
            return []
        if self._has_sales_for_date(local_id, file_date):
            return []
        return [self._finding(
            mall_id=mall_id,
            local_id=local_id,
            local_name=local.get("nombre") or payload.get("local_nombre"),
            finding_type="LOAD_SUCCESS_BUT_SALES_MISSING",
            severity="HIGH",
            source=self._source_from_event(event_type, payload),
            title=f"Carga exitosa sin ventas visibles para {local.get('nombre') or payload.get('local_nombre') or 'local'}",
            description="El evento operativo indica registros procesados, pero no hay ventas visibles para la fecha detectada.",
            evidence={"event_type": event_type, "fecha_archivo": file_date, "records_processed": records, "archivo": payload.get("archivo")},
            root_cause="Posible diferencia de fecha, local asociado o persistencia final en ventas.",
            recommendation="Validar mapeo de fecha/local y reprocesar el archivo si aplica.",
            confidence=0.88,
            priority_score=82,
            fingerprint=f"AGENT:LOAD_SUCCESS_BUT_SALES_MISSING:{local_id}:{file_date}:{payload.get('archivo') or ''}",
        )]

    def _audit_failed_load_event(
        self,
        mall_id: str,
        local: Dict[str, Any],
        payload: Dict[str, Any],
        event_type: str,
    ) -> List[Dict[str, Any]]:
        local_id = str(local.get("id") or payload.get("local_id") or "")
        local_name = local.get("nombre") or payload.get("local_nombre")
        message = str(payload.get("mensaje") or payload.get("error") or "Fallo operativo registrado.")
        finding_type = "WEBSERVICE_AUTH_FAILURE" if "auth" in message.lower() or "credencial" in message.lower() else "INVALID_FILE_STRUCTURE"
        severity = "HIGH" if event_type == EVENT_WEBSERVICE_FAILED else "WARNING"
        return [self._finding(
            mall_id=mall_id,
            local_id=local_id or None,
            local_name=local_name,
            finding_type=finding_type,
            severity=severity,
            source=self._source_from_event(event_type, payload),
            title=f"Fallo operativo en {local_name or 'local sin identificar'}",
            description=message[:500],
            evidence={"event_type": event_type, "archivo": payload.get("archivo"), "estado": payload.get("estado"), "error_count": payload.get("error_count")},
            root_cause="El evento reporta error de procesamiento o recepcion.",
            recommendation="Revisar credenciales, estructura del archivo y detalle del monitor de carga.",
            confidence=0.78,
            priority_score=72 if severity == "HIGH" else 55,
            fingerprint=f"AGENT:{finding_type}:{local_id or 'sin_local'}:{date.today().isoformat()}",
        )]

    def _audit_local_update_event(
        self,
        mall_id: str,
        local: Dict[str, Any],
        payload: Dict[str, Any],
        event_type: str,
    ) -> List[Dict[str, Any]]:
        row = local or payload.get("local") or {}
        local_id = str(row.get("id") or payload.get("local_id") or "")
        if event_type != EVENT_LOCAL_DEACTIVATED:
            return []
        has_import = bool(row.get("sftp_host") or row.get("upsert_activo") or str(row.get("tipo_ejecucion") or "").upper() == "AUTOMATICO")
        if not local_id or not has_import:
            return []
        return [self._finding(
            mall_id=mall_id,
            local_id=local_id,
            local_name=row.get("nombre"),
            finding_type="LOCAL_INACTIVE_BUT_PROCESSING",
            severity="HIGH",
            source="WORKER",
            title="Local inactivo conserva importacion configurada",
            description="El local fue inactivado, pero aun conserva senales de importacion automatica.",
            evidence={"event_type": event_type, "upsert_activo": row.get("upsert_activo"), "tipo_ejecucion": row.get("tipo_ejecucion"), "sftp_host": bool(row.get("sftp_host"))},
            root_cause="La baja operativa no detuvo por completo la configuracion de importacion.",
            recommendation="Confirmar que el importador FTP/SFTP quede pausado y que el worker omita este local.",
            confidence=0.86,
            priority_score=78,
            fingerprint=f"AGENT:LOCAL_INACTIVE_BUT_PROCESSING:{local_id}",
        )]

    def _should_refresh_digest(self, mall_id: str) -> bool:
        interval_minutes = _read_int_env("OPERATIONS_DIGEST_MINUTES", DEFAULT_DIGEST_MINUTES, minimum=5, maximum=1440)
        try:
            latest = (
                self.supabase.table("operations_agent_observations")
                .select("created_at")
                .eq("mall_id", mall_id)
                .eq("observation_type", "OPERATIONAL_DIGEST")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = _response_data(latest)
            if not rows:
                return True
            created_at = rows[0].get("created_at")
            parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).replace(tzinfo=None)
            return parsed <= datetime.utcnow() - timedelta(minutes=interval_minutes)
        except Exception:
            return True

    def _refresh_digest(self, mall_id: str) -> Optional[Dict[str, Any]]:
        intelligence = OperationsIntelligenceService(self.supabase, self.logger)
        digest = intelligence.build_operational_digest(mall_id)
        return self._create_observation(
            mall_id=mall_id,
            local_id=None,
            event_id=None,
            finding_id=None,
            observation_type="OPERATIONAL_DIGEST",
            observation=digest.get("summary_text") or "",
            conclusion=digest.get("top_priority") or "Sin prioridad critica detectada.",
            recommendation=digest.get("recommended_action") or "Continuar monitoreo operativo.",
            confidence=0.80,
            metadata=digest,
        )

    def _load_local(self, local_id: Optional[str]) -> Dict[str, Any]:
        if not local_id:
            return {}
        try:
            response = (
                self.supabase.table("locales")
                .select("*")
                .eq("id", local_id)
                .maybe_single()
                .execute()
            )
            data = getattr(response, "data", None)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _has_sales_for_date(self, local_id: str, sale_date: str) -> bool:
        response = (
            self.supabase.table("ventas")
            .select("id,fecha")
            .eq("local_id", local_id)
            .gte("fecha", sale_date)
            .lte("fecha", sale_date)
            .limit(1)
            .execute()
        )
        rows = _response_data(response)
        return bool(rows)

    def _upsert_finding(self, finding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = {**finding, "updated_at": utcnow_iso()}
        payload.setdefault("detected_at", utcnow_iso())
        payload.setdefault("status", "OPEN")
        response = self.supabase.table("operational_findings").upsert(
            payload,
            on_conflict="mall_id,fingerprint",
        ).execute()
        rows = _response_data(response)
        if rows:
            return rows[0]
        fallback = (
            self.supabase.table("operational_findings")
            .select("*")
            .eq("mall_id", payload["mall_id"])
            .eq("fingerprint", payload["fingerprint"])
            .maybe_single()
            .execute()
        )
        data = getattr(fallback, "data", None)
        return data if isinstance(data, dict) else payload

    def _create_observation(
        self,
        *,
        mall_id: str,
        local_id: Optional[str],
        event_id: Optional[str],
        finding_id: Optional[str],
        observation_type: str,
        observation: str,
        conclusion: str,
        recommendation: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        row = {
            "mall_id": mall_id,
            "local_id": local_id,
            "event_id": event_id,
            "finding_id": finding_id,
            "observation_type": observation_type,
            "observation": observation[:1200],
            "conclusion": conclusion[:1200],
            "recommendation": recommendation[:1200],
            "confidence": round(float(confidence), 2),
            "metadata": metadata or {},
        }
        response = self.supabase.table("operations_agent_observations").insert(row).execute()
        return (_response_data(response) or [row])[0]

    def _touch_pattern(
        self,
        *,
        mall_id: str,
        local_id: Optional[str],
        pattern_type: str,
        pattern_name: str,
        description: str,
        confidence: float,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        existing_response = (
            self.supabase.table("operational_patterns")
            .select("*")
            .eq("mall_id", mall_id)
            .eq("pattern_type", pattern_type)
            .eq("pattern_name", pattern_name)
            .eq("local_id", local_id)
            .maybe_single()
            .execute()
        )
        existing_data = getattr(existing_response, "data", None)
        existing = existing_data if isinstance(existing_data, dict) else None
        if existing:
            row = {
                "occurrences": _safe_int(existing.get("occurrences")) + 1,
                "last_seen": utcnow_iso(),
                "confidence": max(float(existing.get("confidence") or 0), round(float(confidence), 2)),
                "metadata": {**(existing.get("metadata") or {}), "last_event": metadata},
            }
            response = self.supabase.table("operational_patterns").update(row).eq("id", existing["id"]).execute()
            return (_response_data(response) or [{**existing, **row}])[0]
        row = {
            "mall_id": mall_id,
            "local_id": local_id,
            "pattern_type": pattern_type,
            "pattern_name": pattern_name,
            "description": description,
            "occurrences": 1,
            "first_seen": utcnow_iso(),
            "last_seen": utcnow_iso(),
            "confidence": round(float(confidence), 2),
            "status": "ACTIVE",
            "metadata": {"first_event": metadata},
        }
        response = self.supabase.table("operational_patterns").insert(row).execute()
        return (_response_data(response) or [row])[0]

    def _mark_event_failed(self, event_id: Optional[str], error: str) -> None:
        if not event_id:
            return
        self.supabase.table("operations_events").update({
            "processing_status": EVENT_FAILED,
            "processed_at": utcnow_iso(),
            "processing_error": error[:1000],
        }).eq("id", event_id).execute()

    def _finding(
        self,
        *,
        mall_id: str,
        local_id: Optional[str],
        local_name: Optional[str],
        finding_type: str,
        severity: str,
        source: str,
        title: str,
        description: str,
        evidence: Dict[str, Any],
        root_cause: str,
        recommendation: str,
        confidence: float,
        priority_score: int,
        fingerprint: str,
    ) -> Dict[str, Any]:
        return {
            "mall_id": mall_id,
            "local_id": local_id,
            "local_name": local_name,
            "type": finding_type,
            "severity": severity,
            "title": title,
            "description": description,
            "evidence": evidence,
            "root_cause": root_cause,
            "recommendation": recommendation,
            "confidence": round(float(confidence), 2),
            "priority_score": max(0, min(int(priority_score), 100)),
            "status": "OPEN",
            "source": source,
            "metadata": {"agent": "OperationsAgentWorker"},
            "fingerprint": fingerprint,
        }

    def _describe_event(self, event: Dict[str, Any], local: Dict[str, Any]) -> str:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        local_name = local.get("nombre") or payload.get("local_nombre") or "local sin identificar"
        return f"Evento {event.get('event_type')} observado para {local_name} desde {event.get('source') or 'fuente operativa'}."

    @staticmethod
    def _source_from_event(event_type: str, payload: Dict[str, Any]) -> str:
        raw = str(payload.get("canal") or payload.get("source") or "").upper()
        if "WEBSERVICE" in raw or "WEBSERVICE" in event_type:
            return "WEBSERVICE"
        if "SFTP" in raw:
            return "SFTP"
        if "FTP" in raw or "FTP" in event_type:
            return "FTP"
        return "WORKER"

    def _ensure_ready(self) -> None:
        if not self.supabase:
            raise RuntimeError("Supabase no configurado.")


class OperationsIntelligenceService:
    """Central read model for Copilot and Operations Center intelligence."""

    def __init__(self, supabase_client: Any, logger: Optional[logging.Logger] = None):
        self.supabase = supabase_client
        self.logger = logger or logging.getLogger(__name__)

    def build_copilot_context(self, mall_id: str, limit: int = 20) -> Dict[str, Any]:
        findings = self._load_findings(mall_id, limit=limit)
        observations = self._load_observations(mall_id, limit=limit)
        patterns = self._load_patterns(mall_id, limit=limit)
        digest = self.latest_digest(mall_id) or self.build_operational_digest(mall_id)
        summary = self._summary(findings, observations, patterns)
        operational_health = self.getOperationalHealth(findings)
        priority_locations = self.getPriorityLocations(findings)
        return {
            "health": self._health(summary),
            "summary": summary,
            "open_findings": findings,
            "recent_observations": observations,
            "patterns": patterns,
            "operational_digest": digest,
            "changes_since_last_audit": self._changes_since_last_audit(findings, observations),
            "operational_health": operational_health,
            "priority_locations": priority_locations,
            "locations_without_sales": self.getLocationsWithoutSales(findings),
            "missing_days_summary": self.getMissingDaysSummary(findings),
            "import_failures_summary": self.getImportFailuresSummary(findings),
            "recommended_actions": self.getRecommendedActions(findings),
        }

    def build_operational_digest(self, mall_id: str) -> Dict[str, Any]:
        findings = self._load_findings(mall_id, limit=80)
        observations = self._load_observations(mall_id, limit=30, exclude_digest=True)
        critical = [row for row in findings if row.get("severity") == "CRITICAL"]
        high = [row for row in findings if row.get("severity") == "HIGH"]
        top = sorted(findings, key=lambda row: int(row.get("priority_score") or 0), reverse=True)[:1]
        locations_without_sales = self.getLocationsWithoutSales(findings)
        missing_days = self.getMissingDaysSummary(findings)
        import_failures = self.getImportFailuresSummary(findings)
        priority_locations = self.getPriorityLocations(findings)
        top_title = priority_locations[0].get("local_name") if priority_locations else "Sin prioridad critica detectada."
        summary_text = (
            f"Hoy se detectaron {locations_without_sales.get('count', 0)} locales sin ventas, "
            f"{import_failures.get('count', 0)} importaciones fallidas, "
            f"{missing_days.get('days_missing', 0)} dias faltantes y "
            f"{len(priority_locations)} locales con seguimiento requerido."
        )
        return {
            "generated_at": utcnow_iso(),
            "summary_text": summary_text,
            "top_priority": top_title,
            "recommended_action": top[0].get("recommendation") if top else "Continuar monitoreo operativo.",
            "new_findings": len([row for row in findings if self._is_recent(row.get("detected_at"), hours=24)]),
            "critical_findings": len(critical),
            "high_findings": len(high),
        }

    def getOperationalHealth(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        locals_by_id: Dict[str, Dict[str, Any]] = {}
        for finding in findings:
            local_id = str(finding.get("local_id") or finding.get("local_name") or "sin_local")
            row = locals_by_id.setdefault(local_id, {
                "local_id": finding.get("local_id"),
                "local_name": finding.get("local_name") or "Local sin identificar",
                "score": 100,
                "status": "Saludable",
                "missing_days": 0,
                "import_failures": 0,
                "last_activity": finding.get("detected_at"),
                "action": finding.get("recommendation") or "Continuar monitoreo operativo.",
                "priority_score": 0,
            })
            category = self._business_category(finding)
            severity = str(finding.get("severity") or "INFO").upper()
            penalty = {"CRITICAL": 36, "HIGH": 26, "WARNING": 16, "INFO": 8}.get(severity, 8)
            if category == "missing_days":
                row["missing_days"] += self._missing_days_count(finding)
                penalty += min(24, row["missing_days"] * 4)
            if category == "import_failure":
                row["import_failures"] += 1
                penalty += 10
            if category in {"without_sales", "sales_not_visible"}:
                penalty += 14
            row["score"] = max(0, int(row["score"]) - penalty)
            row["priority_score"] = max(int(row.get("priority_score") or 0), int(finding.get("priority_score") or 0))
            row["action"] = finding.get("recommendation") or row["action"]
            row["last_activity"] = finding.get("detected_at") or row["last_activity"]
            if row["score"] < 50:
                row["status"] = "Riesgo operativo"
            elif row["score"] < 80:
                row["status"] = "Atencion requerida"
        locations = sorted(locals_by_id.values(), key=lambda item: (int(item.get("score") or 100), -int(item.get("priority_score") or 0)))
        return {
            "locations": locations,
            "monitored_locations": len(locations),
            "healthy_locations": len([row for row in locations if int(row.get("score") or 0) >= 80]),
            "attention_required": len([row for row in locations if int(row.get("score") or 0) < 80]),
            "active_incidents": len(findings),
        }

    def getPriorityLocations(self, findings: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
        rows = sorted(findings, key=lambda row: int(row.get("priority_score") or 0), reverse=True)
        priorities = []
        for row in rows[:limit]:
            priorities.append({
                "local_id": row.get("local_id"),
                "local_name": row.get("local_name") or "Local sin identificar",
                "reason": self._business_reason(row),
                "action": row.get("recommendation") or "Revisar evidencia operativa.",
                "priority_score": int(row.get("priority_score") or 0),
                "severity": row.get("severity") or "INFO",
            })
        return priorities

    def getLocationsWithoutSales(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        rows = [row for row in findings if self._business_category(row) in {"without_sales", "sales_not_visible"}]
        locals_seen = {str(row.get("local_id") or row.get("local_name") or "") for row in rows}
        return {"count": len([item for item in locals_seen if item]), "items": rows}

    def getMissingDaysSummary(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        rows = [row for row in findings if self._business_category(row) == "missing_days"]
        return {"count": len(rows), "days_missing": sum(self._missing_days_count(row) for row in rows), "items": rows}

    def getImportFailuresSummary(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        rows = [row for row in findings if self._business_category(row) == "import_failure"]
        return {"count": len(rows), "items": rows}

    def getRecommendedActions(self, findings: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
        return [{
            "local_name": row.get("local_name") or "Local sin identificar",
            "problem": self._business_reason(row),
            "action": row.get("recommendation") or "Revisar evidencia operativa.",
            "priority_score": int(row.get("priority_score") or 0),
        } for row in sorted(findings, key=lambda item: int(item.get("priority_score") or 0), reverse=True)[:limit]]

    def latest_digest(self, mall_id: str) -> Optional[Dict[str, Any]]:
        response = (
            self.supabase.table("operations_agent_observations")
            .select("*")
            .eq("mall_id", mall_id)
            .eq("observation_type", "OPERATIONAL_DIGEST")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = _response_data(response)
        if not rows:
            return None
        row = rows[0]
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return {
            **metadata,
            "generated_at": row.get("created_at"),
            "summary_text": row.get("observation") or metadata.get("summary_text"),
            "top_priority": row.get("conclusion") or metadata.get("top_priority"),
            "recommended_action": row.get("recommendation") or metadata.get("recommended_action"),
        }

    def _load_findings(self, mall_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            response = (
                self.supabase.table("operational_findings")
                .select("*")
                .eq("mall_id", mall_id)
                .in_("status", ["OPEN", "ACKNOWLEDGED"])
                .order("priority_score", desc=True)
                .order("detected_at", desc=True)
                .limit(limit)
                .execute()
            )
            return _response_data(response)
        except Exception:
            response = (
                self.supabase.table("operational_findings")
                .select("*")
                .eq("mall_id", mall_id)
                .in_("status", ["OPEN", "ACKNOWLEDGED"])
                .order("detected_at", desc=True)
                .limit(limit)
                .execute()
            )
            return _response_data(response)

    def _load_observations(self, mall_id: str, limit: int = 20, exclude_digest: bool = False) -> List[Dict[str, Any]]:
        query = (
            self.supabase.table("operations_agent_observations")
            .select("*")
            .eq("mall_id", mall_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        rows = _response_data(query.execute())
        if exclude_digest:
            rows = [row for row in rows if row.get("observation_type") != "OPERATIONAL_DIGEST"]
        return rows

    def _load_patterns(self, mall_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        response = (
            self.supabase.table("operational_patterns")
            .select("*")
            .eq("mall_id", mall_id)
            .eq("status", "ACTIVE")
            .order("occurrences", desc=True)
            .order("last_seen", desc=True)
            .limit(limit)
            .execute()
        )
        return _response_data(response)

    def _summary(self, findings: List[Dict[str, Any]], observations: List[Dict[str, Any]], patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_severity: Dict[str, int] = {}
        affected: Set[str] = set()
        for row in findings:
            severity = str(row.get("severity") or "INFO").upper()
            by_severity[severity] = by_severity.get(severity, 0) + 1
            if row.get("local_id"):
                affected.add(str(row["local_id"]))
        return {
            "total_open": len(findings),
            "critical": by_severity.get("CRITICAL", 0),
            "high": by_severity.get("HIGH", 0),
            "warning": by_severity.get("WARNING", 0),
            "info": by_severity.get("INFO", 0),
            "affected_locals": len(affected),
            "observations_24h": len([row for row in observations if self._is_recent(row.get("created_at"), hours=24)]),
            "active_patterns": len(patterns),
            "by_severity": by_severity,
        }

    def _business_category(self, finding: Dict[str, Any]) -> str:
        text = " ".join([
            str(finding.get("type") or ""),
            str(finding.get("title") or ""),
            str(finding.get("description") or ""),
            str(finding.get("source") or ""),
        ]).lower()
        if "missing" in text or "faltante" in text or "dias" in text or "días" in text:
            return "missing_days"
        if "failed" in text or "fallo" in text or "error" in text or "timeout" in text or "invalid_file" in text:
            return "import_failure"
        if "sin ventas" in text or "without_sales" in text or "no report" in text:
            return "without_sales"
        if "ventas visibles" in text or "sales_missing" in text or "sales_not_visible" in text:
            return "sales_not_visible"
        return "follow_up"

    def _business_reason(self, finding: Dict[str, Any]) -> str:
        category = self._business_category(finding)
        if category == "missing_days":
            return "Tiene dias pendientes de informacion."
        if category == "import_failure":
            return "Presenta cargas con error o conexion fallida."
        if category == "sales_not_visible":
            return "La carga fue recibida pero las ventas no aparecen para la fecha procesada."
        if category == "without_sales":
            return "No reporta ventas dentro del periodo esperado."
        return finding.get("description") or "Requiere seguimiento operativo."

    def _missing_days_count(self, finding: Dict[str, Any]) -> int:
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        for key in ("missing_days", "dias_faltantes", "days_missing", "dias"):
            value = evidence.get(key) or finding.get(key)
            if isinstance(value, list):
                return len(value)
            parsed = _safe_int(value)
            if parsed:
                return parsed
        return 1

    @staticmethod
    def _health(summary: Dict[str, Any]) -> str:
        if summary.get("critical"):
            return "ROJO"
        if summary.get("high") or summary.get("warning"):
            return "AMARILLO"
        return "VERDE"

    def _changes_since_last_audit(self, findings: List[Dict[str, Any]], observations: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "new_findings_24h": len([row for row in findings if self._is_recent(row.get("detected_at"), hours=24)]),
            "new_observations_24h": len([row for row in observations if self._is_recent(row.get("created_at"), hours=24)]),
            "recent_titles": [row.get("title") for row in findings if self._is_recent(row.get("detected_at"), hours=24)][:6],
        }

    @staticmethod
    def _is_recent(value: Any, hours: int) -> bool:
        normalized = _normalize_date(value)
        if normalized:
            try:
                return datetime.strptime(normalized, "%Y-%m-%d").date() >= (date.today() - timedelta(days=max(1, hours // 24)))
            except ValueError:
                return False
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
            return parsed >= datetime.utcnow() - timedelta(hours=hours)
        except Exception:
            return False
