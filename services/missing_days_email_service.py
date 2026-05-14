"""Missing-days email notifications and scheduler helpers."""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 fallback only.
    ZoneInfo = None


RESEND_API_KEY_ENV = "RESEND_API_KEY"
RESEND_FROM_EMAIL = "notificaciones@mercasend.net"
RESEND_FROM_NAME = "MercaSend Notificaciones"
RESEND_USER_AGENT = "MSMALL-API/1.0 (mercasend.net)"
RESEND_SENDER_EMAIL_KEY = "RESEND_FROM_EMAIL"
RESEND_SENDER_NAME_KEY = "RESEND_FROM_NAME"
MISSING_DAYS_NOTIFICATION_TYPE = "missing_days_audit"
MISSING_DAYS_SCHEDULER_TZ_ENV = "MISSING_DAYS_EMAIL_TIMEZONE"
DEFAULT_MISSING_DAYS_SCHEDULER_TZ = "America/Santo_Domingo"


def _status_color(missing_count: int) -> Dict[str, str]:
    if missing_count > 5:
        return {
            "label": "Critico",
            "border": "#fecdd3",
            "background": "#fff1f2",
            "text": "#9f1239",
            "icon_bg": "#ffe4e6",
        }
    return {
        "label": "Alerta",
        "border": "#facc15",
        "background": "#fffbeb",
        "text": "#92400e",
        "icon_bg": "#fef3c7",
    }


