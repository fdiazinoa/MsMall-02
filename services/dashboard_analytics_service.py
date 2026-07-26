"""Dashboard BI aggregation with a safe legacy-to-RPC rollout path."""

from __future__ import annotations

import json
import logging
import math
from numbers import Number
from typing import Any, Dict, List, Tuple


def empty_dashboard_result() -> Dict[str, Any]:
    return {
        "ventas_totales_bruto": 0,
        "ventas_totales_neto": 0,
        "transacciones": 0,
        "ticket_promedio": 0,
        "variacion_ventas": 0,
        "top_locales": [],
        "ventas_por_dia": [],
        "ventas_por_tipo_negocio": [],
        "ventas_por_rubro": [],
        "ventas_por_tipo_negocio_top_locales": {},
        "ventas_por_rubro_top_locales": {},
        "ventas_por_tienda_completo": {},
    }


def normalize_dashboard_result(value: Any) -> Dict[str, Any]:
    if isinstance(value, list):
        value = value[0] if value else {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("La RPC del dashboard no devolvió un objeto JSON.")

    normalized = empty_dashboard_result()
    normalized.update(value)
    normalized["ventas_totales_bruto"] = float(normalized.get("ventas_totales_bruto") or 0)
    normalized["ventas_totales_neto"] = float(normalized.get("ventas_totales_neto") or 0)
    normalized["transacciones"] = int(normalized.get("transacciones") or 0)
    normalized["ticket_promedio"] = float(normalized.get("ticket_promedio") or 0)
    normalized["variacion_ventas"] = float(normalized.get("variacion_ventas") or 0)
    return normalized


def dashboard_result_differences(
    expected: Any,
    actual: Any,
    *,
    path: str = "dashboard",
    limit: int = 25,
) -> List[str]:
    differences: List[str] = []

    def compare(left: Any, right: Any, current_path: str) -> None:
        if len(differences) >= limit:
            return
        if isinstance(left, Number) and isinstance(right, Number):
            if not math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=0.01):
                differences.append(f"{current_path}: {left!r} != {right!r}")
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                if key not in left:
                    differences.append(f"{current_path}.{key}: ausente en legacy")
                elif key not in right:
                    differences.append(f"{current_path}.{key}: ausente en v2")
                else:
                    compare(left[key], right[key], f"{current_path}.{key}")
                if len(differences) >= limit:
                    return
            return
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                differences.append(f"{current_path}: longitudes {len(left)} != {len(right)}")
                return
            for index, (left_item, right_item) in enumerate(zip(left, right)):
                compare(left_item, right_item, f"{current_path}[{index}]")
                if len(differences) >= limit:
                    return
            return
        if left != right:
            differences.append(f"{current_path}: {left!r} != {right!r}")

    compare(expected, actual, path)
    return differences


