import os
import stat
import logging
import uuid
import asyncio
import time
import hashlib
from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from supabase import create_client, Client
from dotenv import load_dotenv
import paramiko
from ftplib import FTP
import io
import csv
import json
import posixpath
import pandas as pd
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from services.load_log_service import build_load_log_payload, insert_load_log_row

try:
    from services.connection_monitor_service import ConnectionMonitorService
except Exception:
    ConnectionMonitorService = None  # type: ignore[assignment]

try:
    from services.missing_days_email_service import run_missing_days_email_scheduler
except Exception:
    run_missing_days_email_scheduler = None  # type: ignore[assignment]

try:
    from services.sensitive_ops_service import sanitize_error_text
except Exception:
    def sanitize_error_text(value: object) -> str:
        return str(value or "").strip()

try:
    from analytics_service import run_local_risk_analysis
except Exception:
    def run_local_risk_analysis(*_args, **_kwargs):
        raise RuntimeError("Analytics service not available")

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("import-worker")

# Load Environment
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
DEFAULT_WORKER_TIMEZONE = "America/Santo_Domingo"

supabase: Optional[Client] = None

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error(
        "Supabase credentials missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY)."
    )
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")


def _read_int_env(name: str, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


WORKER_POLL_SECONDS = _read_int_env("WORKER_POLL_SECONDS", 300, minimum=60)
MAX_CONCURRENT_WORKERS = _read_int_env("MAX_CONCURRENT_WORKERS", 3, minimum=1)
MAX_CONCURRENT_PER_HOST = _read_int_env("MAX_CONCURRENT_PER_HOST", 1, minimum=1)
HOURLY_STAGGER_MINUTES = _read_int_env("HOURLY_STAGGER_MINUTES", 15, minimum=0, maximum=55)
MAX_FILES_PER_BATCH = _read_int_env("MAX_FILES_PER_BATCH", 20, minimum=1)


def _worker_timezone() -> ZoneInfo:
    configured = (
        os.getenv("WORKER_TIMEZONE")
        or DEFAULT_WORKER_TIMEZONE
    ).strip() or DEFAULT_WORKER_TIMEZONE
    try:
        return ZoneInfo(configured)
    except ZoneInfoNotFoundError:
        logger.warning(
            "Zona horaria del worker invalida '%s'. Usando %s.",
            configured,
            DEFAULT_WORKER_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_WORKER_TIMEZONE)


def _now_local() -> datetime:
    return datetime.now(_worker_timezone())


def _coerce_datetime_to_reference(value: datetime, reference: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo)
    return value.astimezone(reference.tzinfo)


def _parse_datetime_value(raw: Any, reference: datetime) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return _coerce_datetime_to_reference(parsed, reference)
    except ValueError:
        return None


def _parse_hora_especifica(raw: Any) -> Optional[dt_time]:
    if raw in (None, "", "null"):
        return None
    if isinstance(raw, dt_time):
        return raw

    text = str(raw).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _stable_offset_minutes(local: Dict[str, Any], max_minutes: int = HOURLY_STAGGER_MINUTES) -> int:
    if max_minutes <= 0:
        return 0
    seed = str(local.get("id") or local.get("nombre") or local.get("sftp_host") or "")
    if not seed:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (max_minutes + 1)


def _host_key(local: Dict[str, Any]) -> str:
    return str(local.get("sftp_host") or local.get("host") or "__no_host__").strip().lower()


def _schedule_due_at(local: Dict[str, Any], now: datetime) -> Optional[datetime]:
    frecuencia = str(local.get("frecuencia_cron") or "manual").strip().lower()
    if frecuencia == "manual":
        return None

    last_attempt = _parse_datetime_value(local.get("ultima_ejecucion"), now)
    due_at: Optional[datetime] = None

    if frecuencia == "cada_hora":
        slot_start = now.replace(minute=0, second=0, microsecond=0)
        due_at = slot_start + timedelta(minutes=_stable_offset_minutes(local))
    elif frecuencia == "cada_2_horas":
        slot_hour = now.hour - (now.hour % 2)
        slot_start = now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
        due_at = slot_start + timedelta(minutes=_stable_offset_minutes(local))
    elif frecuencia == "hora_especifica":
        scheduled_time = _parse_hora_especifica(local.get("hora_especifica"))
        if not scheduled_time:
            return None
        due_at = now.replace(
            hour=scheduled_time.hour,
            minute=scheduled_time.minute,
            second=0,
            microsecond=0,
        )
    else:
        return None

    if now < due_at:
        return None
    if last_attempt and last_attempt >= due_at:
        return None
    return due_at

AUTO_SUCCESS_PREFIX = "PR_"
AUTO_ERROR_PREFIX = "ERR_"

def _connection_monitor_service() -> ConnectionMonitorService:
    if ConnectionMonitorService is None:
        raise RuntimeError("ConnectionMonitorService not available")
    return ConnectionMonitorService(supabase, logger)


def run_local_risk_analysis_if_possible(config, trigger: str) -> Optional[dict]:
    local_id = config.get("id")
    if not supabase or not local_id:
        return None
    try:
        snapshot = run_local_risk_analysis(
            local_id,
            supabase_client=supabase,
            logger=logger,
            trigger=trigger,
        )
        summary = snapshot.get("summary") or {}
        logger.info(
            "Semaforo IA actualizado para %s: state=%s alerts=%s score=%s",
            config.get("nombre") or local_id,
            summary.get("risk_state"),
            summary.get("alerts_count"),
            summary.get("risk_score"),
        )
        return snapshot
    except Exception as exc:
        logger.error("Fallo actualizando semaforo IA para %s: %s", config.get("nombre") or local_id, exc)
        return None

def insert_load_log(
    local_nombre: str,
    archivo: str,
    estado: str,
    mensaje: str,
    batch_id: str = None,
    detalles: list = None,
    mall_id: str = None,
    local_id: str = None,
    mall_nombre: str = None,
    canal: str = None,
    records_processed: Optional[int] = None,
    error_count: Optional[int] = None,
    metadata: Optional[dict] = None,
):
    """Inserts a log into Supabase 'logs_carga' table."""
    if not supabase:
        logger.warning("Skipping load log insert: Supabase client not initialized.")
        return
    try:
        log_data = build_load_log_payload(
            local_nombre=local_nombre,
            archivo=archivo,
            estado=estado,
            mensaje=mensaje,
            batch_id=batch_id,
            detalles=detalles,
            mall_id=mall_id,
            mall_nombre=mall_nombre,
            local_id=local_id,
            canal=canal,
            records_processed=records_processed,
            error_count=error_count,
            metadata=metadata,
        )
        insert_load_log_row(supabase, log_data, logger=logger)
        logger.info(f"Log registrado: {mensaje}")
    except Exception as e:
        logger.error(f"Error inserting load log: {e}")

def normalize_date(date_str):
    """
    Attempts to parse a date string into YYYY-MM-DD format.
    Supports: DD/MM/YYYY, YYYY-MM-DD, MM/DD/YYYY, DD-MM-YYYY, YYYY/MM/DD,
    YYYYmmDD and YYYYmmDD with time.
    """
    if not date_str:
        return None
        
    raw_date = str(date_str).strip().strip("'\"")
    # Try common formats
    for fmt in [
        '%d/%m/%Y',
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d-%m-%Y',
        '%Y/%m/%d',
        '%Y%m%d',
        '%Y%m%d %H:%M:%S',
        '%Y%m%d %H:%M',
        '%Y%m%d %H:%M:%S.%f',
        '%Y%m%dT%H:%M:%S',
        '%Y%m%dT%H:%M',
        '%Y%m%dT%H:%M:%S.%f',
    ]:
        try:
            parsed_date = datetime.strptime(raw_date, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _split_transform_fields(raw_fields: Any) -> List[str]:
    if isinstance(raw_fields, list):
        return [str(field).strip() for field in raw_fields if str(field or "").strip()]
    return [part.strip() for part in str(raw_fields or "").split(",") if part.strip()]


def _clean_generated_invoice_piece(value: Any) -> str:
    text = str(value or "").strip().strip("'\"")
    text = " ".join(text.split())
    return text.replace(" ", "").replace("/", "").replace("\\", "").replace("-", "")


def _format_generated_invoice(local_code: Any, sale_date: Any, sequence: int) -> str:
    local_part = _clean_generated_invoice_piece(local_code)
    date_part = _clean_generated_invoice_piece(str(sale_date or "").replace("-", ""))
    return f"{local_part}{date_part}{sequence:04d}"


def _parse_mapped_decimal(value: Any, decimal_separator: Any = ".") -> float:
    if value is None:
        return 0.0

    text = str(value).strip().strip("'\"")
    if not text:
        return 0.0

    text = re.sub(r"\s+", "", text)
    text = text.replace("$", "").replace("RD", "").replace("rd", "")
    if decimal_separator == ",":
        text = text.replace(".", "")
        if text.count(",") > 1:
            sign = "-" if text.startswith("-") else ""
            unsigned = text[1:] if sign else text
            parts = unsigned.split(",")
            if len(parts) >= 3 and all(len(part) == 3 for part in parts[-2:]):
                digits = "".join(parts)
                if len(digits) > 6:
                    text = f"{sign}{digits[:-6]}.{digits[-6:]}"
                else:
                    text = f"{sign}0.{digits.zfill(6)}"
            else:
                text = "".join(parts[:-1]) + "." + parts[-1]
                if sign and not text.startswith("-"):
                    text = f"-{text}"
        else:
            text = text.replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        return float(text)
    except Exception:
        return 0.0


def _parse_import_cutoff_date(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _is_import_date_closed(sale_date: str, cutoff_date: Optional[str]) -> bool:
    return bool(sale_date and cutoff_date and sale_date <= cutoff_date)


def _clean_csv_header_name(name) -> str:
    return str(name or "").replace("\ufeff", "").strip()

def _normalize_csv_row_keys(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    normalized = {}
    for key, value in row.items():
        clean_key = _clean_csv_header_name(key)
        if not clean_key:
            continue
        if clean_key not in normalized:
            normalized[clean_key] = value
    return normalized

def _clean_cell_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1].strip()
        return cleaned
    return value


def _normalize_text_for_csv(content: str) -> str:
    text = str(content or "")
    text = text.replace("\x00", "")
    text = text.replace("\u2028", "\n").replace("\u2029", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for sep in ["\x1e", "\x1d", "\x1c", "\x85", "\x0b", "\x0c"]:
        text = text.replace(sep, "\n")
    if "\n" not in text and text.count("\\n") >= 1:
        text = text.replace("\\n", "\n")
    return text


def _detect_delimiter(content: str) -> str:
    lines = [line for line in _normalize_text_for_csv(content).split("\n") if line.strip()]
    first = lines[0] if lines else ""
    return max([",", ";", "\t", "|"], key=lambda delimiter: first.count(delimiter))


def _decode_worker_text(raw_bytes: bytes, is_json: bool = False) -> str:
    if raw_bytes is None:
        return ""

    candidates = []
    for enc in ["utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1"]:
        try:
            decoded = raw_bytes.decode(enc)
        except Exception:
            continue

        replacement_count = decoded.count("�")
        if is_json:
            stripped = decoded.lstrip()
            json_hint = 1 if (stripped.startswith("{") or stripped.startswith("[")) else 0
            score = (json_hint, -replacement_count, len(decoded), -abs(len(raw_bytes) - len(decoded)))
        else:
            normalized = _normalize_text_for_csv(decoded)
            lines = [line for line in normalized.split("\n") if line.strip()]
            first = lines[0] if lines else ""
            max_delim = max([first.count(delimiter) for delimiter in [",", ";", "\t", "|"]], default=0)
            structured = sum(
                1 for line in lines[:500]
                if max([line.count(delimiter) for delimiter in [",", ";", "\t", "|"]], default=0) >= 1
            )
            score = (structured, len(lines), max_delim, -replacement_count)

        candidates.append((score, decoded, enc))

    if not candidates:
        return raw_bytes.decode("utf-8", errors="replace")

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_decoded, best_enc = candidates[0]
    logger.info(f"Worker decodificación seleccionada: {best_enc} score={best_score} bytes={len(raw_bytes)}")
    return best_decoded


def _normalize_remote_host(host: str) -> str:
    normalized = (host or "").strip()
    if normalized.startswith("sftp://"):
        normalized = normalized[len("sftp://"):]
    elif normalized.startswith("ftp://"):
        normalized = normalized[len("ftp://"):]
    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]
    return normalized


def _candidate_hosts(host: str) -> List[str]:
    normalized = _normalize_remote_host(host)
    if not normalized:
        return []
    candidates = [normalized]
    if normalized.startswith("www.") and len(normalized) > 4:
        candidates.append(normalized[4:])
    return candidates


def get_sftp_client(host, port, user, password):
    last_error = None
    for candidate in _candidate_hosts(host):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(candidate, port=int(port), username=user, password=password, timeout=10)
            transport = ssh.get_transport()
            if transport:
                transport.set_keepalive(30)
            return ssh, ssh.open_sftp()
        except Exception as exc:
            last_error = exc
            try:
                ssh.close()
            except Exception:
                pass
            logger.warning(f"SFTP connect failed for host '{candidate}': {exc}")
    if last_error:
        raise last_error
    raise ValueError("Host remoto inválido o vacío para conexión SFTP")

def get_ftp_client(host, port, user, password):
    last_error = None
    for candidate in _candidate_hosts(host):
        ftp = FTP()
        try:
            ftp.connect(candidate, int(port), timeout=10)
            ftp.login(user, password)
            ftp.set_pasv(True)
            return ftp
        except Exception as exc:
            last_error = exc
            try:
                ftp.close()
            except Exception:
                pass
            logger.warning(f"FTP connect failed for host '{candidate}': {exc}")
    if last_error:
        raise last_error
    raise ValueError("Host remoto inválido o vacío para conexión FTP")

def connect_with_retries(connector, attempts=3, base_delay=2):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return connector()
        except Exception as e:
            last_error = e
            if attempt >= attempts:
                break
            delay = base_delay * attempt
            logger.warning(f"Conexión fallida (intento {attempt}/{attempts}): {e}. Reintentando en {delay}s...")
            time.sleep(delay)
    raise last_error

def _normalize_prefix_value(prefix: Optional[str]) -> str:
    value = str(prefix or "").strip()
    return value if value else ""

def _build_marked_filename(filename: str, prefix: str, extra_prefixes: Sequence[str] = ()) -> str:
    base_name = posixpath.basename(str(filename or "").strip())
    if not base_name:
        return base_name

    candidates = [
        AUTO_SUCCESS_PREFIX,
        AUTO_ERROR_PREFIX,
        "PW_",
        *[_normalize_prefix_value(item) for item in extra_prefixes],
    ]
    normalized_candidates = []
    for candidate in candidates:
        if candidate and candidate not in normalized_candidates:
            normalized_candidates.append(candidate)

    upper_name = base_name.upper()
    changed = True
    while changed:
        changed = False
        for candidate in normalized_candidates:
            if not candidate:
                continue
            candidate_upper = candidate.upper()
            if upper_name.startswith(candidate_upper):
                base_name = base_name[len(candidate):]
                upper_name = base_name.upper()
                changed = True
                break

    return f"{prefix}{base_name}"

def _parse_worker_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "si", "sí", "on"}


def _moving_window_enabled(constants: Dict[str, Any]) -> bool:
    return _parse_worker_bool(constants.get("_moving_window_mode"))


def _format_worker_range_date(value: Any) -> Optional[str]:
    parsed = _format_worker_date_for_message(value)
    if parsed:
        return parsed
    normalized = normalize_date(str(value or ""))
    if normalized:
        try:
            return datetime.strptime(normalized, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return normalized
    return None


def _format_moving_window_message(count: int, stats: Dict[str, Any], errors: list) -> str:
    duplicate_skipped = int(stats.get("duplicate_skipped") or 0)
    date_min = _format_worker_range_date(stats.get("date_min"))
    date_max = _format_worker_range_date(stats.get("date_max"))
    range_text = f" Rango detectado: {date_min} - {date_max}." if date_min and date_max else ""
    message = (
        f"Archivo de ventana móvil procesado.{range_text} "
        f"{count} registros nuevos insertados. "
        f"{duplicate_skipped} registros ya existentes omitidos."
    )
    if errors:
        message += f" Se encontraron {len(errors)} errores parciales."
    return message


def _resolve_worker_processing_outcome(count: int, errors: list, stats: Optional[Dict[str, Any]] = None) -> Tuple[str, str, bool]:
    stats = stats or {}
    moving_window_processed = bool(stats.get("moving_window_mode")) and int(stats.get("duplicate_skipped") or 0) > 0
    if isinstance(count, int) and (count > 0 or moving_window_processed):
        estado = "parcial" if errors else "exito"
        mensaje = (
            _format_moving_window_message(count, stats, errors)
            if stats.get("moving_window_mode")
            else f"Worker: Inserción confirmada de {count} registros."
        )
        if errors:
            if not stats.get("moving_window_mode"):
                mensaje += f" Se encontraron {len(errors)} errores parciales."
        return estado, mensaje, True

    if _is_empty_file_outcome(errors):
        return "error", "Archivo leido con 0 Datos", False

    mensaje = "Worker: No se confirmó inserción en BD."
    if errors:
        mensaje += f" Se encontraron {len(errors)} errores."
    else:
        mensaje += " El archivo se marcará con error para revisión."
    return "error", mensaje, False


def _is_empty_file_outcome(errors: Optional[list]) -> bool:
    if not errors:
        return False
    empty_markers = ("archivo vacio", "archivo vacío", "sin datos validos", "sin datos válidos")
    for error in errors:
        text = str((error or {}).get("error") if isinstance(error, dict) else error).strip().lower()
        if all(marker in text for marker in ("archivo", "sin datos")):
            return True
        if any(marker in text for marker in empty_markers):
            return True
    return False


def _unpack_process_file_result(result: Any) -> Tuple[int, list, Dict[str, Any]]:
    if isinstance(result, tuple) and len(result) >= 3:
        return result[0], result[1], result[2] or {}
    if isinstance(result, tuple) and len(result) >= 2:
        return result[0], result[1], {}
    return 0, [{"linea": 0, "error": "Resultado de procesamiento inválido."}], {}


def _format_worker_date_for_message(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(_worker_timezone())
    return parsed.strftime("%d/%m/%Y")


def _last_successful_import_date(config: Dict[str, Any]) -> Optional[str]:
    if not supabase:
        return None
    local_id = str(config.get("id") or "").strip()
    if not local_id:
        return None

    try:
        response = (
            supabase.table("logs_carga")
            .select("fecha_hora,archivo,estado,records_processed")
            .eq("local_id", local_id)
            .order("fecha_hora", desc=True)
            .limit(25)
            .execute()
        )
        for row in response.data or []:
            archivo = str(row.get("archivo") or "").strip()
            estado = str(row.get("estado") or "").strip().lower()
            processed = row.get("records_processed")
            try:
                processed_count = int(processed) if processed is not None else None
            except (TypeError, ValueError):
                processed_count = None

            has_real_file = bool(archivo) and archivo.upper() != "N/A"
            has_success_status = estado in {"exito", "parcial"}
            has_inserted_rows = processed_count is None or processed_count > 0
            if has_real_file and has_success_status and has_inserted_rows:
                formatted = _format_worker_date_for_message(row.get("fecha_hora"))
                if formatted:
                    return formatted
    except Exception as exc:
        logger.warning("No se pudo consultar ultimo archivo importado para %s: %s", local_id, exc)

    return None


def _build_no_new_file_message(config: Dict[str, Any]) -> str:
    last_import_date = _last_successful_import_date(config)
    if last_import_date:
        return f"Archivo nuevo no encontrado, ultimo archivo importado fecha {last_import_date}"
    return "Archivo nuevo no encontrado, sin importaciones previas"


def _normalize_worker_import_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config or {})
    if not normalized.get("mapping_config"):
        normalized["mapping_config"] = normalized.get("mapping") or {}
    if not normalized.get("constants_config"):
        normalized["constants_config"] = normalized.get("constants") or {}
    if not normalized.get("file_type"):
        normalized["file_type"] = normalized.get("tipo_archivo", "CSV")
    return normalized


def _filter_existing_moving_window_rows(
    rows: List[Dict[str, Any]],
    line_numbers: List[int],
    local_id: str,
) -> Tuple[List[Dict[str, Any]], List[int], int]:
    if not rows or not supabase:
        return rows, line_numbers, 0

    factura_values = [
        str(row.get("factura_no") or "").strip()
        for row in rows
        if row.get("factura_no")
    ]
    factura_values = [value for value in factura_values if value]
    if not factura_values:
        return rows, line_numbers, 0

    existing: set[str] = set()
    unique_facturas = list(dict.fromkeys(factura_values))
    chunk_size = 500
    for start in range(0, len(unique_facturas), chunk_size):
        chunk = unique_facturas[start:start + chunk_size]
        try:
            response = (
                supabase.table("ventas")
                .select("factura_no")
                .eq("local_id", local_id)
                .in_("factura_no", chunk)
                .execute()
            )
            for item in response.data or []:
                factura = str(item.get("factura_no") or "").strip()
                if factura:
                    existing.add(factura)
        except Exception as exc:
            logger.warning("No se pudo consultar duplicados de ventana móvil para %s: %s", local_id, exc)
            return rows, line_numbers, 0

    filtered_rows: List[Dict[str, Any]] = []
    filtered_lines: List[int] = []
    seen_in_file: set[str] = set()
    skipped = 0
    for row, line_no in zip(rows, line_numbers):
        factura = str(row.get("factura_no") or "").strip()
        if factura and (factura in existing or factura in seen_in_file):
            skipped += 1
            continue
        if factura:
            seen_in_file.add(factura)
        filtered_rows.append(row)
        filtered_lines.append(line_no)

    return filtered_rows, filtered_lines, skipped


def process_file_logic(config, filename, content):
    """
    Process file content (CSV or JSON) and insert to database.
    """
    config = _normalize_worker_import_config(config)
    logger.info(f"Procesando contenido de {filename} para {config['nombre']}")
    detalles = []
    registros_exito = 0
    stats: Dict[str, Any] = {
        "moving_window_mode": False,
        "duplicate_skipped": 0,
        "date_min": None,
        "date_max": None,
    }
    
    try:
        file_type = config.get("file_type", "CSV").upper()
        raw_records = []
        
        # 1. Parse Content
        if file_type == "JSON":
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    raw_records = data
                elif isinstance(data, dict):
                    # Try to find list inside (common in some exports)
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            raw_records = v
                            break
                    if not raw_records:
                        raw_records = [data] # Single object
                if raw_records:
                    df = pd.json_normalize(raw_records)
                    raw_records = df.where(pd.notnull(df), None).to_dict(orient='records')
            except Exception as e:
                return 0, [{"linea": 0, "error": f"Error parseando JSON: {e}"}], stats
        else:
            # Default to CSV/TXT
            normalized_content = _normalize_text_for_csv(content)
            reader = csv.DictReader(
                io.StringIO(normalized_content),
                delimiter=_detect_delimiter(normalized_content),
                skipinitialspace=True
            )
            raw_records = [_normalize_csv_row_keys(r) for r in reader]
            
        if not raw_records:
            return 0, [{"linea": 0, "error": "Archivo vacío o sin datos válidos"}], stats
            
        # Get store ID and Mall ID
        local_id = config.get('id')
        mall_id = config.get('mall_id')
        
        if not local_id:
            return 0, [{"linea": 0, "error": "No se pudo determinar el local_id"}], stats
        if not mall_id:
            return 0, [{"linea": 0, "error": "La configuración no tiene mall_id. Importación cancelada para evitar mezcla entre malls."}], stats
            
        # Get mapping
        mapping = config.get('mapping_config') or {}
        constants = config.get('constants_config') or config.get('constants') or {}
        decimal_separator = constants.get("_decimal_separator", ".")
        moving_window_mode = _moving_window_enabled(constants)
        stats["moving_window_mode"] = moving_window_mode
        import_cutoff_date = _parse_import_cutoff_date(config.get("fecha_corte_importacion"))
        configured_local_code = (
            config.get('codigo_interno')
            or config.get('local_codigo')
            or config.get('codigo')
            or config.get('nombre')
            or local_id
        )
        
        valid_rows = []
        valid_line_numbers = []

        for i, row in enumerate(raw_records, start=2):
            try:
                normalized_row = _normalize_csv_row_keys(row)
                lowered_row = {k.lower(): v for k, v in normalized_row.items()}

                def pick_value(sys_field, mapped_header, fallback_header=""):
                    constant_value = _clean_cell_value(constants.get(sys_field))
                    if constant_value not in (None, ""):
                        return constant_value
                    key = _clean_csv_header_name(mapped_header)
                    if key and key in normalized_row:
                        return _clean_cell_value(normalized_row[key])
                    if key and key.lower() in lowered_row:
                        return _clean_cell_value(lowered_row[key.lower()])
                    fallback = _clean_csv_header_name(fallback_header)
                    if fallback and fallback in normalized_row:
                        return _clean_cell_value(normalized_row[fallback])
                    if fallback and fallback.lower() in lowered_row:
                        return _clean_cell_value(lowered_row[fallback.lower()])
                    return ""

                # Map fields using mapping_config
                # mapping_config usually translates system_field -> file_header
                fecha_venta_raw = pick_value('fecha_venta', mapping.get('fecha_venta', 'fecha_venta'), 'fecha')
                factura_no = pick_value('factura_numero', mapping.get('factura_numero', 'factura_numero'), 'factura_no')
                
                # Check for direct key matches if mapping fails
                fecha_venta = normalize_date(fecha_venta_raw)
                
                if fecha_venta_raw and not fecha_venta:
                     detalles.append({"linea": i, "error": f"Formato de fecha inválido: {fecha_venta_raw}"})
                     continue

                if _is_import_date_closed(fecha_venta, import_cutoff_date):
                    detalles.append({
                        "linea": i,
                        "error": f"Fecha {fecha_venta} pertenece a un periodo cerrado (cierre hasta {import_cutoff_date})."
                    })
                    continue

                def resolve_transform_value(part: str) -> str:
                    clean_part = str(part or "").strip()
                    if clean_part in ("numero_registro", "linea", "_line_number"):
                        return f"{i - 1:04d}"
                    if clean_part == "local_codigo":
                        return str(configured_local_code or "")
                    if clean_part == "fecha_venta" and fecha_venta:
                        return fecha_venta.replace("-", "")

                    if clean_part in mapping:
                        return str(pick_value(mapping.get(clean_part), clean_part) or "")

                    return str(pick_value(clean_part, clean_part) or "")

                transform_mode = constants.get("_factura_numero_mode")
                if transform_mode == "generated_sequence":
                    factura_no = _format_generated_invoice(configured_local_code, fecha_venta, i - 1)
                elif transform_mode == "concat":
                    transform_fields = _split_transform_fields(constants.get("_factura_numero_concat_fields"))
                    separator = str(constants.get("_factura_numero_concat_separator", "-"))
                    values = [
                        _clean_generated_invoice_piece(resolve_transform_value(part))
                        for part in transform_fields
                    ]
                    values = [value for value in values if value]
                    if values:
                        factura_no = separator.join(values)

                # Normalización Numérica
                def clean_float(val):
                    return _parse_mapped_decimal(val, decimal_separator)

                total_bruto = clean_float(pick_value('total_bruto', mapping.get('total_bruto', 'total_bruto')))
                total_impuestos = clean_float(pick_value('total_impuestos', mapping.get('total_impuestos', 'total_impuestos')))
                total_neto = clean_float(pick_value('total_neto', mapping.get('total_neto', 'total_neto')))
                
                if not fecha_venta or total_bruto == 0:
                    detalles.append({"linea": i, "error": "Datos incompletos (Fecha o Total Bruto faltante/cero)"})
                    continue

                if moving_window_mode and not factura_no:
                    detalles.append({"linea": i, "error": "Datos incompletos (ID_Documento o No. Factura faltante)"})
                    continue
                
                payload = {
                    "local_id": local_id,
                    "fecha": fecha_venta,
                    "factura_no": str(factura_no) if factura_no else None,
                    "total_bruto": total_bruto,
                    "total_impuestos": total_impuestos,
                    "total_neto": total_neto
                }
                
                if mall_id:
                    payload["mall_id"] = mall_id

                valid_rows.append(payload)
                valid_line_numbers.append(i)
                if fecha_venta:
                    stats["date_min"] = min(stats["date_min"], fecha_venta) if stats["date_min"] else fecha_venta
                    stats["date_max"] = max(stats["date_max"], fecha_venta) if stats["date_max"] else fecha_venta
                
            except Exception as e:
                detalles.append({"linea": i, "error": str(e)})
                logger.error(f"Error en línea {i}: {e}")

        if moving_window_mode and valid_rows:
            valid_rows, valid_line_numbers, duplicate_skipped = _filter_existing_moving_window_rows(
                valid_rows,
                valid_line_numbers,
                local_id,
            )
            stats["duplicate_skipped"] = duplicate_skipped
            if duplicate_skipped:
                logger.info(
                    "%s: ventana móvil omitió %s registros existentes en %s",
                    config.get("nombre"),
                    duplicate_skipped,
                    filename,
                )

        # Bulk insert for better throughput; fallback to row insert if a chunk fails.
        BATCH_SIZE = 500
        for start in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[start:start + BATCH_SIZE]
            lines = valid_line_numbers[start:start + BATCH_SIZE]
            try:
                supabase.table("ventas").insert(batch).execute()
                registros_exito += len(batch)
            except Exception as batch_error:
                logger.warning(f"Batch insert failed for {filename} ({len(batch)} rows): {batch_error}. Falling back to row-level inserts.")
                for payload, line_no in zip(batch, lines):
                    try:
                        supabase.table("ventas").insert(payload).execute()
                        registros_exito += 1
                    except Exception as row_error:
                        detalles.append({"linea": line_no, "error": str(row_error)})
                        logger.error(f"Error insertando línea {line_no}: {row_error}")
                
    except Exception as e:
        logger.error(f"Error general procesando archivo: {e}")
        return 0, [{"linea": 0, "error": str(e)}], stats
            
    return registros_exito, detalles, stats

def process_local_files(config):
    protocol = config.get("sftp_protocol", "SFTP")
    host = config.get("sftp_host")
    port = config.get("sftp_port", 22)
    user = config.get("sftp_user")
    password = config.get("sftp_pass")
    remote_path = config.get("sftp_path", ".")
    file_type = config.get("file_type", "CSV")
    post_action = config.get("accion_post_procesado", "NINGUNA")
    backup_prefix = config.get("prefijo_backup", "PR_")
    custom_backup_prefix = _normalize_prefix_value(backup_prefix)

    ext = f".{file_type.lower()}"
    processed_suffix = ".procesado"
    max_files_per_batch = MAX_FILES_PER_BATCH
    processed_count = 0
    file_errors = 0
    total_pending = 0
    batch_size = 0
    last_error_details = []
    last_error_message = ""

    def _result(ok: bool, message: str) -> Dict[str, Any]:
        return {
            "ok": ok,
            "message": message,
            "processed_files": processed_count,
            "failed_files": file_errors,
            "total_pending": total_pending,
            "batch_size": batch_size,
            "details": last_error_details,
        }

    logger.info(f"Conectando a {config['nombre']} ({protocol}) en {host}...")

    if protocol == "SFTP":
        try:
            ssh, sftp = connect_with_retries(lambda: get_sftp_client(host, port, user, password))
        except Exception as ce:
            message = f"Fallo conexión SFTP: {str(ce)}"
            insert_load_log(
                config['nombre'], "N/A", "error", message,
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal=protocol,
                records_processed=0,
                error_count=1,
                metadata={"source": "worker_auto_import", "connection_error": str(ce)},
            )
            return _result(False, message)

        try:
            try:
                st = sftp.stat(remote_path)
                if not stat.S_ISDIR(st.st_mode):
                    remote_path = posixpath.dirname(remote_path) or "."
            except Exception:
                pass

            items = sftp.listdir_attr(remote_path)
            pending_files = []

            for item in items:
                if stat.S_ISDIR(item.st_mode):
                    continue

                filename = item.filename
                is_processed = processed_suffix in filename
                is_backup = (
                    (custom_backup_prefix and filename.startswith(custom_backup_prefix))
                    or filename.startswith(AUTO_SUCCESS_PREFIX)
                    or filename.startswith(AUTO_ERROR_PREFIX)
                    or filename.startswith("PW_")
                )
                is_match = filename.lower().endswith(ext)
                is_error = ".error" in filename

                if is_match and not is_processed and not is_backup and not is_error:
                    pending_files.append(item)

            pending_files.sort(key=lambda x: x.st_mtime)
            total_pending = len(pending_files)
            batch_files = pending_files[:max_files_per_batch]
            batch_size = len(batch_files)

            if total_pending == 0:
                logger.info(f"📍 {config['nombre']}: No hay archivos pendientes.")
                message = _build_no_new_file_message(config)
                insert_load_log(
                    config['nombre'], "N/A", "exito", message,
                    mall_id=config.get("mall_id"),
                    local_id=config.get("id"),
                    canal=protocol,
                    records_processed=0,
                    error_count=0,
                    metadata={"source": "worker_auto_import", "pending_files": 0, "reason": "no_new_file"},
                )
                return _result(True, message)

            logger.info(f"🚀 {config['nombre']}: Encontrados {total_pending} pendientes. Procesando lote de {batch_size}.")

            for item in batch_files:
                filename = item.filename
                batch_id = str(uuid.uuid4())
                logger.info(f"🔄 [{processed_count + 1}/{batch_size}] Procesando SFTP: {filename}")

                try:
                    with sftp.open(f"{remote_path}/{filename}", 'rb') as f:
                        content = _decode_worker_text(
                            f.read(),
                            is_json=str(filename or "").lower().endswith(".json")
                        )
                    count, errors, stats = _unpack_process_file_result(
                        process_file_logic(config, filename, content)
                    )

                    estado, mensaje, insert_confirmed = _resolve_worker_processing_outcome(count, errors, stats)

                    if insert_confirmed:
                        insert_load_log(
                            config['nombre'], filename, estado, mensaje, batch_id, errors,
                            mall_id=config.get("mall_id"),
                            local_id=config.get("id"),
                            canal=protocol,
                            records_processed=count,
                            error_count=len(errors or []),
                            metadata={"source": "worker_auto_import", **(stats or {})},
                        )
                        if post_action == "RENOMBRAR_BACKUP":
                            handle_post_process_sftp(
                                sftp,
                                remote_path,
                                filename,
                                post_action,
                                processed_suffix,
                                AUTO_SUCCESS_PREFIX,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                        else:
                            handle_post_process_sftp(
                                sftp,
                                remote_path,
                                filename,
                                post_action,
                                processed_suffix,
                                custom_backup_prefix,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                    else:
                        file_errors += 1
                        last_error_message = mensaje
                        last_error_details = list(errors or [])
                        logger.error(f"❌ Error validando archivo {filename}: {mensaje}")
                        insert_load_log(
                            config['nombre'], filename, "error", mensaje, batch_id, errors,
                            mall_id=config.get("mall_id"), local_id=config.get("id")
                        )
                        try:
                            handle_post_process_sftp(
                                sftp,
                                remote_path,
                                filename,
                                "RENOMBRAR_BACKUP",
                                processed_suffix,
                                AUTO_ERROR_PREFIX,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                        except Exception:
                            pass
                        continue

                    processed_count += 1

                except Exception as fe:
                    file_errors += 1
                    last_error_message = str(fe)
                    last_error_details = []
                    logger.error(f"❌ Error crítico en archivo {filename}: {fe}")
                    insert_load_log(
                        config['nombre'], filename, "error", str(fe), batch_id,
                        mall_id=config.get("mall_id"),
                        local_id=config.get("id"),
                        canal=protocol,
                        records_processed=0,
                        error_count=1,
                        metadata={"source": "worker_auto_import", "exception": str(fe)},
                    )
                    try:
                        handle_post_process_sftp(
                            sftp,
                            remote_path,
                            filename,
                            "RENOMBRAR_BACKUP",
                            processed_suffix,
                            AUTO_ERROR_PREFIX,
                            strip_prefixes=(custom_backup_prefix,)
                        )
                    except: pass
            logger.info(f"✅ {config['nombre']}: Lote completado. {processed_count}/{batch_size} archivos procesados exitosamente.")
            if processed_count > 0:
                run_local_risk_analysis_if_possible(config, trigger="worker_auto_import")

        finally:
            if 'sftp' in locals():
                sftp.close()
            if 'ssh' in locals():
                ssh.close()

    elif protocol == "FTP":
        try:
            ftp = connect_with_retries(lambda: get_ftp_client(host, port, user, password))
        except Exception as ce:
            message = f"Fallo conexión FTP: {str(ce)}"
            insert_load_log(
                config['nombre'], "N/A", "error", message,
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal=protocol,
                records_processed=0,
                error_count=1,
                metadata={"source": "worker_auto_import", "connection_error": str(ce)},
            )
            return _result(False, message)

        try:
            try:
                ftp.cwd(remote_path)
            except Exception:
                remote_path_parent = posixpath.dirname(remote_path) or "."
                try:
                    ftp.cwd(remote_path_parent)
                except Exception:
                    pass

            pending_files = []
            for filename in ftp.nlst():
                is_processed = processed_suffix in filename
                is_backup = (
                    (custom_backup_prefix and filename.startswith(custom_backup_prefix))
                    or filename.startswith(AUTO_SUCCESS_PREFIX)
                    or filename.startswith(AUTO_ERROR_PREFIX)
                    or filename.startswith("PW_")
                )
                is_match = filename.lower().endswith(ext)
                is_error = ".error" in filename

                if is_match and not is_processed and not is_backup and not is_error:
                    pending_files.append(filename)

            pending_files.sort()
            total_pending = len(pending_files)
            batch_files = pending_files[:max_files_per_batch]
            batch_size = len(batch_files)

            if total_pending == 0:
                logger.info(f"📍 {config['nombre']}: No hay archivos pendientes.")
                message = _build_no_new_file_message(config)
                insert_load_log(
                    config['nombre'], "N/A", "exito", message,
                    mall_id=config.get("mall_id"),
                    local_id=config.get("id"),
                    canal=protocol,
                    records_processed=0,
                    error_count=0,
                    metadata={"source": "worker_auto_import", "pending_files": 0, "reason": "no_new_file"},
                )
                return _result(True, message)

            logger.info(f"🚀 {config['nombre']}: Encontrados {total_pending} pendientes. Procesando lote de {batch_size}.")

            for filename in batch_files:
                batch_id = str(uuid.uuid4())
                logger.info(f"🔄 [{processed_count + 1}/{batch_size}] Procesando FTP: {filename}")

                try:
                    bio = io.BytesIO()
                    ftp.retrbinary(f"RETR {filename}", bio.write)
                    bio.seek(0)
                    content = _decode_worker_text(
                        bio.read(),
                        is_json=str(filename or "").lower().endswith(".json")
                    )
                    count, errors, stats = _unpack_process_file_result(
                        process_file_logic(config, filename, content)
                    )

                    estado, mensaje, insert_confirmed = _resolve_worker_processing_outcome(count, errors, stats)

                    if insert_confirmed:
                        insert_load_log(
                            config['nombre'], filename, estado, mensaje, batch_id, errors,
                            mall_id=config.get("mall_id"),
                            local_id=config.get("id"),
                            canal=protocol,
                            records_processed=count,
                            error_count=len(errors or []),
                            metadata={"source": "worker_auto_import", **(stats or {})},
                        )
                        if post_action == "RENOMBRAR_BACKUP":
                            handle_post_process_ftp(
                                ftp,
                                filename,
                                post_action,
                                processed_suffix,
                                AUTO_SUCCESS_PREFIX,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                        else:
                            handle_post_process_ftp(
                                ftp,
                                filename,
                                post_action,
                                processed_suffix,
                                custom_backup_prefix,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                    else:
                        file_errors += 1
                        last_error_message = mensaje
                        last_error_details = list(errors or [])
                        logger.error(f"❌ Error validando archivo {filename}: {mensaje}")
                        insert_load_log(
                            config['nombre'], filename, "error", mensaje, batch_id, errors,
                            mall_id=config.get("mall_id"), local_id=config.get("id")
                        )
                        try:
                            handle_post_process_ftp(
                                ftp,
                                filename,
                                "RENOMBRAR_BACKUP",
                                processed_suffix,
                                AUTO_ERROR_PREFIX,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                        except Exception:
                            pass
                        continue

                    processed_count += 1

                except Exception as fe:
                    file_errors += 1
                    last_error_message = str(fe)
                    last_error_details = []
                    logger.error(f"❌ Error crítico en archivo {filename}: {fe}")
                    insert_load_log(
                        config['nombre'], filename, "error", str(fe), batch_id,
                        mall_id=config.get("mall_id"),
                        local_id=config.get("id"),
                        canal=protocol,
                        records_processed=0,
                        error_count=1,
                        metadata={"source": "worker_auto_import", "exception": str(fe)},
                    )
                    try:
                        handle_post_process_ftp(
                            ftp,
                            filename,
                            "RENOMBRAR_BACKUP",
                            processed_suffix,
                            AUTO_ERROR_PREFIX,
                            strip_prefixes=(custom_backup_prefix,)
                        )
                    except: pass
            logger.info(f"✅ {config['nombre']}: Lote completado. {processed_count}/{batch_size} archivos procesados exitosamente.")
            if processed_count > 0:
                run_local_risk_analysis_if_possible(config, trigger="worker_auto_import")
        finally:
            if 'ftp' in locals():
                ftp.quit()

    else:
        message = f"Protocolo no soportado: {protocol}"
        logger.error(message)
        return _result(False, message)

    ok = total_pending == 0 or processed_count > 0
    message = (
        f"Lote completado: {processed_count}/{batch_size} archivos procesados."
        if batch_size
        else "Sin archivos para procesar."
    )
    if not ok and last_error_message:
        message = f"{message} {last_error_message}"
    return _result(ok, message)

def handle_post_process_sftp(sftp, path, filename, action, suffix, prefix="", strip_prefixes: Sequence[str] = ()):
    full_path = f"{path}/{filename}"
    if action == "ELIMINAR":
        logger.info(f"Eliminando archivo remoto: {filename}")
        sftp.remove(full_path)
    elif action == "RENOMBRAR_PROCESADO":
        new_name = f"{full_path}{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Renombrando archivo remoto a: {new_name}")
        sftp.rename(full_path, new_name)
    elif action == "RENOMBRAR_BACKUP":
        new_filename = _build_marked_filename(filename, prefix, strip_prefixes)
        new_full_path = f"{path}/{new_filename}"
        logger.info(f"Renombrando (Backup) archivo remoto a: {new_full_path}")
        sftp.rename(full_path, new_full_path)

def handle_post_process_ftp(ftp, filename, action, suffix, prefix="", strip_prefixes: Sequence[str] = ()):
    if action == "ELIMINAR":
        logger.info(f"Eliminando archivo remoto FTP: {filename}")
        ftp.delete(filename)
    elif action == "RENOMBRAR_PROCESADO":
        new_name = f"{filename}{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Renombrando archivo remoto FTP a: {new_name}")
        ftp.rename(filename, new_name)
    elif action == "RENOMBRAR_BACKUP":
        new_name = _build_marked_filename(filename, prefix, strip_prefixes)
        logger.info(f"Renombrando (Backup) archivo remoto FTP a: {new_name}")
        ftp.rename(filename, new_name)

# --- ASYNC LOGIC ---

async def mark_local_status(local_id: str, status: str):
    """Updates the processing status of a local."""
    try:
        payload = {
            "processing_status": status
        }
        if status == 'BUSY':
            payload["processing_started_at"] = datetime.now(_worker_timezone()).isoformat()
        elif status == 'IDLE':
            payload["ultima_ejecucion"] = datetime.now(_worker_timezone()).isoformat()
            
        await asyncio.to_thread(
            lambda: supabase.table("locales").update(payload).eq("id", local_id).execute()
        )
    except Exception as e:
        logger.error(f"Failed to update status {status} for local {local_id}: {e}")

def _sanitize_health_error(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > 500:
        text = f"{text[:497]}..."
    return text or "unknown_error"


async def _upsert_system_health_value(key: str, value: str):
    if not supabase:
        return
    now_utc = datetime.now(timezone.utc)
    await asyncio.to_thread(
        lambda: supabase.table("system_health").upsert({
            "key": key,
            "value": value,
            "last_update": now_utc.isoformat()
        }).execute()
    )

async def update_heartbeat():
    """Updates the system_health table with current timestamp (UTC)."""
    try:
        now_utc = datetime.now(timezone.utc)
        await _upsert_system_health_value("CRON_LAST_RUN", now_utc.isoformat())
    except Exception as e:
        logger.error(f"Error updating heartbeat: {e}")

async def update_cron_success():
    try:
        now_utc = datetime.now(timezone.utc)
        await _upsert_system_health_value("CRON_LAST_SUCCESS", now_utc.isoformat())
    except Exception as e:
        logger.error(f"Error updating CRON_LAST_SUCCESS: {e}")

async def update_cron_error(error: object):
    try:
        await _upsert_system_health_value("CRON_LAST_ERROR", _sanitize_health_error(error))
    except Exception as e:
        logger.error(f"Error updating CRON_LAST_ERROR: {e}")

async def clear_cron_error():
    try:
        await _upsert_system_health_value("CRON_LAST_ERROR", "")
    except Exception as e:
        logger.error(f"Error clearing CRON_LAST_ERROR: {e}")

async def run_connection_monitor_nightly_if_due():
    if not supabase:
        return {"executed": False, "reason": "supabase_not_configured"}
    if ConnectionMonitorService is None:
        return {"executed": False, "reason": "service_unavailable"}
    try:
        result = await asyncio.to_thread(_connection_monitor_service().run_nightly_monitor_if_due)
        if result.get("executed"):
            summary = (result.get("summary") or {})
            logger.info(
                "🔎 Connection monitor nightly executed total=%s ok=%s fail=%s partial=%s",
                summary.get("total", 0),
                summary.get("ok", 0),
                summary.get("fail", 0),
                summary.get("partial", 0),
            )
        else:
            logger.info("🔎 Connection monitor nightly skipped: %s", result.get("reason"))
        return result
    except Exception as e:
        logger.error(f"Connection monitor nightly failed: {sanitize_error_text(e)}")
        return {"executed": False, "reason": "error", "error": sanitize_error_text(e)}

async def run_missing_days_email_scheduler_if_due():
    if not supabase:
        return {"executed": False, "reason": "supabase_not_configured"}
    if run_missing_days_email_scheduler is None:
        return {"executed": False, "reason": "service_unavailable"}
    try:
        result = await asyncio.to_thread(
            lambda: run_missing_days_email_scheduler(supabase, logger=logger)
        )
        if result.get("executed"):
            logger.info("📬 Missing-days email scheduler executed: %s", result.get("runs"))
        else:
            logger.info("📬 Missing-days email scheduler skipped: %s", result)
        return result
    except Exception as e:
        logger.error(f"Missing-days email scheduler failed: {sanitize_error_text(e)}")
        return {"executed": False, "reason": "error", "error": sanitize_error_text(e)}

async def process_local_safe(local, semaphore, host_semaphore, due_at: Optional[datetime] = None):
    """
    Wraps the synchronous process_local_files in a semaphore and async thread,
    handling DB locking/unlocking and Circuit Breaker.
    """
    local_name = local.get('nombre', 'Unknown')
    consecutive_failures = local.get('consecutive_failures', 0)
    status = local.get('processing_status')

    if status == 'SUSPENDED_AUTH_ERROR':
         logger.warning(f"⛔ [Skipped] {local_name} is SUSPENDED due to auth errors.")
         return

    if consecutive_failures >= 5:
         logger.error(f"⛔ [Suspend] {local_name} reached 5 consecutive failures. Suspending...")
         await mark_local_status(local['id'], 'SUSPENDED_AUTH_ERROR')
         return

    async with semaphore:
        async with host_semaphore:
            logger.info(
                "🔒 [Lock] Locking %s (Status: BUSY, host=%s, due_at=%s)",
                local_name,
                _host_key(local),
                due_at.isoformat() if due_at else "now",
            )
            await mark_local_status(local['id'], 'BUSY')

            try:
                logger.info(f"🚀 [Start] Processing {local_name}...")
                result = await asyncio.to_thread(process_local_files, local)
                if not isinstance(result, dict):
                    result = {"ok": False, "message": "Resultado inválido del worker."}

                if result.get("ok"):
                    logger.info(f"✅ [Done] Finished {local_name}: {result.get('message', 'ok')}")
                    await asyncio.to_thread(
                        lambda: supabase.table("locales").update({"consecutive_failures": 0}).eq("id", local['id']).execute()
                    )
                else:
                    error_text = result.get("message") or "Falló la corrida automática."
                    logger.error(f"❌ [Error] Processing {local_name}: {error_text}")
                    insert_load_log(
                        local_name, "SYSTEM", "error", f"Async processing failed: {error_text}",
                        detalles=result.get("details"),
                        mall_id=local.get("mall_id"),
                        local_id=local.get("id"),
                        canal=local.get("sftp_protocol"),
                        records_processed=0,
                        error_count=max(1, len(result.get("details") or [])),
                        metadata={"source": "worker_async_wrapper", "result": result},
                    )
                    new_failures = consecutive_failures + 1
                    await asyncio.to_thread(
                         lambda: supabase.table("locales").update({"consecutive_failures": new_failures}).eq("id", local['id']).execute()
                    )

            except Exception as e:
                logger.error(f"❌ [Error] Processing {local_name}: {e}")
                insert_load_log(
                    local_name, "SYSTEM", "error", f"Async processing failed: {str(e)}",
                    mall_id=local.get("mall_id"),
                    local_id=local.get("id"),
                    canal=local.get("sftp_protocol"),
                    records_processed=0,
                    error_count=1,
                    metadata={"source": "worker_async_wrapper", "exception": str(e)},
                )

                new_failures = consecutive_failures + 1
                await asyncio.to_thread(
                     lambda: supabase.table("locales").update({"consecutive_failures": new_failures}).eq("id", local['id']).execute()
                )

            finally:
                logger.info(f"🔓 [Release] Unlocking {local_name} (Status: IDLE)")
                await mark_local_status(local['id'], 'IDLE')

async def cleanup_zombies():
    """Reset locales that have been stuck in BUSY for more than 2 hours."""
    try:
        logger.info("🧟 Checking for Zombie processes...")
        
        response = supabase.table("locales").select("*").eq("processing_status", "BUSY").execute()
        zombies = response.data or []
        
        count = 0
        for z in zombies:
            started_at_str = z.get('processing_started_at')
            if not started_at_str:
                is_zombie = True
            else:
                try:
                    started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    now = datetime.now(started.tzinfo) 
                    diff = now - started
                    is_zombie = diff.total_seconds() > 7200 # 2 hours
                except:
                   is_zombie = True
            
            if is_zombie:
                 logger.warning(f"🧟 Resetting ZOMBIE local: {z.get('nombre')} (Stuck since {started_at_str})")
                 supabase.table("locales").update({
                     "processing_status": "IDLE"
                 }).eq("id", z['id']).execute()
                 count += 1
                 
        if count > 0:
            logger.info(f"✨ Cleaned up {count} zombie locks.")
        else:
            logger.info("✅ No zombies found.")
            
    except Exception as e:
        logger.error(f"Error cleaning zombies: {e}")

async def run_worker_async():
    logger.info("🚀 Iniciando Worker de Importación (Async/Concurrent v2)...")
    if not supabase:
        logger.error(
            "Worker skipped: Supabase client not initialized. Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
        return
    
    # 1. Reset Zombies & Heartbeat
    await cleanup_zombies()
    await update_heartbeat()
    
    try:
        response = supabase.table("locales")\
            .select("*")\
            .eq("tipo_ejecucion", "AUTOMATICO")\
            .eq("processing_status", "IDLE")\
            .execute()

        locales = [loc for loc in (response.data or []) if loc.get("mall_id")]
        now = _now_local()
        scheduled_locals = []

        for local in locales:
            due_at = _schedule_due_at(local, now)
            if due_at is None:
                continue
            scheduled_locals.append((
                due_at,
                _stable_offset_minutes(local, 59),
                _host_key(local),
                local,
            ))

        if not scheduled_locals:
            logger.info("😴 No active tasks for this scheduling window.")
            await run_missing_days_email_scheduler_if_due()
            await run_connection_monitor_nightly_if_due()
            await update_cron_success()
            await clear_cron_error()
            return

        scheduled_locals.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                str(item[3].get("nombre") or ""),
            )
        )

        logger.info(
            "📋 Encolados %s locales para ejecución (poll=%ss, max_workers=%s, per_host=%s).",
            len(scheduled_locals),
            WORKER_POLL_SECONDS,
            MAX_CONCURRENT_WORKERS,
            MAX_CONCURRENT_PER_HOST,
        )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        host_semaphores: Dict[str, asyncio.Semaphore] = {}
        tasks = []
        for due_at, _rank, host_key, local in scheduled_locals:
            host_semaphore = host_semaphores.setdefault(host_key, asyncio.Semaphore(MAX_CONCURRENT_PER_HOST))
            tasks.append(process_local_safe(local, semaphore, host_semaphore, due_at))
        await asyncio.gather(*tasks)

        logger.info("🏁 Cycle finished.")
        await run_missing_days_email_scheduler_if_due()
        await run_connection_monitor_nightly_if_due()
        await update_cron_success()
        await clear_cron_error()

    except Exception as e:
        logger.error(f"Critical error in main loop: {e}")
        await update_cron_error(e)

if __name__ == "__main__":
    asyncio.run(run_worker_async())
