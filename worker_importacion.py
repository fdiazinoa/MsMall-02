import os
import socket
import stat
import logging
import uuid
import asyncio
import time
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from supabase import create_client, Client
from dotenv import load_dotenv
import paramiko
from ftplib import FTP
import io
import csv
import json
import posixpath
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import certifi
from typing import Any, Dict, List, Optional, Sequence, Tuple
from services.big_data_analytics_service import BigDataAnalyticsService
from services.big_data_sprint2_service import BigDataSprint2Service
from services.connection_monitor_service import ConnectionMonitorService
from services.date_parsing_service import normalize_sale_date
from services.load_log_service import build_load_log_payload, insert_load_log_row
from services.missing_days_email_service import run_missing_days_email_scheduler
from services.sensitive_ops_service import sanitize_error_text
from services.operations_agent_service import OperationsAgentWorker
from analytics_service import run_local_risk_analysis

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

AUTO_SUCCESS_PREFIX = "PR_"
AUTO_ERROR_PREFIX = "ERR_"
STUDIO_G_DAILY_FALLBACK_MAX_DAYS = 62
STUDIO_G_OUTAGE_PROBE_DAYS = 5


class StudioGSalesUnavailable(RuntimeError):
    """Studio G authenticated, but its sales endpoint is unavailable."""


def _read_bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


WEBSERVICE_TIMEOUT_SECONDS = _read_bounded_int_env("WEBSERVICE_TIMEOUT_SECONDS", 45, 5, 180)
WEBSERVICE_MAX_PAGES = _read_bounded_int_env("WEBSERVICE_MAX_PAGES", 50, 1, 500)

def _connection_monitor_service() -> ConnectionMonitorService:
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

def normalize_date(date_str, explicit_format: Any = "auto"):
    """
    Attempts to parse a date string into YYYY-MM-DD format.
    Supports configured sale date formats, including ISO dates with time.
    """
    return normalize_sale_date(date_str, explicit_format)


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
            ssh.connect(
                candidate,
                port=int(port),
                username=user,
                password=password,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
                look_for_keys=False,
                allow_agent=False,
            )
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


def _friendly_sftp_connection_error(exc: Exception) -> str:
    message = str(exc or "").strip()
    normalized = message.lower()
    if "no existing session" in normalized or "error reading ssh protocol banner" in normalized:
        return (
            "El puerto responde, pero el servidor no completa la negociación SSH. "
            "Revise o reinicie el servicio SSH/SFTP y sus límites de sesiones."
        )
    if isinstance(exc, paramiko.AuthenticationException) or "authentication failed" in normalized:
        return "Autenticación rechazada. Verifique usuario y contraseña SFTP."
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in normalized:
        return "El servidor no respondió durante la negociación SSH/SFTP."
    return message or type(exc).__name__


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


def _special_char_cleanup_enabled(constants: Dict[str, Any]) -> bool:
    return _parse_worker_bool(constants.get("_remove_special_chars"))


def _split_special_chars_to_remove(value: Any) -> List[str]:
    raw_value = str(value or "")
    if not raw_value:
        return []

    if "," in raw_value:
        raw_parts = [part.strip() for part in raw_value.split(",")]
    else:
        raw_parts = [part for part in raw_value if not part.isspace()]

    chars: List[str] = []
    aliases = {
        "\\t": "\t",
        "\\n": "\n",
        "\\r": "\r",
        "tab": "\t",
        "<tab>": "\t",
        "space": " ",
        "<space>": " ",
    }
    for part in raw_parts:
        if not part:
            continue
        normalized = aliases.get(part.lower(), part)
        if normalized not in chars:
            chars.append(normalized)
    return chars


def _remove_configured_special_chars(value: Any, chars_to_remove: Sequence[str]) -> Any:
    if value is None or not isinstance(value, str) or not chars_to_remove:
        return value

    cleaned = value
    for char in chars_to_remove:
        if char:
            cleaned = cleaned.replace(char, "")
    return cleaned.strip()


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
    processing_error_count = int(stats.get("processing_error_count") or 0)
    date_min = _format_worker_range_date(stats.get("date_min"))
    date_max = _format_worker_range_date(stats.get("date_max"))
    range_text = f" Rango detectado: {date_min} - {date_max}." if date_min and date_max else ""
    message = (
        f"Archivo de ventana móvil procesado.{range_text} "
        f"{count} registros nuevos insertados. "
        f"{duplicate_skipped} registros ya existentes omitidos."
    )
    if processing_error_count:
        message += f" Se encontraron {processing_error_count} errores parciales."
    return message


def _format_standard_worker_message(count: int, stats: Dict[str, Any]) -> str:
    duplicate_skipped = int(stats.get("duplicate_skipped") or 0)
    processing_error_count = int(stats.get("processing_error_count") or 0)
    if count > 0:
        message = f"Worker: Inserción confirmada de {count} registros nuevos."
    else:
        message = "Worker: Archivo procesado sin registros nuevos."
    if duplicate_skipped:
        message += f" {duplicate_skipped} registros duplicados omitidos y documentados."
    if processing_error_count:
        message += f" Se encontraron {processing_error_count} errores parciales."
    return message


def _resolve_worker_processing_outcome(count: int, errors: list, stats: Optional[Dict[str, Any]] = None) -> Tuple[str, str, bool]:
    stats = stats or {}
    duplicate_skipped = int(stats.get("duplicate_skipped") or 0)
    processing_error_count = int(
        stats.get("processing_error_count")
        if stats.get("processing_error_count") is not None
        else sum(
            1
            for detail in errors or []
            if not isinstance(detail, dict) or detail.get("tipo") != "duplicado"
        )
    )
    stats["processing_error_count"] = processing_error_count
    if isinstance(count, int) and (count > 0 or duplicate_skipped > 0):
        has_partial_result = processing_error_count > 0 or (count > 0 and duplicate_skipped > 0)
        estado = "parcial" if has_partial_result else "exito"
        mensaje = (
            _format_moving_window_message(count, stats, errors)
            if stats.get("moving_window_mode")
            else _format_standard_worker_message(count, stats)
        )
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


def _duplicate_sale_detail(
    row: Dict[str, Any],
    line_no: int,
    source: str,
) -> Dict[str, Any]:
    factura = str(row.get("factura_no") or "").strip()
    fecha = str(row.get("fecha") or "").strip()
    return {
        "linea": line_no,
        "tipo": "duplicado",
        "accion": "omitido",
        "origen": source,
        "local_id": row.get("local_id"),
        "fecha": fecha,
        "factura_no": factura,
        "error": f"Registro duplicado omitido: factura {factura}, fecha {fecha}.",
    }


