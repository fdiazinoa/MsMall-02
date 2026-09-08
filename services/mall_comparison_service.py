"""Cross-mall comparison aggregates built from the existing period metrics RPC."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _first(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _aggregate_dimension(locales: Iterable[Dict[str, Any]], field: str, fallback: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for local in locales:
        label = str(local.get(field) or "").strip() or fallback
        row = grouped.setdefault(
            label,
            {
                "nombre": label,
                "total_bruto": 0.0,
                "total_neto": 0.0,
                "transacciones": 0,
                "cantidad_locales": 0,
            },
        )
        row["total_bruto"] += _number(local.get("total_bruto"))
        row["total_neto"] += _number(local.get("total_neto"))
        row["transacciones"] += int(_number(local.get("transacciones")))
        row["cantidad_locales"] += 1

    output = []
    for row in grouped.values():
        transactions = int(row["transacciones"])
        row["ticket_promedio"] = row["total_bruto"] / transactions if transactions else 0.0
        output.append(row)
    return sorted(output, key=lambda item: (-item["total_bruto"], item["nombre"]))


class MallComparisonService:
    """Load comparable mall, store, business category and rubro metrics."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    def load(self, mall_ids: List[str], start_date: str, end_date: str) -> Dict[str, Any]:
        details_response = (
            self.supabase.table("malls")
            .select("id,nombre,conf_locale,conf_moneda")
            .in_("id", mall_ids)
            .execute()
        )
        details = {str(row.get("id")): row for row in (details_response.data or [])}
        missing = [mall_id for mall_id in mall_ids if mall_id not in details]
        if missing:
            raise ValueError("Uno o más malls seleccionados no existen.")

        malls: List[Dict[str, Any]] = []
        for mall_id in mall_ids:
            store_response = (
                self.supabase.table("locales")
                .select("id,nombre,rubro,tipo_negocio")
                .eq("mall_id", mall_id)
                .execute()
            )
            stores = store_response.data or []
            metrics_response = self.supabase.rpc(
                "get_metricas_periodo",
                {
                    "mall_id_param": mall_id,
                    "fecha_inicio_param": start_date,
                    "fecha_fin_param": end_date,
                },
            ).execute()
            metrics_rows = metrics_response.data or []
            metrics_by_id = {
                str(_first(row, "local_id", "out_local_id")): row
                for row in metrics_rows
                if _first(row, "local_id", "out_local_id")
            }

            locales = []
            for store in stores:
                local_id = str(store.get("id") or "")
                metric = metrics_by_id.get(local_id, {})
                gross = _number(_first(metric, "total_bruto", "out_total_bruto"))
                net = _number(_first(metric, "total_neto", "out_total_neto"))
                transactions = int(_number(_first(metric, "transacciones", "out_transacciones")))
                locales.append(
                    {
                        "id": local_id,
                        "nombre": store.get("nombre") or _first(metric, "local_nombre", "out_local_nombre") or "Local sin nombre",
                        "rubro": store.get("rubro") or _first(metric, "rubro", "out_rubro") or "Sin rubro",
                        "categoria": store.get("tipo_negocio") or "Sin categoría",
                        "total_bruto": gross,
                        "total_neto": net,
                        "transacciones": transactions,
                        "ticket_promedio": gross / transactions if transactions else 0.0,
                    }
                )

            total_gross = sum(row["total_bruto"] for row in locales)
            total_net = sum(row["total_neto"] for row in locales)
            transactions = sum(row["transacciones"] for row in locales)
            mall = details[mall_id]
            malls.append(
                {
                    "id": mall_id,
                    "nombre": mall.get("nombre") or "Mall sin nombre",
                    "locale": mall.get("conf_locale") or "es-DO",
                    "moneda": mall.get("conf_moneda") or "DOP",
                    "total_bruto": total_gross,
                    "total_neto": total_net,
                    "transacciones": transactions,
                    "ticket_promedio": total_gross / transactions if transactions else 0.0,
                    "locales": sorted(locales, key=lambda row: (-row["total_bruto"], row["nombre"])),
                    "rubros": _aggregate_dimension(locales, "rubro", "Sin rubro"),
                    "categorias": _aggregate_dimension(locales, "categoria", "Sin categoría"),
                }
            )

        return {"start_date": start_date, "end_date": end_date, "malls": malls}
