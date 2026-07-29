"""Phase 3A explainable 7/30/90-day commercial prediction.

The model intentionally stays deterministic and aggregate-only.  It learns a
robust weekday baseline, a bounded recent trend and event/holiday adjustments
only when at least two comparable historical observations exist.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from services.big_data_phase_one_service import (
    EVENT_TYPE_LABELS,
    WEEKDAY_LABELS,
    country_holiday_map,
)


PHASE_THREE_A_VERSION = "big-data-prediction-phase-three-a-v1"
FORECAST_HORIZONS = (7, 30, 90)
MIN_HISTORY_DAYS = 28
MIN_CONTEXT_OBSERVATIONS = 2
MAX_HISTORY_ROWS = 500
MAX_CALENDAR_EVENTS = 500
RECENT_WINDOW_DAYS = 28
INTERVAL_Z_SCORE = 1.64


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _median(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.median(materialized) if materialized else 0.0


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.mean(materialized) if materialized else 0.0


def _percent_change(current: float, reference: float) -> Optional[float]:
    if not reference:
        return None
    return (current - reference) / abs(reference) * 100


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _dates(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        return []
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]


def _normalize_rows(
    rows: Iterable[Mapping[str, Any]],
    start_date: date,
    as_of: date,
) -> dict[date, float]:
    """Consolidate aggregate rows and reject out-of-window/future values."""
    normalized: dict[date, float] = defaultdict(float)
    for row in rows:
        if not row.get("period_date"):
            continue
        row_date = _day(row["period_date"])
        if start_date <= row_date <= as_of:
            normalized[row_date] += _number(row.get("sales_net"))
    return dict(normalized)


def _normalize_events(
    events: Iterable[Mapping[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[dict[date, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    normalized: list[dict[str, Any]] = []
    for event in events:
        if not event.get("start_date") or not event.get("end_date"):
            continue
        raw_start = _day(event["start_date"])
        raw_end = _day(event["end_date"])
        event_start = max(raw_start, start_date)
        event_end = min(raw_end, end_date)
        if event_end < event_start:
            continue
        event_type = str(event.get("event_type") or "OTHER")
        item = {
            "id": str(event.get("id") or ""),
            "name": str(event.get("name") or "Evento del mall"),
            "event_type": event_type,
            "event_type_label": EVENT_TYPE_LABELS.get(event_type, "Otro evento"),
            "start_date": raw_start.isoformat(),
            "end_date": raw_end.isoformat(),
            "expected_impact": str(event.get("expected_impact") or "NEUTRAL"),
        }
        normalized.append(item)
        for event_date in _dates(event_start, event_end):
            by_date[event_date].append(item)
    return dict(by_date), normalized


def _quality(
    *,
    history_by_date: Mapping[date, float],
    start_date: date,
    as_of: date,
    residuals: list[float],
) -> dict[str, Any]:
    expected_days = max((as_of - start_date).days + 1, 0)
    days_with_data = len(history_by_date)
    coverage = days_with_data / expected_days * 100 if expected_days else 0.0
    last_data_date = max(history_by_date, default=None)
    stale_days = (as_of - last_data_date).days if last_data_date else None
    average_sales = abs(_mean(history_by_date.values()))
    residual_deviation = (
        statistics.stdev(residuals)
        if len(residuals) > 1
        else average_sales * 0.15
    )
    residual_cv = residual_deviation / average_sales if average_sales else 1.0

    sample_score = min(days_with_data / 84, 1) * 40
    coverage_score = min(coverage / 100, 1) * 35
    stability_score = max(1 - min(residual_cv, 1), 0) * 15
    freshness_score = 10 if stale_days is not None and stale_days <= 1 else 5 if stale_days is not None and stale_days <= 3 else 0
    score = round(sample_score + coverage_score + stability_score + freshness_score, 1)
    status = "RELIABLE" if score >= 80 else "REVIEW" if score >= 60 else "LOW_CONFIDENCE"
    confidence = "HIGH" if status == "RELIABLE" else "MEDIUM" if status == "REVIEW" else "LOW"

    reasons: list[str] = []
    if days_with_data < MIN_HISTORY_DAYS:
        reasons.append("Se requieren al menos 28 días históricos para proyectar.")
    elif days_with_data < 56:
        reasons.append("Hay menos de ocho semanas de historial; la estacionalidad es limitada.")
    if coverage < 80:
        reasons.append("La cobertura histórica es inferior a 80%.")
    if stale_days is None:
        reasons.append("No existe una fecha de venta procesada para establecer el corte.")
    elif stale_days > 1:
        reasons.append(f"El último dato disponible tiene {stale_days} días de rezago.")
    if residual_cv > 0.75:
        reasons.append("La variabilidad histórica es alta frente a la venta promedio.")
    if any(value < 0 for value in history_by_date.values()):
        reasons.append("El historial contiene días de venta neta negativa.")

    return {
        "score": score,
        "status": status,
        "confidence": confidence,
        "expected_days": expected_days,
        "days_with_data": days_with_data,
        "coverage_percent": round(coverage, 1),
        "last_data_date": last_data_date.isoformat() if last_data_date else None,
        "stale_days": stale_days,
        "residual_variation_percent": round(residual_cv * 100, 1),
        "reasons": reasons,
    }


def build_phase_three_a_prediction(
    *,
    mall_id: str,
    start_date: date,
    as_of: date,
    mall_rows: Iterable[Mapping[str, Any]],
    holidays: Optional[Mapping[date, str]] = None,
    calendar_events: Iterable[Mapping[str, Any]] = (),
    country_code: Optional[str] = None,
) -> dict[str, Any]:
    """Build one explainable response containing the 7/30/90-day horizons."""
    forecast_end = as_of + timedelta(days=max(FORECAST_HORIZONS))
    history_by_date = _normalize_rows(mall_rows, start_date, as_of)
    holiday_map = dict(holidays or {})
    events_by_date, normalized_events = _normalize_events(
        calendar_events, start_date, forecast_end
    )

    clean_by_weekday: dict[int, list[float]] = defaultdict(list)
    for row_date, value in history_by_date.items():
        if row_date not in holiday_map and row_date not in events_by_date:
            clean_by_weekday[row_date.weekday()].append(value)
    clean_values = [
        value for values in clean_by_weekday.values() for value in values
    ]
    fallback = _median(clean_values or history_by_date.values())
    baseline_by_weekday = {
        weekday: (
            _median(clean_by_weekday.get(weekday, []))
            if len(clean_by_weekday.get(weekday, [])) >= 2
            else fallback
        )
        for weekday in range(7)
    }

    residuals = [
        value - baseline_by_weekday[row_date.weekday()]
        for row_date, value in history_by_date.items()
        if row_date not in holiday_map and row_date not in events_by_date
    ]
    quality = _quality(
        history_by_date=history_by_date,
        start_date=start_date,
        as_of=as_of,
        residuals=residuals,
    )

    common = {
        "mall_id": mall_id,
        "status": (
            "OK"
            if len(history_by_date) >= MIN_HISTORY_DAYS
            else "INSUFFICIENT_DATA"
        ),
        "period": {
            "history_start": start_date.isoformat(),
            "as_of": as_of.isoformat(),
            "forecast_end": forecast_end.isoformat(),
        },
        "quality": quality,
        "version": PHASE_THREE_A_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if len(history_by_date) < MIN_HISTORY_DAYS:
        return {
            **common,
            "horizons": [],
            "daily": [],
            "drivers": {
                "trend_percent": 0.0,
                "weekday_pattern": [],
                "event_adjustments": [],
                "holiday_adjustment": {
                    "observations": 0,
                    "adjustment_percent": 0.0,
                    "applied": False,
                },
            },
            "calendar_context": {
                "country_code": country_code,
                "holiday_source": "python-holidays" if country_code else None,
                "registered_events": normalized_events,
            },
            "methodology": (
                "No se emite una proyección hasta contar con al menos 28 días "
                "históricos de agregados del mall."
            ),
        }

    recent_start = as_of - timedelta(days=RECENT_WINDOW_DAYS - 1)
    previous_start = recent_start - timedelta(days=RECENT_WINDOW_DAYS)
    previous_end = recent_start - timedelta(days=1)
    recent_values = [
        value
        for row_date, value in history_by_date.items()
        if recent_start <= row_date <= as_of
        and row_date not in holiday_map
        and row_date not in events_by_date
    ]
    previous_values = [
        value
        for row_date, value in history_by_date.items()
        if previous_start <= row_date <= previous_end
        and row_date not in holiday_map
        and row_date not in events_by_date
    ]
    raw_trend = (
        _percent_change(_mean(recent_values), _mean(previous_values))
        if len(recent_values) >= 14 and len(previous_values) >= 14
        else 0.0
    )
    trend_percent = round(_clamp(raw_trend or 0.0, -20.0, 20.0), 1)

    event_lifts: dict[str, list[float]] = defaultdict(list)
    holiday_lifts: list[float] = []
    for row_date, observed in history_by_date.items():
        baseline = baseline_by_weekday[row_date.weekday()]
        lift = _percent_change(observed, baseline)
        if lift is None:
            continue
        if row_date in holiday_map:
            holiday_lifts.append(lift)
        for event in events_by_date.get(row_date, []):
            event_lifts[event["event_type"]].append(lift)

    learned_event_adjustments: dict[str, dict[str, Any]] = {}
    for event_type, lifts in event_lifts.items():
        applied = len(lifts) >= MIN_CONTEXT_OBSERVATIONS
        learned_event_adjustments[event_type] = {
            "event_type": event_type,
            "event_type_label": EVENT_TYPE_LABELS.get(event_type, "Otro evento"),
            "observations": len(lifts),
            "adjustment_percent": (
                round(_clamp(_median(lifts), -40.0, 60.0), 1) if applied else 0.0
            ),
            "applied": applied,
        }
    holiday_applied = len(holiday_lifts) >= MIN_CONTEXT_OBSERVATIONS
    holiday_adjustment = {
        "observations": len(holiday_lifts),
        "adjustment_percent": (
            round(_clamp(_median(holiday_lifts), -40.0, 60.0), 1)
            if holiday_applied
            else 0.0
        ),
        "applied": holiday_applied,
    }

    residual_deviation = (
        statistics.stdev(residuals)
        if len(residuals) > 1
        else abs(fallback) * 0.15
    )
    daily: list[dict[str, Any]] = []
    for offset in range(1, max(FORECAST_HORIZONS) + 1):
        forecast_date = as_of + timedelta(days=offset)
        base = baseline_by_weekday[forecast_date.weekday()]
        adjustments: list[dict[str, Any]] = []
        adjustment_percent = trend_percent
        if trend_percent:
            adjustments.append(
                {
                    "source": "RECENT_TREND",
                    "label": "Tendencia reciente",
                    "percent": trend_percent,
                    "observations": len(recent_values),
                    "applied": True,
                }
            )
        holiday_name = holiday_map.get(forecast_date)
        if holiday_name:
            adjustment_percent += holiday_adjustment["adjustment_percent"]
            adjustments.append(
                {
                    "source": "HOLIDAY",
                    "label": holiday_name,
                    "percent": holiday_adjustment["adjustment_percent"],
                    "observations": holiday_adjustment["observations"],
                    "applied": holiday_adjustment["applied"],
                }
            )
        day_events = events_by_date.get(forecast_date, [])
        for event in day_events:
            learned = learned_event_adjustments.get(event["event_type"])
            if learned:
                adjustment_percent += learned["adjustment_percent"]
                observations = learned["observations"]
                applied = learned["applied"]
                percent = learned["adjustment_percent"]
            else:
                observations = 0
                applied = False
                percent = 0.0
            adjustments.append(
                {
                    "source": "CALENDAR_EVENT",
                    "label": event["name"],
                    "event_type": event["event_type"],
                    "percent": percent,
                    "observations": observations,
                    "applied": applied,
                }
            )
        adjustment_percent = _clamp(adjustment_percent, -60.0, 80.0)
        expected = base * (1 + adjustment_percent / 100)
        interval = INTERVAL_Z_SCORE * residual_deviation
        daily.append(
            {
                "date": forecast_date.isoformat(),
                "weekday": forecast_date.weekday(),
                "weekday_label": WEEKDAY_LABELS[forecast_date.weekday()],
                "expected_sales": round(expected, 2),
                "lower_bound": round(expected - interval, 2),
                "upper_bound": round(expected + interval, 2),
                "baseline_sales": round(base, 2),
                "adjustment_percent": round(adjustment_percent, 1),
                "adjustments": adjustments,
                "is_weekend": forecast_date.weekday() >= 5,
                "is_holiday": bool(holiday_name),
                "holiday_name": holiday_name,
                "events": day_events,
                "confidence": quality["confidence"],
            }
        )

    recent_average = _mean(recent_values)
    horizons: list[dict[str, Any]] = []
    for days in FORECAST_HORIZONS:
        scoped = daily[:days]
        expected_sales = sum(item["expected_sales"] for item in scoped)
        interval = INTERVAL_Z_SCORE * residual_deviation * math.sqrt(days)
        weekend_sales = sum(
            item["expected_sales"] for item in scoped if item["is_weekend"]
        )
        horizons.append(
            {
                "days": days,
                "start_date": scoped[0]["date"],
                "end_date": scoped[-1]["date"],
                "expected_sales": round(expected_sales, 2),
                "lower_bound": round(expected_sales - interval, 2),
                "upper_bound": round(expected_sales + interval, 2),
                "average_daily_sales": round(expected_sales / days, 2),
                "comparison_recent_average_percent": (
                    round(
                        _percent_change(expected_sales / days, recent_average) or 0.0,
                        1,
                    )
                    if recent_average
                    else None
                ),
                "weekend_share_percent": (
                    round(weekend_sales / expected_sales * 100, 1)
                    if expected_sales
                    else 0.0
                ),
                "known_context_days": sum(
                    1
                    for item in scoped
                    if item["is_holiday"] or item["events"]
                ),
                "confidence": quality["confidence"],
            }
        )

    weekday_pattern = [
        {
            "weekday": weekday,
            "label": WEEKDAY_LABELS[weekday],
            "is_weekend": weekday >= 5,
            "baseline_sales": round(baseline_by_weekday[weekday], 2),
            "days_observed": len(clean_by_weekday.get(weekday, [])),
        }
        for weekday in range(7)
    ]
    return {
        **common,
        "horizons": horizons,
        "daily": daily,
        "drivers": {
            "trend_percent": trend_percent,
            "trend_window_days": RECENT_WINDOW_DAYS,
            "weekday_pattern": weekday_pattern,
            "event_adjustments": sorted(
                learned_event_adjustments.values(),
                key=lambda item: item["event_type"],
            ),
            "holiday_adjustment": holiday_adjustment,
        },
        "calendar_context": {
            "country_code": country_code,
            "holiday_source": "python-holidays" if country_code else None,
            "registered_events": normalized_events,
        },
        "methodology": (
            "Mediana robusta por día de semana sobre agregados del mall, excluyendo "
            "feriados y eventos conocidos de la referencia. La tendencia reciente se "
            "limita a ±20%. Los ajustes por feriado o tipo de evento se aplican solo "
            "con al menos dos observaciones históricas comparables. El rango corresponde "
            "a un intervalo explicable del 80% basado en residuos históricos; no es una garantía."
        ),
    }


class BigDataPhaseThreeService:
    """Bounded Supabase adapter for Phase 3A."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    def prediction(
        self,
        mall_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        as_of = min(end_date, date.today())
        forecast_end = as_of + timedelta(days=max(FORECAST_HORIZONS))
        rows = (
            self.supabase.table("big_data_daily_aggregates")
            .select(
                "period_date,sales_net,transaction_count,records_processed,"
                "coverage_status,updated_at"
            )
            .eq("mall_id", mall_id)
            .eq("grain", "mall")
            .gte("period_date", start_date.isoformat())
            .lte("period_date", as_of.isoformat())
            .order("period_date")
            .limit(MAX_HISTORY_ROWS)
            .execute()
            .data
            or []
        )
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
        holidays = country_holiday_map(country_code, start_date, forecast_end)
        events = (
            self.supabase.table("big_data_calendar_events")
            .select(
                "id,name,event_type,start_date,end_date,expected_impact"
            )
            .eq("mall_id", mall_id)
            .eq("active", True)
            .lte("start_date", forecast_end.isoformat())
            .gte("end_date", start_date.isoformat())
            .order("start_date")
            .limit(MAX_CALENDAR_EVENTS)
            .execute()
            .data
            or []
        )
        return build_phase_three_a_prediction(
            mall_id=mall_id,
            start_date=start_date,
            as_of=as_of,
            mall_rows=rows,
            holidays=holidays,
            calendar_events=events,
            country_code=country_code,
        )
