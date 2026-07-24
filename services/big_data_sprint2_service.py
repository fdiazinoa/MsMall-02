"""Explainable Sprint 2 analytics built exclusively from Sprint 1 aggregates.

This module is intentionally independent from ``analytics.py`` and its Legacy
projection contracts.  The pure functions are shared by the API, worker and
tests; the service wrapper only performs bounded aggregate reads.
"""
from __future__ import annotations

import calendar
import hashlib
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional


FORECAST_MODEL_VERSION = "big-data-forecast-v1"
ANOMALY_RULE_VERSION = "big-data-anomaly-v1"
MIN_FORECAST_DAYS = 3


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _percent_change(current: float, previous: Optional[float]) -> Optional[float]:
    if previous is None:
        return None
    if previous == 0:
        return 100.0 if current else 0.0
    return (current - previous) / abs(previous) * 100


def anomaly_fingerprint(
    mall_id: str,
    anomaly_type: str,
    period_start: date,
    period_end: date,
    *,
    local_id: Optional[str] = None,
    category_id: Optional[str] = None,
) -> str:
    """Stable identity used to make repeated anomaly detection idempotent."""
    identity = "|".join(
        [
            ANOMALY_RULE_VERSION,
            mall_id,
            local_id or "",
            category_id or "",
            anomaly_type,
            period_start.isoformat(),
            period_end.isoformat(),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_monthly_forecast(
    rows: Iterable[dict[str, Any]],
    *,
    mall_id: str,
    as_of: date,
    grain: str = "mall",
    dimension_key: Optional[str] = None,
    previous_month_sales: Optional[float] = None,
    previous_year_sales: Optional[float] = None,
    target_sales: Optional[float] = None,
) -> dict[str, Any]:
    """Build a weekday-aware monthly close estimate with an explicit interval."""
    month_start = as_of.replace(day=1)
    month_end = as_of.replace(day=calendar.monthrange(as_of.year, as_of.month)[1])
    normalized = [
        {**row, "_date": _day(row.get("period_date")), "_sales": _number(row.get("sales_net"))}
        for row in rows
        if row.get("period_date")
    ]
    current = [row for row in normalized if month_start <= row["_date"] <= as_of]
    historical = [row for row in normalized if row["_date"] < month_start]
    observed_dates = {row["_date"] for row in current}
    elapsed_days = as_of.day
    coverage = len(observed_dates) / elapsed_days if elapsed_days else 0.0
    historical_range = {
        "start": min((row["_date"] for row in historical), default=None),
        "end": max((row["_date"] for row in historical), default=None),
    }

    low_confidence_reasons: list[str] = []
    if len(observed_dates) < MIN_FORECAST_DAYS:
        low_confidence_reasons.append("Menos de tres días del mes tienen información.")
    if len(historical) < 14:
        low_confidence_reasons.append("Hay menos de catorce días de historial comparable.")
    if coverage < 0.8:
        low_confidence_reasons.append("La cobertura del período transcurrido es inferior a 80%.")
    if any(row["_sales"] < 0 for row in current):
        low_confidence_reasons.append("El período contiene valores negativos.")

    common = {
        "mall_id": mall_id,
        "grain": grain,
        "dimension_key": dimension_key,
        "period_start": month_start.isoformat(),
        "period_end": month_end.isoformat(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "historical_range": {
            key: value.isoformat() if value else None for key, value in historical_range.items()
        },
        "coverage": round(coverage * 100, 2),
        "methodology": (
            "Promedio explicable por día de semana sobre agregados diarios; "
            "usa el mes actual como respaldo y un intervalo basado en residuos históricos."
        ),
        "model_version": FORECAST_MODEL_VERSION,
        "low_confidence_reasons": low_confidence_reasons,
    }
    if len(observed_dates) < MIN_FORECAST_DAYS and len(historical) < 14:
        return {
            **common,
            "status": "INSUFFICIENT_DATA",
            "confidence": "LOW",
            "accumulated_sales": sum(row["_sales"] for row in current),
            "days_with_data": len(observed_dates),
            "days_remaining": (month_end - as_of).days,
        }

    current_by_weekday: dict[int, list[float]] = defaultdict(list)
    historical_by_weekday: dict[int, list[float]] = defaultdict(list)
    for row in current:
        current_by_weekday[row["_date"].weekday()].append(row["_sales"])
    for row in historical:
        historical_by_weekday[row["_date"].weekday()].append(row["_sales"])
    current_values = [row["_sales"] for row in current]
    historical_values = [row["_sales"] for row in historical]
    fallback = statistics.mean(current_values or historical_values or [0.0])

    future_values: list[float] = []
    cursor = as_of + timedelta(days=1)
    while cursor <= month_end:
        weekday_values = historical_by_weekday.get(cursor.weekday()) or current_by_weekday.get(cursor.weekday())
        future_values.append(statistics.mean(weekday_values) if weekday_values else fallback)
        cursor += timedelta(days=1)

    accumulated = sum(current_values)
    expected = accumulated + sum(future_values)
    residuals: list[float] = []
    for row in historical:
        peers = [v for v in historical_by_weekday[row["_date"].weekday()] if v != row["_sales"]]
        baseline = statistics.mean(peers) if peers else fallback
        residuals.append(row["_sales"] - baseline)
    daily_error = statistics.stdev(residuals) if len(residuals) > 1 else abs(fallback) * 0.15
    interval = 1.96 * daily_error * math.sqrt(max(len(future_values), 1))

    confidence = "HIGH"
    if low_confidence_reasons:
        confidence = "LOW" if coverage < 0.6 or len(historical) < 14 else "MEDIUM"
    elif len(historical) < 56 or coverage < 0.95:
        confidence = "MEDIUM"

    return {
        **common,
        "status": "OK",
        "confidence": confidence,
        "accumulated_sales": round(accumulated, 2),
        "days_with_data": len(observed_dates),
        "days_remaining": len(future_values),
        "expected_close": round(expected, 2),
        "lower_bound": round(expected - interval, 2),
        "upper_bound": round(expected + interval, 2),
        "previous_month_sales": previous_month_sales,
        "previous_month_difference_percent": _percent_change(expected, previous_month_sales),
        "previous_year_sales": previous_year_sales,
        "previous_year_difference_percent": _percent_change(expected, previous_year_sales),
        "target_sales": target_sales,
        "target_completion_percent": (
            expected / target_sales * 100 if target_sales and target_sales > 0 else None
        ),
    }


def detect_explainable_anomalies(
    rows: Iterable[dict[str, Any]],
    *,
    mall_id: str,
    period_start: date,
    period_end: date,
    coverage_percent: float,
    failed_imports: int = 0,
    local_id: Optional[str] = None,
    category_id: Optional[str] = None,
    category_expected: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Detect deterministic anomalies, prioritizing data quality over claims."""
    normalized = sorted(
        [
            {
                **row,
                "_date": _day(row.get("period_date")),
                "_sales": _number(row.get("sales_net")),
                "_records": int(_number(row.get("records_processed") or row.get("transaction_count"))),
            }
            for row in rows
            if row.get("period_date")
        ],
        key=lambda item: item["_date"],
    )
    findings: list[dict[str, Any]] = []

    def add(
        anomaly_type: str,
        severity: str,
        observed: float,
        expected: float,
        explanation: str,
        evidence: dict[str, Any],
    ) -> None:
        difference = observed - expected
        findings.append(
            {
                "mall_id": mall_id,
                "local_id": local_id,
                "category_id": category_id,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "type": anomaly_type,
                "severity": severity,
                "observed_value": observed,
                "expected_value": expected,
                "absolute_difference": difference,
                "percentage_difference": difference / abs(expected) * 100 if expected else None,
                "coverage": coverage_percent,
                "explanation": explanation,
                "evidence": evidence,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "status": "OPEN",
                "rule_version": ANOMALY_RULE_VERSION,
                "fingerprint": anomaly_fingerprint(
                    mall_id,
                    anomaly_type,
                    period_start,
                    period_end,
                    local_id=local_id,
                    category_id=category_id,
                ),
            }
        )

    if coverage_percent < 80 or failed_imports:
        add(
            "DATA_INCOMPLETE",
            "HIGH" if coverage_percent < 60 or failed_imports else "WARNING",
            coverage_percent,
            100,
            "El período está incompleto; no se concluye una caída comercial.",
            {"failed_imports": failed_imports, "days_present": len(normalized)},
        )
        return findings
    if len(normalized) < 4:
        return findings

    sales = [row["_sales"] for row in normalized]
    records = [row["_records"] for row in normalized]
    baseline_sales = statistics.mean(sales[:-1]) if len(sales) > 1 else 0
    baseline_records = statistics.mean(records[:-1]) if len(records) > 1 else 0
    latest = normalized[-1]
    deviation = (latest["_sales"] - baseline_sales) / abs(baseline_sales) if baseline_sales else 0

    if latest["_sales"] == 0 and baseline_sales > 0:
        add("ZERO_ACTIVITY", "HIGH", 0, baseline_sales, "No hubo venta donde normalmente existe actividad.", {"date": latest["_date"].isoformat()})
    elif deviation <= -0.30:
        add("UNUSUAL_DROP", "HIGH", latest["_sales"], baseline_sales, "La venta observada está al menos 30% por debajo de su referencia.", {"date": latest["_date"].isoformat()})
    elif deviation >= 0.30:
        add("UNUSUAL_INCREASE", "WARNING", latest["_sales"], baseline_sales, "La venta observada está al menos 30% por encima de su referencia.", {"date": latest["_date"].isoformat()})

    if baseline_records and abs(latest["_records"] - baseline_records) / baseline_records >= 0.5:
        add("RECORD_COUNT_SHIFT", "WARNING", latest["_records"], baseline_records, "La cantidad de registros cambió al menos 50%.", {"date": latest["_date"].isoformat()})
    if latest["_sales"] < 0 and latest["_sales"] < statistics.mean(sales[:-1]):
        add("ATYPICAL_NEGATIVE", "HIGH", latest["_sales"], baseline_sales, "Se detectó un valor negativo atípico.", {"date": latest["_date"].isoformat()})
    if len(sales) >= 5 and all(value < baseline_sales * 0.8 for value in sales[-3:]):
        add("CONSECUTIVE_BELOW_EXPECTED", "HIGH", statistics.mean(sales[-3:]), baseline_sales, "Tres días consecutivos están por debajo de 80% de la referencia.", {"dates": [row["_date"].isoformat() for row in normalized[-3:]]})
    if category_expected and abs(latest["_sales"] - category_expected) / abs(category_expected) >= 0.3:
        add("CATEGORY_DEVIATION", "WARNING", latest["_sales"], category_expected, "El local se desvía al menos 30% de la referencia de su categoría.", {"date": latest["_date"].isoformat()})
    if len(sales) >= 7:
        recent = statistics.mean(sales[-3:])
        monthly = statistics.mean(sales)
        if monthly and abs(recent - monthly) / abs(monthly) >= 0.25:
            add("DAILY_MONTHLY_TREND_GAP", "WARNING", recent, monthly, "La tendencia de los últimos tres días difiere al menos 25% del promedio mensual.", {"recent_days": 3})
    return findings


class BigDataSprint2Service:
    """Bounded database adapter for forecast, anomaly and executive contracts."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    def _aggregate_rows(
        self,
        mall_id: str,
        start_date: date,
        end_date: date,
        *,
        grain: str,
        dimension_key: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.supabase.table("big_data_daily_aggregates")
            .select("period_date,sales_net,sales_gross,taxes,transaction_count,records_processed,coverage_status,updated_at,dimension_key,local_id,category_id,category_name")
            .eq("mall_id", mall_id)
            .eq("grain", grain)
            .gte("period_date", start_date.isoformat())
            .lte("period_date", end_date.isoformat())
            .order("period_date")
            .limit(5000)
        )
        if dimension_key:
            query = query.eq("dimension_key", dimension_key)
        return query.execute().data or []

    def forecast(
        self,
        mall_id: str,
        as_of: date,
        *,
        grain: str = "mall",
        dimension_key: Optional[str] = None,
    ) -> dict[str, Any]:
        history_start = (as_of.replace(day=1) - timedelta(days=370)).replace(day=1)
        rows = self._aggregate_rows(
            mall_id, history_start, as_of, grain=grain, dimension_key=dimension_key
        )
        previous_month_end = as_of.replace(day=1) - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        previous_year_start = as_of.replace(year=as_of.year - 1, day=1)
        previous_year_end = previous_year_start.replace(
            day=calendar.monthrange(previous_year_start.year, previous_year_start.month)[1]
        )
        previous_month = sum(
            _number(row.get("sales_net"))
            for row in rows
            if previous_month_start <= _day(row["period_date"]) <= previous_month_end
        )
        previous_year = sum(
            _number(row.get("sales_net"))
            for row in rows
            if previous_year_start <= _day(row["period_date"]) <= previous_year_end
        )
        return build_monthly_forecast(
            rows,
            mall_id=mall_id,
            as_of=as_of,
            grain=grain,
            dimension_key=dimension_key,
            previous_month_sales=previous_month,
            previous_year_sales=previous_year,
        )

    def detect_and_persist_anomalies(
        self, mall_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        rows = self._aggregate_rows(mall_id, start_date, end_date, grain="mall")
        expected_days = (end_date - start_date).days + 1
        days_present = len({_day(row["period_date"]) for row in rows})
        coverage = days_present / expected_days * 100 if expected_days else 0
        logs = (
            self.supabase.table("logs_carga")
            .select("estado")
            .eq("mall_id", mall_id)
            .gte("fecha_hora", start_date.isoformat())
            .lt("fecha_hora", (end_date + timedelta(days=1)).isoformat())
            .limit(1000)
            .execute()
            .data
            or []
        )
        failed_imports = sum(
            1 for log in logs if str(log.get("estado") or "").lower() in {"error", "failed"}
        )
        findings = detect_explainable_anomalies(
            rows,
            mall_id=mall_id,
            period_start=start_date,
            period_end=end_date,
            coverage_percent=coverage,
            failed_imports=failed_imports,
        )
        if coverage >= 80 and not failed_imports:
            category_rows = self._aggregate_rows(
                mall_id, start_date, end_date, grain="category"
            )
            local_rows = self._aggregate_rows(
                mall_id, start_date, end_date, grain="local"
            )
            category_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            local_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in category_rows:
                category_groups[str(row.get("dimension_key"))].append(row)
            for row in local_rows:
                local_groups[str(row.get("dimension_key"))].append(row)
            for dimension, scoped_rows in list(category_groups.items())[:200]:
                scoped_coverage = (
                    len({_day(row["period_date"]) for row in scoped_rows})
                    / expected_days
                    * 100
                    if expected_days
                    else 0
                )
                findings.extend(
                    detect_explainable_anomalies(
                        scoped_rows,
                        mall_id=mall_id,
                        category_id=str(scoped_rows[0].get("category_id") or dimension),
                        period_start=start_date,
                        period_end=end_date,
                        coverage_percent=scoped_coverage,
                    )
                )
            classifications = (
                self.supabase.table("local_commercial_classifications")
                .select("local_id,category_id")
                .in_("local_id", list(local_groups.keys())[:500])
                .limit(500)
                .execute()
                .data
                or []
            )
            local_category = {
                str(row.get("local_id")): str(row.get("category_id"))
                for row in classifications
                if row.get("local_id") and row.get("category_id")
            }
            category_members: dict[str, int] = defaultdict(int)
            for category_id in local_category.values():
                category_members[category_id] += 1
            category_latest: dict[str, float] = {}
            for scoped_rows in category_groups.values():
                category_id = str(scoped_rows[0].get("category_id") or "")
                if category_id:
                    latest_row = max(scoped_rows, key=lambda row: _day(row["period_date"]))
                    category_latest[category_id] = _number(latest_row.get("sales_net"))
            for local_id, scoped_rows in list(local_groups.items())[:500]:
                category_id = local_category.get(local_id)
                expected = (
                    category_latest.get(category_id, 0)
                    / max(category_members.get(category_id, 1), 1)
                    if category_id
                    else None
                )
                scoped_coverage = (
                    len({_day(row["period_date"]) for row in scoped_rows})
                    / expected_days
                    * 100
                    if expected_days
                    else 0
                )
                findings.extend(
                    detect_explainable_anomalies(
                        scoped_rows,
                        mall_id=mall_id,
                        local_id=local_id,
                        period_start=start_date,
                        period_end=end_date,
                        coverage_percent=scoped_coverage,
                        category_expected=expected,
                    )
                )
        for finding in findings:
            payload = {
                "mall_id": mall_id,
                "local_id": finding.get("local_id"),
                "type": finding["type"],
                "severity": finding["severity"],
                "title": self._anomaly_title(finding["type"]),
                "description": finding["explanation"],
                "evidence": finding["evidence"],
                "root_cause": (
                    "Cobertura o importaciones incompletas."
                    if finding["type"] == "DATA_INCOMPLETE"
                    else "Desviación estadística respecto de la referencia explicable."
                ),
                "recommendation": (
                    "Completar las importaciones antes de evaluar el desempeño comercial."
                    if finding["type"] == "DATA_INCOMPLETE"
                    else "Revisar evidencia, cobertura y contexto comercial."
                ),
                "confidence": 0.95 if finding["type"] == "DATA_INCOMPLETE" else 0.8,
                "status": "OPEN",
                "source": "BIG_DATA_ANOMALY",
                "detected_at": finding["detected_at"],
                "fingerprint": finding["fingerprint"],
                "metadata": {
                    "category_id": finding.get("category_id"),
                    "period_start": finding["period_start"],
                    "period_end": finding["period_end"],
                    "observed_value": finding["observed_value"],
                    "expected_value": finding["expected_value"],
                    "absolute_difference": finding["absolute_difference"],
                    "percentage_difference": finding["percentage_difference"],
                    "coverage": finding["coverage"],
                    "rule_version": finding["rule_version"],
                },
            }
            (
                self.supabase.table("operational_findings")
                .upsert(payload, on_conflict="mall_id,fingerprint")
                .execute()
            )
            event_exists = (
                self.supabase.table("operations_events")
                .select("id")
                .eq("mall_id", mall_id)
                .eq("fingerprint", finding["fingerprint"])
                .limit(1)
                .execute()
                .data
                or []
            )
            if not event_exists:
                try:
                    self.supabase.table("operations_events").insert(
                        {
                            "mall_id": mall_id,
                            "local_id": finding.get("local_id"),
                            "event_type": finding["type"],
                            "source": "BIG_DATA_ANOMALY",
                            "severity": finding["severity"],
                            "payload": {
                                **finding,
                                "finding_fingerprint": finding["fingerprint"],
                            },
                            "processing_status": "PENDING",
                            "fingerprint": finding["fingerprint"],
                        }
                    ).execute()
                except Exception:
                    # The unique index resolves a simultaneous detector race;
                    # any other persistence error must still fail the job.
                    raced = (
                        self.supabase.table("operations_events")
                        .select("id")
                        .eq("mall_id", mall_id)
                        .eq("fingerprint", finding["fingerprint"])
                        .limit(1)
                        .execute()
                        .data
                        or []
                    )
                    if not raced:
                        raise
        active = (
            self.supabase.table("operational_findings")
            .select("id,fingerprint,metadata")
            .eq("mall_id", mall_id)
            .eq("source", "BIG_DATA_ANOMALY")
            .in_("status", ["OPEN", "ACKNOWLEDGED"])
            .limit(2000)
            .execute()
            .data
            or []
        )
        detected_fingerprints = {finding["fingerprint"] for finding in findings}
        resolved_at = datetime.now(timezone.utc).isoformat()
        for previous in active:
            metadata = previous.get("metadata") or {}
            same_period = (
                metadata.get("period_start") == start_date.isoformat()
                and metadata.get("period_end") == end_date.isoformat()
            )
            if (
                same_period
                and previous.get("fingerprint") not in detected_fingerprints
                and previous.get("id")
            ):
                self.supabase.table("operational_findings").update(
                    {
                        "status": "RESOLVED",
                        "resolved_at": resolved_at,
                        "updated_at": resolved_at,
                        "metadata": {
                            **metadata,
                            "resolution_reason": "DATA_CORRECTED_OR_CONDITION_CLEARED",
                        },
                    }
                ).eq("id", previous["id"]).eq("mall_id", mall_id).execute()
        return findings

    def executive_summary(
        self, mall_id: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        rows = self._aggregate_rows(mall_id, start_date, end_date, grain="mall")
        net = sum(_number(row.get("sales_net")) for row in rows)
        expected_days = (end_date - start_date).days + 1
        days_present = len({_day(row["period_date"]) for row in rows})
        coverage = days_present / expected_days * 100 if expected_days else 0
        forecast = self.forecast(mall_id, min(end_date, date.today()))
        findings = (
            self.supabase.table("operational_findings")
            .select("id,type,severity,title,description,status,local_id,local_name,detected_at,metadata")
            .eq("mall_id", mall_id)
            .in_("status", ["OPEN", "ACKNOWLEDGED"])
            .order("priority_score", desc=True)
            .limit(10)
            .execute()
            .data
            or []
        )
        observations = (
            self.supabase.table("operations_agent_observations")
            .select("id,observation,conclusion,recommendation,confidence,created_at,metadata")
            .eq("mall_id", mall_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
            .data
            or []
        )
        quality_blocked = coverage < 80 or any(
            finding.get("type") == "DATA_INCOMPLETE" for finding in findings
        )
        return {
            "mall_id": mall_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "general_status": (
                "DATA_INCOMPLETE"
                if quality_blocked
                else "ATTENTION_REQUIRED"
                if findings
                else "NORMAL"
            ),
            "accumulated_sales": round(net, 2),
            "coverage": round(coverage, 2),
            "forecast": forecast,
            "top_categories": self._category_performance(mall_id, start_date, end_date)[:5],
            "categories_in_reduction": [
                row
                for row in self._category_performance(mall_id, start_date, end_date)
                if row["sales_net"] < 0
            ][:5],
            "highlighted_stores": self._local_performance(
                mall_id, start_date, end_date
            )[:5],
            "stores_requiring_review": [
                {
                    "local_id": finding.get("local_id"),
                    "local_name": finding.get("local_name"),
                    "severity": finding.get("severity"),
                    "reason": finding.get("title"),
                }
                for finding in findings
                if finding.get("local_id")
            ][:5],
            "anomalies": findings,
            "observations": observations,
            "updated_at": max(
                (row.get("updated_at") for row in rows if row.get("updated_at")),
                default=None,
            ),
            "facts_only": True,
        }

    def _category_performance(
        self, mall_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        rows = self._aggregate_rows(mall_id, start_date, end_date, grain="category")
        totals: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("dimension_key") or row.get("category_id") or "unclassified")
            item = totals.setdefault(
                key,
                {
                    "category_id": row.get("category_id"),
                    "category_name": row.get("category_name") or "Sin homologar",
                    "sales_net": 0.0,
                },
            )
            item["sales_net"] += _number(row.get("sales_net"))
        return sorted(totals.values(), key=lambda item: item["sales_net"], reverse=True)

    def _local_performance(
        self, mall_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        rows = self._aggregate_rows(mall_id, start_date, end_date, grain="local")
        totals: dict[str, float] = defaultdict(float)
        for row in rows:
            if row.get("local_id"):
                totals[str(row["local_id"])] += _number(row.get("sales_net"))
        names: dict[str, str] = {}
        if totals:
            local_rows = (
                self.supabase.table("locales")
                .select("id,nombre")
                .eq("mall_id", mall_id)
                .in_("id", list(totals.keys())[:500])
                .limit(500)
                .execute()
                .data
                or []
            )
            names = {
                str(row.get("id")): str(row.get("nombre") or "Local")
                for row in local_rows
            }
        return sorted(
            [
                {
                    "local_id": local_id,
                    "local_name": names.get(local_id, "Local"),
                    "sales_net": round(sales, 2),
                }
                for local_id, sales in totals.items()
            ],
            key=lambda item: item["sales_net"],
            reverse=True,
        )

    @staticmethod
    def _anomaly_title(anomaly_type: str) -> str:
        return {
            "DATA_INCOMPLETE": "Información incompleta",
            "UNUSUAL_DROP": "Caída inusual de ventas",
            "UNUSUAL_INCREASE": "Incremento inusual de ventas",
            "ZERO_ACTIVITY": "Día sin actividad esperada",
            "RECORD_COUNT_SHIFT": "Cambio abrupto en registros",
            "ATYPICAL_NEGATIVE": "Valor negativo atípico",
            "CONSECUTIVE_BELOW_EXPECTED": "Varios días por debajo de lo esperado",
        }.get(anomaly_type, anomaly_type.replace("_", " ").title())
