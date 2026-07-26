from pathlib import Path
from types import SimpleNamespace

import pytest

from services.dashboard_analytics_service import (
    DashboardAnalyticsService,
    dashboard_result_differences,
    empty_dashboard_result,
    normalize_dashboard_result,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeRpcQuery:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return SimpleNamespace(data=self.payload)


class FakeRpcSupabase:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return FakeRpcQuery(self.payload)


def test_dashboard_rpc_v2_normalizes_the_complete_contract():
    payload = {
        **empty_dashboard_result(),
        "ventas_totales_bruto": "125.50",
        "ventas_totales_neto": "100.25",
        "transacciones": "2",
        "ticket_promedio": "62.75",
    }
    fake = FakeRpcSupabase(payload)

    result = DashboardAnalyticsService(fake).load_v2("mall-1", "2026-07-01", "2026-07-26")

    assert result["ventas_totales_bruto"] == 125.5
    assert result["ventas_totales_neto"] == 100.25
    assert result["transacciones"] == 2
    assert result["ticket_promedio"] == 62.75
    assert fake.calls == [
        (
            "get_dashboard_kpis_v2",
            {
                "p_mall_id": "mall-1",
                "p_start_date": "2026-07-01",
                "p_end_date": "2026-07-26",
            },
        )
    ]


def test_dashboard_v2_falls_back_to_legacy_without_breaking_the_endpoint(monkeypatch):
    service = DashboardAnalyticsService(FakeRpcSupabase(RuntimeError("RPC unavailable")))
    legacy = {**empty_dashboard_result(), "transacciones": 7}
    monkeypatch.setattr(service, "load_legacy", lambda *_args: legacy)

    result, source = service.load("mall-1", "2026-07-01", "2026-07-26", mode="v2")

    assert result == legacy
    assert source == "legacy-fallback"


def test_dashboard_shadow_comparison_tolerates_currency_rounding():
    expected = {
        **empty_dashboard_result(),
        "ventas_totales_bruto": 100.001,
        "top_locales": [{"name": "Local A", "total": 100.001}],
    }
    actual = {
        **empty_dashboard_result(),
        "ventas_totales_bruto": 100.006,
        "top_locales": [{"name": "Local A", "total": 100.006}],
    }

    assert dashboard_result_differences(expected, actual) == []


def test_dashboard_result_rejects_non_object_rpc_payload():
    with pytest.raises(ValueError, match="objeto JSON"):
        normalize_dashboard_result(42)


def test_dashboard_rpc_migration_is_internal_and_returns_all_ui_sections():
    migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260726194846_dashboard_bi_kpis_v2.sql"
    ).read_text(encoding="utf-8")

    assert "security invoker" in migration.lower()
    assert "set search_path = ''" in migration.lower()
    assert "revoke all on function public.get_dashboard_kpis_v2" in migration.lower()
    assert "grant execute on function public.get_dashboard_kpis_v2" in migration.lower()
    for field in (
        "ventas_por_tipo_negocio",
        "ventas_por_rubro",
        "ventas_por_tipo_negocio_top_locales",
        "ventas_por_rubro_top_locales",
        "ventas_por_tienda_completo",
    ):
        assert f"'{field}'" in migration


def test_dashboard_name_parity_migration_preserves_legacy_store_names():
    migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260726200659_fix_dashboard_store_name_parity.sql"
    ).read_text(encoding="utf-8")

    assert "coalesce(nullif(l.nombre, ''), 'Local sin nombre') as local_name" in migration
    assert "btrim(l.nombre)" not in migration
