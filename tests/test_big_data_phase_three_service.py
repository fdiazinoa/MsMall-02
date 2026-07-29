from datetime import date, timedelta

from services.big_data_phase_three_service import (
    PHASE_THREE_A_VERSION,
    build_phase_three_a_prediction,
)


def _rows(start: date, days: int, value_for_date):
    return [
        {
            "period_date": (start + timedelta(days=offset)).isoformat(),
            "sales_net": value_for_date(start + timedelta(days=offset)),
            "coverage_status": "COMPLETE",
        }
        for offset in range(days)
    ]


def test_phase_three_a_builds_explainable_7_30_90_day_horizons():
    start = date(2026, 4, 27)  # Monday
    as_of = start + timedelta(days=83)
    rows = _rows(
        start,
        84,
        lambda row_date: 150.0 if row_date.weekday() >= 5 else 100.0,
    )

    result = build_phase_three_a_prediction(
        mall_id="mall-1",
        start_date=start,
        as_of=as_of,
        mall_rows=rows,
        country_code="DO",
    )

    assert result["version"] == PHASE_THREE_A_VERSION
    assert result["status"] == "OK"
    assert result["quality"]["confidence"] == "HIGH"
    assert [item["days"] for item in result["horizons"]] == [7, 30, 90]
    assert len(result["daily"]) == 90
    assert result["daily"][0]["date"] == (as_of + timedelta(days=1)).isoformat()
    assert result["drivers"]["weekday_pattern"][5]["baseline_sales"] == 150
    assert result["drivers"]["weekday_pattern"][0]["baseline_sales"] == 100
    assert result["horizons"][0]["upper_bound"] >= result["horizons"][0]["expected_sales"]
    assert result["horizons"][0]["lower_bound"] <= result["horizons"][0]["expected_sales"]


def test_phase_three_a_learns_and_applies_repeated_event_type():
    start = date(2026, 4, 1)
    as_of = start + timedelta(days=83)
    first_promotion = start + timedelta(days=20)
    second_promotion = start + timedelta(days=48)
    future_promotion = as_of + timedelta(days=4)
    promotion_dates = {first_promotion, second_promotion}
    rows = _rows(
        start,
        84,
        lambda row_date: 120.0 if row_date in promotion_dates else 100.0,
    )
    events = [
        {
            "id": "past-1",
            "name": "Promo abril",
            "event_type": "PROMOTION",
            "start_date": first_promotion.isoformat(),
            "end_date": first_promotion.isoformat(),
            "expected_impact": "UP",
        },
        {
            "id": "past-2",
            "name": "Promo mayo",
            "event_type": "PROMOTION",
            "start_date": second_promotion.isoformat(),
            "end_date": second_promotion.isoformat(),
            "expected_impact": "UP",
        },
        {
            "id": "future-1",
            "name": "Promo agosto",
            "event_type": "PROMOTION",
            "start_date": future_promotion.isoformat(),
            "end_date": future_promotion.isoformat(),
            "expected_impact": "UP",
        },
    ]

    result = build_phase_three_a_prediction(
        mall_id="mall-1",
        start_date=start,
        as_of=as_of,
        mall_rows=rows,
        calendar_events=events,
    )

    learned = result["drivers"]["event_adjustments"][0]
    future = next(item for item in result["daily"] if item["date"] == future_promotion.isoformat())
    event_adjustment = next(
        item for item in future["adjustments"] if item["source"] == "CALENDAR_EVENT"
    )
    assert learned["event_type"] == "PROMOTION"
    assert learned["observations"] == 2
    assert learned["adjustment_percent"] == 20
    assert learned["applied"] is True
    assert event_adjustment["applied"] is True
    assert event_adjustment["percent"] == 20
    assert future["expected_sales"] == 120


def test_phase_three_a_does_not_invent_an_event_adjustment_from_one_example():
    start = date(2026, 4, 1)
    as_of = start + timedelta(days=83)
    past_event = start + timedelta(days=20)
    future_event = as_of + timedelta(days=2)
    rows = _rows(
        start,
        84,
        lambda row_date: 130.0 if row_date == past_event else 100.0,
    )

    result = build_phase_three_a_prediction(
        mall_id="mall-1",
        start_date=start,
        as_of=as_of,
        mall_rows=rows,
        calendar_events=[
            {
                "id": "past",
                "name": "Actividad anterior",
                "event_type": "MALL_ACTIVITY",
                "start_date": past_event.isoformat(),
                "end_date": past_event.isoformat(),
            },
            {
                "id": "future",
                "name": "Actividad futura",
                "event_type": "MALL_ACTIVITY",
                "start_date": future_event.isoformat(),
                "end_date": future_event.isoformat(),
            },
        ],
    )

    learned = result["drivers"]["event_adjustments"][0]
    future = next(item for item in result["daily"] if item["date"] == future_event.isoformat())
    event_adjustment = next(
        item for item in future["adjustments"] if item["source"] == "CALENDAR_EVENT"
    )
    assert learned["observations"] == 1
    assert learned["applied"] is False
    assert learned["adjustment_percent"] == 0
    assert event_adjustment["applied"] is False
    assert future["expected_sales"] == 100


def test_phase_three_a_rejects_future_rows_and_requires_minimum_history():
    start = date(2026, 7, 1)
    as_of = start + timedelta(days=26)
    rows = _rows(start, 27, lambda _row_date: 100.0)
    rows.append(
        {
            "period_date": (as_of + timedelta(days=30)).isoformat(),
            "sales_net": 999999,
        }
    )

    result = build_phase_three_a_prediction(
        mall_id="mall-1",
        start_date=start,
        as_of=as_of,
        mall_rows=rows,
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["quality"]["days_with_data"] == 27
    assert result["horizons"] == []
    assert result["daily"] == []
    assert "28 días" in result["quality"]["reasons"][0]