def build_missing_days_email_html(
    *,
    mall_name: str,
    local_name: str,
    fecha_inicio: str,
    fecha_fin: str,
    missing_details: List[Dict[str, Any]],
    report_url: Optional[str] = None,
) -> str:
    """Builds the HTML body used for missing-sales-days alerts."""
    missing_count = len(missing_details)
    palette = _status_color(missing_count)
    safe_mall = escape(mall_name or "Mall")
    safe_local = escape(local_name or "Local")
    safe_start = escape(fecha_inicio)
    safe_end = escape(fecha_fin)
    safe_report_url = escape(report_url or "")

    cards = []
    for item in missing_details:
        date = escape(str(item.get("fecha") or item.get("fecha_faltante") or ""))
        cause = escape(str(item.get("causa") or "Sin transacciones registradas"))
        log_id = item.get("log_id")
        log_line = ""
        if log_id:
            log_line = (
                '<div style="margin-top:6px;color:#94a3b8;font-size:11px;line-height:1.35;">'
                f"Log ID: #{escape(str(log_id))}"
                "</div>"
            )

        cards.append(
            f"""
            <td style="padding:0 12px 12px 0;width:50%;vertical-align:top;">
              <div style="border:1px solid #fde68a;border-radius:8px;background:#ffffff;padding:14px 16px;">
                <div style="display:flex;gap:10px;align-items:flex-start;">
                  <div style="color:#94a3b8;font-size:18px;line-height:1;">&#9888;</div>
                  <div>
                    <div style="font-size:16px;font-weight:700;color:#334155;line-height:1.25;">{date}</div>
                    <div style="margin-top:4px;color:#64748b;font-size:12px;font-weight:700;line-height:1.35;">{cause}</div>
                    {log_line}
                  </div>
                </div>
              </div>
            </td>
            """
        )

    rows = []
    for idx in range(0, len(cards), 2):
        rows.append(f"<tr>{''.join(cards[idx:idx + 2])}</tr>")

    report_button = ""
    if safe_report_url:
        report_button = f"""
          <div style="padding:20px 24px 0;text-align:right;">
            <a href="{safe_report_url}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:8px;padding:10px 16px;font-size:13px;font-weight:700;">
              Ver auditoria en MSMALL
            </a>
          </div>
        """

    if missing_count == 0:
        return f"""
        <!doctype html>
        <html>
          <body style="margin:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;color:#1e293b;">
            <div style="max-width:760px;margin:0 auto;padding:24px;">
              <div style="border:1px solid #bbf7d0;border-radius:14px;background:#f0fdf4;padding:22px;">
                <div style="font-size:18px;font-weight:800;color:#166534;">Auditoria completa</div>
                <div style="margin-top:8px;font-size:14px;color:#166534;">
                  {safe_local} no tiene dias faltantes entre {safe_start} y {safe_end}.
                </div>
              </div>
            </div>
          </body>
        </html>
        """

    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;color:#1e293b;">
        <div style="display:none;max-height:0;overflow:hidden;">
          Faltan ventas para {missing_count} dias en {safe_local}.
        </div>
        <div style="max-width:820px;margin:0 auto;padding:24px;">
          <div style="margin-bottom:14px;color:#64748b;font-size:13px;">
            {safe_mall} &middot; {safe_local} &middot; Periodo {safe_start} al {safe_end}
          </div>

          <div style="border:1px solid {palette['border']};border-radius:14px;background:{palette['background']};overflow:hidden;">
            <div style="padding:22px 24px;border-bottom:1px solid {palette['border']};">
              <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
                <tr>
                  <td style="width:42px;vertical-align:top;">
                    <div style="width:36px;height:36px;border-radius:999px;background:{palette['icon_bg']};color:#f59e0b;text-align:center;line-height:36px;font-size:18px;">&#9888;</div>
                  </td>
                  <td style="vertical-align:top;">
                    <div style="font-size:20px;line-height:1.3;font-weight:800;color:#7c2d12;">
                      Atencion: Faltan ventas para {missing_count} dias
                    </div>
                    <div style="margin-top:6px;font-size:14px;line-height:1.45;color:#7c2d12;">
                      <strong>Local auditado:</strong> {safe_local}
                    </div>
                    <div style="margin-top:6px;font-size:14px;line-height:1.45;color:#9a3412;">
                      Se detectaron dias sin transacciones registradas en el periodo seleccionado.
                    </div>
                  </td>
                  <td style="text-align:right;vertical-align:top;">
                    <span style="display:inline-block;border:1px solid {palette['border']};border-radius:999px;padding:6px 10px;font-size:12px;font-weight:800;color:{palette['text']};background:#ffffff;">
                      {palette['label']}
                    </span>
                  </td>
                </tr>
              </table>
            </div>

            <div style="padding:16px 18px 22px;">
              <div style="color:#f59e0b;text-transform:uppercase;font-size:12px;letter-spacing:.04em;font-weight:800;margin:0 0 14px 0;">
                Detalle de dias faltantes y auditoria de logs
              </div>
              <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
                {''.join(rows)}
              </table>
            </div>
          </div>

          {report_button}

          <div style="padding:18px 4px 0;color:#94a3b8;font-size:11px;line-height:1.45;">
            Este mensaje fue generado automaticamente por MSMALL. Revise la causa antes de contactar al local o reintentar la carga.
          </div>
        </div>
      </body>
    </html>
    """


def _normalize_missing_days_sale_date(raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.strftime("%Y-%m-%d")
    value = str(raw_value).strip()
    if not value:
        return None
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    try:
        parsed = datetime.fromisoformat(value[:19])
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None


def load_missing_days_details_for_local(
    supabase_client: Any,
    *,
    local_id: str,
    local_name: str,
    mall_id: str,
    fecha_inicio: str,
    fecha_fin: str,
) -> List[Dict[str, Any]]:
    start_date = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    end_date = datetime.strptime(fecha_fin, "%Y-%m-%d")
    total_days = (end_date - start_date).days + 1
    expected_dates = {
        (start_date + timedelta(days=x)).strftime("%Y-%m-%d")
        for x in range(total_days)
    }

    rows: List[Dict[str, Any]] = []
    page_size = 2000
    page = 0
    while True:
        chunk = (
            supabase_client.table("ventas")
            .select("id, fecha")
            .eq("local_id", local_id)
            .gte("fecha", fecha_inicio)
            .lte("fecha", fecha_fin)
            .order("id")
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        ).data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1

    actual_dates = {
        normalized
        for normalized in (_normalize_missing_days_sale_date(row.get("fecha")) for row in rows)
        if normalized
    }
    missing_dates = sorted(list(expected_dates - actual_dates))
    if not missing_dates:
        return []

    try:
        logs_resp = (
            supabase_client.table("logs_carga")
            .select("*")
            .eq("local_id", local_id)
            .gte("fecha_hora", f"{fecha_inicio}T00:00:00")
            .lte("fecha_hora", f"{fecha_fin}T23:59:59")
            .order("fecha_hora", desc=True)
            .execute()
        )
    except Exception:
        logs_resp = type("Tmp", (), {"data": []})()

    logs = logs_resp.data or []
    if not logs and local_name:
        legacy_q = (
            supabase_client.table("logs_carga")
            .select("*")
            .eq("local_nombre", local_name)
            .gte("fecha_hora", f"{fecha_inicio}T00:00:00")
            .lte("fecha_hora", f"{fecha_fin}T23:59:59")
            .order("fecha_hora", desc=True)
        )
        if mall_id:
            legacy_q = legacy_q.eq("mall_id", mall_id)
        logs = legacy_q.execute().data or []

    logs_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for row in logs:
        fecha_log = str(row.get("fecha_hora") or "").split("T")[0] or None
        if fecha_log:
            logs_by_date.setdefault(fecha_log, []).append(row)

    details: List[Dict[str, Any]] = []
    for missing_date in missing_dates:
        cause = "Proceso no ejecutado / Sin conexion"
        log_id = None
        day_logs = logs_by_date.get(missing_date) or []
        if day_logs:
            last_log = day_logs[0]
            log_id = last_log.get("id")
            status_text = str(last_log.get("estado") or "").strip().lower()
            if status_text == "error":
                cause = "Fallo Tecnico / Error de Lectura"
            elif status_text in {"no_encontrado", "no encontrado"}:
                cause = "Archivo no disponible en FTP"
            elif status_text in {"exito", "success", "parcial"}:
                cause = "Procesado con Exito (Posible archivo vacio)"
        details.append({"fecha": missing_date, "causa": cause, "log_id": log_id})
    return details


def missing_days_report_url(mall_id: str, local_id: str, fecha_inicio: str, fecha_fin: str) -> Optional[str]:
    app_url = (os.getenv("APP_BASE_URL") or os.getenv("FRONTEND_URL") or "").strip().rstrip("/")
    if not app_url:
        return None
    return (
        f"{app_url}/?view=reports"
        f"&mall_id={mall_id}"
        f"&local_id={local_id}"
        f"&start_date={fecha_inicio}"
        f"&end_date={fecha_fin}"
    )


def _system_health_value(supabase_client: Any, key: str) -> Optional[str]:
    if not supabase_client:
        return None
    try:
        row = (
            supabase_client.table("system_health")
            .select("value")
            .eq("key", key)
            .maybe_single()
            .execute()
        ).data or {}
        value = row.get("value")
        return str(value).strip() if value is not None else None
    except Exception:
        return None


def _normalize_sender_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return RESEND_FROM_EMAIL
    if not email.endswith("@mercasend.net"):
        return RESEND_FROM_EMAIL
    return email


def _normalize_sender_name(value: str) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 80:
        return RESEND_FROM_NAME
    return name


def load_resend_sender_config(supabase_client: Any = None) -> Dict[str, str]:
    raw_email = (
        _system_health_value(supabase_client, RESEND_SENDER_EMAIL_KEY)
        or os.getenv("RESEND_FROM_EMAIL")
        or RESEND_FROM_EMAIL
    )
    raw_name = (
        _system_health_value(supabase_client, RESEND_SENDER_NAME_KEY)
        or os.getenv("RESEND_FROM_NAME")
        or RESEND_FROM_NAME
    )
    return {
        "from_email": _normalize_sender_email(raw_email),
        "from_name": _normalize_sender_name(raw_name),
    }


def send_resend_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
) -> Dict[str, Any]:
    api_key = os.getenv(RESEND_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"Falta {RESEND_API_KEY_ENV}.")

    sender = load_resend_sender_config()
    sender_email = _normalize_sender_email(from_email or sender["from_email"])
    sender_name = _normalize_sender_name(from_name or sender["from_name"])
    payload: Dict[str, Any] = {
        "from": f"{sender_name} <{sender_email}>",
        "to": [to_email],
        "subject": subject,
        "text": text_body,
    }
    clean_cc = [email for email in (cc_emails or []) if email]
    if clean_cc:
        payload["cc"] = clean_cc
    if html_body:
        payload["html"] = html_body

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": RESEND_USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend {exc.code}: {raw or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo conectar con Resend: {exc}") from exc


def _normalize_weekdays(values: Any) -> List[int]:
    normalized = set()
    for value in values or []:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            normalized.add(day)
    return sorted(normalized)


def _parse_send_time(value: Any) -> Tuple[int, int]:
    candidate = str(value or "08:00").strip()[:5]
    if not re.match(r"^\d{2}:\d{2}$", candidate):
        return 8, 0
    hour, minute = [int(part) for part in candidate.split(":")]
    if hour > 23 or minute > 59:
        return 8, 0
    return hour, minute


def _scheduler_tz():
    tz_name = os.getenv(MISSING_DAYS_SCHEDULER_TZ_ENV, DEFAULT_MISSING_DAYS_SCHEDULER_TZ)
    if ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo(DEFAULT_MISSING_DAYS_SCHEDULER_TZ)
    return timezone.utc


def _local_scheduler_now(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(_scheduler_tz())


def missing_days_schedule_slot(settings: Dict[str, Any], now: Optional[datetime] = None) -> Tuple[bool, Optional[str], str]:
    if not settings.get("enabled"):
        return False, None, "disabled"

    local_now = _local_scheduler_now(now)
    weekdays = _normalize_weekdays(settings.get("weekdays") or [])
    if local_now.weekday() not in weekdays:
        return False, None, "weekday_not_selected"

    hour, minute = _parse_send_time(settings.get("send_time"))
    scheduled_at = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now < scheduled_at:
        return False, None, "send_time_not_reached"

    slot = f"{local_now.strftime('%Y-%m-%d')}T{hour:02d}:{minute:02d}"
    return True, slot, "due"


def _system_health_key(mall_id: str, suffix: str) -> str:
    return f"MISSING_DAYS_EMAIL_{suffix}:{mall_id}"


def _system_health_get(supabase_client: Any, key: str) -> Optional[str]:
    row = (
        supabase_client.table("system_health")
        .select("value")
        .eq("key", key)
        .maybe_single()
        .execute()
    ).data or {}
    return row.get("value")


def _system_health_upsert(supabase_client: Any, key: str, value: str) -> None:
    supabase_client.table("system_health").upsert({
        "key": key,
        "value": value,
        "last_update": datetime.now(timezone.utc).isoformat(),
    }).execute()


def send_missing_days_emails_for_mall(
    supabase_client: Any,
    settings: Dict[str, Any],
    *,
    logger: Any = None,
    send_email: Callable[..., Dict[str, Any]] = send_resend_email,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    mall_id = str(settings.get("mall_id") or "").strip()
    if not mall_id:
        raise ValueError("mall_id es requerido.")

    lookback_days = max(1, min(90, int(settings.get("lookback_days") or 7)))
    fecha_fin_date = _local_scheduler_now(now).date()
    fecha_inicio_date = fecha_fin_date - timedelta(days=lookback_days - 1)
    fecha_inicio = fecha_inicio_date.strftime("%Y-%m-%d")
    fecha_fin = fecha_fin_date.strftime("%Y-%m-%d")

    try:
        mall_res = supabase_client.table("malls").select("nombre").eq("id", mall_id).maybe_single().execute()
        mall_name = (mall_res.data or {}).get("nombre") or "MSMALL"
    except Exception:
        mall_name = "MSMALL"

    stores = (
        supabase_client.table("locales")
        .select("id, nombre, email")
        .eq("mall_id", mall_id)
        .order("nombre")
        .execute()
    ).data or []

    results: List[Dict[str, Any]] = []
    cc_emails = [str(email or "").strip().lower() for email in (settings.get("cc_emails") or []) if email]
    send_only_with_gaps = settings.get("send_only_with_gaps") is not False
    sender = load_resend_sender_config(supabase_client)

    for store in stores:
        local_id = str(store.get("id") or "")
        local_name = store.get("nombre") or local_id
        local_email = str(store.get("email") or "").strip().lower()

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", local_email):
            results.append({
                "local_id": local_id,
                "local_nombre": local_name,
                "email": local_email or None,
                "status": "skipped",
                "missing_days": 0,
                "reason": "Local sin email valido de notificaciones.",
            })
            continue

        missing_details = load_missing_days_details_for_local(
            supabase_client,
            local_id=local_id,
            local_name=local_name,
            mall_id=mall_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        missing_count = len(missing_details)
        if missing_count == 0 and send_only_with_gaps:
            results.append({
                "local_id": local_id,
                "local_nombre": local_name,
                "email": local_email,
                "status": "skipped",
                "missing_days": 0,
                "reason": "Sin dias faltantes en el periodo.",
            })
            continue

        html_body = build_missing_days_email_html(
            mall_name=mall_name,
            local_name=local_name,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            missing_details=missing_details,
            report_url=missing_days_report_url(mall_id, local_id, fecha_inicio, fecha_fin),
        )
        subject = (
            f"Auditoria de dias faltantes: {local_name} ({missing_count} dias)"
            if missing_count > 0
            else f"Auditoria de dias faltantes: {local_name} sin brechas"
        )
        text_body = (
            f"Auditoria de dias faltantes para {local_name}. "
            f"Periodo {fecha_inicio} al {fecha_fin}. "
            f"Dias faltantes: {missing_count}."
        )

        try:
            resend_result = send_email(
                local_email,
                subject,
                text_body,
                html_body,
                cc_emails,
                from_email=sender["from_email"],
                from_name=sender["from_name"],
            )
            results.append({
                "local_id": local_id,
                "local_nombre": local_name,
                "email": local_email,
                "status": "sent",
                "missing_days": missing_count,
                "resend_id": resend_result.get("id"),
            })
        except Exception as exc:
            if logger:
                logger.error("Error enviando auditoria de dias faltantes a %s: %s", local_name, exc)
            results.append({
                "local_id": local_id,
                "local_nombre": local_name,
                "email": local_email,
                "status": "failed",
                "missing_days": missing_count,
                "reason": str(exc) or "Error enviando email.",
            })

    sent = len([row for row in results if row["status"] == "sent"])
    skipped = len([row for row in results if row["status"] == "skipped"])
    failed = len([row for row in results if row["status"] == "failed"])
    return {
        "status": "success" if failed == 0 else "partial",
        "mall_id": mall_id,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "requested": len(stores),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


def run_missing_days_email_scheduler(
    supabase_client: Any,
    *,
    logger: Any = None,
    now: Optional[datetime] = None,
    send_email: Callable[..., Dict[str, Any]] = send_resend_email,
) -> Dict[str, Any]:
    if not supabase_client:
        return {"executed": False, "reason": "supabase_not_configured", "runs": []}
    if not os.getenv(RESEND_API_KEY_ENV):
        return {"executed": False, "reason": "resend_not_configured", "runs": []}

    rows = (
        supabase_client.table("email_notification_settings")
        .select("*")
        .eq("notification_type", MISSING_DAYS_NOTIFICATION_TYPE)
        .eq("enabled", True)
        .execute()
    ).data or []

    runs: List[Dict[str, Any]] = []
    for settings in rows:
        mall_id = str(settings.get("mall_id") or "").strip()
        if not mall_id:
            continue

        due, slot, reason = missing_days_schedule_slot(settings, now=now)
        last_slot_key = _system_health_key(mall_id, "LAST_SLOT")
        status_key = _system_health_key(mall_id, "LAST_STATUS")
        if not due or not slot:
            runs.append({"mall_id": mall_id, "executed": False, "reason": reason})
            continue

        last_slot = _system_health_get(supabase_client, last_slot_key)
        if last_slot == slot:
            runs.append({"mall_id": mall_id, "executed": False, "reason": "already_sent_for_slot", "slot": slot})
            continue

        result = send_missing_days_emails_for_mall(
            supabase_client,
            settings,
            logger=logger,
            send_email=send_email,
            now=now,
        )
        _system_health_upsert(supabase_client, last_slot_key, slot)
        _system_health_upsert(
            supabase_client,
            status_key,
            f"{result['status']}: sent={result['sent']} skipped={result['skipped']} failed={result['failed']}",
        )
        runs.append({"mall_id": mall_id, "executed": True, "slot": slot, **result})

    return {
        "executed": any(run.get("executed") for run in runs),
        "checked": len(rows),
        "runs": runs,
    }
