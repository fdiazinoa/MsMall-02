"""Efficient read paths for the sales cube."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


AGGREGATE_PAGE_SIZE = 1000
AGGREGATE_MIN_RANGE_DAYS = 8
logger = logging.getLogger(__name__)


def should_use_daily_aggregates(fecha_inicio: str, fecha_fin: str) -> bool:
    """Use compact daily data for ranges likely to exceed the HTTP timeout."""
    try:
        start = date.fromisoformat(fecha_inicio)
        end = date.fromisoformat(fecha_fin)
    except (TypeError, ValueError):
        return False
    return (end - start).days + 1 >= AGGREGATE_MIN_RANGE_DAYS


def fetch_sales_cube_daily_aggregates(
    supabase_client: Any,
    *,
    mall_id: str,
    local_ids: Iterable[str],
    fecha_inicio: str,
    fecha_fin: str,
) -> Optional[List[Dict[str, Any]]]:
    """Return complete daily aggregates, or ``None`` when raw sales are safer."""
    normalized_ids = list(dict.fromkeys(str(value) for value in local_ids if value))
    if not normalized_ids:
        return []
    if not should_use_daily_aggregates(fecha_inicio, fecha_fin):
        return None

    try:
        pending = (
            supabase_client.table("big_data_refresh_queue")
            .select("affected_date,status")
            .eq("mall_id", mall_id)
            .gte("affected_date", fecha_inicio)
            .lte("affected_date", fecha_fin)
            .in_("status", ["pending", "failed"])
            .limit(AGGREGATE_PAGE_SIZE)
            .execute()
            .data
            or []
        )
        if pending:
            affected_dates = sorted(
                str(row.get("affected_date")) for row in pending if row.get("affected_date")
            )
            if affected_dates:
                refresh_start = affected_dates[0]
                refresh_end = affected_dates[-1]
                supabase_client.rpc(
                    "refresh_big_data_aggregates",
                    {
                        "p_mall_id": mall_id,
                        "p_start_date": refresh_start,
                        "p_end_date": refresh_end,
                        "p_calculation_version": "v1",
                    },
                ).execute()
                (
                    supabase_client.table("big_data_refresh_queue")
                    .update(
                        {
                            "status": "completed",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "last_error": None,
                        }
                    )
                    .eq("mall_id", mall_id)
                    .gte("affected_date", refresh_start)
                    .lte("affected_date", refresh_end)
                    .in_("status", ["pending", "failed"])
                    .execute()
                )

        rows: List[Dict[str, Any]] = []
        last_date: Any = None
        last_dimension: Any = None
        while True:
            query = (
                supabase_client.table("big_data_daily_aggregates")
                .select(
                    "period_date,dimension_key,local_id,sales_net,sales_gross,"
                    "taxes,transaction_count,coverage_status"
                )
                .eq("mall_id", mall_id)
                .eq("grain", "local")
                .in_("local_id", normalized_ids)
                .gte("period_date", fecha_inicio)
                .lte("period_date", fecha_fin)
            )
            if last_date is not None and last_dimension is not None:
                query = query.or_(
                    "period_date.gt."
                    f"{last_date},and(period_date.eq.{last_date},dimension_key.gt.{last_dimension})"
                )

            chunk = (
                query.order("period_date")
                .order("dimension_key")
                .limit(AGGREGATE_PAGE_SIZE)
                .execute()
                .data
                or []
            )
            if not chunk:
                break
            if any(row.get("coverage_status") != "complete" for row in chunk):
                return None
            rows.extend(chunk)
            if len(chunk) < AGGREGATE_PAGE_SIZE:
                break

            next_date = chunk[-1].get("period_date")
            next_dimension = chunk[-1].get("dimension_key")
            if (
                next_date is None
                or next_dimension is None
                or (next_date, next_dimension) == (last_date, last_dimension)
            ):
                raise RuntimeError("La paginacion del agregado del cubo no pudo avanzar.")
            last_date = next_date
            last_dimension = next_dimension

        if not rows:
            return None

        return [
            {
                "local_id": row.get("local_id"),
                "fecha": row.get("period_date"),
                "total_neto": row.get("sales_net") or 0,
                "total_bruto": row.get("sales_gross") or 0,
                "total_impuestos": row.get("taxes") or 0,
                "transacciones": row.get("transaction_count") or 0,
            }
            for row in rows
        ]
    except Exception as exc:
        # The aggregate subsystem is optional. The caller retains a raw-sales fallback.
        logger.warning("No se pudo usar el agregado diario del cubo: %s", exc)
        return None
