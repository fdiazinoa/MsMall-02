"""Phase 1 commercial intelligence derived from bounded Big Data aggregates.

The contract intentionally answers questions that the operational BI dashboard
does not: when a pattern repeats, whether a date is unusual, which stores
explain the movement, and whether the available data is reliable enough to act.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional


WEEKDAY_LABELS = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
PHASE_ONE_VERSION = "big-data-intelligence-phase-one-v1"
CONTRIBUTOR_WINDOW_DAYS = 42
QUALITY_WINDOW_DAYS = 63
EVENT_TYPE_LABELS = {
    "PROMOTION": "Promoción",
    "HALLWAY_SALE": "Venta de pasillo",
    "MALL_ACTIVITY": "Actividad del mall",
    "HOLIDAY": "Feriado especial",
    "OTHER": "Otro evento",
}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _date_range(start_date: date, end_date: date) -> list[date]:
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]


def _median(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.median(materialized) if materialized else 0.0


def _average(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.mean(materialized) if materialized else 0.0


def _percent_change(observed: float, expected: float) -> Optional[float]:
    if not expected:
        return None
    return (observed - expected) / abs(expected) * 100


def _normalize_mall_rows(rows: Iterable[Mapping[str, Any]]) -> dict[date, dict[str, Any]]:
    normalized: dict[date, dict[str, Any]] = {}
    for row in rows:
        if not row.get("period_date"):
            continue
        row_date = _day(row["period_date"])
        item = normalized.setdefault(
            row_date,
            {
                "period_date": row_date,
                "sales_net": 0.0,
                "transactions": 0,
                "coverage_status": row.get("coverage_status"),
                "updated_at": row.get("updated_at"),
            },
        )
        item["sales_net"] += _number(row.get("sales_net"))
        item["transactions"] += int(
            _number(row.get("records_processed") or row.get("transaction_count"))
        )
        if row.get("updated_at"):
            item["updated_at"] = row.get("updated_at")
    return normalized


def _normalize_local_rows(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[date, float]]:
    normalized: dict[str, dict[date, float]] = defaultdict(dict)
    for row in rows:
        local_id = str(row.get("local_id") or row.get("dimension_key") or "")
        if not local_id or not row.get("period_date"):
            continue
        row_date = _day(row["period_date"])
        normalized[local_id][row_date] = (
            normalized[local_id].get(row_date, 0.0) + _number(row.get("sales_net"))
        )
    return dict(normalized)


def _events_by_date(
    events: Iterable[Mapping[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[dict[date, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    normalized: list[dict[str, Any]] = []
    for event in events:
        event_start = max(_day(event.get("start_date")), start_date)
        event_end = min(_day(event.get("end_date")), end_date)
        if event_end < event_start:
            continue
        item = {
            "id": str(event.get("id") or ""),
            "name": str(event.get("name") or "Evento del mall"),
            "event_type": str(event.get("event_type") or "OTHER"),
            "event_type_label": EVENT_TYPE_LABELS.get(
                str(event.get("event_type") or "OTHER"), "Otro evento"
            ),
            "start_date": _day(event.get("start_date")).isoformat(),
            "end_date": _day(event.get("end_date")).isoformat(),
            "expected_impact": str(event.get("expected_impact") or "NEUTRAL"),
            "notes": event.get("notes"),
        }
        normalized.append(item)
        for event_date in _date_range(event_start, event_end):
            by_date[event_date].append(item)
    return dict(by_date), normalized


def _confidence_from_peers(peer_count: int, quality_score: float) -> float:
    peer_confidence = min(0.96, 0.5 + peer_count * 0.07)
    return round(peer_confidence * max(min(quality_score / 100, 1), 0.35), 2)


def _quality_status(score: float) -> str:
    if score >= 90:
        return "RELIABLE"
    if score >= 75:
        return "REVIEW"
    return "LOW_CONFIDENCE"


def _build_quality(
    *,
    calendar_dates: list[date],
    mall_by_date: Mapping[date, Mapping[str, Any]],
    local_by_id: Mapping[str, Mapping[date, float]],
    logs: Iterable[Mapping[str, Any]],
    active_local_count: int,
    last_processed_sale_date: Optional[Any],
    last_analytics_update: Optional[Any],
    local_window_start: date,
    analysis_end: date,
) -> dict[str, Any]:
    expected_days = len(calendar_dates)
    present_dates = [row_date for row_date in calendar_dates if row_date in mall_by_date]
    day_coverage = len(present_dates) / expected_days * 100 if expected_days else 0.0
    missing_dates = [
        row_date.isoformat() for row_date in calendar_dates if row_date not in mall_by_date
    ]

    local_window_dates = _date_range(local_window_start, analysis_end)
    reporting_local_ids = {
        local_id
        for local_id, values in local_by_id.items()
        if any(row_date in values for row_date in local_window_dates)
    }
    reported_store_days = sum(
        1
        for local_id in reporting_local_ids
        for row_date in local_window_dates
        if row_date in local_by_id.get(local_id, {})
    )
    expected_store_days = len(reporting_local_ids) * len(local_window_dates)
    store_day_coverage = (
        reported_store_days / expected_store_days * 100 if expected_store_days else 0.0
    )

    log_rows = list(logs)
    failed_imports = sum(
        1
        for row in log_rows
        if str(row.get("estado") or "").strip().lower() in {"error", "failed", "fallido"}
    )
    partial_imports = sum(
        1
        for row in log_rows
        if str(row.get("estado") or "").strip().lower() in {"parcial", "partial"}
    )
    imports_evaluated = len(log_rows)
    failure_rate = failed_imports / imports_evaluated if imports_evaluated else 0.0
    partial_rate = partial_imports / imports_evaluated if imports_evaluated else 0.0
    import_health = max(100 - failure_rate * 100 - partial_rate * 50, 0)

    if expected_store_days:
        score = day_coverage * 0.55 + store_day_coverage * 0.25 + import_health * 0.20
    else:
        score = day_coverage * 0.80 + import_health * 0.20

    last_processed = _day(last_processed_sale_date) if last_processed_sale_date else None
    stale_days = max((analysis_end - last_processed).days, 0) if last_processed else None
    if stale_days is None:
        score = min(score, 55)
    elif stale_days > 2:
        score = min(score, 65)
    elif stale_days > 1:
        score = min(score, 82)
    if failure_rate >= 0.05:
        score = min(score, 84)
    elif failure_rate >= 0.01:
        score = min(score, 89)

    score = round(max(min(score, 100), 0), 1)
    status = _quality_status(score)
    confidence = "HIGH" if status == "RELIABLE" else "MEDIUM" if status == "REVIEW" else "LOW"
    blockers: list[str] = []
    if day_coverage < 90:
        blockers.append("El período contiene días sin agregados de venta.")
    if expected_store_days and store_day_coverage < 80:
        blockers.append("La cobertura local-día es inferior a 80%.")
    if failed_imports:
        blockers.append(
            f"Existen {failed_imports} importaciones fallidas "
            f"({failure_rate * 100:.1f}%) en la ventana de calidad."
        )
    if partial_imports:
        blockers.append(f"Existen {partial_imports} importaciones parciales en la ventana de calidad.")
    if stale_days is None:
        blockers.append("El proceso analítico todavía no tiene fecha de corte confirmada.")
    elif stale_days > 1:
        blockers.append(f"El último dato procesado tiene {stale_days} días de rezago.")

    return {
        "score": score,
        "status": status,
        "confidence": confidence,
        "day_coverage_percent": round(day_coverage, 1),
        "store_day_coverage_percent": round(store_day_coverage, 1),
        "expected_days": expected_days,
        "days_with_data": len(present_dates),
        "missing_days": len(missing_dates),
        "missing_dates": missing_dates[:31],
        "active_local_count": active_local_count,
        "reporting_local_count": len(reporting_local_ids),
        "failed_imports": failed_imports,
        "failed_import_percent": round(failure_rate * 100, 1),
        "partial_imports": partial_imports,
        "partial_import_percent": round(partial_rate * 100, 1),
        "imports_evaluated": imports_evaluated,
        "last_processed_sale_date": last_processed.isoformat() if last_processed else None,
        "last_analytics_update": last_analytics_update,
        "stale_days": stale_days,
        "coverage_window": {
            "start": local_window_start.isoformat(),
            "end": analysis_end.isoformat(),
        },
        "blockers": blockers,
    }


def _build_contributors(
    *,
    target_date: date,
    impact: float,
    local_by_id: Mapping[str, Mapping[date, float]],
    local_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for local_id, values_by_date in local_by_id.items():
        observed = values_by_date.get(target_date, 0.0)
        weekday_peers = [
            value
            for row_date, value in values_by_date.items()
            if row_date != target_date and row_date.weekday() == target_date.weekday()
        ]
        fallback_peers = [
            value for row_date, value in values_by_date.items() if row_date != target_date
        ]
        peers = weekday_peers if len(weekday_peers) >= 2 else fallback_peers
        if not peers:
            continue
        expected = _median(peers)
        contribution = observed - expected
        if impact and contribution and (contribution > 0) != (impact > 0):
            continue
        candidates.append(
            {
                "local_id": local_id,
                "local_name": local_names.get(local_id, "Local"),
                "observed_sales": round(observed, 2),
                "expected_sales": round(expected, 2),
                "contribution": round(contribution, 2),
                "peer_days": len(peers),
            }
        )
    candidates.sort(key=lambda row: abs(row["contribution"]), reverse=True)
    selected = candidates[:4]
    explained = sum(abs(row["contribution"]) for row in selected)
    denominator = abs(impact) if impact else explained
    for row in selected:
        row["impact_share_percent"] = round(
            abs(row["contribution"]) / denominator * 100, 1
        ) if denominator else 0.0
    return selected


def build_phase_one_intelligence(
    *,
    mall_id: str,
    start_date: date,
    end_date: date,
    mall_rows: Iterable[Mapping[str, Any]],
    local_rows: Iterable[Mapping[str, Any]],
    logs: Iterable[Mapping[str, Any]] = (),
    local_names: Optional[Mapping[str, str]] = None,
    active_local_count: int = 0,
    holidays: Optional[Mapping[date, str]] = None,
    calendar_events: Iterable[Mapping[str, Any]] = (),
    last_processed_sale_date: Optional[Any] = None,
    last_analytics_update: Optional[Any] = None,
    country_code: Optional[str] = None,
) -> dict[str, Any]:
    """Build the full Phase 1 response without performing database access."""
    analysis_end = min(end_date, date.today())
    if analysis_end < start_date:
        analysis_end = start_date
    calendar_dates = _date_range(start_date, analysis_end)
    mall_by_date = _normalize_mall_rows(mall_rows)
    local_by_id = _normalize_local_rows(local_rows)
    local_names = local_names or {}
    holiday_map = dict(holidays or {})
    event_map, normalized_events = _events_by_date(
        calendar_events, start_date, analysis_end
    )
    known_context_dates = set(event_map)
    local_window_start = max(start_date, analysis_end - timedelta(days=CONTRIBUTOR_WINDOW_DAYS - 1))

    quality = _build_quality(
        calendar_dates=calendar_dates,
        mall_by_date=mall_by_date,
        local_by_id=local_by_id,
        logs=logs,
        active_local_count=active_local_count,
        last_processed_sale_date=last_processed_sale_date,
        last_analytics_update=last_analytics_update,
        local_window_start=local_window_start,
        analysis_end=analysis_end,
    )

    baseline_by_weekday: dict[int, list[float]] = defaultdict(list)
    for row_date, row in mall_by_date.items():
        if (
            start_date <= row_date <= analysis_end
            and row_date not in holiday_map
            and row_date not in known_context_dates
        ):
            baseline_by_weekday[row_date.weekday()].append(_number(row.get("sales_net")))

    calendar_items: list[dict[str, Any]] = []
    anomaly_candidates: list[dict[str, Any]] = []
    explained_candidates: list[dict[str, Any]] = []
    for row_date in calendar_dates:
        row = mall_by_date.get(row_date)
        observed = _number(row.get("sales_net")) if row else 0.0
        peers = [
            value
            for peer_date, peer_row in mall_by_date.items()
            if peer_date != row_date
            and peer_date.weekday() == row_date.weekday()
            and peer_date not in holiday_map
            and peer_date not in known_context_dates
            and start_date <= peer_date <= analysis_end
            for value in [_number(peer_row.get("sales_net"))]
        ]
        baseline = _median(peers)
        deviation = _percent_change(observed, baseline) if row else None
        holiday_name = holiday_map.get(row_date)
        day_events = event_map.get(row_date, [])
        is_weekend = row_date.weekday() >= 5
        is_outlier = bool(
            row
            and deviation is not None
            and abs(deviation) >= 30
            and len(peers) >= 2
        )
        event_matches_direction = any(
            event["expected_impact"] == "NEUTRAL"
            or (event["expected_impact"] == "UP" and observed - baseline >= 0)
            or (event["expected_impact"] == "DOWN" and observed - baseline < 0)
            for event in day_events
        )
        known_context_matches = bool(holiday_name) or event_matches_direction
        status = (
            "MISSING"
            if not row
            else "ANOMALY"
            if is_outlier and not known_context_matches
            else "EXPLAINED_EVENT"
            if day_events
            else "HOLIDAY"
            if holiday_name
            else "ANOMALY"
            if is_outlier
            else "WEEKEND"
            if is_weekend
            else "NORMAL"
        )
        item = {
            "date": row_date.isoformat(),
            "weekday": row_date.weekday(),
            "weekday_label": WEEKDAY_LABELS[row_date.weekday()],
            "sales_net": round(observed, 2) if row else None,
            "transactions": int(row.get("transactions") or 0) if row else 0,
            "expected_sales": round(baseline, 2) if baseline else None,
            "deviation_percent": round(deviation, 1) if deviation is not None else None,
            "impact": round(observed - baseline, 2) if row and baseline else None,
            "is_weekend": is_weekend,
            "is_holiday": bool(holiday_name),
            "holiday_name": holiday_name,
            "has_known_event": bool(day_events),
            "events": day_events,
            "context_matches_direction": known_context_matches,
            "status": status,
            "coverage_status": row.get("coverage_status") if row else "MISSING",
        }
        calendar_items.append(item)
        if is_outlier and known_context_matches:
            explained_candidates.append({**item, "_peer_count": len(peers)})
        elif is_outlier:
            anomaly_candidates.append({**item, "_peer_count": len(peers)})

    weekday_pattern: list[dict[str, Any]] = []
    overall_average = _average(
        row["sales_net"] for row in mall_by_date.values() if row.get("sales_net") is not None
    )
    for weekday, label in enumerate(WEEKDAY_LABELS):
        values = [
            _number(row.get("sales_net"))
            for row_date, row in mall_by_date.items()
            if start_date <= row_date <= analysis_end and row_date.weekday() == weekday
        ]
        average = _average(values)
        variation = _percent_change(average, overall_average)
        weekday_pattern.append(
            {
                "weekday": weekday,
                "label": label,
                "is_weekend": weekday >= 5,
                "average_sales": round(average, 2),
                "median_sales": round(_median(values), 2),
                "days_observed": len(values),
                "variation_vs_daily_average_percent": round(variation or 0, 1),
            }
        )

    weekend_values = [
        row["median_sales"]
        for row in weekday_pattern
        if row["is_weekend"] and row["days_observed"]
    ]
    weekday_values = [
        row["median_sales"]
        for row in weekday_pattern
        if not row["is_weekend"] and row["days_observed"]
    ]
    weekend_average = _average(weekend_values)
    weekday_average = _average(weekday_values)
    weekend_lift = _percent_change(weekend_average, weekday_average)
    observed_patterns = [row for row in weekday_pattern if row["days_observed"]]
    best_weekday = max(observed_patterns, key=lambda row: row["average_sales"], default=None)

    anomalies: list[dict[str, Any]] = []
    for item in anomaly_candidates:
        impact = _number(item.get("impact"))
        contributors = _build_contributors(
            target_date=_day(item["date"]),
            impact=impact,
            local_by_id=local_by_id,
            local_names=local_names,
        )
        direction = "por encima" if impact > 0 else "por debajo"
        context = (
            (
                " Coincide con "
                + ", ".join(event["name"] for event in item["events"])
                + ", pero la dirección no coincide con el impacto esperado."
            )
            if item.get("events")
            else f" Coincide con {item['holiday_name']}."
            if item.get("holiday_name")
            else " Coincide con fin de semana."
            if item.get("is_weekend")
            else ""
        )
        dominant = contributors[0] if contributors else None
        explanation = (
            f"La venta estuvo {abs(_number(item['deviation_percent'])):.1f}% {direction} "
            f"de la mediana de otros {item['weekday_label'].lower()}."
            f"{context}"
        )
        if dominant:
            explanation += (
                f" {dominant['local_name']} es el principal contribuyente identificado."
            )
        anomalies.append(
            {
                "date": item["date"],
                "direction": "UP" if impact > 0 else "DOWN",
                "severity": "HIGH" if abs(_number(item["deviation_percent"])) >= 50 else "WARNING",
                "observed_sales": item["sales_net"],
                "expected_sales": item["expected_sales"],
                "impact": item["impact"],
                "deviation_percent": item["deviation_percent"],
                "weekday_label": item["weekday_label"],
                "holiday_name": item.get("holiday_name"),
                "is_weekend": item.get("is_weekend"),
                "confidence": _confidence_from_peers(
                    int(item["_peer_count"]), quality["score"]
                ),
                "explanation": explanation,
                "recommendation": (
                    "Validar importaciones antes de concluir desempeño comercial."
                    if quality["confidence"] == "LOW"
                    else "Revisar los locales contribuyentes y el contexto comercial de la fecha."
                ),
                "contributors": contributors,
            }
        )
    anomalies.sort(
        key=lambda row: (bool(row["contributors"]), abs(_number(row["impact"]))),
        reverse=True,
    )
    anomalies = anomalies[:8]

    explained_events: list[dict[str, Any]] = []
    for item in explained_candidates:
        impact = _number(item.get("impact"))
        contributors = _build_contributors(
            target_date=_day(item["date"]),
            impact=impact,
            local_by_id=local_by_id,
            local_names=local_names,
        )
        event_names = ", ".join(event["name"] for event in item["events"])
        context_name = event_names or item.get("holiday_name") or "el calendario comercial"
        direction = "por encima" if impact > 0 else "por debajo"
        explained_events.append(
            {
                "date": item["date"],
                "direction": "UP" if impact > 0 else "DOWN",
                "observed_sales": item["sales_net"],
                "expected_sales": item["expected_sales"],
                "impact": item["impact"],
                "deviation_percent": item["deviation_percent"],
                "weekday_label": item["weekday_label"],
                "confidence": _confidence_from_peers(
                    int(item["_peer_count"]), quality["score"]
                ),
                "events": item["events"],
                "holiday_name": item.get("holiday_name"),
                "explanation": (
                    f"La venta estuvo {abs(_number(item['deviation_percent'])):.1f}% "
                    f"{direction} de su referencia y coincide con {context_name}. "
                    "Se clasifica como movimiento explicado, no como anomalía pendiente."
                ),
                "contributors": contributors,
            }
        )
    explained_events.sort(
        key=lambda row: abs(_number(row["impact"])), reverse=True
    )
    explained_events = explained_events[:8]

    holiday_deviations = [
        _number(item["deviation_percent"])
        for item in calendar_items
        if item.get("is_holiday") and item.get("deviation_percent") is not None
    ]
    insights: list[dict[str, Any]] = []
    if quality["confidence"] == "LOW":
        insights.append(
            {
                "type": "DATA_QUALITY",
                "tone": "warning",
                "title": "La calidad limita las conclusiones comerciales",
                "statement": quality["blockers"][0] if quality["blockers"] else "Complete la información antes de actuar.",
                "metric": quality["score"],
                "metric_suffix": "/100",
            }
        )
    if weekend_lift is not None:
        insights.append(
            {
                "type": "WEEKEND_PATTERN",
                "tone": "positive" if weekend_lift >= 0 else "negative",
                "title": "Efecto recurrente de fin de semana",
                "statement": (
                    f"Los sábados y domingos venden en promedio {abs(weekend_lift):.1f}% "
                    f"{'más' if weekend_lift >= 0 else 'menos'} que los días laborables."
                ),
                "metric": round(weekend_lift, 1),
                "metric_suffix": "%",
            }
        )
    if explained_events:
        explained_impact = sum(_number(item["impact"]) for item in explained_events)
        insights.append(
            {
                "type": "KNOWN_EVENT_IMPACT",
                "tone": "positive" if explained_impact >= 0 else "negative",
                "title": "Movimientos asociados al calendario comercial",
                "statement": (
                    f"{len(explained_events)} fecha(s) con desviación relevante coinciden "
                    "con promociones, ventas de pasillo o actividades registradas."
                ),
                "metric": round(explained_impact, 2),
                "metric_suffix": "",
            }
        )
    if holiday_deviations:
        holiday_lift = _average(holiday_deviations)
        insights.append(
            {
                "type": "HOLIDAY_PATTERN",
                "tone": "positive" if holiday_lift >= 0 else "negative",
                "title": "Comportamiento en feriados",
                "statement": (
                    f"Los feriados observados se desviaron en promedio {abs(holiday_lift):.1f}% "
                    f"{'por encima' if holiday_lift >= 0 else 'por debajo'} de su referencia semanal."
                ),
                "metric": round(holiday_lift, 1),
                "metric_suffix": "%",
            }
        )
    if best_weekday:
        insights.append(
            {
                "type": "BEST_WEEKDAY",
                "tone": "neutral",
                "title": "Día con mayor venta promedio",
                "statement": (
                    f"{best_weekday['label']} lidera con un promedio diario de "
                    f"{best_weekday['average_sales']:.2f}."
                ),
                "metric": best_weekday["average_sales"],
                "metric_suffix": "",
            }
        )

    return {
        "mall_id": mall_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "analysis_end": analysis_end.isoformat(),
        },
        "general_status": (
            "DATA_INCOMPLETE"
            if quality["confidence"] == "LOW"
            else "ATTENTION_REQUIRED"
            if anomalies
            else "NORMAL"
        ),
        "quality": quality,
        "calendar": calendar_items,
        "weekday_pattern": weekday_pattern,
        "seasonality": {
            "weekend_average_sales": round(weekend_average, 2),
            "weekday_average_sales": round(weekday_average, 2),
            "weekend_lift_percent": round(weekend_lift, 1) if weekend_lift is not None else None,
            "best_weekday": best_weekday,
            "holiday_days_observed": len(holiday_deviations),
        },
        "anomalies": anomalies,
        "explained_events": explained_events,
        "insights": insights[:4],
        "calendar_context": {
            "country_code": country_code,
            "holiday_source": "python-holidays" if country_code else None,
            "registered_events": normalized_events,
        },
        "methodology": (
            "Medianas por día de semana sobre agregados diarios; anomalías desde 30% "
            "de desviación con al menos dos fechas comparables. Los eventos registrados "
            "se excluyen de la referencia y se muestran como movimientos explicados. "
            "Las causas se estiman por contribución de locales en una ventana reciente de 42 días."
        ),
        "version": PHASE_ONE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def country_holiday_map(
    country_code: Optional[str], start_date: date, end_date: date
) -> dict[date, str]:
    """Load official holidays lazily so analytical tests remain dependency-light."""
    if not country_code:
        return {}
    try:
        import holidays as holidays_library
    except ImportError:
        return {}
    years = list(range(start_date.year, end_date.year + 1))
    calendar = holidays_library.country_holidays(
        country_code,
        years=years,
        observed=True,
        language="es",
    )
    return {
        holiday_date: str(name)
        for holiday_date, name in calendar.items()
        if start_date <= holiday_date <= end_date
    }


def attach_anomaly_reviews(
    intelligence: dict[str, Any],
    reviews: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach one mall-scoped human review to each analytical date."""
    reviews_by_date = {
        str(review.get("anomaly_date"))[:10]: dict(review)
        for review in reviews
        if review.get("anomaly_date")
    }
    for collection in ("anomalies", "explained_events"):
        for item in intelligence.get(collection, []):
            item["review"] = reviews_by_date.get(str(item.get("date"))[:10])
    return intelligence


