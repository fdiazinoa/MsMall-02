from datetime import date, timedelta

import pytest

from services.big_data_phase_three_b_service import (
    PHASE_THREE_B_VERSION,
    build_phase_three_b_simulation,
)


def _prediction(as_of: date, *, status: str = "OK"):
    daily = []
    for offset in range(1, 91):
        projected_date = as_of + timedelta(days=offset)
        daily.append(
            {
                "date": projected_date.isoformat(),
                "expected_sales": 100,
                "lower_bound": 80,
                "upper_bound": 120,
                "confidence": "HIGH",
            }
        )
    return {
        "mall_id": "mall-1",
        "status": status,
        "period": {"as_of": as_of.isoformat()},
        "quality": {"confidence": "HIGH"},
        "daily": daily if status == "OK" else [],
        "drivers": {
            "event_adjustments": [
                {
                    "event_type": "PROMOTION",
                    "observations": 4,
                    "adjustment_percent": 12,
                    "applied": True,
                }
            ]
        },
    }


def test_phase_three_b_compares_manual_scenario_against_base_forecast():
    as_of = date(2026, 7, 29)
    result = build_phase_three_b_simulation(
        prediction=_prediction(as_of),
        name="Semana de moda",
        scenario_type="PROMOTION",
        start_date=as_of + timedelta(days=2),
        end_date=as_of + timedelta(days=4),
        adjustment_percent=15,
        notes="Supuesto aprobado por comercial.",
    )

    assert result["status"] == "OK"
    assert result["model_version"] == PHASE_THREE_B_VERSION
    assert result["period"]["affected_days"] == 3
    assert result["result"]["baseline_sales"] == 300
    assert result["result"]["scenario_sales"] == 345
    assert result["result"]["incremental_sales"] == 45
    assert result["result"]["lower_bound"] == 276
    assert result["result"]["upper_bound"] == 414
    assert result["assumption"]["historical_reference"]["adjustment_percent"] == 12
    assert result["assumption"]["source"] == "MANUAL"
    assert result["warnings"] == []
    assert "no demuestra causalidad" in result["methodology"]


def test_phase_three_b_warns_when_manual_assumption_lacks_history():
    as_of = date(2026, 7, 29)
    prediction = _prediction(as_of)
    prediction["drivers"]["event_adjustments"] = []

    result = build_phase_three_b_simulation(
        prediction=prediction,
        name="Horario extendido",
        scenario_type="EXTENDED_HOURS",
        start_date=as_of + timedelta(days=1),
        end_date=as_of + timedelta(days=1),
        adjustment_percent=8,
    )

    assert len(result["warnings"]) == 1
    assert "supuesto manual" in result["warnings"][0]


def test_phase_three_b_warns_when_base_already_contains_calendar_context():
    as_of = date(2026, 7, 29)
    prediction = _prediction(as_of)
    prediction["daily"][0]["events"] = [
        {"id": "event-1", "name": "Feria del mall", "event_type": "MALL_ACTIVITY"}
    ]

    result = build_phase_three_b_simulation(
        prediction=prediction,
        name="Feria del mall",
        scenario_type="MALL_ACTIVITY",
        start_date=as_of + timedelta(days=1),
        end_date=as_of + timedelta(days=1),
        adjustment_percent=8,
    )

    assert result["assumption"]["overlapping_context"][0]["date"] == (
        as_of + timedelta(days=1)
    ).isoformat()
    assert any("contando el mismo efecto dos veces" in item for item in result["warnings"])


def test_phase_three_b_rejects_dates_outside_the_90_day_forecast():
    as_of = date(2026, 7, 29)

    with pytest.raises(ValueError, match="próximos 90 días"):
        build_phase_three_b_simulation(
            prediction=_prediction(as_of),
            name="Escenario lejano",
            scenario_type="OTHER",
            start_date=as_of + timedelta(days=91),
            end_date=as_of + timedelta(days=92),
            adjustment_percent=5,
        )


def test_phase_three_b_requires_a_valid_phase_three_a_prediction():
    as_of = date(2026, 7, 29)

    with pytest.raises(ValueError, match="historial suficiente"):
        build_phase_three_b_simulation(
            prediction=_prediction(as_of, status="INSUFFICIENT_DATA"),
            name="Promoción",
            scenario_type="PROMOTION",
            start_date=as_of + timedelta(days=1),
            end_date=as_of + timedelta(days=2),
            adjustment_percent=5,
        )