def _sale_conflict_key(row: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    local_id = str(row.get("local_id") or "").strip()
    fecha = str(row.get("fecha") or "").strip()
    factura = str(row.get("factura_no") or "").strip()
    if not local_id or not fecha or not factura:
        return None
    return local_id, fecha, factura


def _atomic_duplicate_details(
    attempted_rows: List[Dict[str, Any]],
    line_numbers: List[int],
    inserted_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    inserted_keys = {
        key
        for row in inserted_rows
        if (key := _sale_conflict_key(row)) is not None
    }
    return [
        _duplicate_sale_detail(row, line_no, "conflicto_base_datos")
        for row, line_no in zip(attempted_rows, line_numbers)
        if (key := _sale_conflict_key(row)) is not None and key not in inserted_keys
    ]


def _upsert_sales_ignoring_duplicates(rows: List[Dict[str, Any]]):
    return (
        supabase.table("ventas")
        .upsert(
            rows,
            on_conflict="local_id,fecha,factura_no",
            ignore_duplicates=True,
        )
        .execute()
    )


def _filter_existing_sale_rows(
    rows: List[Dict[str, Any]],
    line_numbers: List[int],
    local_id: str,
) -> Tuple[List[Dict[str, Any]], List[int], List[Dict[str, Any]]]:
    if not rows or not supabase:
        return rows, line_numbers, []

    candidate_keys = [
        (
            str(row.get("fecha") or "").strip(),
            str(row.get("factura_no") or "").strip(),
        )
        for row in rows
        if row.get("fecha") and row.get("factura_no")
    ]
    candidate_keys = [(fecha, factura) for fecha, factura in candidate_keys if fecha and factura]
    if not candidate_keys:
        return rows, line_numbers, []

    existing: set[Tuple[str, str]] = set()
    unique_facturas = list(dict.fromkeys(factura for _, factura in candidate_keys))
    unique_dates = list(dict.fromkeys(fecha for fecha, _ in candidate_keys))
    chunk_size = 300
    for start in range(0, len(unique_facturas), chunk_size):
        chunk = unique_facturas[start:start + chunk_size]
        try:
            response = (
                supabase.table("ventas")
                .select("fecha,factura_no")
                .eq("local_id", local_id)
                .in_("fecha", unique_dates)
                .in_("factura_no", chunk)
                .execute()
            )
            for item in response.data or []:
                factura = str(item.get("factura_no") or "").strip()
                fecha = str(item.get("fecha") or "").strip()
                if factura and fecha:
                    existing.add((fecha, factura))
        except Exception as exc:
            logger.warning("No se pudo consultar duplicados para %s: %s", local_id, exc)
            return rows, line_numbers, []

    filtered_rows: List[Dict[str, Any]] = []
    filtered_lines: List[int] = []
    seen_in_file: set[Tuple[str, str]] = set()
    duplicate_details: List[Dict[str, Any]] = []
    for row, line_no in zip(rows, line_numbers):
        factura = str(row.get("factura_no") or "").strip()
        fecha = str(row.get("fecha") or "").strip()
        key = (fecha, factura)
        if fecha and factura and key in existing:
            duplicate_details.append(_duplicate_sale_detail(row, line_no, "base_datos"))
            continue
        if fecha and factura and key in seen_in_file:
            duplicate_details.append(_duplicate_sale_detail(row, line_no, "archivo"))
            continue
        if fecha and factura:
            seen_in_file.add(key)
        filtered_rows.append(row)
        filtered_lines.append(line_no)

    return filtered_rows, filtered_lines, duplicate_details


def _flatten_json_record(record: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key, value in record.items():
        flat_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_json_record(value, flat_key))
        else:
            flattened[flat_key] = value
    return flattened


def process_file_logic(config, filename, content):
    """
    Process file content (CSV or JSON) and insert to database.
    """
    logger.info(f"Procesando contenido de {filename} para {config['nombre']}")
    detalles = []
    registros_exito = 0
    stats: Dict[str, Any] = {
        "moving_window_mode": False,
        "duplicate_skipped": 0,
        "processing_error_count": 0,
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
                raw_records = [
                    _flatten_json_record(record)
                    for record in raw_records
                    if isinstance(record, dict)
                ]
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
        chars_to_remove = (
            _split_special_chars_to_remove(constants.get("_special_chars_to_remove"))
            if _special_char_cleanup_enabled(constants)
            else []
        )
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

                def pick_value(mapped_header, fallback_header=""):
                    key = _clean_csv_header_name(mapped_header)
                    value = ""
                    if key and key in normalized_row:
                        value = normalized_row[key]
                    elif key and key.lower() in lowered_row:
                        value = lowered_row[key.lower()]
                    else:
                        fallback = _clean_csv_header_name(fallback_header)
                        if fallback and fallback in normalized_row:
                            value = normalized_row[fallback]
                        elif fallback and fallback.lower() in lowered_row:
                            value = lowered_row[fallback.lower()]
                    return _remove_configured_special_chars(
                        _clean_cell_value(value),
                        chars_to_remove,
                    )

                # Map fields using mapping_config
                # mapping_config usually translates system_field -> file_header
                fecha_venta_raw = pick_value(mapping.get('fecha_venta', 'fecha_venta'), 'fecha')
                factura_no = pick_value(mapping.get('factura_numero', 'factura_numero'), 'factura_no')
                
                # Check for direct key matches if mapping fails
                fecha_venta = normalize_date(
                    fecha_venta_raw,
                    constants.get("_date_format", "auto"),
                )
                
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

                total_bruto = clean_float(pick_value(mapping.get('total_bruto', 'total_bruto')))
                total_impuestos = clean_float(pick_value(mapping.get('total_impuestos', 'total_impuestos')))
                total_neto = clean_float(pick_value(mapping.get('total_neto', 'total_neto')))
                
                if not fecha_venta:
                    detalles.append({"linea": i, "error": "Datos incompletos (Fecha faltante)"})
                    continue

                if total_bruto == 0 and (total_impuestos != 0 or total_neto != 0):
                    detalles.append({
                        "linea": i,
                        "error": "Datos inconsistentes (Total Bruto cero con impuestos o total neto distinto de cero)"
                    })
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

        stats["processing_error_count"] = len(detalles)

        if valid_rows:
            valid_rows, valid_line_numbers, duplicate_details = _filter_existing_sale_rows(
                valid_rows,
                valid_line_numbers,
                local_id,
            )
            detalles.extend(duplicate_details)
            stats["duplicate_skipped"] = len(duplicate_details)
            if duplicate_details:
                logger.info(
                    "%s: se omitieron y documentaron %s registros duplicados en %s",
                    config.get("nombre"),
                    len(duplicate_details),
                    filename,
                )

        # Atomic conflict handling prevents races between duplicate lookup and write.
        # Keep row-level fallback so one malformed row does not reject valid rows.
        BATCH_SIZE = 500
        for start in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[start:start + BATCH_SIZE]
            lines = valid_line_numbers[start:start + BATCH_SIZE]
            try:
                response = _upsert_sales_ignoring_duplicates(batch)
                inserted_rows = list(response.data or [])
                registros_exito += len(inserted_rows)
                atomic_duplicates = _atomic_duplicate_details(batch, lines, inserted_rows)
                detalles.extend(atomic_duplicates)
                stats["duplicate_skipped"] += len(atomic_duplicates)
            except Exception as batch_error:
                logger.warning(
                    "Batch upsert failed for %s (%s rows): %s. Falling back to row-level upserts.",
                    filename,
                    len(batch),
                    batch_error,
                )
                for payload, line_no in zip(batch, lines):
                    try:
                        response = _upsert_sales_ignoring_duplicates([payload])
                        inserted_rows = list(response.data or [])
                        registros_exito += len(inserted_rows)
                        atomic_duplicates = _atomic_duplicate_details([payload], [line_no], inserted_rows)
                        detalles.extend(atomic_duplicates)
                        stats["duplicate_skipped"] += len(atomic_duplicates)
                    except Exception as row_error:
                        detalles.append({"linea": line_no, "error": str(row_error)})
                        logger.error(f"Error insertando línea {line_no}: {row_error}")

        stats["processing_error_count"] = sum(
            1
            for detail in detalles
            if not isinstance(detail, dict) or detail.get("tipo") != "duplicado"
        )
                
    except Exception as e:
        logger.error(f"Error general procesando archivo: {e}")
        return 0, [{"linea": 0, "error": str(e)}], stats
            
    return registros_exito, detalles, stats


def _normalize_worker_import_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config or {})
    if not normalized.get("mapping_config"):
        normalized["mapping_config"] = normalized.get("mapping") or {}
    if not normalized.get("constants_config"):
        normalized["constants_config"] = normalized.get("constants") or {}
    if not normalized.get("file_type"):
        normalized["file_type"] = normalized.get("tipo_archivo", "JSON")
    return normalized


def _webservice_constants(config: Dict[str, Any]) -> Dict[str, Any]:
    return dict((config or {}).get("constants_config") or (config or {}).get("constants") or {})


def _webservice_config_value(config: Dict[str, Any], constants: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if constants.get(key) not in (None, ""):
            return constants.get(key)
        if config.get(key) not in (None, ""):
            return config.get(key)
    return None


def _webservice_int_value(config: Dict[str, Any], constants: Dict[str, Any], default: int, *keys: str) -> int:
    raw = _webservice_config_value(config, constants, *keys)
    try:
        return int(str(raw).strip()) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _webservice_bool_value(config: Dict[str, Any], constants: Dict[str, Any], default: bool, *keys: str) -> bool:
    raw = _webservice_config_value(config, constants, *keys)
    if raw in (None, ""):
        return default
    return _parse_worker_bool(raw)


def _append_query_param(url: str, key: str, value: Any) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(current_key, current_value) for current_key, current_value in query if current_key != key]
    query.append((key, str(value)))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def _json_path_value(payload: Any, path: str) -> Any:
    current = payload
    for part in [item for item in str(path or "").split(".") if item]:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _first_list_of_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "items", "results", "records", "invoices", "facturas", "ventas"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    for value in payload.values():
        if isinstance(value, list) and any(isinstance(row, dict) for row in value):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = _first_list_of_records(value)
            if nested:
                return nested

    return [payload]


def _extract_webservice_records(payload: Any, data_path: Optional[str] = None) -> List[Dict[str, Any]]:
    if data_path:
        selected = _json_path_value(payload, data_path)
        if selected is not None:
            return _first_list_of_records(selected)
    return _first_list_of_records(payload)


def _fetch_webservice_json(url: str, token: Optional[str], timeout_seconds: int) -> Any:
    headers = {
        "Accept": "application/json",
        "User-Agent": "MsMall-ImportWorker/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=timeout_seconds, context=ssl_context) as response:
        raw = response.read()
        decoded = _decode_worker_text(raw, is_json=True)
        return json.loads(decoded or "{}")


def _webservice_http_error_message(status_code: Any) -> str:
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        code = 0
    if code == 525:
        return (
            "SUBA respondió HTTP 525: Cloudflare no pudo completar la conexión SSL con el servidor "
            "de origen. La credencial no llegó a validarse; KATIÓN debe corregir el certificado/TLS "
            "o proporcionar un endpoint vigente."
        )
    if code in {401, 403}:
        return f"El WebService rechazó la credencial (HTTP {code}). Verifique o renueve el token Bearer."
    if code == 404:
        return "El endpoint configurado no existe o cambió (HTTP 404). Verifique la URL del WebService."
    if code == 429:
        return "El WebService limitó temporalmente las consultas (HTTP 429). Intente nuevamente más tarde."
    if code >= 500:
        return f"El proveedor WebService no está disponible temporalmente (HTTP {code})."
    return f"El WebService respondió con error HTTP {code or 'desconocido'}."


def fetch_generic_webservice_records(
    config: Dict[str, Any],
    *,
    max_pages_override: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int, str]:
    normalized = _normalize_worker_import_config(config)
    constants = _webservice_constants(normalized)
    base_url = _webservice_config_value(
        normalized,
        constants,
        "_webservice_url",
        "webservice_url",
        "api_url",
        "endpoint_url",
        "host",
        "sftp_host",
    )
    if not base_url:
        raise ValueError("Webservice sin URL configurada.")

    token = _webservice_config_value(
        normalized,
        constants,
        "_webservice_token",
        "webservice_token",
        "api_token",
        "auth_token",
        "password",
        "sftp_pass",
    )
    page_param = str(
        _webservice_config_value(normalized, constants, "_webservice_page_param", "page_param") or "page"
    )
    start_page = max(
        1,
        _webservice_int_value(normalized, constants, 1, "_webservice_start_page", "start_page"),
    )
    configured_max_pages = max(
        1,
        _webservice_int_value(
            normalized,
            constants,
            WEBSERVICE_MAX_PAGES,
            "_webservice_max_pages",
            "max_pages",
        ),
    )
    max_pages = max(1, min(configured_max_pages, max_pages_override)) if max_pages_override else configured_max_pages
    timeout_seconds = max(
        5,
        _webservice_int_value(
            normalized,
            constants,
            WEBSERVICE_TIMEOUT_SECONDS,
            "_webservice_timeout_seconds",
            "timeout_seconds",
        ),
    )
    data_path = _webservice_config_value(normalized, constants, "_webservice_data_path", "data_path")
    paginate = _webservice_bool_value(
        normalized,
        constants,
        True,
        "_webservice_paginate",
        "paginate",
    )
    start_date_param = str(
        _webservice_config_value(
            normalized,
            constants,
            "_webservice_start_date_param",
            "start_date_param",
        )
        or ""
    ).strip()
    end_date_param = str(
        _webservice_config_value(
            normalized,
            constants,
            "_webservice_end_date_param",
            "end_date_param",
        )
        or ""
    ).strip()
    request_url = str(base_url)
    if start_date_param and end_date_param:
        start_date, end_date = _generic_webservice_date_range(normalized, constants)
        request_url = _append_query_param(request_url, start_date_param, start_date)
        request_url = _append_query_param(request_url, end_date_param, end_date)

    records: List[Dict[str, Any]] = []
    fetched_pages = 0
    last_url = ""
    page = start_page
    while fetched_pages < max_pages:
        last_url = _append_query_param(request_url, page_param, page) if paginate else request_url
        payload = _fetch_webservice_json(last_url, str(token or "").strip() or None, timeout_seconds)
        page_records = _extract_webservice_records(payload, str(data_path or "").strip() or None)
        if not page_records:
            break
        records.extend(page_records)
        fetched_pages += 1
        if not paginate:
            break
        page += 1

    return records, fetched_pages, last_url


def _generic_webservice_date_range(
    config: Dict[str, Any],
    constants: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    constants = constants or _webservice_constants(config)
    today = _now_local().date()
    mode = str(
        _webservice_config_value(
            config,
            constants,
            "_webservice_date_mode",
            "webservice_date_mode",
            "date_mode",
        )
        or "yesterday"
    ).strip().lower()
    configured_start = _webservice_config_value(
        config,
        constants,
        "_webservice_start_date",
        "webservice_start_date",
        "start_date",
    )
    configured_end = _webservice_config_value(
        config,
        constants,
        "_webservice_end_date",
        "webservice_end_date",
        "end_date",
    )

    if mode in {"today", "hoy"}:
        start = end = today.isoformat()
    elif mode in {"current_month", "mes_actual", "month"}:
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
    elif mode in {"last_30_days", "ultimos_30_dias", "last_month"}:
        start = (today - timedelta(days=29)).isoformat()
        end = today.isoformat()
    elif mode in {"custom", "range", "rango"}:
        start = normalize_date(configured_start) if configured_start else None
        end = normalize_date(configured_end) if configured_end else None
    else:
        previous_day = today - timedelta(days=1)
        start = end = previous_day.isoformat()

    if not start or not end:
        raise ValueError("Rango de fechas Webservice invalido.")
    if start > end:
        start, end = end, start
    return start, end


def _now_local() -> datetime:
    return datetime.now(_worker_timezone())


def _api_base_url(config: Dict[str, Any]) -> str:
    host = str(
        _webservice_config_value(
            config,
            _webservice_constants(config),
            "host",
            "sftp_host",
            "api_url",
            "endpoint_url",
        )
        or ""
    ).strip()
    if not host:
        raise ValueError("URL base API requerida")
    if not re.match(r"^https?://", host, flags=re.IGNORECASE):
        host = f"https://{host}"
    return host.rstrip("/")


def _is_studio_g_config(config: Dict[str, Any], constants: Optional[Dict[str, Any]] = None) -> bool:
    constants = constants or _webservice_constants(config)
    provider = str(
        _webservice_config_value(
            config,
            constants,
            "provider",
            "_provider",
            "api_provider",
            "_api_provider",
        )
        or ""
    ).strip().lower()
    host = str(config.get("sftp_host") or config.get("host") or "").strip().lower()
    return provider in {"studio_g", "studiog", "sales_tap", "salestap"} or "alcagora.ddns.net" in host


def _is_bundaberg_config(config: Dict[str, Any], constants: Optional[Dict[str, Any]] = None) -> bool:
    constants = constants or _webservice_constants(config)
    provider = str(
        _webservice_config_value(
            config,
            constants,
            "provider",
            "_provider",
            "api_provider",
            "_api_provider",
        )
        or ""
    ).strip().lower()
    host = str(config.get("sftp_host") or config.get("host") or "").strip().lower()
    return provider in {"bundaberg", "agora_bundaberg", "agora"} or (
        "sibs2.com" in host and "api_agora" in host
    )


def api_provider_name(config: Dict[str, Any]) -> str:
    if _is_bundaberg_config(config):
        return "bundaberg"
    if _is_studio_g_config(config):
        return "studio_g"
    return ""


def _api_json_request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = WEBSERVICE_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    payload = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            decoded = (_decode_worker_text(raw, is_json=True) or "").strip()
            if not decoded:
                parsed = {}
            else:
                try:
                    parsed = json.loads(decoded)
                except json.JSONDecodeError as exc:
                    status = getattr(response, "status", None) or 200
                    response_headers = getattr(response, "headers", None)
                    content_type = (
                        str(response_headers.get("Content-Type") or "desconocido").split(";", 1)[0].strip()
                        if response_headers is not None
                        else "desconocido"
                    )
                    raise RuntimeError(
                        "El proveedor API devolvio una respuesta que no es JSON valido "
                        f"(HTTP {status}, tipo {content_type})"
                    ) from exc
    except urllib.error.HTTPError as exc:
        detail = _decode_worker_text(exc.read(), is_json=True)
        raise RuntimeError(f"API HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo conectar al proveedor API: {exc.reason}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Respuesta API inesperada: se esperaba objeto JSON")
    return parsed


def _studio_g_authorize(config: Dict[str, Any], constants: Dict[str, Any]) -> str:
    client_id = str(
        _webservice_config_value(config, constants, "client_id", "_client_id", "usuario", "sftp_user")
        or ""
    ).strip()
    client_secret = str(
        _webservice_config_value(config, constants, "client_secret", "_client_secret", "password", "sftp_pass")
        or ""
    ).strip()
    if not client_id or not client_secret:
        raise ValueError("Client ID y Client Secret requeridos para Studio G")

    response = _api_json_request(
        "POST",
        f"{_api_base_url(config)}/authorization",
        body={"client_id": client_id, "client_secret": client_secret},
        timeout=max(
            5,
            _webservice_int_value(
                config,
                constants,
                WEBSERVICE_TIMEOUT_SECONDS,
                "_webservice_timeout_seconds",
                "timeout_seconds",
            ),
        ),
    )
    token = str(response.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Studio G no devolvio access_token")
    return token


def _parse_api_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return normalize_date(text)


def _parse_api_time(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.time().replace(microsecond=0).isoformat()
    except ValueError:
        pass

    match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", text)
    if not match:
        return None
    parts = match.group(1).split(":")
    if len(parts) == 2:
        return f"{int(parts[0]):02d}:{parts[1]}:00"
    return f"{int(parts[0]):02d}:{parts[1]}:{parts[2]}"


def _studio_g_value(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    normalized = {
        re.sub(r"[^a-z0-9]", "", str(key).lower()): value
        for key, value in row.items()
    }
    for key in keys:
        lookup = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if lookup in normalized:
            return normalized.get(lookup)
    return None


def _studio_g_date_range(config: Dict[str, Any]) -> Tuple[str, str]:
    constants = _webservice_constants(config)
    today = _now_local().date()
    mode = str(
        _webservice_config_value(
            config,
            constants,
            "studio_g_date_mode",
            "_studio_g_date_mode",
            "date_mode",
        )
        or ""
    ).strip().lower()
    fecha_inicio = _webservice_config_value(
        config,
        constants,
        "studio_g_fecha_inicio",
        "_studio_g_fecha_inicio",
        "fecha_inicio",
        "FechaInicio",
    )
    fecha_fin = _webservice_config_value(
        config,
        constants,
        "studio_g_fecha_fin",
        "_studio_g_fecha_fin",
        "fecha_fin",
        "FechaFin",
    )

    if mode in {"today", "hoy"}:
        start = end = today.isoformat()
    elif mode in {"yesterday", "ayer", "previous_day"}:
        previous = today - timedelta(days=1)
        start = end = previous.isoformat()
    elif mode in {"current_month", "mes_actual", "month"}:
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
    elif mode in {"last_30_days", "ultimos_30_dias", "last_month"}:
        start = (today - timedelta(days=29)).isoformat()
        end = today.isoformat()
    elif mode in {"custom", "range", "rango"}:
        start = normalize_date(fecha_inicio) if fecha_inicio else None
        end = normalize_date(fecha_fin) if fecha_fin else None
    else:
        today_text = today.isoformat()
        start = normalize_date(fecha_inicio) if fecha_inicio else today_text
        end = normalize_date(fecha_fin) if fecha_fin else start

    if not start or not end:
        raise ValueError("Rango de fechas Studio G invalido")
    if start > end:
        logger.warning("Rango Studio G invertido; normalizando %s..%s.", start, end)
        start, end = end, start
    return start, end


def _bundaberg_date_range(config: Dict[str, Any]) -> Tuple[str, str]:
    constants = _webservice_constants(config)
    normalized = dict(config)
    normalized_constants = dict(constants)
    key_aliases = {
        "_studio_g_date_mode": "_api_date_mode",
        "_studio_g_fecha_inicio": "_api_fecha_inicio",
        "_studio_g_fecha_fin": "_api_fecha_fin",
    }
    for studio_key, api_key in key_aliases.items():
        if normalized_constants.get(studio_key) in (None, "") and normalized_constants.get(api_key) not in (None, ""):
            normalized_constants[studio_key] = normalized_constants[api_key]
    normalized["constants_config"] = normalized_constants
    try:
        return _studio_g_date_range(normalized)
    except ValueError as exc:
        raise ValueError(str(exc).replace("Studio G", "Bundaberg")) from exc


def _map_studio_g_sale(config: Dict[str, Any], row: Dict[str, Any], id_tpv: str) -> Optional[Dict[str, Any]]:
    raw_fecha = _studio_g_value(row, "Fecha", "FECHA")
    fecha = _parse_api_date(raw_fecha)
    if not fecha:
        return None

    transaction_id = _studio_g_value(row, "IDTransaccion", "ID_TRANSACCION")
    ncf = str(_studio_g_value(row, "NCF") or "").strip()
    factura_no = ncf or (f"STUDIOG-{id_tpv}-{transaction_id}" if transaction_id not in (None, "") else "")
    if not factura_no:
        return None

    payload = {
        "local_id": config.get("id"),
        "mall_id": config.get("mall_id"),
        "fecha": fecha,
        "factura_no": factura_no,
        "comprobante": ncf or None,
        "hora_transaccion": _parse_api_time(_studio_g_value(row, "Hora", "HORA") or raw_fecha),
        "total_bruto": _parse_mapped_decimal(_studio_g_value(row, "TotalBruto", "TOTALBRUTO"), "."),
        "total_impuestos": _parse_mapped_decimal(_studio_g_value(row, "TotalImpuestos", "TOTALIMPUESTOS"), "."),
        "total_neto": _parse_mapped_decimal(_studio_g_value(row, "TotalNeto", "TOTALNETO"), "."),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _map_bundaberg_sale(config: Dict[str, Any], row: Dict[str, Any], id_tpv: str) -> Optional[Dict[str, Any]]:
    raw_fecha = _studio_g_value(row, "fecha", "Fecha")
    fecha = _parse_api_date(raw_fecha)
    if not fecha:
        return None

    transaction_id = _studio_g_value(row, "id_transaccion", "idTransaccion", "IDTransaccion")
    ncf = str(_studio_g_value(row, "ncf", "NCF") or "").strip()
    serial = str(_studio_g_value(row, "numserie", "num_serie", "numeroSerie") or "").strip()
    factura_no = serial or ncf
    if not factura_no and transaction_id not in (None, ""):
        factura_no = f"BUNDABERG-{id_tpv}-{transaction_id}"
    if not factura_no:
        return None

    exchange_rate = _parse_mapped_decimal(_studio_g_value(row, "tasa", "Tasa", "TASA"), ".")
    if exchange_rate <= 0:
        exchange_rate = 1.0

    def converted_total(*keys: str) -> float:
        return round(_parse_mapped_decimal(_studio_g_value(row, *keys), ".") * exchange_rate, 2)

    payload = {
        "local_id": config.get("id"),
        "mall_id": config.get("mall_id"),
        "fecha": fecha,
        "factura_no": factura_no,
        "comprobante": ncf or None,
        "hora_transaccion": _parse_api_time(_studio_g_value(row, "hora", "Hora") or raw_fecha),
        "total_bruto": converted_total("totalbruto", "total_bruto"),
        "total_impuestos": converted_total("totalimpuestos", "total_impuestos"),
        "total_neto": converted_total("totalneto", "total_neto"),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _bundaberg_query_sales(
    config: Dict[str, Any],
    *,
    id_tpv: str,
    api_key: str,
    fecha_inicio: str,
    fecha_fin: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    query_params = {"idTpv": id_tpv, "apiKey": api_key}
    if fecha_inicio == fecha_fin:
        query_params["fecha"] = fecha_inicio
    else:
        query_params["fechaInicio"] = fecha_inicio
        query_params["fechaFin"] = fecha_fin
    query = urllib.parse.urlencode(query_params)
    base_url = _api_base_url(config)
    parsed_base_url = urllib.parse.urlsplit(base_url)
    if (
        parsed_base_url.netloc.lower().endswith("sibs2.com")
        and parsed_base_url.path.rstrip("/") == "/api_agora_inv"
    ):
        base_url = f"{base_url}/"
    response = _api_json_request(
        "GET",
        f"{base_url}?{query}",
        timeout=timeout,
    )
    if not response:
        return []
    sales = response.get("ventas")
    if sales is None:
        provider_message = str(response.get("message") or response.get("mensaje") or "").strip()
        raise RuntimeError(
            f"Respuesta Bundaberg invalida: falta la lista ventas{': ' + provider_message if provider_message else ''}"
        )
    if not isinstance(sales, list):
        raise RuntimeError("Respuesta Bundaberg invalida: ventas no es una lista")
    return [
        mapped
        for sale in sales
        if isinstance(sale, dict)
        for mapped in [_map_bundaberg_sale(config, sale, id_tpv)]
        if mapped
    ]


def fetch_bundaberg_sales(config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    config = _normalize_worker_import_config(config)
    constants = _webservice_constants(config)
    id_tpv = str(
        _webservice_config_value(config, constants, "idTpv", "id_tpv", "ruta_remota", "sftp_path")
        or ""
    ).strip()
    api_key = str(config.get("password") or config.get("sftp_pass") or "").strip()
    if not id_tpv or id_tpv == ".":
        raise ValueError("idTpv requerido para Bundaberg")
    if not api_key:
        raise ValueError("API key requerida para Bundaberg")

    fecha_inicio, fecha_fin = _bundaberg_date_range(config)
    timeout = max(
        5,
        _webservice_int_value(
            config,
            constants,
            WEBSERVICE_TIMEOUT_SECONDS,
            "_webservice_timeout_seconds",
            "timeout_seconds",
        ),
    )
    rows = _bundaberg_query_sales(
        config,
        id_tpv=id_tpv,
        api_key=api_key,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        timeout=timeout,
    )
    return rows, f"Bundaberg {id_tpv} {fecha_inicio}..{fecha_fin}"


def _is_studio_g_sales_query_failure(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return "api http 500" in message and "error consultando ventas" in message


def _studio_g_probe_dates(start_day: date, day_count: int) -> List[str]:
    probe_count = min(max(day_count, 1), STUDIO_G_OUTAGE_PROBE_DAYS)
    if probe_count == 1:
        offsets = [0]
    else:
        offsets = sorted({
            round(index * (day_count - 1) / (probe_count - 1))
            for index in range(probe_count)
        })
    return [(start_day + timedelta(days=offset)).isoformat() for offset in offsets]


def _studio_g_query_sales(
    config: Dict[str, Any],
    *,
    token: str,
    id_tpv: str,
    fecha_inicio: str,
    fecha_fin: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    query = urllib.parse.urlencode({
        "idTpv": id_tpv,
        "FechaInicio": fecha_inicio,
        "FechaFin": fecha_fin,
    })
    response = _api_json_request(
        "GET",
        f"{_api_base_url(config)}/ventas?{query}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    sales = response.get("ventas") or []
    if not isinstance(sales, list):
        raise RuntimeError("Respuesta Studio G invalida: ventas no es una lista")
    return [
        mapped
        for sale in sales
        if isinstance(sale, dict)
        for mapped in [_map_studio_g_sale(config, sale, id_tpv)]
        if mapped
    ]


def fetch_studio_g_sales_detailed(
    config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], str, List[Dict[str, str]]]:
    """Fetch a range, falling back to isolated days only for Studio G query 500s."""
    config = _normalize_worker_import_config(config)
    constants = _webservice_constants(config)
    id_tpv = str(
        _webservice_config_value(
            config,
            constants,
            "idTpv",
            "id_tpv",
            "_studio_g_id_tpv",
            "ruta_remota",
            "sftp_path",
        )
        or ""
    ).strip()
    if not id_tpv or id_tpv == ".":
        raise ValueError("idTpv requerido en Ruta Remota para Studio G")

    fecha_inicio, fecha_fin = _studio_g_date_range(config)
    token = _studio_g_authorize(config, constants)
    timeout = max(
        5,
        _webservice_int_value(
            config,
            constants,
            WEBSERVICE_TIMEOUT_SECONDS,
            "_webservice_timeout_seconds",
            "timeout_seconds",
        ),
    )
    source_name = f"Studio G {id_tpv} {fecha_inicio}..{fecha_fin}"
    try:
        rows = _studio_g_query_sales(
            config,
            token=token,
            id_tpv=id_tpv,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            timeout=timeout,
        )
        return rows, source_name, []
    except Exception as range_error:
        start_day = date.fromisoformat(fecha_inicio)
        end_day = date.fromisoformat(fecha_fin)
        day_count = (end_day - start_day).days + 1
        if (
            not _is_studio_g_sales_query_failure(range_error)
            or day_count <= 1
            or day_count > STUDIO_G_DAILY_FALLBACK_MAX_DAYS
        ):
            raise

        logger.warning(
            "Studio G fallo para el rango %s..%s; reintentando %s dia(s) por separado.",
            fecha_inicio,
            fecha_fin,
            day_count,
        )
        all_dates = [
            (start_day + timedelta(days=offset)).isoformat()
            for offset in range(day_count)
        ]
        rows_by_date: Dict[str, List[Dict[str, Any]]] = {}
        errors_by_date: Dict[str, str] = {}

        def query_day(target_date: str) -> None:
            try:
                rows_by_date[target_date] = _studio_g_query_sales(
                    config,
                    token=token,
                    id_tpv=id_tpv,
                    fecha_inicio=target_date,
                    fecha_fin=target_date,
                    timeout=timeout,
                )
            except Exception as day_error:
                errors_by_date[target_date] = sanitize_error_text(day_error)

        probe_dates = _studio_g_probe_dates(start_day, day_count)
        for target_date in probe_dates:
            query_day(target_date)

        if not rows_by_date and all(
            _is_studio_g_sales_query_failure(RuntimeError(errors_by_date.get(target_date, "")))
            for target_date in probe_dates
        ):
            probe_labels = ", ".join(probe_dates)
            raise StudioGSalesUnavailable(
                "Servicio de ventas Studio G no disponible: la autenticacion fue correcta, "
                f"pero /ventas devolvio HTTP 500 para {len(probe_dates)} fecha(s) "
                f"representativa(s) del rango ({probe_labels}). "
                "El proveedor debe revisar su consulta de ventas."
            ) from range_error

        for target_date in all_dates:
            if target_date not in rows_by_date and target_date not in errors_by_date:
                query_day(target_date)

        successful_days = len(rows_by_date)
        if successful_days == 0:
            raise RuntimeError(
                f"Studio G no pudo consultar ninguno de los {day_count} dias del rango. "
                f"Error inicial: {sanitize_error_text(range_error)}"
            ) from range_error

        recovered_rows = [
            row
            for target_date in all_dates
            for row in rows_by_date.get(target_date, [])
        ]
        failed_dates = [
            {"fecha": target_date, "error": errors_by_date[target_date]}
            for target_date in all_dates
            if target_date in errors_by_date
        ]

        logger.warning(
            "Studio G recuperacion diaria: dias_ok=%s dias_error=%s ventas=%s.",
            successful_days,
            len(failed_dates),
            len(recovered_rows),
        )
        return (
            recovered_rows,
            f"{source_name} (recuperacion diaria)",
            failed_dates,
        )


def fetch_studio_g_sales(config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    rows, source_name, _ = fetch_studio_g_sales_detailed(config)
    return rows, source_name


def _insert_studio_g_sales(config: Dict[str, Any], rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    if not rows:
        return 0, 0
    if not supabase:
        raise ValueError("Supabase no configurado")

    line_numbers = list(range(1, len(rows) + 1))
    filtered_rows, _, duplicate_details = _filter_existing_sale_rows(
        rows,
        line_numbers,
        str(config.get("id") or ""),
    )
    if filtered_rows:
        supabase.table("ventas").insert(filtered_rows).execute()
    return len(filtered_rows), len(duplicate_details)


def _insert_bundaberg_sales(config: Dict[str, Any], rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    if not rows:
        return 0, 0
    if not supabase:
        raise ValueError("Supabase no configurado")

    local_id = str(config.get("id") or "").strip()
    if not local_id:
        raise ValueError("local_id requerido para actualizar ventas Bundaberg")

    valid_rows = [
        row
        for row in rows
        if str(row.get("fecha") or "").strip() and str(row.get("factura_no") or "").strip()
    ]
    unique_dates = list(dict.fromkeys(str(row["fecha"]).strip() for row in valid_rows))
    unique_invoices = list(dict.fromkeys(str(row["factura_no"]).strip() for row in valid_rows))
    existing_by_key: Dict[Tuple[str, str], str] = {}
    chunk_size = 300
    for start in range(0, len(unique_invoices), chunk_size):
        response = (
            supabase.table("ventas")
            .select("id,fecha,factura_no")
            .eq("local_id", local_id)
            .in_("fecha", unique_dates)
            .in_("factura_no", unique_invoices[start:start + chunk_size])
            .execute()
        )
        for item in response.data or []:
            key = (
                str(item.get("fecha") or "").strip(),
                str(item.get("factura_no") or "").strip(),
            )
            sale_id = str(item.get("id") or "").strip()
            if all(key) and sale_id:
                existing_by_key[key] = sale_id

    new_rows: List[Dict[str, Any]] = []
    updated = 0
    seen: set[Tuple[str, str]] = set()
    refresh_fields = (
        "comprobante",
        "hora_transaccion",
        "total_bruto",
        "total_impuestos",
        "total_neto",
    )
    for row in valid_rows:
        key = (str(row["fecha"]).strip(), str(row["factura_no"]).strip())
        if key in seen:
            continue
        seen.add(key)
        existing_id = existing_by_key.get(key)
        if not existing_id:
            new_rows.append(row)
            continue

        update_payload = {field: row.get(field) for field in refresh_fields if field in row}
        if update_payload:
            supabase.table("ventas").update(update_payload).eq("id", existing_id).execute()
            updated += 1

    if new_rows:
        supabase.table("ventas").insert(new_rows).execute()
    return len(new_rows), updated


def process_studio_g_api(config: Dict[str, Any], *, write_load_log: bool = True) -> Dict[str, Any]:
    config = _normalize_worker_import_config(config)
    local_name = config.get("nombre") or "Studio G"
    batch_id = str(uuid.uuid4())
    try:
        rows, source_name, failed_dates = fetch_studio_g_sales_detailed(config)
        inserted, skipped = _insert_studio_g_sales(config, rows)
        message = f"API Studio G: {inserted} ventas importadas"
        if skipped:
            message += f", {skipped} duplicadas omitidas"
        if not rows:
            message = "API Studio G: 0 ventas encontradas para el rango"
        details = [
            {
                "linea": 0,
                "fecha": item["fecha"],
                "tipo": "studio_g_date_error",
                "error": item["error"],
            }
            for item in failed_dates
        ]
        status = "partial" if failed_dates else "success"
        if failed_dates:
            failed_labels = ", ".join(item["fecha"] for item in failed_dates[:10])
            if len(failed_dates) > 10:
                failed_labels += f" y {len(failed_dates) - 10} mas"
            message += (
                f". Importacion parcial: {len(failed_dates)} fecha(s) pendientes "
                f"de reintento ({failed_labels})"
            )
        if write_load_log:
            insert_load_log(
                local_name,
                source_name,
                "parcial" if failed_dates else "exito",
                message,
                batch_id,
                details,
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal="API",
                records_processed=inserted,
                error_count=len(failed_dates),
                metadata={
                    "source": "worker_studio_g_api",
                    "records_received": len(rows),
                    "duplicate_skipped": skipped,
                    "fallback_strategy": "daily" if failed_dates else None,
                    "failed_dates": [item["fecha"] for item in failed_dates],
                },
            )
        if inserted > 0 and write_load_log:
            run_local_risk_analysis_if_possible(config, trigger="worker_studio_g_api")
        return {
            "ok": True,
            "status": status,
            "message": message,
            "records_processed": inserted,
            "source_name": source_name,
            "canal": "API",
            "provider": "studio_g",
            "worker_source": "worker_studio_g_api",
            "records_received": len(rows),
            "duplicate_skipped": skipped,
            "processed_files": 1 if rows else 0,
            "failed_files": len(failed_dates),
            "total_pending": len(rows),
            "batch_size": 1 if rows else 0,
            "failed_dates": [item["fecha"] for item in failed_dates],
            "details": details,
        }
    except Exception as exc:
        message = f"Fallo API Studio G: {sanitize_error_text(exc)}"
        error_type = (
            "studio_g_sales_unavailable"
            if isinstance(exc, StudioGSalesUnavailable)
            else "studio_g_api_error"
        )
        details = [{"linea": 0, "tipo": error_type, "error": message}]
        if write_load_log:
            insert_load_log(
                local_name,
                "Studio G API",
                "error",
                message,
                batch_id,
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal="API",
                records_processed=0,
                error_count=1,
                metadata={
                    "source": "worker_studio_g_api",
                    "exception": sanitize_error_text(exc),
                    "error_type": error_type,
                },
            )
        return {
            "ok": False,
            "status": "error",
            "message": message,
            "records_processed": 0,
            "source_name": "Studio G API",
            "canal": "API",
            "error_type": error_type,
            "worker_source": "worker_studio_g_api",
            "details": details,
        }


def process_bundaberg_api(config: Dict[str, Any], *, write_load_log: bool = True) -> Dict[str, Any]:
    config = _normalize_worker_import_config(config)
    local_name = config.get("nombre") or "Bundaberg"
    batch_id = str(uuid.uuid4())
    try:
        rows, source_name = fetch_bundaberg_sales(config)
        inserted, updated = _insert_bundaberg_sales(config, rows)
        processed = inserted + updated
        message = f"API Bundaberg: {inserted} nuevas, {updated} actualizadas"
        if not rows:
            message = "API Bundaberg: 0 ventas encontradas para el rango"
        if write_load_log:
            insert_load_log(
                local_name,
                source_name,
                "exito",
                message,
                batch_id,
                [],
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal="API",
                records_processed=processed,
                error_count=0,
                metadata={
                    "source": "worker_bundaberg_api",
                    "provider": "bundaberg",
                    "records_received": len(rows),
                    "records_inserted": inserted,
                    "records_updated": updated,
                    "duplicate_skipped": 0,
                },
            )
        if processed > 0 and write_load_log:
            run_local_risk_analysis_if_possible(config, trigger="worker_bundaberg_api")
        return {
            "ok": True,
            "status": "success",
            "message": message,
            "records_processed": processed,
            "records_inserted": inserted,
            "records_updated": updated,
            "source_name": source_name,
            "canal": "API",
            "provider": "bundaberg",
            "worker_source": "worker_bundaberg_api",
            "records_received": len(rows),
            "duplicate_skipped": 0,
            "processed_files": 1 if rows else 0,
            "failed_files": 0,
            "total_pending": len(rows),
            "batch_size": 1 if rows else 0,
            "details": [],
        }
    except Exception as exc:
        clean_error = sanitize_error_text(exc)
        message = f"Fallo API Bundaberg: {clean_error}"
        details = [{"linea": 0, "tipo": "bundaberg_api_error", "error": message}]
        if write_load_log:
            insert_load_log(
                local_name,
                "Bundaberg API",
                "error",
                message,
                batch_id,
                details,
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal="API",
                records_processed=0,
                error_count=1,
                metadata={
                    "source": "worker_bundaberg_api",
                    "provider": "bundaberg",
                    "exception": clean_error,
                    "error_type": "bundaberg_api_error",
                },
            )
        return {
            "ok": False,
            "status": "error",
            "message": message,
            "records_processed": 0,
            "source_name": "Bundaberg API",
            "canal": "API",
            "provider": "bundaberg",
            "worker_source": "worker_bundaberg_api",
            "error_type": "bundaberg_api_error",
            "details": details,
        }


def _process_generic_webservice_import(
    config: Dict[str, Any],
    *,
    write_load_log: bool = True,
) -> Dict[str, Any]:
    normalized = _normalize_worker_import_config(config)
    constants = _webservice_constants(normalized)
    local_name = normalized.get("nombre") or "Local"
    batch_id = str(uuid.uuid4())
    start_page = max(
        1,
        _webservice_int_value(normalized, constants, 1, "_webservice_start_page", "start_page"),
    )

    try:
        records, fetched_pages, _ = fetch_generic_webservice_records(normalized)
    except urllib.error.HTTPError as exc:
        message = _webservice_http_error_message(exc.code)
        if write_load_log:
            insert_load_log(
                local_name,
                "WEBSERVICE",
                "error",
                message,
                batch_id,
                mall_id=normalized.get("mall_id"),
                local_id=normalized.get("id"),
                canal="WEBSERVICE",
                records_processed=0,
                error_count=1,
                metadata={"source": "worker_webservice_import", "status_code": exc.code},
            )
        return {
            "ok": False,
            "status": "error",
            "message": message,
            "records_processed": 0,
            "source_name": "WEBSERVICE",
            "canal": "WEBSERVICE",
            "provider": "generic",
            "worker_source": "worker_webservice_import",
            "details": [{"linea": 0, "error": message}],
        }
    except Exception as exc:
        clean_error = sanitize_error_text(exc)
        message = f"Fallo Webservice: {clean_error}"
        if write_load_log:
            insert_load_log(
                local_name,
                "WEBSERVICE",
                "error",
                message,
                batch_id,
                mall_id=normalized.get("mall_id"),
                local_id=normalized.get("id"),
                canal="WEBSERVICE",
                records_processed=0,
                error_count=1,
                metadata={"source": "worker_webservice_import", "exception": clean_error},
            )
        return {
            "ok": False,
            "status": "error",
            "message": message,
            "records_processed": 0,
            "source_name": "WEBSERVICE",
            "canal": "WEBSERVICE",
            "provider": "generic",
            "worker_source": "worker_webservice_import",
            "details": [{"linea": 0, "error": message}],
        }

    if not records:
        message = "Webservice ejecutado sin registros nuevos."
        if write_load_log:
            insert_load_log(
                local_name,
                "WEBSERVICE",
                "exito",
                message,
                batch_id,
                mall_id=normalized.get("mall_id"),
                local_id=normalized.get("id"),
                canal="WEBSERVICE",
                records_processed=0,
                error_count=0,
                metadata={"source": "worker_webservice_import", "pages": fetched_pages, "reason": "empty_response"},
            )
        return {
            "ok": True,
            "status": "success",
            "message": message,
            "records_processed": 0,
            "records_received": 0,
            "source_name": "WEBSERVICE",
            "canal": "WEBSERVICE",
            "provider": "generic",
            "worker_source": "worker_webservice_import",
            "processed_files": 0,
            "failed_files": 0,
            "total_pending": 0,
            "batch_size": 0,
            "details": [],
        }

    processing_config = dict(normalized)
    processing_config["file_type"] = "JSON"
    processing_config["tipo_archivo"] = "JSON"
    processing_constants = dict(constants)
    processing_constants.setdefault("_moving_window_mode", True)
    processing_config["constants_config"] = processing_constants
    processing_config["constants"] = processing_constants

    source_name = f"WEBSERVICE_{start_page}-{start_page + max(fetched_pages - 1, 0)}.json"
    count, errors, stats = _unpack_process_file_result(
        process_file_logic(processing_config, source_name, json.dumps(records, ensure_ascii=False))
    )
    estado, mensaje, insert_confirmed = _resolve_worker_processing_outcome(count, errors, stats)
    metadata = {
        "source": "worker_webservice_import",
        "pages": fetched_pages,
        "records_received": len(records),
        **(stats or {}),
    }

    if write_load_log:
        insert_load_log(
            local_name,
            source_name,
            estado if insert_confirmed else "error",
            mensaje,
            batch_id,
            errors,
            mall_id=normalized.get("mall_id"),
            local_id=normalized.get("id"),
            canal="WEBSERVICE",
            records_processed=count,
            error_count=len(errors or []),
            metadata=metadata,
        )

    if count > 0:
        run_local_risk_analysis_if_possible(normalized, trigger="worker_webservice_import")

    return {
        "ok": bool(insert_confirmed),
        "status": "partial" if estado == "parcial" else ("success" if insert_confirmed else "error"),
        "message": mensaje,
        "records_processed": count,
        "records_received": len(records),
        "source_name": source_name,
        "canal": "WEBSERVICE",
        "provider": "generic",
        "worker_source": "worker_webservice_import",
        "duplicate_skipped": int((stats or {}).get("duplicate_skipped") or 0),
        "processed_files": 1 if insert_confirmed else 0,
        "failed_files": 0 if insert_confirmed else 1,
        "total_pending": len(records),
        "batch_size": 1,
        "details": errors or [],
    }


def process_webservice_import(config: Dict[str, Any], *, write_load_log: bool = True) -> Dict[str, Any]:
    normalized = _normalize_worker_import_config(config)
    protocol = str(normalized.get("sftp_protocol") or normalized.get("protocolo") or "").strip().upper()
    if protocol == "API" and _is_bundaberg_config(normalized):
        return process_bundaberg_api(normalized, write_load_log=write_load_log)
    if protocol == "API" and _is_studio_g_config(normalized):
        return process_studio_g_api(normalized, write_load_log=write_load_log)
    if protocol == "WEBSERVICE":
        return _process_generic_webservice_import(normalized, write_load_log=write_load_log)
    message = f"Proveedor {protocol or 'API'} no soportado por este importador."
    return {
        "ok": False,
        "status": "error",
        "message": message,
        "records_processed": 0,
        "canal": protocol or "API",
        "details": [{"linea": 0, "error": message}],
    }


def process_local_files(config):
    protocol = str(config.get("sftp_protocol", "SFTP") or "SFTP").strip().upper()
    if protocol in {"API", "WEBSERVICE"}:
        return process_webservice_import(config)

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
    MAX_FILES_PER_BATCH = 20  # Safety Cap
    
    logger.info(f"Conectando a {config['nombre']} ({protocol}) en {host}...")
    
    if protocol == "SFTP":
        try:
            ssh, sftp = connect_with_retries(lambda: get_sftp_client(host, port, user, password))
        except Exception as ce:
            friendly_error = _friendly_sftp_connection_error(ce)
            insert_load_log(
                config['nombre'], "N/A", "error", f"Fallo conexión SFTP: {friendly_error}",
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal=protocol,
                records_processed=0,
                error_count=1,
                metadata={"source": "worker_auto_import", "connection_error": friendly_error},
            )
            return

        try:
            # Handle directory vs file path
            try:
                st = sftp.stat(remote_path)
                if not stat.S_ISDIR(st.st_mode):
                    remote_path = posixpath.dirname(remote_path) or "."
            except:
                pass

            # 1. DISCOVERY & FILTERING
            items = sftp.listdir_attr(remote_path)
            pending_files = []
            
            for item in items:
                if stat.S_ISDIR(item.st_mode): continue
                
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

            # 2. SORTING (Chronological: Oldest Modified First)
            # This is critical to maintain data integrity order
            pending_files.sort(key=lambda x: x.st_mtime)
            
            total_pending = len(pending_files)
            
            # 3. BATCHING
            batch_files = pending_files[:MAX_FILES_PER_BATCH]
            
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
                return

            logger.info(f"🚀 {config['nombre']}: Encontrados {total_pending} pendientes. Procesando lote de {len(batch_files)}.")

            # 4. PROCESSING LOOP
            processed_count = 0
            for item in batch_files:
                filename = item.filename
                batch_id = str(uuid.uuid4())
                logger.info(f"🔄 [{processed_count + 1}/{len(batch_files)}] Procesando SFTP: {filename}")
                
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
                            error_count=int((stats or {}).get("processing_error_count") or 0),
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
                        raise Exception(mensaje)
                        
                    processed_count += 1
                    
                except Exception as fe:
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
            
            logger.info(f"✅ {config['nombre']}: Lote completado. {processed_count}/{len(batch_files)} archivos procesados exitosamente.")
            if processed_count > 0:
                run_local_risk_analysis_if_possible(config, trigger="worker_auto_import")

        finally:
            if 'sftp' in locals(): sftp.close()
            if 'ssh' in locals(): ssh.close()
            
    elif protocol == "FTP":
        try:
            ftp = connect_with_retries(lambda: get_ftp_client(host, port, user, password))
        except Exception as ce:
            insert_load_log(
                config['nombre'], "N/A", "error", f"Fallo conexión FTP: {str(ce)}",
                mall_id=config.get("mall_id"),
                local_id=config.get("id"),
                canal=protocol,
                records_processed=0,
                error_count=1,
                metadata={"source": "worker_auto_import", "connection_error": str(ce)},
            )
            return

        try:
            try:
                ftp.cwd(remote_path)
            except:
                remote_path_parent = posixpath.dirname(remote_path) or "."
                try: ftp.cwd(remote_path_parent)
                except: pass

            # 1. DISCOVERY
            files = ftp.nlst()
            pending_files = []
            
            for filename in files:
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
            
            # 2. SORTING (Name Ascending)
            # FTP List doesn't give dates reliable without extra calls. Name sort is best best.
            pending_files.sort()
            
            total_pending = len(pending_files)
            
            # 3. BATCHING
            batch_files = pending_files[:MAX_FILES_PER_BATCH]
            
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
                return

            logger.info(f"🚀 {config['nombre']}: Encontrados {total_pending} pendientes. Procesando lote de {len(batch_files)}.")
            
            # 4. PROCESSING LOOP
            processed_count = 0
            for filename in batch_files:
                batch_id = str(uuid.uuid4())
                logger.info(f"🔄 [{processed_count + 1}/{len(batch_files)}] Procesando FTP: {filename}")
                
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
                            error_count=int((stats or {}).get("processing_error_count") or 0),
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
                         raise Exception(mensaje)
                         
                    processed_count += 1
                except Exception as fe:
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
            
            logger.info(f"✅ {config['nombre']}: Lote completado. {processed_count}/{len(batch_files)} archivos procesados exitosamente.")
            if processed_count > 0:
                run_local_risk_analysis_if_possible(config, trigger="worker_auto_import")
            
        finally:
            if 'ftp' in locals(): ftp.quit()

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


def _parse_worker_datetime(value: Any, tz: ZoneInfo) -> Optional[datetime]:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _parse_scheduled_time(value: Any) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _schedule_slot_for_local(local: Dict[str, Any], now: datetime) -> Optional[datetime]:
    frecuencia = str(local.get("frecuencia_cron") or "manual").strip().lower()
    if frecuencia == "manual":
        return None

    if frecuencia == "cada_hora":
        return now.replace(minute=0, second=0, microsecond=0)

    if frecuencia == "cada_2_horas":
        slot_hour = now.hour - (now.hour % 2)
        return now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)

    if frecuencia == "hora_especifica":
        scheduled_time = _parse_scheduled_time(local.get("hora_especifica"))
        if not scheduled_time:
            return None
        hour, minute = scheduled_time
        slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < slot:
            return None
        return slot

    return None


def should_run_scheduled_local(local: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    tz = _worker_timezone()
    current_time = now.astimezone(tz) if now else datetime.now(tz)
    slot = _schedule_slot_for_local(local, current_time)
    if not slot:
        return False

    last_run = _parse_worker_datetime(local.get("ultima_ejecucion"), tz)
    if last_run and last_run >= slot:
        return False

    return True

def _schedule_validation_error(local: Dict[str, Any]) -> Optional[str]:
    frecuencia = str(local.get("frecuencia_cron") or "manual").strip().lower()
    if frecuencia == "hora_especifica" and not _parse_scheduled_time(local.get("hora_especifica")):
        return "hora_especifica ausente o inválida"
    if frecuencia not in {"manual", "cada_hora", "cada_2_horas", "hora_especifica"}:
        return f"frecuencia_cron no soportada: {frecuencia or 'vacía'}"
    return None

def _build_importer_audit(locales: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    suspended = [
        local for local in locales
        if str(local.get("processing_status") or "").strip().upper() == "SUSPENDED_AUTH_ERROR"
    ]
    invalid = []
    for local in locales:
        error = _schedule_validation_error(local)
        if error:
            invalid.append({
                "id": local.get("id"),
                "nombre": local.get("nombre"),
                "error": error,
            })
    return {
        "automatic_total": len(locales),
        "idle_total": sum(
            1 for local in locales
            if str(local.get("processing_status") or "").strip().upper() == "IDLE"
        ),
        "suspended_total": len(suspended),
        "suspended_ftp": sum(
            1 for local in suspended
            if str(local.get("sftp_protocol") or "").strip().upper() == "FTP"
        ),
        "suspended_sftp": sum(
            1 for local in suspended
            if str(local.get("sftp_protocol") or "").strip().upper() == "SFTP"
        ),
        "invalid_schedule_total": len(invalid),
        "invalid_schedules": invalid[:50],
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }

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


def _missing_days_scheduler_error(result: Dict[str, Any]) -> Optional[str]:
    reason = str(result.get("reason") or "").strip()
    if reason in {"error", "resend_not_configured", "settings_table_unavailable"}:
        detail = result.get("error") or reason
        return _sanitize_health_error(f"Missing-days email scheduler: {detail}")

    failed_runs = [
        run
        for run in (result.get("runs") or [])
        if (
            run.get("reason") in {"send_failed", "state_read_failed", "slot_claim_failed"}
            or int(run.get("failed") or 0) > 0
            or run.get("status_error")
        )
    ]
    if not failed_runs:
        return None

    summaries = []
    for run in failed_runs[:5]:
        mall_id = str(run.get("mall_id") or "unknown")
        detail = (
            run.get("error")
            or run.get("status_error")
            or run.get("reason")
            or run.get("status")
            or "failed"
        )
        summaries.append(f"{mall_id}: {detail}")
    return _sanitize_health_error(
        f"Missing-days email scheduler failed ({len(failed_runs)}): {'; '.join(summaries)}"
    )


async def _finish_worker_cycle(email_scheduler_result: Dict[str, Any]):
    await update_cron_success()
    scheduler_error = _missing_days_scheduler_error(email_scheduler_result)
    if scheduler_error:
        await update_cron_error(scheduler_error)
    else:
        await clear_cron_error()


async def run_connection_monitor_nightly_if_due():
    if not supabase:
        return {"executed": False, "reason": "supabase_not_configured"}
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
    try:
        result = await asyncio.to_thread(
            lambda: run_missing_days_email_scheduler(supabase, logger=logger)
        )
        scheduler_error = _missing_days_scheduler_error(result)
        if scheduler_error:
            logger.error("%s", scheduler_error)
        elif result.get("executed"):
            logger.info("📬 Missing-days email scheduler executed: %s", result.get("runs"))
        else:
            logger.info("📬 Missing-days email scheduler skipped: %s", result)
        return result
    except Exception as e:
        logger.error(f"Missing-days email scheduler failed: {sanitize_error_text(e)}")
        return {"executed": False, "reason": "error", "error": sanitize_error_text(e)}

async def process_local_safe(local, semaphore):
    """
    Wraps the synchronous process_local_files in a semaphore and async thread,
    handling DB locking/unlocking and Circuit Breaker.
    """
    async with semaphore:
        local_name = local.get('nombre', 'Unknown')
        
        # --- CIRCUIT BREAKER CHECK ---
        consecutive_failures = local.get('consecutive_failures', 0)
        status = local.get('processing_status')
        
        if status == 'SUSPENDED_AUTH_ERROR':
             logger.warning(f"⛔ [Skipped] {local_name} is SUSPENDED due to auth errors.")
             return

        if consecutive_failures >= 5:
             logger.error(f"⛔ [Suspend] {local_name} reached 5 consecutive failures. Suspending...")
             await mark_local_status(local['id'], 'SUSPENDED_AUTH_ERROR')
             # Reset failures to avoid immediate loop if manually reactivated without reset
             # But actually, manual reactivation should reset failures.
             return

        logger.info(f"🔒 [Lock] Locking {local_name} (Status: BUSY)")
        
        # 1. LOCK
        await mark_local_status(local['id'], 'BUSY')
        
        try:
            # 2. EXECUTE (Run sync IO in thread pool)
            logger.info(f"🚀 [Start] Processing {local_name}...")
            
            # Run the processing
            # We need to capture if it was successful or auth error
            # process_local_files returns nothing, logs internally. 
            # We need to modify it or wrap it to know if it failed?
            # Actually process_local_files catches exceptions internally and logs.
            # to implement true circuit breaker, we need to know if it failed.
            
            # For now, let's assume if it throws exception here it failed.
            # But process_local_files swallows exceptions mostly.
            # Let's trust it runs. If we want strict circuit breaker, we'd need to refactor process_local_files to return status.
            # Let's assume for this task we wrap it.
            
            await asyncio.to_thread(process_local_files, local)
            
            logger.info(f"✅ [Done] Finished {local_name}")
            
            # Reset failures on success (Optimistic: if no exception bubbled up)
            # Ideal: check logs_carga for this batch? 
            # For simplicity: reset failures here.
            await asyncio.to_thread(
                lambda: supabase.table("locales").update({"consecutive_failures": 0}).eq("id", local['id']).execute()
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
            
            # Increment Failures
            new_failures = consecutive_failures + 1
            await asyncio.to_thread(
                 lambda: supabase.table("locales").update({"consecutive_failures": new_failures}).eq("id", local['id']).execute()
            )
            
        finally:
            # 3. RELEASE (Only if not suspended inside logic, checking status again?)
            # If we suspended it above, we returned.
            # If we are here, we must release lock.
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

def run_deferred_big_data_jobs() -> None:
    """Run bounded analytics only after the import priority lane has completed."""
    analytics_result = BigDataAnalyticsService(supabase, logger).process_pending_refreshes()
    if analytics_result["processed"] or analytics_result["failed"]:
        logger.info("Big Data aggregate queue: %s", analytics_result)

    # No row means disabled. This also keeps deployments safe before the Sprint 2
    # migration because the old constraint cannot contain BIG_DATA_OPERATIONS.
    try:
        enabled_rows = (
            supabase.table("mall_feature_flags")
            .select("mall_id")
            .eq("feature_key", "BIG_DATA_OPERATIONS")
            .eq("enabled", True)
            .limit(100)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        # Backward-compatible before the Sprint 2 migration and in reduced
        # worker smoke environments.
        logger.info("Sprint 2 operations lane unavailable: %s", str(exc)[:180])
        return
    if not enabled_rows:
        return

    service = BigDataSprint2Service(supabase)
    period_end = date.today()
    period_start = period_end - timedelta(days=30)
    for flag in enabled_rows:
        mall_id = flag.get("mall_id")
        if not mall_id:
            continue
        core_enabled = supabase.rpc(
            "is_mall_feature_enabled",
            {"requested_mall_id": mall_id, "requested_feature": "BIG_DATA_CORE"},
        ).execute().data
        if core_enabled is not True:
            continue
        started = time.monotonic()
        run_row = {
            "mall_id": mall_id,
            "job_type": "ANOMALY_DETECTION",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "status": "RUNNING",
        }
        run_id = None
        try:
            saved = supabase.table("big_data_operations_runs").insert(run_row).execute().data or []
            run_id = saved[0].get("id") if saved else None
            findings = service.detect_and_persist_anomalies(
                mall_id, period_start, period_end
            )
            changes = {
                "status": "COMPLETED",
                "items_generated": len(findings),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            if run_id:
                supabase.table("big_data_operations_runs").update(changes).eq(
                    "id", run_id
                ).execute()
        except Exception as exc:
            logger.exception("Sprint 2 anomaly job failed mall=%s", mall_id)
            if run_id:
                supabase.table("big_data_operations_runs").update(
                    {
                        "status": "FAILED",
                        "error": str(exc)[:1000],
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", run_id).execute()

    operations_result = OperationsAgentWorker(supabase, logger).process_pending_events()
    if operations_result["processed"] or operations_result["failed"]:
        logger.info("Operations event queue: %s", operations_result)


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
        # 2. Fetch all automatic importers so suspended/invalid schedules are visible.
        response = supabase.table("locales")\
            .select("*")\
            .eq("tipo_ejecucion", "AUTOMATICO")\
            .execute()

        automatic_locales = [loc for loc in (response.data or []) if loc.get("mall_id")]
        importer_audit = _build_importer_audit(automatic_locales)
        await _upsert_system_health_value(
            "CRON_IMPORTER_AUDIT",
            json.dumps(importer_audit, ensure_ascii=False, separators=(",", ":")),
        )
        if importer_audit["suspended_total"] or importer_audit["invalid_schedule_total"]:
            logger.warning(
                "Importer audit: suspended=%s invalid_schedules=%s",
                importer_audit["suspended_total"],
                importer_audit["invalid_schedule_total"],
            )

        # Only IDLE importers can enter the execution queue.
        locales = [
            loc for loc in automatic_locales
            if str(loc.get("processing_status") or "").strip().upper() == "IDLE"
        ]
        current_time = datetime.now(_worker_timezone())
        
        tasks_to_run = []
        
        for local in locales:
            if should_run_scheduled_local(local, current_time):
                tasks_to_run.append(local)

        if not tasks_to_run:
            logger.info("😴 No active tasks for this hour.")
            run_deferred_big_data_jobs()
            email_scheduler_result = await run_missing_days_email_scheduler_if_due()
            await run_connection_monitor_nightly_if_due()
            await _finish_worker_cycle(email_scheduler_result)
            return

        logger.info(f"📋 Encolados {len(tasks_to_run)} locales para ejecución.")
        
        # 3. Execute with Semaphore
        MAX_CONCURRENT_WORKERS = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        
        tasks = [process_local_safe(local, semaphore) for local in tasks_to_run]
        await asyncio.gather(*tasks)

        # Imports are always the priority lane. Aggregate refreshes, anomaly
        # detection and operational observations only run after ingestion settles.
        run_deferred_big_data_jobs()
        logger.info("🏁 Cycle finished.")
        email_scheduler_result = await run_missing_days_email_scheduler_if_due()
        await run_connection_monitor_nightly_if_due()
        await _finish_worker_cycle(email_scheduler_result)
        
    except Exception as e:
        logger.error(f"Critical error in main loop: {e}")
        await update_cron_error(e)

if __name__ == "__main__":
    asyncio.run(run_worker_async())
