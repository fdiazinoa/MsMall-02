"""Low-I/O read helpers for the high-volume ``ventas`` table."""

from typing import Any, Dict, Iterable, List, Optional


DEFAULT_SALES_PAGE_SIZE = 1000


def _select_with_cursor(select_fields: str) -> str:
    fields = str(select_fields or "*").strip() or "*"
    if fields == "*":
        return fields
    selected = {field.strip() for field in fields.split(",")}
    cursor_fields = [field for field in ("id", "fecha") if field not in selected]
    return ",".join([*cursor_fields, fields])


def fetch_sales_rows_keyset(
    supabase_client: Any,
    *,
    select_fields: str,
    fecha_inicio: str,
    fecha_fin: str,
    local_ids: Optional[Iterable[str]] = None,
    local_id: Optional[str] = None,
    mall_id: Optional[str] = None,
    page_size: int = DEFAULT_SALES_PAGE_SIZE,
) -> List[Dict[str, Any]]:
    """Fetch a date window with keyset pagination over ``(fecha, id)``."""
    safe_page_size = max(1, min(int(page_size or DEFAULT_SALES_PAGE_SIZE), DEFAULT_SALES_PAGE_SIZE))
    normalized_local_ids = list(dict.fromkeys(str(value) for value in (local_ids or []) if value))
    if local_ids is not None and not normalized_local_ids:
        return []

    rows: List[Dict[str, Any]] = []
    last_date: Any = None
    last_id: Any = None
    while True:
        query = (
            supabase_client.table("ventas")
            .select(_select_with_cursor(select_fields))
            .gte("fecha", fecha_inicio)
            .lte("fecha", fecha_fin)
        )
        if mall_id:
            query = query.eq("mall_id", mall_id)
        if local_id:
            query = query.eq("local_id", local_id)
        elif local_ids is not None:
            query = query.in_("local_id", normalized_local_ids)
        if last_date is not None and last_id is not None:
            query = query.or_(
                f"fecha.gt.{last_date},and(fecha.eq.{last_date},id.gt.{last_id})"
            )

        chunk = (
            query.order("fecha")
            .order("id")
            .limit(safe_page_size)
            .execute()
            .data
            or []
        )
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < safe_page_size:
            break

        next_date = chunk[-1].get("fecha")
        next_id = chunk[-1].get("id")
        if next_date is None or next_id is None or (next_date, next_id) == (last_date, last_id):
            raise RuntimeError("La paginacion de ventas no pudo avanzar por fecha e id.")
        last_date = next_date
        last_id = next_id

    return rows
