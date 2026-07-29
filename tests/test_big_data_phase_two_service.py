from datetime import date, timedelta

from services.big_data_phase_two_service import (
    PHASE_TWO_VERSION,
    build_phase_two_diagnostic,
)


def _local_rows(start: date, values: list[float]):
    return [
        {
            "period_date": (start + timedelta(days=index)).isoformat(),
            "local_id": "local-a",
            "sales_net": value,
            "transaction_count": 10,
            "coverage_status": "complete",
        }
        for index, value in enumerate(values)
    ]


def _peer_rows(start: date, totals_by_local: dict[str, float]):
    return [
        {
            "period_date": start.isoformat(),
            "local_id": local_id,
            "sales_net": total,
        }
        for local_id, total in totals_by_local.items()
    ]


def test_phase_two_explains_commercial_movement_with_category_benchmark():
    start = date(2026, 6, 1)
    end = start + timedelta(days=27)
    values = [100.0] * 28
    values[21] = 180.0

    result = build_phase_two_diagnostic(
        mall_id="mall-1",
        local={"id": "local-a", "nombre": "Local A", "rubro": "Retail"},
        start_date=start,
        end_date=end,
        target_date=date(2026, 6, 22),
        local_rows=_local_rows(start, values),
        peer_rows=_peer_rows(
            start,
            {"local-a": 2980.0, "local-b": 2500.0, "local-c": 2000.0},
        ),
        peer_names={
            "local-a": "Local A",
            "local-b": "Local B",
            "local-c": "Local C",
        },
        category_id="category-1",
        category_name="Moda",
        logs=[
            {
                "fecha_hora": "2026-06-22T08:00:00+00:00",
                "archivo": "ventas_22062026.csv",
                "estado": "exito",
                "records_processed": 10,
                "error_count": 0,
            }
        ],
    )

    assert result["version"] == PHASE_TWO_VERSION
    assert result["headline"]["observed_sales"] == 180
    assert result["headline"]["expected_sales"] == 100
    assert result["headline"]["deviation_percent"] == 80
    assert result["benchmark"]["status"] == "OK"
    assert result["benchmark"]["rank"] == 1
    assert result["benchmark"]["comparable_stores"] == 3
    assert result["diagnosis"]["classification"] == "COMMERCIAL_MOVEMENT"
    assert result["evidence"]["imports"][0]["match"] == "FILE_DATE"
    assert result["evidence"]["related_import_issue"] is False


def test_phase_two_marks_signal_as_mixed_when_related_import_is_partial():
    start = date(2026, 6, 1)
    end = start + timedelta(days=27)
    values = [100.0] * 28
    values[21] = 40.0

    result = build_phase_two_diagnostic(
        mall_id="mall-1",
        local={"id": "local-a", "nombre": "Local A"},
        start_date=start,
        end_date=end,
        target_date=date(2026, 6, 22),
        local_rows=_local_rows(start, values),
        logs=[
            {
                "fecha_hora": "2026-06-23T02:00:00+00:00",
                "archivo": "ventas_22062026.txt",
                "estado": "parcial",
                "records_processed": 4,
                "error_count": 6,
                "mensaje": "Se insertaron registros válidos y se aislaron errores.",
            }
        ],
    )

    assert result["diagnosis"]["classification"] == "MIXED"
    assert result["evidence"]["related_import_issue"] is True
    assert result["evidence"]["imports"][0]["has_issue"] is True
    assert "recalcular" in result["diagnosis"]["recommendation"].lower()


def test_phase_two_can_use_explicit_rubro_fallback_while_taxonomy_is_empty():
    start = date(2026, 6, 1)
    end = start + timedelta(days=6)
    result = build_phase_two_diagnostic(
        mall_id="mall-1",
        local={"id": "local-a", "nombre": "Local A", "rubro": "Moda"},
        start_date=start,
        end_date=end,
        target_date=end,
        local_rows=_local_rows(start, [100.0] * 7),
        peer_rows=_peer_rows(
            start,
            {"local-a": 700.0, "local-b": 600.0, "local-c": 500.0},
        ),
        peer_names={
            "local-a": "Local A",
            "local-b": "Local B",
            "local-c": "Local C",
        },
        category_name="Moda",
        category_source="RUBRO_FALLBACK",
    )

    assert result["benchmark"]["status"] == "OK"
    assert result["benchmark"]["category_source"] == "RUBRO_FALLBACK"
    assert result["local"]["category_source"] == "RUBRO_FALLBACK"


def test_phase_two_does_not_claim_a_cause_without_comparable_history():
    target = date(2026, 7, 28)
    result = build_phase_two_diagnostic(
        mall_id="mall-1",
        local={"id": "local-a", "nombre": "Local A"},
        start_date=target,
        end_date=target,
        target_date=target,
        local_rows=[
            {
                "period_date": target.isoformat(),
                "local_id": "local-a",
                "sales_net": 100,
                "coverage_status": "complete",
            }
        ],
    )

    assert result["diagnosis"]["classification"] == "INSUFFICIENT_DATA"
    assert result["headline"]["deviation_percent"] is None
    assert result["diagnosis"]["confidence"] <= 0.4
