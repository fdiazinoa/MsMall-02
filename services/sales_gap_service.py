"""Shared sales-gap calculation used by audit reports and email notifications."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from services.sales_query_service import DEFAULT_SALES_PAGE_SIZE, fetch_sales_rows_keyset


SALES_PAGE_SIZE = DEFAULT_SALES_PAGE_SIZE


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
    return load_actual_sales_dates_by_local(
        supabase_client,
        local_ids=[local_id],
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    ).get(str(local_id), set())


def load_actual_sales_dates_by_local(
    supabase_client: Any,
    *,
    local_ids: List[str],
    fecha_inicio: str,
    fecha_fin: str,
) -> Dict[str, Set[str]]:
    """Load distinct dates for many stores in one keyset-paginated scan."""
    normalized_ids = list(dict.fromkeys(str(local_id) for local_id in local_ids if local_id))
    dates_by_local: Dict[str, Set[str]] = {local_id: set() for local_id in normalized_ids}
    rows = fetch_sales_rows_keyset(
        supabase_client,
        select_fields="local_id,fecha",
        local_ids=normalized_ids,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        page_size=SALES_PAGE_SIZE,
    )
    for row in rows:
        local_id = str(row.get("local_id") or "")
        normalized_date = normalize_sales_date(row.get("fecha"))
        if local_id in dates_by_local and normalized_date:
            dates_by_local[local_id].add(normalized_date)
    return dates_by_local


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
