"""Phase 3B commercial scenarios and action-plan persistence.

Scenarios are overlays on top of the explainable Phase 3A forecast. They are
decision-support estimates, not causal claims. The service keeps every query
mall-scoped and bounded because it runs with the Supabase service role.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from services.big_data_phase_three_service import BigDataPhaseThreeService


PHASE_THREE_B_VERSION = "big-data-scenarios-phase-three-b-v1"
MAX_SCENARIOS = 100
MAX_ACTIONS = 500
DELETABLE_SCENARIO_STATUSES = {"DRAFT", "CANCELLED"}
SCENARIO_TYPE_LABELS = {
    "PROMOTION": "Promoción",
    "HALLWAY_SALE": "Venta de pasillo",
    "MALL_ACTIVITY": "Actividad del mall",
    "HOLIDAY": "Feriado especial",
    "EXTENDED_HOURS": "Horario extendido",
    "OTHER": "Otro escenario",
}


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_phase_three_b_simulation(
    *,
    prediction: Mapping[str, Any],
    name: str,
    scenario_type: str,
    start_date: date,
    end_date: date,
    adjustment_percent: float,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Overlay a bounded manual assumption on the Phase 3A daily forecast."""
    if prediction.get("status") != "OK":
        raise ValueError(
            "La predicción base no tiene historial suficiente para simular."
        )
    if end_date < start_date:
        raise ValueError("La fecha final no puede ser anterior a la inicial.")
    if not -60 <= adjustment_percent <= 80:
        raise ValueError("El ajuste debe estar entre -60% y +80%.")

    daily = list(prediction.get("daily") or [])
    if not daily:
        raise ValueError("La predicción base no contiene días proyectados.")
    first_forecast_date = _day(daily[0]["date"])
    last_forecast_date = _day(daily[-1]["date"])
    if start_date < first_forecast_date or end_date > last_forecast_date:
        raise ValueError(
            "El escenario debe estar dentro de los próximos 90 días proyectados."
        )

    affected = [
        item
        for item in daily
        if start_date <= _day(item["date"]) <= end_date
    ]
    if not affected:
        raise ValueError("El escenario no afecta ningún día proyectado.")

    multiplier = 1 + adjustment_percent / 100
    simulated_daily: list[dict[str, Any]] = []
    for item in affected:
        baseline = _number(item.get("expected_sales"))
        scenario_sales = baseline * multiplier
        simulated_daily.append(
            {
                "date": str(item["date"]),
                "baseline_sales": round(baseline, 2),
                "scenario_sales": round(scenario_sales, 2),
                "incremental_sales": round(scenario_sales - baseline, 2),
                "lower_bound": round(_number(item.get("lower_bound")) * multiplier, 2),
                "upper_bound": round(_number(item.get("upper_bound")) * multiplier, 2),
                "confidence": item.get("confidence")
                or prediction.get("quality", {}).get("confidence", "LOW"),
            }
        )

    baseline_sales = sum(item["baseline_sales"] for item in simulated_daily)
    scenario_sales = sum(item["scenario_sales"] for item in simulated_daily)
    lower_bound = sum(item["lower_bound"] for item in simulated_daily)
    upper_bound = sum(item["upper_bound"] for item in simulated_daily)

    historical_reference = next(
        (
            item
            for item in prediction.get("drivers", {}).get(
                "event_adjustments", []
            )
            if item.get("event_type") == scenario_type
        ),
        None,
    )
    overlapping_context = [
        {
            "date": str(item["date"]),
            "holiday_name": item.get("holiday_name"),
            "events": [
                {
                    "id": event.get("id"),
                    "name": event.get("name"),
                    "event_type": event.get("event_type"),
                }
                for event in item.get("events", [])
            ],
        }
        for item in affected
        if item.get("holiday_name") or item.get("events")
    ]
    warnings: list[str] = []
    if overlapping_context:
        warnings.append(
            "La predicción base ya incorpora contexto registrado en una o más "
            "fechas. El supuesto se aplicará de forma adicional; revise que no "
            "esté contando el mismo efecto dos veces."
        )
    if historical_reference and historical_reference.get("applied"):
        reference_percent = _number(
            historical_reference.get("adjustment_percent")
        )
        if abs(adjustment_percent - reference_percent) > 20:
            warnings.append(
                "El supuesto manual difiere más de 20 puntos del comportamiento "
                "histórico comparable."
            )
    else:
        warnings.append(
            "No hay suficientes observaciones comparables; el impacto es un "
            "supuesto manual y debe revisarse."
        )
    quality = prediction.get("quality") or {}
    if quality.get("confidence") == "LOW":
        warnings.append(
            "La predicción base tiene confianza baja; use el escenario como rango "
            "de planificación, no como compromiso."
        )

    return {
        "status": "OK",
        "mall_id": prediction.get("mall_id"),
        "name": name.strip(),
        "scenario_type": scenario_type,
        "scenario_type_label": SCENARIO_TYPE_LABELS.get(
            scenario_type, "Otro escenario"
        ),
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "affected_days": len(simulated_daily),
            "forecast_as_of": prediction.get("period", {}).get("as_of"),
        },
        "assumption": {
            "adjustment_percent": round(adjustment_percent, 2),
            "source": "MANUAL",
            "notes": notes.strip() if notes else None,
            "historical_reference": historical_reference,
            "overlapping_context": overlapping_context,
        },
        "result": {
            "baseline_sales": round(baseline_sales, 2),
            "scenario_sales": round(scenario_sales, 2),
            "incremental_sales": round(scenario_sales - baseline_sales, 2),
            "incremental_percent": round(adjustment_percent, 2),
            "lower_bound": round(lower_bound, 2),
            "upper_bound": round(upper_bound, 2),
            "confidence": quality.get("confidence", "LOW"),
        },
        "daily": simulated_daily,
        "warnings": warnings,
        "methodology": (
            "El escenario aplica un supuesto explícito sobre la predicción diaria "
            "de Fase 3A durante el rango seleccionado. La diferencia representa "
            "un impacto potencial para planificación; no demuestra causalidad ni "
            "garantiza el resultado."
        ),
        "model_version": PHASE_THREE_B_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


