"""Shared sales-gap calculation used by audit reports and email notifications."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import pandas as pd


SALES_PAGE_SIZE = 1000


def normalize_sales_date(raw_value: Any) -> Optional[str]:
    """Normalize database date/timestamp values to YYYY-MM-DD."""
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
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None


def expected_sales_dates(fecha_inicio: str, fecha_fin: str) -> Set[str]:
    start_date = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    end_date = datetime.strptime(fecha_fin, "%Y-%m-%d")
    total_days = (end_date - start_date).days + 1
    if total_days < 1:
        raise ValueError("fecha_fin debe ser igual o posterior a fecha_inicio")
    return {
        (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(total_days)
    }


def load_actual_sales_dates_for_local(
    supabase_client: Any,
    *,
    local_id: str,
    fecha_inicio: str,
    fecha_fin: str,
) -> Set[str]:
    """Load every distinct sales date for one store using deterministic pagination."""
    rows: List[Dict[str, Any]] = []
    page = 0
    while True:
        chunk = (
            supabase_client.table("ventas")
            .select("id, fecha")
            .eq("local_id", local_id)
            .gte("fecha", fecha_inicio)
            .lte("fecha", fecha_fin)
            .order("id")
            .range(page * SALES_PAGE_SIZE, (page + 1) * SALES_PAGE_SIZE - 1)
            .execute()
        ).data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < SALES_PAGE_SIZE:
            break
        page += 1

    return {
        normalized
        for normalized in (normalize_sales_date(row.get("fecha")) for row in rows)
        if normalized
    }


def load_missing_sales_dates_for_local(
    supabase_client: Any,
    *,
    local_id: str,
    fecha_inicio: str,
    fecha_fin: str,
) -> List[str]:
    expected_dates = expected_sales_dates(fecha_inicio, fecha_fin)
    actual_dates = load_actual_sales_dates_for_local(
        supabase_client,
        local_id=local_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    return sorted(expected_dates - actual_dates)
