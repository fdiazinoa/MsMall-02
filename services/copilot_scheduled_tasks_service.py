"""One-off tasks confirmed from MsMall Copilot and executed by the Railway worker."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.missing_days_email_service import (
    build_consolidated_missing_days_email_html,
    consolidated_missing_days_report_url,
    load_resend_sender_config,
    send_resend_email,
)
from services.sales_gap_service import expected_sales_dates, load_actual_sales_dates_by_local


TASK_TYPE_MISSING_SALES_CONSECUTIVE = "missing_sales_consecutive"
DEFAULT_TIMEZONE = "America/Santo_Domingo"
DEFAULT_SEND_HOUR = 8
MAX_TASK_ATTEMPTS = 3
_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


def _timezone(timezone_name: str = DEFAULT_TIMEZONE) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _valid_email(value: Any) -> Optional[str]:
    email = str(value or "").strip().lower()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return email
    return None


def _scheduled_date(text: str, local_now: datetime) -> Optional[date]:
    if re.search(r"\bpasado\s+manana\b", text):
        return local_now.date() + timedelta(days=2)
    if re.search(r"\bmanana\b", text):
        return local_now.date() + timedelta(days=1)
    if re.search(r"\bhoy\b", text):
        return local_now.date()
    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso_match:
        try:
            return date(*(int(part) for part in iso_match.groups()))
        except ValueError:
            return None
    local_date_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", text)
    if local_date_match:
        day, month, year = (int(part) for part in local_date_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    weekday_match = re.search(
        r"\b(?:el\s+)?(?:proximo\s+)?(" + "|".join(_WEEKDAYS) + r")\b",
        text,
    )
    if weekday_match:
        target = _WEEKDAYS[weekday_match.group(1)]
        days_ahead = (target - local_now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return local_now.date() + timedelta(days=days_ahead)
    return None


def _scheduled_time(text: str) -> datetime_time:
    match = re.search(
        r"(?:\ba\s+las?\s+)?\b(\d{1,2})(?::(\d{2}))?\s*(a\.?\s*m\.?|p\.?\s*m\.?)(?=\s|$|[,;])",
        text,
    )
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3).replace(".", "").replace(" ", "")
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
            return datetime_time(hour=hour, minute=minute)

    match = re.search(r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\b", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime_time(hour=hour, minute=minute)
    return datetime_time(hour=DEFAULT_SEND_HOUR)


_NUMBER_WORDS = {
    "uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30,
}


def _consecutive_days(text: str) -> int:
    day_token = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
    match = re.search(
        rf"\b{day_token}\s+dias?(?:\s+consecutivos?)?\s+sin(?:\s+registrar)?\s+ventas\b",
        text,
    )
    if not match:
        match = re.search(
            rf"\bsin(?:\s+registrar)?\s+ventas(?:\s+durante|\s+por|\s+en)?\s+{day_token}\s+dias?\b",
            text,
        )
    if not match:
        match = re.search(
            rf"\b(?:llevan?|tienen?)\s+{day_token}\s+dias?(?:\s+consecutivos?)?\s+sin(?:\s+registrar)?\s+ventas\b",
            text,
        )
    if not match:
        match = re.search(
            rf"\bno\s+(?:han\s+)?registrado\s+ventas(?:\s+durante|\s+por)\s+{day_token}\s+dias?\b",
            text,
        )
    if not match:
        return 7
    token = match.group(1)
    return int(token) if token.isdigit() else _NUMBER_WORDS[token]


def parse_copilot_schedule_request(
    message: str,
    *,
    user_email: Optional[str],
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Optional[Dict[str, Any]]:
    """Parse the supported deterministic intent without delegating authorization to an LLM."""
    text = _normalized(message)
    has_delivery = any(term in text for term in (
        "enviame", "enviar", "mandar", "mandame", "correo", "email", "mail",
        "programa", "agendame", "avisame", "reportame",
    ))
    has_subject = any(term in text for term in ("local", "locales", "tienda", "tiendas"))
    has_sales_gap = "ventas" in text and bool(re.search(
        r"(?:\bsin(?:\s+registrar)?\s+ventas\b|\bno\s+(?:han\s+)?registrado\s+ventas\b)",
        text,
    ))
    if not (has_delivery and has_subject and has_sales_gap):
        return None

    if re.search(r"\b(?:cada|todos\s+los|todas\s+las)\b", text):
        raise ValueError("Esta versión admite una ejecución única. Indica una fecha concreta para programarla.")

    tz = _timezone(timezone_name)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(tz)
    run_date = _scheduled_date(text, local_now)
    if run_date is None:
        if any(term in text for term in ("programa", "agendame")):
            raise ValueError("Indica cuándo ejecutar el proceso, por ejemplo: mañana o el próximo lunes.")
        return None

    consecutive_days = _consecutive_days(text)
    if not 1 <= consecutive_days <= 90:
        raise ValueError("La cantidad de días debe estar entre 1 y 90.")

    recipient_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", message)
    recipient_email = _valid_email(recipient_match.group(0) if recipient_match else user_email)
    if not recipient_email:
        raise ValueError("Tu usuario no tiene un correo válido para recibir el reporte.")

    run_time = _scheduled_time(text)
    scheduled_local = datetime.combine(run_date, run_time, tzinfo=tz)
    if scheduled_local <= local_now:
        raise ValueError("La fecha y hora programadas deben estar en el futuro.")

    return {
        "task_type": TASK_TYPE_MISSING_SALES_CONSECUTIVE,
        "scheduled_for": scheduled_local.astimezone(timezone.utc).isoformat(),
        "scheduled_for_local": scheduled_local.isoformat(),
        "timezone": tz.key,
        "lookback_days": consecutive_days,
        "consecutive_days": consecutive_days,
        "recipient_email": recipient_email,
        "explicit_recipient": bool(recipient_match),
        "instruction": str(message or "").strip(),
    }


def _sanitize_error(error: Any, limit: int = 500) -> str:
    text = str(error or "unknown_error").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def send_consecutive_missing_sales_report(
    supabase_client: Any,
    task: Dict[str, Any],
    *,
    send_email: Callable[..., Dict[str, Any]] = send_resend_email,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Send one tenant-scoped report, including a successful zero-findings result."""
    mall_id = str(task.get("mall_id") or "").strip()
    recipient_email = _valid_email(task.get("recipient_email"))
    consecutive_days = max(1, min(90, int(task.get("consecutive_days") or 7)))
    if not mall_id or not recipient_email:
        raise ValueError("La tarea no tiene mall o destinatario válido.")

    tz = _timezone(str(task.get("timezone") or DEFAULT_TIMEZONE))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_today = current.astimezone(tz).date()
    period_end = local_today - timedelta(days=1)
    period_start = period_end - timedelta(days=consecutive_days - 1)
    fecha_inicio = period_start.isoformat()
    fecha_fin = period_end.isoformat()

    mall_row = (
        supabase_client.table("malls")
        .select("id,nombre")
        .eq("id", mall_id)
        .maybe_single()
        .execute()
    ).data or {}
    mall_name = str(mall_row.get("nombre") or "MSMALL")
    stores = (
        supabase_client.table("locales")
        .select("id,nombre,codigo_interno,activo")
        .eq("mall_id", mall_id)
        .order("nombre")
        .execute()
    ).data or []
    stores = [store for store in stores if store.get("activo") is not False and store.get("id")]

    store_ids = [str(store["id"]) for store in stores]
    actual_dates = (
        load_actual_sales_dates_by_local(
            supabase_client,
            local_ids=store_ids,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        if store_ids
        else {}
    )
    expected_dates = expected_sales_dates(fecha_inicio, fecha_fin)
    findings: List[Dict[str, Any]] = []
    for store in stores:
        local_id = str(store["id"])
        missing_dates = sorted(expected_dates - actual_dates.get(local_id, set()))
        if len(missing_dates) != consecutive_days:
            continue
        findings.append({
            "local_id": local_id,
            "local_name": str(store.get("nombre") or local_id),
            "local_code": str(store.get("codigo_interno") or ""),
            "missing_count": len(missing_dates),
            "missing_details": [
                {"fecha": missing_date, "causa": "Sin ventas registradas"}
                for missing_date in missing_dates
            ],
        })

    subject = f"Locales con {consecutive_days} días consecutivos sin ventas - {mall_name}"
    if findings:
        text_body = (
            f"Se encontraron {len(findings)} locales de {mall_name} sin ventas registradas "
            f"durante los {consecutive_days} días completos entre {fecha_inicio} y {fecha_fin}."
        )
    else:
        text_body = (
            f"No se encontraron locales de {mall_name} con {consecutive_days} días consecutivos "
            f"sin ventas entre {fecha_inicio} y {fecha_fin}."
        )
    html_body = build_consolidated_missing_days_email_html(
        mall_name=mall_name,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        local_summaries=findings,
        report_url=consolidated_missing_days_report_url(mall_id, fecha_inicio, fecha_fin),
        body_message=text_body,
    )
    sender = load_resend_sender_config(supabase_client)
    resend_result = send_email(
        recipient_email,
        subject,
        text_body,
        html_body,
        [],
        from_email=sender["from_email"],
        from_name=sender["from_name"],
    )
    return {
        "status": "sent",
        "mall_id": mall_id,
        "recipient_email": recipient_email,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "consecutive_days": consecutive_days,
        "locals_count": len(findings),
        "local_ids": [row["local_id"] for row in findings],
        "resend_id": resend_result.get("id"),
    }


def _is_missing_tasks_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "copilot_scheduled_tasks" in text and (
        "does not exist" in text or "schema cache" in text or "pgrst205" in text
    )


def run_copilot_scheduled_tasks(
    supabase_client: Any,
    *,
    logger: Any = None,
    send_email: Callable[..., Dict[str, Any]] = send_resend_email,
    now: Optional[datetime] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Claim and execute due tasks. Conditional updates prevent duplicate delivery."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    try:
        rows = (
            supabase_client.table("copilot_scheduled_tasks")
            .select("*")
            .eq("status", "scheduled")
            .lte("scheduled_for", current.isoformat())
            .order("scheduled_for")
            .limit(max(1, min(100, int(limit))))
            .execute()
        ).data or []
    except Exception as exc:
        if _is_missing_tasks_table_error(exc):
            return {"executed": False, "reason": "tasks_table_unavailable", "runs": []}
        raise

    runs: List[Dict[str, Any]] = []
    for row in rows:
        task_id = str(row.get("id") or "")
        attempts = int(row.get("attempt_count") or 0) + 1
        claim = (
            supabase_client.table("copilot_scheduled_tasks")
            .update({
                "status": "running",
                "attempt_count": attempts,
                "started_at": current.isoformat(),
                "updated_at": current.isoformat(),
            })
            .eq("id", task_id)
            .eq("status", "scheduled")
            .execute()
        ).data or []
        if not claim:
            runs.append({"id": task_id, "executed": False, "reason": "already_claimed"})
            continue

        claimed = {**row, **claim[0], "attempt_count": attempts}
        try:
            result = send_consecutive_missing_sales_report(
                supabase_client,
                claimed,
                send_email=send_email,
                now=current,
            )
            supabase_client.table("copilot_scheduled_tasks").update({
                "status": "completed",
                "result": result,
                "last_error": None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", task_id).eq("status", "running").execute()
            runs.append({"id": task_id, "executed": True, **result})
        except Exception as exc:
            error_text = _sanitize_error(exc)
            retry = attempts < MAX_TASK_ATTEMPTS
            update = {
                "status": "scheduled" if retry else "failed",
                "last_error": error_text,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if retry:
                update["scheduled_for"] = (current + timedelta(minutes=5)).isoformat()
            else:
                update["completed_at"] = datetime.now(timezone.utc).isoformat()
            supabase_client.table("copilot_scheduled_tasks").update(update).eq(
                "id", task_id
            ).eq("status", "running").execute()
            if logger:
                logger.error("Copilot scheduled task %s failed: %s", task_id, error_text)
            runs.append({
                "id": task_id,
                "executed": False,
                "reason": "retry_scheduled" if retry else "failed",
                "error": error_text,
            })

    return {
        "executed": any(run.get("executed") for run in runs),
        "checked": len(rows),
        "failed": sum(1 for run in runs if run.get("reason") == "failed"),
        "runs": runs,
    }