class DashboardAnalyticsService:
    """Loads Dashboard BI data using legacy pagination or the v2 aggregate RPC."""

    VALID_MODES = {"legacy", "shadow", "v2"}

    def __init__(self, supabase_client: Any, logger: logging.Logger | None = None):
        self.supabase = supabase_client
        self.logger = logger or logging.getLogger("dashboard-analytics")

    @classmethod
    def normalize_mode(cls, mode: str | None) -> str:
        normalized = str(mode or "legacy").strip().lower()
        return normalized if normalized in cls.VALID_MODES else "legacy"

    def load(
        self,
        mall_id: str,
        start_date: str,
        end_date: str,
        *,
        mode: str = "legacy",
    ) -> Tuple[Dict[str, Any], str]:
        normalized_mode = self.normalize_mode(mode)
        if normalized_mode == "legacy":
            return self.load_legacy(mall_id, start_date, end_date), "legacy"

        if normalized_mode == "shadow":
            legacy = self.load_legacy(mall_id, start_date, end_date)
            try:
                optimized = self.load_v2(mall_id, start_date, end_date)
                differences = dashboard_result_differences(legacy, optimized)
                if differences:
                    self.logger.warning(
                        "Dashboard BI shadow mismatch for mall %s (%s to %s): %s",
                        mall_id,
                        start_date,
                        end_date,
                        "; ".join(differences),
                    )
                    return legacy, "legacy-shadow-mismatch"
                self.logger.info(
                    "Dashboard BI shadow match for mall %s (%s to %s)",
                    mall_id,
                    start_date,
                    end_date,
                )
                return legacy, "legacy-shadow-match"
            except Exception as exc:
                self.logger.warning("Dashboard BI shadow RPC failed; legacy preserved: %s", exc)
                return legacy, "legacy-shadow-error"

        try:
            return self.load_v2(mall_id, start_date, end_date), "v2"
        except Exception as exc:
            self.logger.exception("Dashboard BI v2 failed; falling back to legacy: %s", exc)
            return self.load_legacy(mall_id, start_date, end_date), "legacy-fallback"

    def load_v2(self, mall_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        response = self.supabase.rpc(
            "get_dashboard_kpis_v2",
            {
                "p_mall_id": mall_id,
                "p_start_date": start_date,
                "p_end_date": end_date,
            },
        ).execute()
        return normalize_dashboard_result(response.data)

    def load_legacy(self, mall_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        stores_response = (
            self.supabase.table("locales")
            .select("id, nombre, rubro, tipo_negocio")
            .eq("mall_id", mall_id)
            .execute()
        )
        stores = stores_response.data or []
        store_map = {str(store["id"]): store for store in stores if store.get("id")}
        allowed_local_ids = list(store_map)
        if not allowed_local_ids:
            return empty_dashboard_result()

        sales: List[Dict[str, Any]] = []
        page_size = 1000
        page = 0
        while True:
            response = (
                self.supabase.table("ventas")
                .select("local_id, fecha, total_bruto, total_neto")
                .in_("local_id", allowed_local_ids)
                .gte("fecha", start_date)
                .lte("fecha", end_date)
                .order("fecha")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )
            chunk = response.data or []
            if not chunk:
                break
            sales.extend(chunk)
            if len(chunk) < page_size:
                break
            page += 1

        sales_by_store: Dict[str, float] = {}
        total_bruto = 0.0
        total_neto = 0.0
        sales_by_day: Dict[str, float] = {}
        sales_by_business_type: Dict[str, float] = {}
        sales_by_rubro: Dict[str, float] = {}
        stores_by_business_type: Dict[str, Dict[str, Dict[str, Any]]] = {}
        stores_by_rubro: Dict[str, Dict[str, Dict[str, Any]]] = {}

        def segment_label(value: Any, fallback: str) -> str:
            label = str(value or "").strip()
            return label if label else fallback

        def add_segment_store(
            segment_store_map: Dict[str, Dict[str, Dict[str, Any]]],
            segment: str,
            store_name: str,
            bruto: float,
            neto: float,
        ) -> None:
            store_totals = segment_store_map.setdefault(segment, {})
            totals = store_totals.setdefault(
                store_name,
                {
                    "name": store_name,
                    "total": 0.0,
                    "total_neto": 0.0,
                    "transacciones": 0,
                },
            )
            totals["total"] += bruto
            totals["total_neto"] += neto
            totals["transacciones"] += 1

        for sale in sales:
            store = store_map.get(str(sale.get("local_id") or ""))
            if not store:
                continue
            store_name = store.get("nombre") or "Local sin nombre"
            bruto = float(sale.get("total_bruto") or 0)
            neto = float(sale.get("total_neto") or 0)
            total_bruto += bruto
            total_neto += neto
            sales_by_store[store_name] = sales_by_store.get(store_name, 0) + bruto

            business_type = segment_label(store.get("tipo_negocio"), "Sin tipo de negocio")
            rubro = segment_label(store.get("rubro"), "Sin rubro")
            sales_by_business_type[business_type] = sales_by_business_type.get(business_type, 0) + bruto
            sales_by_rubro[rubro] = sales_by_rubro.get(rubro, 0) + bruto
            add_segment_store(stores_by_business_type, business_type, store_name, bruto, neto)
            add_segment_store(stores_by_rubro, rubro, store_name, bruto, neto)

            day = str(sale.get("fecha") or "")
            sales_by_day[day] = sales_by_day.get(day, 0) + bruto

        def segment_items(values: Dict[str, float]) -> List[Dict[str, Any]]:
            return [
                {"name": key, "value": value}
                for key, value in sorted(values.items(), key=lambda item: item[1], reverse=True)
            ]

        def segment_top_stores(
            segment_store_map: Dict[str, Dict[str, Dict[str, Any]]],
        ) -> Dict[str, List[Dict[str, Any]]]:
            output: Dict[str, List[Dict[str, Any]]] = {}
            for segment, segment_stores in segment_store_map.items():
                segment_total = sum(float(item.get("total") or 0) for item in segment_stores.values())
                output[segment] = []
                for item in sorted(
                    segment_stores.values(),
                    key=lambda row: row["total"],
                    reverse=True,
                )[:10]:
                    bruto = float(item.get("total") or 0)
                    transactions = int(item.get("transacciones") or 0)
                    output[segment].append(
                        {
                            "name": item["name"],
                            "total": bruto,
                            "total_neto": float(item.get("total_neto") or 0),
                            "transacciones": transactions,
                            "ticket_promedio": bruto / transactions if transactions > 0 else 0,
                            "participacion": bruto / segment_total * 100 if segment_total > 0 else 0,
                        }
                    )
            return output

        return {
            "ventas_totales_bruto": total_bruto,
            "ventas_totales_neto": total_neto,
            "transacciones": len(sales),
            "ticket_promedio": total_bruto / len(sales) if sales else 0,
            "variacion_ventas": 0,
            "top_locales": [
                {"name": key, "total": value}
                for key, value in sorted(sales_by_store.items(), key=lambda item: item[1], reverse=True)[:5]
            ],
            "ventas_por_dia": [
                {"fecha": key, "total": value}
                for key, value in sorted(sales_by_day.items())
            ],
            "ventas_por_tipo_negocio": segment_items(sales_by_business_type),
            "ventas_por_rubro": segment_items(sales_by_rubro),
            "ventas_por_tipo_negocio_top_locales": segment_top_stores(stores_by_business_type),
            "ventas_por_rubro_top_locales": segment_top_stores(stores_by_rubro),
            "ventas_por_tienda_completo": sales_by_store,
        }
