from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple


def _as_clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_sales_dedup_key(row: Dict[str, Any]) -> Optional[str]:
    local_id = _as_clean_text(row.get("local_id"))
    fecha = _as_clean_text(row.get("fecha"))
    factura_no = _as_clean_text(row.get("factura_no"))
    if not local_id or not fecha or not factura_no:
        return None
    return f"{local_id}|{fecha}|{factura_no}"


def build_exporter_sale_factura_no(exporter_row: Dict[str, Any]) -> Optional[str]:
    granularity = (_as_clean_text(exporter_row.get("granularity")) or "transaction").lower()
    documento_numero = _as_clean_text(exporter_row.get("documento_numero"))
    if granularity == "daily":
        resumen_id = _as_clean_text(exporter_row.get("resumen_id")) or documento_numero
        if not resumen_id:
            return None
        return f"WS-DAILY:{resumen_id}"
    return documento_numero


def map_exporter_ingest_row_to_sale(exporter_row: Dict[str, Any]) -> Dict[str, Any]:
    granularity = (_as_clean_text(exporter_row.get("granularity")) or "transaction").lower()
    factura_no = build_exporter_sale_factura_no(exporter_row)
    total_impuestos = exporter_row.get("total_impuesto")
    if total_impuestos is None:
        total_impuestos = exporter_row.get("total_impuestos")

    metadata = {
        "source": "exporter_webservice",
        "source_table": "exporter_sales_ingest",
        "granularity": granularity,
        "batch_id": _as_clean_text(exporter_row.get("batch_id")),
        "dedup_key": _as_clean_text(exporter_row.get("dedup_key")),
        "documento_tipo": _as_clean_text(exporter_row.get("documento_tipo")),
        "documento_numero": _as_clean_text(exporter_row.get("documento_numero")),
        "resumen_id": _as_clean_text(exporter_row.get("resumen_id")),
        "cantidad_documentos": exporter_row.get("cantidad_documentos"),
        "raw_meta": exporter_row.get("raw_meta"),
    }

    sale = {
        "mall_id": exporter_row.get("mall_id"),
        "local_id": exporter_row.get("local_id"),
        "fecha": exporter_row.get("fecha_venta"),
        "hora_transaccion": exporter_row.get("hora_venta"),
        "factura_no": factura_no,
        "total_bruto": exporter_row.get("total_bruto"),
        "total_impuestos": total_impuestos,
        "total_neto": exporter_row.get("total_neto"),
        "metadata": {k: v for k, v in metadata.items() if v not in (None, "", [], {})},
    }
    return {k: v for k, v in sale.items() if v is not None or k == "metadata"}


def prepare_exporter_sales_rows(exporter_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared_rows: List[Dict[str, Any]] = []
    for index, exporter_row in enumerate(exporter_rows, start=1):
        sale = map_exporter_ingest_row_to_sale(exporter_row)
        missing = [
            field_name
            for field_name in ("mall_id", "local_id", "fecha", "factura_no", "total_bruto", "total_impuestos", "total_neto")
            if sale.get(field_name) in (None, "")
        ]
        if missing:
            raise ValueError(
                f"row {index}: no se pudo promover a ventas, faltan {', '.join(missing)}"
            )
        prepared_rows.append(sale)
    return prepared_rows


def upsert_sales_rows(db: Any, sales_rows: List[Dict[str, Any]], *, logger: Optional[logging.Logger] = None) -> Dict[str, int]:
    if not sales_rows:
        return {"processed": 0, "inserted": 0, "updated": 0}
    if db is None:
        raise ValueError("Supabase no configurado para promocion de ventas")

    log = logger or logging.getLogger("exporter-sales-promotion")
    keyed_rows: Dict[str, Dict[str, Any]] = {}
    no_key_rows: List[Dict[str, Any]] = []
    for row in sales_rows:
        dedup_key = build_sales_dedup_key(row)
        if dedup_key:
            keyed_rows[dedup_key] = row
        else:
            no_key_rows.append(row)

    existing_map: Dict[str, str] = {}
    if keyed_rows:
        local_ids = list({str(row.get("local_id")) for row in keyed_rows.values() if row.get("local_id")})
        fechas = list({str(row.get("fecha")) for row in keyed_rows.values() if row.get("fecha")})
        if local_ids and fechas:
            existing_res = (
                db.table("ventas")
                .select("id, local_id, fecha, factura_no")
                .in_("local_id", local_ids)
                .in_("fecha", fechas)
                .execute()
            )
            existing_rows = getattr(existing_res, "data", None) or []
            for existing_row in existing_rows:
                dedup_key = build_sales_dedup_key(existing_row)
                if dedup_key and existing_row.get("id"):
                    existing_map[dedup_key] = str(existing_row["id"])

    inserts: List[Dict[str, Any]] = []
    updates: List[Tuple[str, Dict[str, Any]]] = []
    for dedup_key, row in keyed_rows.items():
        existing_id = existing_map.get(dedup_key)
        if existing_id:
            updates.append((existing_id, row))
        else:
            inserts.append(row)
    inserts.extend(no_key_rows)

    try:
        if keyed_rows:
            db.table("ventas").upsert(
                list(keyed_rows.values()),
                on_conflict="local_id,fecha,factura_no",
            ).execute()
        if no_key_rows:
            db.table("ventas").insert(no_key_rows).execute()
    except Exception as exc:
        message = str(exc).lower()
        if "no unique" not in message and "on conflict" not in message:
            raise
        log.warning(
            "No existe constraint unica para upsert en ventas(local_id,fecha,factura_no). Aplicando fallback de update/insert."
        )
        for existing_id, row in updates:
            db.table("ventas").update({k: v for k, v in row.items() if k != "id"}).eq("id", existing_id).execute()
        if inserts:
            db.table("ventas").insert(inserts).execute()

    return {
        "processed": len(keyed_rows) + len(no_key_rows),
        "inserted": len(inserts),
        "updated": len(updates),
    }


def promote_exporter_rows_to_sales(db: Any, exporter_rows: List[Dict[str, Any]], *, logger: Optional[logging.Logger] = None) -> Dict[str, int]:
    prepared_rows = prepare_exporter_sales_rows(exporter_rows)
    return upsert_sales_rows(db, prepared_rows, logger=logger)
