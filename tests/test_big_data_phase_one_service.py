from datetime import date, timedelta

from services.big_data_phase_one_service import (
    PHASE_ONE_VERSION,
    build_phase_one_intelligence,
    country_holiday_map,
)


def _mall_rows(start: date, values: list[float]):
    return [
        {
            "period_date": (start + timedelta(days=index)).isoformat(),
            "sales_net": value,
            "records_processed": 10,
            "coverage_status": "COMPLETE",
        }
        for index, value in enumerate(values)
    ]


def _local_rows(start: date, values_by_local: dict[str, list[float]]):
    rows = []
    for local_id, values in values_by_local.items():
        rows.extend(
            {
                "period_date": (start + timedelta(days=index)).isoformat(),
                "local_id": local_id,
                "dimension_key": local_id,
                "sales_net": value,
            }
            for index, value in enumerate(values)
        )
    return rows


def test_phase_one_explains_weekend_holiday_and_store_contributors():
    start = date(2026, 6, 1)  # Monday
    end = start + timedelta(days=27)
    mall_values = [
        150 if (start + timedelta(days=index)).weekday() >= 5 else 100
        for index in range(28)
    ]
    mall_values[21] = 200  # Monday anomaly after three comparable Mondays.
    local_a = [value * 0.6 for value in mall_values]
    local_b = [value * 0.4 for value in mall_values]
    local_a[21] = 150
    local_b[21] = 50

    result = build_phase_one_intelligence(
        mall_id="mall-1",
        start_date=start,
        end_date=end,
        mall_rows=_mall_rows(start, mall_values),
        local_rows=_local_rows(start, {"local-a": local_a, "local-b": local_b}),
        logs=[{"estado": "exito"}],
        local_names={"local-a": "Local A", "local-b": "Local B"},
        active_local_count=2,
        holidays={date(2026, 6, 4): "Corpus Christi"},
        last_processed_sale_date=end,
        last_analytics_update="2026-06-28T05:00:00+00:00",
        country_code="DO",
    )

    assert result["version"] == PHASE_ONE_VERSION
    assert result["quality"]["status"] == "RELIABLE"
    assert result["seasonality"]["weekend_lift_percent"] == 50
    holiday = next(item for item in result["calendar"] if item["date"] == "2026-06-04")
    assert holiday["holiday_name"] == "Corpus Christi"
    anomaly = next(item for item in result["anomalies"] if item["date"] == "2026-06-22")
    assert anomaly["direction"] == "UP"
    assert anomaly["deviation_percent"] == 100
    assert anomaly["contributors"][0]["local_name"] == "Local A"
    assert "principal contribuyente" in anomaly["explanation"]


def test_phase_one_blocks_commercial_conclusions_when_quality_is_low():
    start = date(2026, 7, 1)
    end = date(2026, 7, 10)
    result = build_phase_one_intelligence(
        mall_id="mall-1",
        start_date=start,
        end_date=end,
        mall_rows=_mall_rows(start, [100, 100, 30]),
        local_rows=[],
        logs=[{"estado": "error"}, {"estado": "parcial"}],
        active_local_count=8,
        last_processed_sale_date=date(2026, 7, 3),
    )

    assert result["general_status"] == "DATA_INCOMPLETE"
    assert result["quality"]["confidence"] == "LOW"
    assert result["quality"]["missing_days"] == 7
    assert result["quality"]["failed_imports"] == 1
    assert result["quality"]["partial_imports"] == 1
    assert result["insights"][0]["type"] == "DATA_QUALITY"


def test_registered_mall_event_is_explained_and_removed_from_anomalies():
    start = date(2026, 6, 1)
    end = start + timedelta(days=27)
    mall_values = [100.0] * 28
    mall_values[21] = 180.0
    local_values = [100.0] * 28
    local_values[21] = 180.0

    result = build_phase_one_intelligence(
        mall_id="mall-1",
        start_date=start,
        end_date=end,
        mall_rows=_mall_rows(start, mall_values),
        local_rows=_local_rows(start, {"local-a": local_values}),
        local_names={"local-a": "Local A"},
        active_local_count=1,
        calendar_events=[
            {
                "id": "event-1",
                "name": "Feria de verano",
                "event_type": "HALLWAY_SALE",
                "start_date": "2026-06-22",
                "end_date": "2026-06-22",
                "expected_impact": "UP",
                "notes": "Venta en pasillos centrales",
            }
        ],
        last_processed_sale_date=end,
    )

    calendar_day = next(
        item for item in result["calendar"] if item["date"] == "2026-06-22"
    )
    assert calendar_day["status"] == "EXPLAINED_EVENT"
    assert calendar_day["events"][0]["event_type_label"] == "Venta de pasillo"
    assert result["anomalies"] == []
    assert result["explained_events"][0]["events"][0]["name"] == "Feria de verano"
    assert "movimiento explicado" in result["explained_events"][0]["explanation"]


def test_registered_event_stays_anomalous_when_direction_contradicts_plan():
    start = date(2026, 6, 1)
    end = start + timedelta(days=27)
    mall_values = [100.0] * 28
    mall_values[21] = 45.0

    result = build_phase_one_intelligence(
        mall_id="mall-1",
        start_date=start,
        end_date=end,
        mall_rows=_mall_rows(start, mall_values),
        local_rows=[],
        calendar_events=[
            {
                "id": "event-1",
                "name": "Promoción de verano",
                "event_type": "PROMOTION",
                "start_date": "2026-06-22",
                "end_date": "2026-06-22",
                "expected_impact": "UP",
            }
        ],
        last_processed_sale_date=end,
    )

    assert result["explained_events"] == []
    anomaly = next(item for item in result["anomalies"] if item["date"] == "2026-06-22")
    assert "no coincide con el impacto esperado" in anomaly["explanation"]


def test_phase_one_caps_future_ranges_at_today(monkeypatch):
    start = date.today() - timedelta(days=2)
    end = date.today() + timedelta(days=5)
    result = build_phase_one_intelligence(
        mall_id="mall-1",
        start_date=start,
        end_date=end,
        mall_rows=_mall_rows(start, [100, 100, 100]),
        local_rows=[],
        last_processed_sale_date=date.today(),
    )

    assert result["period"]["analysis_end"] == date.today().isoformat()
    assert result["quality"]["expected_days"] == 3


def test_dominican_calendar_uses_observed_public_holidays():
    calendar = country_holiday_map(
        "DO", date(2026, 1, 1), date(2026, 12, 31)
    )

    assert calendar[date(2026, 1, 5)] == "Día de los Santos Reyes"
    assert calendar[date(2026, 6, 4)] == "Corpus Christi"
