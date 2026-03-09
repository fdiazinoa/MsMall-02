import re
from datetime import datetime
from typing import Any, Dict, List, Optional


EXTENDED_LOAD_LOG_COLUMNS = {
    "mall_id",
    "mall_nombre",
    "local_id",
    "canal",
    "records_processed",
    "error_count",
    "metadata",
}

LEGACY_LOAD_LOG_COLUMNS = {
    "fecha_hora",
    "local_nombre",
    "archivo",
    "estado",
    "mensaje",
    "batch_id",
    "detalles",
}

_MISSING_COLUMN_PATTERNS = [
    re.compile(r'column ["\']?([a-zA-Z_][a-zA-Z0-9_]*)["\']?(?: of relation ["\'][^"\']+["\'])? does not exist'),
    re.compile(r'could not find the ["\']?([a-zA-Z_][a-zA-Z0-9_]*)["\']? column'),
]


def normalize_load_channel(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper == "WEBSERVICE":
        return "WebService"
    if upper in {"FTP", "SFTP", "API"}:
        return upper
    return raw


def _coerce_non_negative_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(str(value).strip()))
    except Exception:
        return None
    return max(parsed, 0)


def _normalize_details(detalles: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not isinstance(detalles, list):
        return []
    return [item for item in detalles if isinstance(item, dict)]


def _derive_error_count(estado: str, detalles: List[Dict[str, Any]], error_count: Any) -> int:
    explicit = _coerce_non_negative_int(error_count)
    if explicit is not None:
        return explicit
    if detalles:
        return len(detalles)
    if str(estado or "").strip().lower() == "error":
        return 1
    return 0


def build_load_log_payload(
    *,
    local_nombre: str,
    archivo: str,
    estado: str,
    mensaje: str,
    batch_id: Optional[str] = None,
    detalles: Optional[List[Dict[str, Any]]] = None,
    mall_id: Optional[str] = None,
    mall_nombre: Optional[str] = None,
    local_id: Optional[str] = None,
    canal: Optional[str] = None,
    records_processed: Any = None,
    error_count: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_details = _normalize_details(detalles)
    normalized_status = str(estado or "").strip().lower() or "error"
    normalized_records = _coerce_non_negative_int(records_processed)
    normalized_error_count = _derive_error_count(normalized_status, normalized_details, error_count)
    normalized_channel = normalize_load_channel(canal)
    metadata_payload = dict(metadata or {})

    if batch_id and "batch_id" not in metadata_payload:
        metadata_payload["batch_id"] = str(batch_id)
    if normalized_channel and "canal" not in metadata_payload:
        metadata_payload["canal"] = normalized_channel
    if normalized_records is not None and "records_processed" not in metadata_payload:
        metadata_payload["records_processed"] = normalized_records
    if "error_count" not in metadata_payload:
        metadata_payload["error_count"] = normalized_error_count
    if mall_id and "mall_id" not in metadata_payload:
        metadata_payload["mall_id"] = mall_id
    if mall_nombre and "mall_nombre" not in metadata_payload:
        metadata_payload["mall_nombre"] = mall_nombre
    if local_id and "local_id" not in metadata_payload:
        metadata_payload["local_id"] = local_id
    if local_nombre and "local_nombre" not in metadata_payload:
        metadata_payload["local_nombre"] = local_nombre
    if archivo and "archivo" not in metadata_payload:
        metadata_payload["archivo"] = archivo

    payload = {
        "fecha_hora": datetime.now().isoformat(),
        "local_nombre": local_nombre,
        "archivo": archivo,
        "estado": normalized_status,
        "mensaje": mensaje,
        "batch_id": str(batch_id) if batch_id else None,
        "detalles": normalized_details,
        "mall_id": mall_id,
        "mall_nombre": mall_nombre,
        "local_id": local_id,
        "canal": normalized_channel,
        "records_processed": normalized_records,
        "error_count": normalized_error_count,
        "metadata": metadata_payload,
    }
    return {
        key: value
        for key, value in payload.items()
        if value is not None or key in {"detalles", "metadata"}
    }


def _extract_missing_column_name(error_text: str) -> Optional[str]:
    for pattern in _MISSING_COLUMN_PATTERNS:
        match = pattern.search(error_text)
        if match:
            return match.group(1)
    return None


def _looks_like_schema_error(error_text: str) -> bool:
    normalized = error_text.lower()
    return "schema" in normalized or "column" in normalized


def _stash_removed_value(payload: Dict[str, Any], field_name: str) -> None:
    if field_name not in payload:
        return
    value = payload.pop(field_name)
    if field_name == "metadata" or value is None:
        return
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and field_name not in metadata:
        metadata[field_name] = value


def insert_load_log_row(supabase_client: Any, payload: Dict[str, Any], logger: Any = None) -> None:
    if not supabase_client:
        return

    attempt_payload = dict(payload or {})
    while True:
        try:
            supabase_client.table("logs_carga").insert(attempt_payload).execute()
            return
        except Exception as exc:
            error_text = str(exc)
            missing_column = _extract_missing_column_name(error_text)
            if missing_column and missing_column in attempt_payload:
                _stash_removed_value(attempt_payload, missing_column)
                if logger:
                    logger.warning("logs_carga fallback removing unsupported column '%s'", missing_column)
                continue

            if "invalid input syntax for type uuid" in error_text.lower() and "batch_id" in attempt_payload:
                _stash_removed_value(attempt_payload, "batch_id")
                if logger:
                    logger.warning("logs_carga fallback removing incompatible batch_id")
                continue

            if _looks_like_schema_error(error_text):
                changed = False
                for field_name in EXTENDED_LOAD_LOG_COLUMNS:
                    if field_name in attempt_payload:
                        _stash_removed_value(attempt_payload, field_name)
                        changed = True
                if changed:
                    if logger:
                        logger.warning("logs_carga fallback using legacy payload after schema mismatch")
                    continue
            raise
