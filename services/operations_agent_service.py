"""Concurrent, deterministic consumer for the official operational model."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


class OperationsAgentWorker:
    """Claims events atomically and creates traceable observations and patterns."""

    def __init__(self, supabase_client: Any, logger: logging.Logger | None = None):
        self.supabase = supabase_client
        self.logger = logger or logging.getLogger("operations-agent")

    def process_pending_events(self, limit: int = 25) -> dict[str, Any]:
        started = time.monotonic()
        result: dict[str, Any] = {
            "processed": 0,
            "failed": 0,
            "observations": 0,
            "patterns": 0,
        }
        events = _rows(
            self.supabase.rpc(
                "claim_operations_events",
                {"p_limit": max(1, min(limit, 100)), "p_timeout_minutes": 15},
            ).execute()
        )
        for event in events:
            try:
                counts = self._process_claimed_event(event)
                result["processed"] += 1
                result["observations"] += counts["observations"]
                result["patterns"] += counts["patterns"]
            except Exception as exc:  # Each claim remains independently retryable.
                result["failed"] += 1
                self.logger.exception("Operational event failed id=%s", event.get("id"))
                (
                    self.supabase.table("operations_events")
                    .update(
                        {
                            "processing_status": "FAILED",
                            "processing_error": str(exc)[:1000],
                        }
                    )
                    .eq("id", event.get("id"))
                    .eq("claim_token", event.get("claim_token"))
                    .execute()
                )
        result["duration_ms"] = int((time.monotonic() - started) * 1000)
        return result

    def _process_claimed_event(self, event: dict[str, Any]) -> dict[str, int]:
        event_id = event.get("id")
        mall_id = event.get("mall_id")
        local_id = event.get("local_id")
        event_type = str(event.get("event_type") or "OPERATIONAL_EVENT")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        severity = str(event.get("severity") or "INFO").upper()

        observation = self._deterministic_observation(event_type, payload)
        observation_row = {
            "mall_id": mall_id,
            "local_id": local_id,
            "event_id": event_id,
            "observation_type": event_type,
            "observation": observation,
            "conclusion": self._deterministic_conclusion(event_type),
            "recommendation": self._deterministic_recommendation(event_type),
            "confidence": 0.95,
            "metadata": {
                "metrics": self._safe_metrics(payload),
                "period": payload.get("period") or payload.get("date"),
                "coverage": payload.get("coverage"),
                "rule_version": "operations-observation-v1",
                "generated_at": _utcnow(),
                "source_event_id": event_id,
                "severity": severity,
            },
        }
        self.supabase.table("operations_agent_observations").insert(observation_row).execute()

        pattern_count = 0
        if event_type in {
            "DATA_INCOMPLETE",
            "IMPORT_FAILED",
            "SALES_IMPORT_FAILED",
            "UNUSUAL_DROP",
            "ZERO_ACTIVITY",
        }:
            self._touch_pattern(event_type, event)
            pattern_count = 1

        # The claim-token predicate is essential: if the same event was requeued
        # during processing, this older owner cannot overwrite the newer claim.
        (
            self.supabase.table("operations_events")
            .update(
                {
                    "processing_status": "PROCESSED",
                    "processed_at": _utcnow(),
                    "processing_error": None,
                }
            )
            .eq("id", event_id)
            .eq("claim_token", event.get("claim_token"))
            .execute()
        )
        return {"observations": 1, "patterns": pattern_count}

    def _touch_pattern(self, pattern_type: str, event: dict[str, Any]) -> None:
        mall_id, local_id = event.get("mall_id"), event.get("local_id")
        query = (
            self.supabase.table("operational_patterns")
            .select("id,occurrences,first_seen")
            .eq("mall_id", mall_id)
            .eq("pattern_type", pattern_type)
        )
        query = query.eq("local_id", local_id) if local_id else query.is_("local_id", "null")
        existing = getattr(query.maybe_single().execute(), "data", None)
        now = _utcnow()
        if existing:
            (
                self.supabase.table("operational_patterns")
                .update(
                    {
                        "occurrences": int(existing.get("occurrences") or 0) + 1,
                        "last_seen": now,
                        "confidence": min(
                            0.99, 0.5 + int(existing.get("occurrences") or 0) * 0.05
                        ),
                        "status": "ACTIVE",
                    }
                )
                .eq("id", existing["id"])
                .execute()
            )
            return
        self.supabase.table("operational_patterns").insert(
            {
                "mall_id": mall_id,
                "local_id": local_id,
                "pattern_type": pattern_type,
                "pattern_name": f"Recurrencia {pattern_type}",
                "description": "Comportamiento recurrente detectado por eventos operativos.",
                "occurrences": 1,
                "first_seen": now,
                "last_seen": now,
                "confidence": 0.5,
                "status": "ACTIVE",
                "metadata": {"rule_version": "operations-pattern-v1"},
            }
        ).execute()

    @staticmethod
    def _safe_metrics(payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "observed_value",
            "expected_value",
            "absolute_difference",
            "percentage_difference",
            "coverage",
            "records_processed",
            "missing_locations",
        }
        return {key: payload[key] for key in allowed if key in payload}

    @staticmethod
    def _deterministic_observation(event_type: str, payload: dict[str, Any]) -> str:
        if event_type == "DATA_INCOMPLETE":
            missing = payload.get("missing_locations")
            suffix = f" porque {missing} locales no han reportado" if missing else ""
            return f"El resultado está incompleto{suffix}."
        if event_type in {"IMPORT_FAILED", "SALES_IMPORT_FAILED"}:
            return "Una importación fallida puede afectar la cobertura del período."
        if event_type == "UNUSUAL_DROP":
            percent = abs(float(payload.get("percentage_difference") or 0))
            return f"Las ventas están {percent:.1f}% por debajo del período comparable."
        if event_type == "FORECAST_LOW_CONFIDENCE":
            return "La proyección tiene confianza baja por información insuficiente."
        return f"Se registró el evento operativo {event_type}."

    @staticmethod
    def _deterministic_conclusion(event_type: str) -> str:
        if event_type in {"DATA_INCOMPLETE", "IMPORT_FAILED", "SALES_IMPORT_FAILED"}:
            return "La calidad debe validarse antes de emitir una conclusión comercial."
        return "La observación se deriva de métricas estructuradas y reglas explicables."

    @staticmethod
    def _deterministic_recommendation(event_type: str) -> str:
        if event_type in {"DATA_INCOMPLETE", "IMPORT_FAILED", "SALES_IMPORT_FAILED"}:
            return "Revisar cargas pendientes y actualizar agregados antes de evaluar ventas."
        return "Revisar la evidencia y marcar el hallazgo según corresponda."