class BigDataPhaseOneService:
    """Bounded Supabase adapter for the Phase 1 intelligence contract."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    def intelligence(
        self, mall_id: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        analysis_end = min(end_date, date.today())
        local_window_start = max(
            start_date, analysis_end - timedelta(days=CONTRIBUTOR_WINDOW_DAYS - 1)
        )
        quality_window_start = max(
            start_date, analysis_end - timedelta(days=QUALITY_WINDOW_DAYS - 1)
        )

        mall_rows = (
            self.supabase.table("big_data_daily_aggregates")
            .select(
                "period_date,sales_net,transaction_count,records_processed,"
                "coverage_status,updated_at"
            )
            .eq("mall_id", mall_id)
            .eq("grain", "mall")
            .gte("period_date", start_date.isoformat())
            .lte("period_date", analysis_end.isoformat())
            .order("period_date")
            .limit(500)
            .execute()
            .data
            or []
        )
        local_rows = (
            self.supabase.table("big_data_daily_aggregates")
            .select("period_date,dimension_key,local_id,sales_net")
            .eq("mall_id", mall_id)
            .eq("grain", "local")
            .gte("period_date", local_window_start.isoformat())
            .lte("period_date", analysis_end.isoformat())
            .order("period_date")
            .limit(10000)
            .execute()
            .data
            or []
        )
        locals_rows = (
            self.supabase.table("locales")
            .select("id,nombre")
            .eq("mall_id", mall_id)
            .eq("activo", True)
            .limit(500)
            .execute()
            .data
            or []
        )
        logs = (
            self.supabase.table("logs_carga")
            .select("fecha_hora,estado,error_count,records_processed,local_id")
            .eq("mall_id", mall_id)
            .gte("fecha_hora", quality_window_start.isoformat())
            .lt("fecha_hora", (analysis_end + timedelta(days=1)).isoformat())
            .order("fecha_hora", desc=True)
            .limit(2000)
            .execute()
            .data
            or []
        )
        watermark_response = (
            self.supabase.table("big_data_watermarks")
            .select("last_processed_sale_date,last_successful_refresh_at")
            .eq("mall_id", mall_id)
            .maybe_single()
            .execute()
        )
        watermark = getattr(watermark_response, "data", None) or {}
        mall_response = (
            self.supabase.table("malls")
            .select("timezone")
            .eq("id", mall_id)
            .maybe_single()
            .execute()
        )
        mall = getattr(mall_response, "data", None) or {}
        country_code = (
            "DO" if mall.get("timezone") == "America/Santo_Domingo" else None
        )
        holiday_map = country_holiday_map(
            country_code, start_date, analysis_end
        )
        calendar_events = (
            self.supabase.table("big_data_calendar_events")
            .select(
                "id,name,event_type,start_date,end_date,expected_impact,notes"
            )
            .eq("mall_id", mall_id)
            .eq("active", True)
            .lte("start_date", analysis_end.isoformat())
            .gte("end_date", start_date.isoformat())
            .order("start_date")
            .limit(500)
            .execute()
            .data
            or []
        )
        anomaly_reviews = (
            self.supabase.table("big_data_anomaly_reviews")
            .select(
                "id,anomaly_date,status,cause_type,explanation,evidence,"
                "owner_name,anomaly_snapshot,created_at,updated_at,resolved_at"
            )
            .eq("mall_id", mall_id)
            .gte("anomaly_date", start_date.isoformat())
            .lte("anomaly_date", analysis_end.isoformat())
            .order("anomaly_date")
            .limit(500)
            .execute()
            .data
            or []
        )
        intelligence = build_phase_one_intelligence(
            mall_id=mall_id,
            start_date=start_date,
            end_date=end_date,
            mall_rows=mall_rows,
            local_rows=local_rows,
            logs=logs,
            local_names={
                str(row.get("id")): str(row.get("nombre") or "Local")
                for row in locals_rows
            },
            active_local_count=len(locals_rows),
            holidays=holiday_map,
            calendar_events=calendar_events,
            last_processed_sale_date=watermark.get("last_processed_sale_date"),
            last_analytics_update=watermark.get("last_successful_refresh_at"),
            country_code=country_code,
        )
        return attach_anomaly_reviews(intelligence, anomaly_reviews)
