"""Bounded store diagnostics for Big Data commercial intelligence Phase 2."""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional


PHASE_TWO_VERSION = "big-data-diagnostic-phase-two-v1"
DIAGNOSTIC_WINDOW_DAYS = 90
MAX_MALL_LOCALS = 500
MAX_CATEGORY_MEMBERS = 200
MAX_PEER_ROWS = 10000
MAX_IMPORT_LOGS = 100


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _median(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.median(materialized) if materialized else 0.0


def _percent_change(observed: float, expected: float) -> Optional[float]:
    if not expected:
        return None
    return (observed - expected) / abs(expected) * 100


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _filename_matches_target(filename: str, target_date: date) -> bool:
    normalized = "".join(character for character in filename if character.isdigit())
    tokens = {
        target_date.strftime("%Y%m%d"),
        target_date.strftime("%d%m%Y"),
        target_date.strftime("%y%m%d"),
        target_date.strftime("%d%m%y"),
    }
    return any(token in normalized for token in tokens)


def _import_evidence(
    logs: Iterable[Mapping[str, Any]], target_date: date
) -> tuple[list[dict[str, Any]], bool]:
    evidence: list[dict[str, Any]] = []
    has_issue = False
    for log in logs:
        filename = str(log.get("archivo") or "Archivo no identificado")
        log_date = _day(log.get("fecha_hora")) if log.get("fecha_hora") else None
        if _filename_matches_target(filename, target_date):
            match = "FILE_DATE"
        elif log_date and abs((log_date - target_date).days) <= 2:
            match = "PROCESSING_DATE"
        else:
            match = "PERIOD"
        status = _normalize_status(log.get("estado"))
        error_count = _integer(log.get("error_count"))
        issue = status in {
            "error",
            "failed",
            "fail",
            "parcial",
            "partial",
            "no_encontrado",
        } or error_count > 0
        has_issue = has_issue or (issue and match != "PERIOD")
        evidence.append(
            {
                "date": str(log.get("fecha_hora") or ""),
                "filename": filename,
                "status": status or "sin_estado",
                "channel": log.get("canal"),
                "message": log.get("mensaje"),
                "records_processed": _integer(log.get("records_processed")),
                "error_count": error_count,
                "match": match,
                "has_issue": issue,
            }
        )
    evidence.sort(
        key=lambda row: (
            {"FILE_DATE": 2, "PROCESSING_DATE": 1, "PERIOD": 0}[row["match"]],
            row["date"],
        ),
        reverse=True,
    )
    return evidence[:10], has_issue


def build_phase_two_diagnostic(
    *,
    mall_id: str,
    local: Mapping[str, Any],
    start_date: date,
    end_date: date,
    target_date: date,
    local_rows: Iterable[Mapping[str, Any]],
    peer_rows: Iterable[Mapping[str, Any]] = (),
    peer_names: Optional[Mapping[str, str]] = None,
    category_id: Optional[str] = None,
    category_name: Optional[str] = None,
    category_source: Optional[str] = None,
    logs: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a deterministic diagnosis without performing database access."""
    peer_names = peer_names or {}
    local_id = str(local.get("id") or "")
    normalized_local_rows: dict[date, dict[str, Any]] = {}
    for row in local_rows:
        if not row.get("period_date"):
            continue
        row_date = _day(row["period_date"])
        normalized_local_rows[row_date] = {
            "sales_net": _number(row.get("sales_net")),
            "transactions": _integer(row.get("transaction_count")),
            "coverage_status": str(row.get("coverage_status") or "complete").lower(),
        }

    target = normalized_local_rows.get(target_date)
    target_sales = _number(target.get("sales_net")) if target else 0.0
    same_weekday_peers = [
        row["sales_net"]
        for row_date, row in normalized_local_rows.items()
        if row_date != target_date and row_date.weekday() == target_date.weekday()
    ]
    fallback_peers = [
        row["sales_net"]
        for row_date, row in normalized_local_rows.items()
        if row_date != target_date
    ]
    baseline_peers = (
        same_weekday_peers if len(same_weekday_peers) >= 2 else fallback_peers
    )
    expected_sales = _median(baseline_peers)
    contribution = target_sales - expected_sales
    deviation_percent = _percent_change(target_sales, expected_sales)

    weekday_baselines = {
        weekday: _median(
            row["sales_net"]
            for row_date, row in normalized_local_rows.items()
            if row_date.weekday() == weekday
        )
        for weekday in range(7)
    }
    timeline = [
        {
            "date": row_date.isoformat(),
            "sales_net": round(row["sales_net"], 2),
            "expected_sales": round(weekday_baselines[row_date.weekday()], 2),
            "transactions": row["transactions"],
            "coverage_status": row["coverage_status"],
            "is_target": row_date == target_date,
        }
        for row_date, row in sorted(normalized_local_rows.items())
    ]

    peer_totals: dict[str, float] = {}
    for row in peer_rows:
        member_id = str(row.get("local_id") or row.get("dimension_key") or "")
        if not member_id:
            continue
        peer_totals[member_id] = peer_totals.get(member_id, 0.0) + _number(
            row.get("sales_net")
        )
    comparable_values = sorted(peer_totals.values())
    local_period_sales = sum(row["sales_net"] for row in normalized_local_rows.values())
    benchmark: dict[str, Any]
    has_comparison_group = bool(category_id or category_name)
    if has_comparison_group and local_id in peer_totals and len(comparable_values) >= 3:
        category_median = _median(comparable_values)
        category_average = sum(comparable_values) / len(comparable_values)
        rank = sorted(comparable_values, reverse=True).index(peer_totals[local_id]) + 1
        benchmark = {
            "status": "OK",
            "category_id": category_id,
            "category_name": category_name,
            "category_source": category_source,
            "comparable_stores": len(comparable_values),
            "local_sales": round(peer_totals[local_id], 2),
            "category_average": round(category_average, 2),
            "category_median": round(category_median, 2),
            "difference_vs_median_percent": round(
                _percent_change(peer_totals[local_id], category_median) or 0, 1
            ),
            "rank": rank,
            "percentile": round(
                sum(value <= peer_totals[local_id] for value in comparable_values)
                / len(comparable_values)
                * 100,
                1,
            ),
            "category_share_percent": round(
                peer_totals[local_id] / sum(comparable_values) * 100, 1
            )
            if sum(comparable_values)
            else 0.0,
            "leaders": [
                {
                    "local_id": member_id,
                    "local_name": peer_names.get(member_id, "Local"),
                    "sales_net": round(total, 2),
                }
                for member_id, total in sorted(
                    peer_totals.items(), key=lambda item: item[1], reverse=True
                )[:3]
            ],
        }
    else:
        benchmark = {
            "status": "INSUFFICIENT_DATA",
            "category_id": category_id,
            "category_name": category_name,
            "category_source": category_source,
            "comparable_stores": len(comparable_values),
            "local_sales": round(local_period_sales, 2),
            "reason": (
                "El local no tiene categoría homologada."
                if not has_comparison_group
                else "Se requieren al menos tres locales comparables con datos."
            ),
        }

    import_evidence, related_import_issue = _import_evidence(logs, target_date)
    target_coverage_issue = not target or target.get("coverage_status") != "complete"
    has_commercial_signal = (
        deviation_percent is not None and abs(deviation_percent) >= 20
    )
    if target_coverage_issue and has_commercial_signal:
        classification = "MIXED"
    elif related_import_issue:
        classification = "MIXED" if has_commercial_signal else "IMPORT_ISSUE"
    elif len(baseline_peers) < 2:
        classification = "INSUFFICIENT_DATA"
    else:
        classification = "COMMERCIAL_MOVEMENT"

    factors: list[dict[str, Any]] = []
    if deviation_percent is not None:
        factors.append(
            {
                "type": "LOCAL_BASELINE",
                "tone": "positive" if deviation_percent >= 0 else "negative",
                "label": "Comportamiento propio",
                "detail": (
                    f"El local estuvo {abs(deviation_percent):.1f}% "
                    f"{'por encima' if deviation_percent >= 0 else 'por debajo'} "
                    f"de su referencia para ese día de semana."
                ),
            }
        )
    if benchmark.get("status") == "OK":
        difference = _number(benchmark.get("difference_vs_median_percent"))
        factors.append(
            {
                "type": "CATEGORY_BENCHMARK",
                "tone": "positive" if difference >= 0 else "negative",
                "label": "Comparación con su categoría",
                "detail": (
                    f"Ocupa la posición {benchmark['rank']} de "
                    f"{benchmark['comparable_stores']} y está "
                    f"{abs(difference):.1f}% "
                    f"{'sobre' if difference >= 0 else 'bajo'} la mediana."
                ),
            }
        )
    factors.append(
        {
            "type": "IMPORT_EVIDENCE",
            "tone": "warning" if related_import_issue else "neutral",
            "label": "Evidencia de importación",
            "detail": (
                "Se encontraron errores o cargas parciales relacionadas con la fecha."
                if related_import_issue
                else "No se encontraron fallos relacionados en la evidencia disponible."
            ),
        }
    )

    confidence = min(
        0.95,
        0.4
        + min(len(baseline_peers), 6) * 0.06
        + min(_integer(benchmark.get("comparable_stores")), 5) * 0.03,
    )
    if target_coverage_issue:
        confidence = min(confidence, 0.45)
    if classification == "INSUFFICIENT_DATA":
        confidence = min(confidence, 0.4)

    if classification == "COMMERCIAL_MOVEMENT":
        summary = (
            "La evidencia disponible apunta a un movimiento comercial del local, "
            "sin fallos de importación relacionados."
        )
        recommendation = (
            "Validar el contexto comercial del local y comparar el resultado con "
            "promociones, tráfico y actividad del mall."
        )
    elif classification == "IMPORT_ISSUE":
        summary = (
            "La variación puede estar explicada por falta o degradación de datos, "
            "no por desempeño comercial."
        )
        recommendation = (
            "Corregir o reprocesar la importación relacionada antes de evaluar el local."
        )
    elif classification == "MIXED":
        summary = (
            "Existe una señal comercial, pero coincide con problemas de cobertura o "
            "importación que reducen la confiabilidad."
        )
        recommendation = (
            "Resolver la evidencia de datos y recalcular el período antes de tomar una decisión."
        )
    else:
        summary = "No existe historia comparable suficiente para concluir la causa."
        recommendation = (
            "Esperar más días comparables o completar la clasificación comercial del local."
        )

    expected_days = (end_date - start_date).days + 1
    complete_days = sum(
        row["coverage_status"] == "complete" for row in normalized_local_rows.values()
    )
    return {
        "mall_id": mall_id,
        "local": {
            "id": local_id,
            "name": str(local.get("nombre") or "Local"),
            "business_type": local.get("rubro"),
            "category_id": category_id,
            "category_name": category_name,
            "category_source": category_source,
        },
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "target_date": target_date.isoformat(),
        },
        "headline": {
            "observed_sales": round(target_sales, 2),
            "expected_sales": round(expected_sales, 2),
            "contribution": round(contribution, 2),
            "deviation_percent": round(deviation_percent, 1)
            if deviation_percent is not None
            else None,
            "peer_days": len(baseline_peers),
        },
        "benchmark": benchmark,
        "timeline": timeline,
        "evidence": {
            "imports": import_evidence,
            "related_import_issue": related_import_issue,
            "coverage": {
                "expected_days": expected_days,
                "days_with_data": len(normalized_local_rows),
                "complete_days": complete_days,
                "percent": round(
                    len(normalized_local_rows) / expected_days * 100, 1
                )
                if expected_days
                else 0.0,
                "target_status": (
                    target.get("coverage_status") if target else "missing"
                ),
            },
        },
        "diagnosis": {
            "classification": classification,
            "confidence": round(confidence, 2),
            "summary": summary,
            "factors": factors,
            "recommendation": recommendation,
        },
        "methodology": (
            "Mediana del mismo día de semana para el local, comparación con locales "
            "homologados de la misma categoría y evidencia de importación acotada al período."
        ),
        "version": PHASE_TWO_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


class BigDataPhaseTwoService:
    """Supabase adapter with mall-scoped, date-bounded diagnostic queries."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    def diagnostic(
        self,
        mall_id: str,
        local_id: str,
        start_date: date,
        end_date: date,
        target_date: date,
    ) -> Optional[dict[str, Any]]:
        window_start = max(
            start_date, target_date - timedelta(days=DIAGNOSTIC_WINDOW_DAYS - 1)
        )
        window_end = target_date
        local_response = (
            self.supabase.table("locales")
            .select("id,nombre,rubro,mall_id,activo")
            .eq("mall_id", mall_id)
            .eq("id", local_id)
            .maybe_single()
            .execute()
        )
        local = getattr(local_response, "data", None)
        if not local:
            return None

        mall_locals = (
            self.supabase.table("locales")
            .select("id,nombre,rubro")
            .eq("mall_id", mall_id)
            .eq("activo", True)
            .limit(MAX_MALL_LOCALS)
            .execute()
            .data
            or []
        )
        mall_local_ids = [str(row["id"]) for row in mall_locals if row.get("id")]
        classifications = []
        if mall_local_ids:
            classifications = (
                self.supabase.table("local_commercial_classifications")
                .select("local_id,category_id")
                .in_("local_id", mall_local_ids)
                .limit(MAX_MALL_LOCALS)
                .execute()
                .data
                or []
            )
        category_by_local = {
            str(row.get("local_id")): str(row.get("category_id"))
            for row in classifications
            if row.get("local_id") and row.get("category_id")
        }
        category_id = category_by_local.get(local_id)
        category_name = None
        category_source = None
        if category_id:
            category_response = (
                self.supabase.table("commercial_taxonomy")
                .select("id,name")
                .eq("mall_id", mall_id)
                .eq("id", category_id)
                .maybe_single()
                .execute()
            )
            category = getattr(category_response, "data", None) or {}
            category_name = category.get("name")
            category_source = "HOMOLOGATED"
        elif local.get("rubro"):
            category_name = str(local.get("rubro"))
            category_source = "RUBRO_FALLBACK"

        local_rows = (
            self.supabase.table("big_data_daily_aggregates")
            .select(
                "period_date,local_id,sales_net,transaction_count,coverage_status"
            )
            .eq("mall_id", mall_id)
            .eq("grain", "local")
            .eq("local_id", local_id)
            .gte("period_date", window_start.isoformat())
            .lte("period_date", window_end.isoformat())
            .order("period_date")
            .limit(DIAGNOSTIC_WINDOW_DAYS)
            .execute()
            .data
            or []
        )
        if category_id:
            member_ids = [
                member_id
                for member_id, member_category_id in category_by_local.items()
                if member_category_id == category_id
            ][:MAX_CATEGORY_MEMBERS]
        elif category_name:
            normalized_rubro = category_name.strip().casefold()
            member_ids = [
                str(row["id"])
                for row in mall_locals
                if row.get("id")
                and str(row.get("rubro") or "").strip().casefold() == normalized_rubro
            ][:MAX_CATEGORY_MEMBERS]
        else:
            member_ids = []
        peer_rows = []
        if member_ids:
            peer_rows = (
                self.supabase.table("big_data_daily_aggregates")
                .select("period_date,dimension_key,local_id,sales_net")
                .eq("mall_id", mall_id)
                .eq("grain", "local")
                .in_("local_id", member_ids)
                .gte("period_date", window_start.isoformat())
                .lte("period_date", window_end.isoformat())
                .limit(MAX_PEER_ROWS)
                .execute()
                .data
                or []
            )
        evidence_end = (
            min(date.today(), target_date + timedelta(days=2)) + timedelta(days=1)
        )
        logs = (
            self.supabase.table("logs_carga")
            .select(
                "fecha_hora,estado,archivo,canal,mensaje,records_processed,"
                "error_count,detalles,metadata"
            )
            .eq("mall_id", mall_id)
            .eq("local_id", local_id)
            .gte("fecha_hora", (window_start - timedelta(days=2)).isoformat())
            .lt("fecha_hora", evidence_end.isoformat())
            .order("fecha_hora", desc=True)
            .limit(MAX_IMPORT_LOGS)
            .execute()
            .data
            or []
        )
        return build_phase_two_diagnostic(
            mall_id=mall_id,
            local=local,
            start_date=window_start,
            end_date=window_end,
            target_date=target_date,
            local_rows=local_rows,
            peer_rows=peer_rows,
            peer_names={
                str(row.get("id")): str(row.get("nombre") or "Local")
                for row in mall_locals
            },
            category_id=category_id,
            category_name=str(category_name) if category_name else None,
            category_source=category_source,
            logs=logs,
        )
