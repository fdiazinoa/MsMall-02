"""Background-only processing for the Sprint 1 Big Data aggregates."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict


class BigDataAnalyticsService:
    def __init__(self, supabase_client: Any, logger: logging.Logger | None = None):
        self.supabase = supabase_client
        self.logger = logger or logging.getLogger("big-data-worker")

    def process_pending_refreshes(self, limit: int = 50) -> Dict[str, int]:
        """Processes queued dates grouped by mall; safe to retry after a worker failure."""
        result = {"processed": 0, "failed": 0, "malls": 0}
        if not self.supabase or not hasattr(self.supabase, "rpc"):
            return result

        # Claiming is done inside Postgres, not with a read-then-update race.
        # The RPC uses FOR UPDATE SKIP LOCKED and also recovers abandoned claims.
        queued = (
            self.supabase.rpc("claim_big_data_refresh_queue", {"p_limit": limit})
            .execute()
            .data
            or []
        )
        by_mall: Dict[str, list[dict]] = defaultdict(list)
        for item in queued:
            if item.get("mall_id") and item.get("affected_date"):
                by_mall[item["mall_id"]].append(item)

        for mall_id, items in by_mall.items():
            started = time.monotonic()
            try:
                dates = sorted(date.fromisoformat(item["affected_date"]) for item in items)
                self.supabase.rpc("refresh_big_data_aggregates", {
                    "p_mall_id": mall_id,
                    "p_start_date": dates[0].isoformat(),
                    "p_end_date": dates[-1].isoformat(),
                    "p_calculation_version": "v1",
                }).execute()
                for item in items:
                    # An import may have requeued this date while the aggregate
                    # was running. Its token is then cleared, so do not overwrite
                    # newer pending work as completed.
                    self.supabase.table("big_data_refresh_queue").update({
                        "status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(), "last_error": None,
                    }).eq("id", item["id"]).eq("claim_token", item["claim_token"]).execute()
                self.supabase.table("big_data_refresh_runs").insert({
                    "mall_id": mall_id, "start_date": dates[0].isoformat(), "end_date": dates[-1].isoformat(),
                    "status": "completed", "records_processed": len(items),
                    "duration_ms": int((time.monotonic() - started) * 1000), "completed_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                result["processed"] += len(items)
                result["malls"] += 1
            except Exception as exc:  # Keep each mall independently retryable.
                self.logger.exception("Big Data refresh failed for mall %s", mall_id)
                for item in items:
                    self.supabase.table("big_data_refresh_queue").update({
                        "status": "failed", "last_error": str(exc)[:1000],
                    }).eq("id", item["id"]).eq("claim_token", item["claim_token"]).execute()
                result["failed"] += len(items)
        return result
