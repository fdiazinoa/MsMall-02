from datetime import date, timedelta

from services.big_data_sprint2_service import (
    ANOMALY_RULE_VERSION,
    FORECAST_MODEL_VERSION,
    build_monthly_forecast,
    detect_explainable_anomalies,
)


def _rows(start: date, values: list[float], records: int = 10):
    return [
        {
            "period_date": (start + timedelta(days=index)).isoformat(),
            "sales_net": value,
            "records_processed": records,
        }
        for index, value in enumerate(values)
    ]


def test_forecast_is_independent_explainable_and_has_interval():
    historical = _rows(date(2026, 5, 1), [100 + index % 7 * 10 for index in range(61)])
    current = _rows(date(2026, 7, 1), [110, 120, 130, 140, 150, 160, 170, 180, 190, 200])
    result = build_monthly_forecast(
        historical + current,
        mall_id="mall-1",
        as_of=date(2026, 7, 10),
        previous_month_sales=3000,
        previous_year_sales=2800,
    )

    assert result["status"] == "OK"
    assert result["model_version"] == FORECAST_MODEL_VERSION
    assert result["lower_bound"] < result["expected_close"] < result["upper_bound"]
    assert result["days_with_data"] == 10
    assert result["days_remaining"] == 21
    assert result["methodology"]
    assert result["historical_range"]["start"] == "2026-05-01"


def test_forecast_reports_insufficient_data_for_new_store():
    result = build_monthly_forecast(
        _rows(date(2026, 7, 1), [100, 120]),
        mall_id="mall-1",
        as_of=date(2026, 7, 2),
        grain="local",
        dimension_key="new-store",
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["confidence"] == "LOW"
    assert result["expected_close"] if "expected_close" in result else True
    assert result["low_confidence_reasons"]


def test_missing_days_and_negative_values_reduce_confidence():
    historical = _rows(date(2026, 6, 1), [100] * 30)
    current = [
        {"period_date": "2026-07-01", "sales_net": 100},
        {"period_date": "2026-07-03", "sales_net": -20},
        {"period_date": "2026-07-05", "sales_net": 120},
    ]
    result = build_monthly_forecast(
        historical + current, mall_id="mall-1", as_of=date(2026, 7, 5)
    )

    assert result["status"] == "OK"
    assert result["confidence"] == "MEDIUM"
    assert result["coverage"] == 60
    assert any("negativos" in reason for reason in result["low_confidence_reasons"])


def test_incomplete_data_prevents_false_commercial_drop():
    rows = _rows(date(2026, 7, 1), [100, 100, 100, 20])
    findings = detect_explainable_anomalies(
        rows,
        mall_id="mall-1",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 4),
        coverage_percent=50,
        failed_imports=2,
    )

    assert [finding["type"] for finding in findings] == ["DATA_INCOMPLETE"]
    assert "no se concluye una caída" in findings[0]["explanation"]


def test_drop_increase_zero_records_negative_and_repeated_run_are_deterministic():
    scenarios = {
        "UNUSUAL_DROP": [100, 100, 100, 60],
        "UNUSUAL_INCREASE": [100, 100, 100, 150],
        "ZERO_ACTIVITY": [100, 100, 100, 0],
        "ATYPICAL_NEGATIVE": [100, 100, 100, -50],
    }
    for expected_type, values in scenarios.items():
        kwargs = dict(
            rows=_rows(date(2026, 7, 1), values),
            mall_id="mall-1",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 4),
            coverage_percent=100,
        )
        first = detect_explainable_anomalies(**kwargs)
        second = detect_explainable_anomalies(**kwargs)
        assert expected_type in {finding["type"] for finding in first}
        assert [item["fingerprint"] for item in first] == [
            item["fingerprint"] for item in second
        ]
        assert all(item["rule_version"] == ANOMALY_RULE_VERSION for item in first)


def test_record_count_shift_and_consecutive_low_days():
    rows = _rows(date(2026, 7, 1), [100, 100, 100, 20, 20, 20], records=10)
    rows[-1]["records_processed"] = 1
    findings = detect_explainable_anomalies(
        rows,
        mall_id="mall-1",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 6),
        coverage_percent=100,
    )
    types = {finding["type"] for finding in findings}
    assert "RECORD_COUNT_SHIFT" in types
    assert "CONSECUTIVE_BELOW_EXPECTED" in types