class BigDataPhaseThreeBService:
    """Bounded Supabase adapter for Phase 3B scenario workflows."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    def simulate(
        self,
        *,
        mall_id: str,
        history_start: date,
        as_of: date,
        name: str,
        scenario_type: str,
        start_date: date,
        end_date: date,
        adjustment_percent: float,
        notes: Optional[str] = None,
    ) -> dict[str, Any]:
        prediction = BigDataPhaseThreeService(self.supabase).prediction(
            mall_id, history_start, as_of
        )
        return build_phase_three_b_simulation(
            prediction=prediction,
            name=name,
            scenario_type=scenario_type,
            start_date=start_date,
            end_date=end_date,
            adjustment_percent=adjustment_percent,
            notes=notes,
        )

    def refresh_scenario_results(
        self, mall_id: str, as_of: Optional[date] = None
    ) -> int:
        """Persist observed results for active/completed scenarios that ended."""
        response = self.supabase.rpc(
            "refresh_big_data_scenario_results",
            {
                "p_mall_id": mall_id,
                "p_as_of": (as_of or date.today()).isoformat(),
            },
        ).execute()
        refreshed = getattr(response, "data", 0)
        if isinstance(refreshed, list):
            refreshed = refreshed[0] if refreshed else 0
        return int(refreshed or 0)

    def list_scenarios(self, mall_id: str) -> dict[str, Any]:
        # One set-based database operation keeps finished evaluations current,
        # including late imports or corrected aggregate rows.
        self.refresh_scenario_results(mall_id)
        scenarios = (
            self.supabase.table("big_data_scenarios")
            .select("*")
            .eq("mall_id", mall_id)
            .order("created_at", desc=True)
            .limit(MAX_SCENARIOS)
            .execute()
            .data
            or []
        )
        scenario_ids = [row["id"] for row in scenarios if row.get("id")]
        actions: list[dict[str, Any]] = []
        if scenario_ids:
            actions = (
                self.supabase.table("big_data_scenario_actions")
                .select("*")
                .eq("mall_id", mall_id)
                .in_("scenario_id", scenario_ids)
                .order("sort_order")
                .limit(MAX_ACTIONS)
                .execute()
                .data
                or []
            )
        by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for action in actions:
            by_scenario[str(action.get("scenario_id"))].append(action)
        return {
            "data": [
                {
                    **scenario,
                    "actions": by_scenario.get(str(scenario.get("id")), []),
                }
                for scenario in scenarios
            ],
            "limit": MAX_SCENARIOS,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def create_scenario(
        self,
        *,
        mall_id: str,
        user_id: str,
        history_start: date,
        as_of: date,
        name: str,
        scenario_type: str,
        start_date: date,
        end_date: date,
        adjustment_percent: float,
        notes: Optional[str],
        actions: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        simulation = self.simulate(
            mall_id=mall_id,
            history_start=history_start,
            as_of=as_of,
            name=name,
            scenario_type=scenario_type,
            start_date=start_date,
            end_date=end_date,
            adjustment_percent=adjustment_percent,
            notes=notes,
        )
        result = simulation["result"]
        scenario_rows = (
            self.supabase.table("big_data_scenarios")
            .insert(
                {
                    "mall_id": mall_id,
                    "name": simulation["name"],
                    "scenario_type": scenario_type,
                    "status": "DRAFT",
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "adjustment_percent": adjustment_percent,
                    "baseline_sales": result["baseline_sales"],
                    "scenario_sales": result["scenario_sales"],
                    "incremental_sales": result["incremental_sales"],
                    "lower_bound": result["lower_bound"],
                    "upper_bound": result["upper_bound"],
                    "confidence": result["confidence"],
                    "model_version": simulation["model_version"],
                    "assumptions": {
                        "source": simulation["assumption"]["source"],
                        "forecast_as_of": simulation["period"]["forecast_as_of"],
                        "affected_days": simulation["period"]["affected_days"],
                        "historical_reference": simulation["assumption"][
                            "historical_reference"
                        ],
                        "overlapping_context": simulation["assumption"][
                            "overlapping_context"
                        ],
                        "warnings": simulation["warnings"],
                    },
                    "notes": notes.strip() if notes else None,
                    "created_by": user_id,
                }
            )
            .execute()
            .data
            or []
        )
        if not scenario_rows:
            raise RuntimeError("No se pudo guardar el escenario.")
        scenario = scenario_rows[0]
        action_rows = [
            {
                "scenario_id": scenario["id"],
                "mall_id": mall_id,
                "title": str(action.get("title") or "").strip(),
                "owner_name": (
                    str(action.get("owner_name") or "").strip() or None
                ),
                "due_date": (
                    _day(action["due_date"]).isoformat()
                    if action.get("due_date")
                    else None
                ),
                "notes": str(action.get("notes") or "").strip() or None,
                "sort_order": position,
                "created_by": user_id,
            }
            for position, action in enumerate(actions)
            if str(action.get("title") or "").strip()
        ]
        created_actions: list[dict[str, Any]] = []
        try:
            if action_rows:
                created_actions = (
                    self.supabase.table("big_data_scenario_actions")
                    .insert(action_rows)
                    .execute()
                    .data
                    or []
                )
        except Exception:
            # Keep the workflow all-or-nothing from the application's perspective.
            self.supabase.table("big_data_scenarios").delete().eq(
                "id", scenario["id"]
            ).eq("mall_id", mall_id).execute()
            raise
        return {**scenario, "actions": created_actions, "simulation": simulation}

    def update_scenario_status(
        self, mall_id: str, scenario_id: str, status: str
    ) -> dict[str, Any]:
        current = (
            self.supabase.table("big_data_scenarios")
            .select("id,status")
            .eq("id", scenario_id)
            .eq("mall_id", mall_id)
            .maybe_single()
            .execute()
            .data
        )
        if not current:
            raise LookupError("Escenario no encontrado.")
        transitions = {
            "DRAFT": {"APPROVED", "CANCELLED"},
            "APPROVED": {"ACTIVE", "CANCELLED"},
            "ACTIVE": {"COMPLETED", "CANCELLED"},
            "COMPLETED": set(),
            "CANCELLED": set(),
        }
        if status not in transitions.get(str(current["status"]), set()):
            raise ValueError(
                f"No se puede pasar de {current['status']} a {status}."
            )
        updated = (
            self.supabase.table("big_data_scenarios")
            .update(
                {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", scenario_id)
            .eq("mall_id", mall_id)
            .execute()
            .data
            or []
        )
        if not updated:
            raise LookupError("Escenario no encontrado.")
        return updated[0]

    def delete_scenario(self, mall_id: str, scenario_id: str) -> dict[str, Any]:
        """Delete an accidental draft or cancelled scenario and its actions."""
        current = (
            self.supabase.table("big_data_scenarios")
            .select("id,name,status")
            .eq("id", scenario_id)
            .eq("mall_id", mall_id)
            .maybe_single()
            .execute()
            .data
        )
        if not current:
            raise LookupError("Escenario no encontrado.")
        if current["status"] not in DELETABLE_SCENARIO_STATUSES:
            raise ValueError(
                "Solo se pueden eliminar escenarios en borrador o cancelados."
            )

        deleted = (
            self.supabase.table("big_data_scenarios")
            .delete()
            .eq("id", scenario_id)
            .eq("mall_id", mall_id)
            .eq("status", current["status"])
            .execute()
            .data
            or []
        )
        if not deleted:
            raise ValueError(
                "El escenario cambió de estado; actualice la lista antes de eliminarlo."
            )
        return {
            "id": scenario_id,
            "name": current["name"],
            "status": current["status"],
            "deleted": True,
        }

    def update_action_status(
        self, mall_id: str, action_id: str, status: str
    ) -> dict[str, Any]:
        current = (
            self.supabase.table("big_data_scenario_actions")
            .select("id,scenario_id,status")
            .eq("id", action_id)
            .eq("mall_id", mall_id)
            .maybe_single()
            .execute()
            .data
        )
        if not current:
            raise LookupError("Acción no encontrada.")
        scenario = (
            self.supabase.table("big_data_scenarios")
            .select("id,status")
            .eq("id", current["scenario_id"])
            .eq("mall_id", mall_id)
            .maybe_single()
            .execute()
            .data
        )
        if not scenario:
            raise LookupError("Escenario no encontrado.")
        if scenario["status"] in {"COMPLETED", "CANCELLED"}:
            raise ValueError(
                "No se pueden modificar acciones de un escenario cerrado."
            )
        transitions = {
            "PENDING": {"IN_PROGRESS", "DONE", "CANCELLED"},
            "IN_PROGRESS": {"PENDING", "DONE", "CANCELLED"},
            "DONE": set(),
            "CANCELLED": set(),
        }
        if (
            status != current["status"]
            and status not in transitions.get(str(current["status"]), set())
        ):
            raise ValueError(
                f"No se puede pasar de {current['status']} a {status}."
            )
        updated = (
            self.supabase.table("big_data_scenario_actions")
            .update(
                {
                    "status": status,
                    "completed_at": (
                        datetime.now(timezone.utc).isoformat()
                        if status == "DONE"
                        else None
                    ),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", action_id)
            .eq("mall_id", mall_id)
            .execute()
            .data
            or []
        )
        if not updated:
            raise LookupError("Acción no encontrada.")
        return updated[0]
