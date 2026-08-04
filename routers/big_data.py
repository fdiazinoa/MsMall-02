"""Authenticated Big Data read contracts. All analytical reads use aggregate RPCs."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from supabase import create_client

from services.big_data_phase_one_service import BigDataPhaseOneService
from services.big_data_phase_two_service import BigDataPhaseTwoService
from services.big_data_phase_three_service import BigDataPhaseThreeService
from services.big_data_phase_three_b_service import BigDataPhaseThreeBService
from services.big_data_sprint2_service import BigDataSprint2Service

router = APIRouter(prefix="/api/v1/big-data", tags=["Big Data"])
security = HTTPBearer()
_url = os.getenv("SUPABASE_URL")
_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
db = create_client(_url, _key) if _url and _key else None
_system_admins = {email.strip().lower() for email in os.getenv("SYSTEM_ADMIN_EMAILS", "").split(",") if email.strip()}


async def current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not db:
        raise HTTPException(500, "Supabase no configurado")
    try:
        auth = db.auth.get_user(credentials.credentials)
        user = auth.user
        if not user:
            raise ValueError("missing user")
        return {"id": user.id, "email": (getattr(user, "email", "") or "").lower()}
    except Exception as exc:
        raise HTTPException(401, "Autenticación inválida") from exc


def _date_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(422, "El rango de fechas es inválido")
    if (end_date - start_date).days > 366:
        raise HTTPException(422, "El rango máximo es 366 días")


def _authorize(mall_id: str, user: dict) -> None:
    if user["email"] in _system_admins:
        return
    response = db.rpc("validate_mall_access", {"p_current_user": user["id"], "requested_mall_id": mall_id}).execute()
    if response.data is not True:
        raise HTTPException(403, "No tienes acceso a este mall")


def _require_core(mall_id: str) -> None:
    enabled = db.rpc("is_mall_feature_enabled", {"requested_mall_id": mall_id, "requested_feature": "BIG_DATA_CORE"}).execute().data
    if enabled is not True:
        raise HTTPException(403, "Big Data no está activado para este mall")


def _require_feature(mall_id: str, feature: str) -> None:
    _require_core(mall_id)
    enabled = db.rpc(
        "is_mall_feature_enabled",
        {"requested_mall_id": mall_id, "requested_feature": feature},
    ).execute().data
    if enabled is not True:
        raise HTTPException(403, f"{feature} no está activado para este mall")


def _context(mall_id: str, start_date: date, end_date: date, user: dict) -> None:
    _date_range(start_date, end_date)
    _authorize(mall_id, user)
    _require_core(mall_id)


def _rpc(name: str, mall_id: str, start_date: date, end_date: date) -> list[dict]:
    return db.rpc(name, {"p_mall_id": mall_id, "p_start_date": start_date.isoformat(), "p_end_date": end_date.isoformat()}).execute().data or []


class FindingAction(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=1000)


class FindingComment(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)


class CalendarEventPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    event_type: Literal[
        "PROMOTION", "HALLWAY_SALE", "MALL_ACTIVITY", "HOLIDAY", "OTHER"
    ]
    start_date: date
    end_date: date
    expected_impact: Literal["UP", "DOWN", "NEUTRAL"] = "UP"
    notes: Optional[str] = Field(default=None, max_length=1000)


class AnomalySnapshotPayload(BaseModel):
    direction: Literal["UP", "DOWN"]
    observed_sales: float
    expected_sales: float
    impact: float
    deviation_percent: float
    confidence: float = Field(ge=0, le=1)
    model_version: str = Field(min_length=2, max_length=120)


class AnomalyReviewPayload(BaseModel):
    status: Literal["IN_REVIEW", "EXPLAINED", "DISMISSED"]
    cause_type: Literal[
        "UNKNOWN",
        "COMMERCIAL_EVENT",
        "DATA_IMPORT",
        "STORE_ACTIVITY",
        "OPERATIONS",
        "EXTERNAL_FACTOR",
        "DATA_CORRECTION",
        "FALSE_POSITIVE",
        "OTHER",
    ]
    explanation: str = Field(min_length=5, max_length=2000)
    evidence: Optional[str] = Field(default=None, min_length=2, max_length=2000)
    owner_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    snapshot: AnomalySnapshotPayload


class ScenarioActionPayload(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    owner_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    due_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class ScenarioPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    scenario_type: Literal[
        "PROMOTION",
        "HALLWAY_SALE",
        "MALL_ACTIVITY",
        "HOLIDAY",
        "EXTENDED_HOURS",
        "OTHER",
    ]
    start_date: date
    end_date: date
    adjustment_percent: float = Field(ge=-60, le=80)
    notes: Optional[str] = Field(default=None, max_length=2000)


class ScenarioCreatePayload(ScenarioPayload):
    actions: list[ScenarioActionPayload] = Field(default_factory=list, max_length=20)


class ScenarioStatusPayload(BaseModel):
    status: Literal["APPROVED", "ACTIVE", "COMPLETED", "CANCELLED"]


class ScenarioActionStatusPayload(BaseModel):
    status: Literal["PENDING", "IN_PROGRESS", "DONE", "CANCELLED"]


def _require_big_data_manager(mall_id: str, user: dict) -> None:
    _authorize(mall_id, user)
    if user["email"] in _system_admins:
        return
    profile = (
        db.table("profiles")
        .select("role")
        .eq("id", user["id"])
        .maybe_single()
        .execute()
        .data
        or {}
    )
    if str(profile.get("role") or "").lower() not in {
        "admin",
        "administrador",
        "it",
        "tic",
    }:
        raise HTTPException(
            403, "Esta acción de Big Data requiere rol administrador o IT"
        )


@router.get("/summary")
async def summary(mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    current = (_rpc("big_data_mall_summary", mall_id, start_date, end_date) or [{}])[0]
    days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous = (_rpc("big_data_mall_summary", mall_id, previous_end - timedelta(days=days - 1), previous_end) or [{}])[0]
    current_net, previous_net = float(current.get("sales_net") or 0), float(previous.get("sales_net") or 0)
    variation = ((current_net - previous_net) / previous_net * 100) if previous_net else (100 if current_net else 0)
    return {"mall_id": mall_id, "start_date": start_date, "end_date": end_date, "current": current,
            "previous": previous, "variation_percent": variation, "updated_at": current.get("updated_at")}


@router.get("/daily-evolution")
async def daily_evolution(mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    return {"data": _rpc("big_data_daily_evolution", mall_id, start_date, end_date), "updated_at": None}


@router.get("/categories")
async def categories(mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    rows = _rpc("big_data_category_distribution", mall_id, start_date, end_date)
    total = sum(float(row.get("sales_net") or 0) for row in rows)
    return {"data": [{**row, "share_percent": (float(row.get("sales_net") or 0) / total * 100 if total else 0)} for row in rows]}


@router.get("/ranking")
async def ranking(mall_id: str, start_date: date, end_date: date, limit: int = Query(20, ge=1, le=100), user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    rows = db.table("big_data_daily_aggregates").select("local_id,sales_net,transaction_count,updated_at,locales(nombre)").eq("mall_id", mall_id).eq("grain", "local").gte("period_date", start_date.isoformat()).lte("period_date", end_date.isoformat()).execute().data or []
    aggregate: dict[str, dict] = {}
    for row in rows:
        item = aggregate.setdefault(row["local_id"], {"local_id": row["local_id"], "name": (row.get("locales") or {}).get("nombre", "Local"), "sales_net": 0, "transactions": 0})
        item["sales_net"] += float(row.get("sales_net") or 0); item["transactions"] += int(row.get("transaction_count") or 0)
    data = sorted(aggregate.values(), key=lambda row: row["sales_net"], reverse=True)[:limit]
    return {"data": [{**row, "ticket_average": row["sales_net"] / row["transactions"] if row["transactions"] else 0} for row in data]}


@router.get("/quality")
async def quality(mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    # Supabase's maybe_single() returns None when the mall has not been processed
    # yet. That is an expected initial state, not an API failure.
    watermark_response = db.table("big_data_watermarks").select("*").eq("mall_id", mall_id).maybe_single().execute()
    watermark = getattr(watermark_response, "data", None) or {}
    logs = db.table("logs_carga").select("estado").eq("mall_id", mall_id).gte("fecha_hora", start_date.isoformat()).lte("fecha_hora", (end_date + timedelta(days=1)).isoformat()).execute().data or []
    expected = (end_date - start_date).days + 1
    present = _rpc("big_data_daily_evolution", mall_id, start_date, end_date)
    return {"last_analytics_update": watermark.get("last_successful_refresh_at"), "last_sale_processed": watermark.get("last_processed_sale_date"),
            "coverage_percent": len(present) / expected * 100 if expected else 0, "days_incomplete": max(expected - len(present), 0),
            "failed_imports": sum(1 for log in logs if str(log.get("estado")).lower() == "error"), "status": "updated" if watermark else "pending"}


@router.get("/intelligence/phase-one")
async def phase_one_intelligence(
    mall_id: str,
    start_date: date,
    end_date: date,
    user: dict = Depends(current_user),
):
    """Calendar, seasonality, explainable anomalies and data confidence."""
    _context(mall_id, start_date, end_date, user)
    try:
        return BigDataPhaseOneService(db).intelligence(
            mall_id, start_date, end_date
        )
    except Exception as exc:
        message = str(exc).lower()
        if "big_data_anomaly_reviews" in message and (
            "does not exist" in message
            or "schema cache" in message
            or "permission denied" in message
        ):
            raise HTTPException(
                503,
                "La base de datos no está actualizada: aplique la migración "
                "big_data_anomaly_reviews.",
            ) from exc
        raise


@router.get("/intelligence/phase-one/calendar/{target_date}/stores")
async def phase_one_calendar_day_stores(
    target_date: date,
    mall_id: str,
    user: dict = Depends(current_user),
):
    """Store composition and historical comparison for one calendar day."""
    _authorize(mall_id, user)
    _require_core(mall_id)
    if target_date > date.today():
        raise HTTPException(422, "No se puede analizar una fecha futura.")
    return BigDataPhaseOneService(db).calendar_day_breakdown(
        mall_id, target_date
    )


@router.put("/intelligence/phase-one/anomalies/{anomaly_date}/review")
async def upsert_phase_one_anomaly_review(
    anomaly_date: date,
    mall_id: str,
    payload: AnomalyReviewPayload,
    user: dict = Depends(current_user),
):
    """Persist the human investigation without requiring a calendar event."""
    _require_big_data_manager(mall_id, user)
    _require_core(mall_id)
    if anomaly_date > date.today():
        raise HTTPException(422, "No se puede investigar una fecha futura.")
    if (
        payload.status in {"EXPLAINED", "DISMISSED"}
        and payload.cause_type == "UNKNOWN"
    ):
        raise HTTPException(
            422,
            "Seleccione una causa antes de cerrar la investigación.",
        )

    now = datetime.now(timezone.utc).isoformat()
    values = {
        "status": payload.status,
        "cause_type": payload.cause_type,
        "explanation": payload.explanation.strip(),
        "evidence": payload.evidence.strip() if payload.evidence else None,
        "owner_name": payload.owner_name.strip() if payload.owner_name else None,
        "anomaly_snapshot": payload.snapshot.dict(),
        "updated_by": user["id"],
        "updated_at": now,
        "resolved_at": (
            now if payload.status in {"EXPLAINED", "DISMISSED"} else None
        ),
    }
    try:
        current = (
            db.table("big_data_anomaly_reviews")
            .select("id")
            .eq("mall_id", mall_id)
            .eq("anomaly_date", anomaly_date.isoformat())
            .maybe_single()
            .execute()
            .data
        )
        if current:
            rows = (
                db.table("big_data_anomaly_reviews")
                .update(values)
                .eq("id", current["id"])
                .eq("mall_id", mall_id)
                .execute()
                .data
                or []
            )
        else:
            rows = (
                db.table("big_data_anomaly_reviews")
                .insert(
                    {
                        **values,
                        "mall_id": mall_id,
                        "anomaly_date": anomaly_date.isoformat(),
                        "created_by": user["id"],
                    }
                )
                .execute()
                .data
                or []
            )
        if not rows:
            raise RuntimeError("No se pudo guardar la investigación.")
        return rows[0]
    except Exception as exc:
        message = str(exc).lower()
        if "big_data_anomaly_reviews" in message and (
            "does not exist" in message
            or "schema cache" in message
            or "permission denied" in message
        ):
            raise HTTPException(
                503,
                "La base de datos no está actualizada: aplique la migración "
                "big_data_anomaly_reviews.",
            ) from exc
        raise


@router.get("/intelligence/phase-two/stores/{local_id}")
async def phase_two_store_diagnostic(
    local_id: str,
    mall_id: str,
    start_date: date,
    end_date: date,
    target_date: date,
    user: dict = Depends(current_user),
):
    """Explain a local contribution with peers and import evidence."""
    _context(mall_id, start_date, end_date, user)
    analysis_end = min(end_date, date.today())
    if target_date < start_date or target_date > analysis_end:
        raise HTTPException(
            422, "La fecha de diagnóstico debe pertenecer al período analizado"
        )
    diagnostic = BigDataPhaseTwoService(db).diagnostic(
        mall_id, local_id, start_date, end_date, target_date
    )
    if not diagnostic:
        raise HTTPException(404, "Local no encontrado en el mall seleccionado")
    return diagnostic


@router.post("/calendar-events")
async def create_calendar_event(
    mall_id: str,
    payload: CalendarEventPayload,
    user: dict = Depends(current_user),
):
    """Register mall context so known events are not reported as anomalies."""
    _require_big_data_manager(mall_id, user)
    _require_core(mall_id)
    if payload.end_date < payload.start_date:
        raise HTTPException(422, "La fecha final no puede ser anterior a la inicial")
    if (payload.end_date - payload.start_date).days > 366:
        raise HTTPException(422, "Un evento no puede superar 367 días")
    row = {
        "mall_id": mall_id,
        "name": payload.name.strip(),
        "event_type": payload.event_type,
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "expected_impact": payload.expected_impact,
        "notes": payload.notes.strip() if payload.notes else None,
        "created_by": user["id"],
    }
    try:
        created = (
            db.table("big_data_calendar_events")
            .insert(row)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        message = str(exc).lower()
        if "big_data_calendar_events" in message and (
            "does not exist" in message or "schema cache" in message
        ):
            raise HTTPException(
                503,
                "La base de datos no está actualizada: aplique la migración "
                "big_data_calendar_events.",
            ) from exc
        if "duplicate" in message or "23505" in message:
            raise HTTPException(
                409, "Ya existe un evento activo con ese nombre y rango."
            ) from exc
        raise
    if not created:
        raise HTTPException(500, "No se pudo registrar el contexto comercial")
    return created[0]


@router.delete("/calendar-events/{event_id}")
async def delete_calendar_event(
    event_id: str,
    mall_id: str,
    user: dict = Depends(current_user),
):
    """Soft-delete an event while preserving its audit trail."""
    _require_big_data_manager(mall_id, user)
    _require_core(mall_id)
    result = (
        db.table("big_data_calendar_events")
        .update(
            {
                "active": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", event_id)
        .eq("mall_id", mall_id)
        .eq("active", True)
        .execute()
        .data
        or []
    )
    if not result:
        raise HTTPException(404, "Evento no encontrado en el mall seleccionado")
    return {"status": "deleted", "id": event_id}


@router.get("/stores/{local_id}/profile")
async def store_profile(local_id: str, mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    local = db.table("locales").select("id,nombre,rubro,mall_id,local_commercial_classifications(sector_id,category_id,subcategory_id)").eq("id", local_id).eq("mall_id", mall_id).maybe_single().execute().data
    if not local:
        raise HTTPException(404, "Local no encontrado en el mall seleccionado")
    rows = db.table("big_data_daily_aggregates").select("period_date,sales_net,transaction_count,updated_at").eq("mall_id", mall_id).eq("grain", "local").eq("local_id", local_id).gte("period_date", start_date.isoformat()).lte("period_date", end_date.isoformat()).execute().data or []
    net, transactions = sum(float(r.get("sales_net") or 0) for r in rows), sum(int(r.get("transaction_count") or 0) for r in rows)
    logs = db.table("logs_carga").select("fecha_hora,estado,mensaje").eq("local_id", local_id).order("fecha_hora", desc=True).limit(5).execute().data or []
    return {"local": local, "period": {"sales_net": net, "transactions": transactions, "ticket_average": net / transactions if transactions else 0,
             "last_sale_received": max((r.get("period_date") for r in rows), default=None), "daily_evolution": rows}, "imports": logs}


@router.get("/stores/{local_id}/category-benchmark")
async def category_benchmark(local_id: str, mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    # An unclassified local is expected during the Sprint 2 rollout. Supabase's
    # maybe_single() returns None in that case, so treat it as insufficient
    # benchmark data instead of turning the whole Profile 360 request into a 500.
    classification_response = db.table("local_commercial_classifications").select("category_id").eq("local_id", local_id).maybe_single().execute()
    classifications = getattr(classification_response, "data", None) or {}
    category_id = classifications.get("category_id")
    if not category_id:
        return {"status": "insufficient_data", "reason": "El local no tiene categoría homologada."}
    category_rows = db.table("big_data_daily_aggregates").select("local_id,sales_net").eq("mall_id", mall_id).eq("grain", "local").gte("period_date", start_date.isoformat()).lte("period_date", end_date.isoformat()).execute().data or []
    # Category membership is resolved through the local classification, avoiding cross-mall comparisons.
    members = db.table("local_commercial_classifications").select("local_id").eq("category_id", category_id).execute().data or []
    member_ids = {member["local_id"] for member in members}
    totals: dict[str, float] = {}
    for row in category_rows:
        if row.get("local_id") in member_ids:
            totals[row["local_id"]] = totals.get(row["local_id"], 0) + float(row.get("sales_net") or 0)
    values = sorted(totals.values())
    if len(values) < 3 or local_id not in totals:
        return {"status": "insufficient_data", "comparable_stores": len(values)}
    local_value = totals[local_id]
    median = values[len(values)//2] if len(values) % 2 else (values[len(values)//2-1] + values[len(values)//2]) / 2
    rank = sorted(values, reverse=True).index(local_value) + 1
    return {"status": "ok", "comparable_stores": len(values), "local_sales": local_value,
            "category_average": sum(values) / len(values), "category_median": median, "rank": rank,
            "percentile": sum(value <= local_value for value in values) / len(values) * 100,
            "category_share_percent": local_value / sum(values) * 100 if sum(values) else 0}


@router.post("/rebuild")
async def rebuild(mall_id: str, start_date: date, end_date: date, user: dict = Depends(current_user)):
    _context(mall_id, start_date, end_date, user)
    _require_big_data_manager(mall_id, user)
    rows = [{"mall_id": mall_id, "affected_date": (start_date + timedelta(days=offset)).isoformat(), "requested_by": user["id"]} for offset in range((end_date-start_date).days + 1)]
    db.table("big_data_refresh_queue").upsert(rows, on_conflict="mall_id,affected_date").execute()
    return {"status": "queued", "dates": len(rows)}


def _capability_context(mall_id: str, user: dict, feature: str) -> None:
    _authorize(mall_id, user)
    _require_feature(mall_id, feature)


def _raise_scenario_storage_error(exc: Exception) -> None:
    message = str(exc).lower()
    if (
        "big_data_scenarios" in message
        or "big_data_scenario_actions" in message
        or "refresh_big_data_scenario_results" in message
    ):
        if (
            "does not exist" in message
            or "schema cache" in message
            or "permission denied" in message
        ):
            raise HTTPException(
                503,
                "La base de datos no está actualizada: aplique la migración "
                "de escenarios y evaluación de resultados de Big Data.",
            ) from exc
    if "duplicate" in message or "23505" in message:
        raise HTTPException(
            409,
            "Ya existe un escenario abierto con ese nombre y rango.",
        ) from exc
    raise exc


@router.get("/intelligence/phase-three-a/prediction")
async def phase_three_a_prediction(
    mall_id: str,
    start_date: date,
    end_date: date,
    user: dict = Depends(current_user),
):
    """Project the next 7/30/90 days from bounded mall aggregates."""
    _date_range(start_date, end_date)
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    if start_date > date.today():
        raise HTTPException(422, "La historia de predicción no puede iniciar en el futuro")
    return BigDataPhaseThreeService(db).prediction(mall_id, start_date, end_date)


@router.post("/intelligence/phase-three-b/simulate")
async def phase_three_b_simulate(
    mall_id: str,
    history_start: date,
    as_of: date,
    payload: ScenarioPayload,
    user: dict = Depends(current_user),
):
    """Estimate a planning scenario without persisting it."""
    _date_range(history_start, as_of)
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    try:
        return BigDataPhaseThreeBService(db).simulate(
            mall_id=mall_id,
            history_start=history_start,
            as_of=as_of,
            name=payload.name,
            scenario_type=payload.scenario_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            adjustment_percent=payload.adjustment_percent,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/intelligence/phase-three-b/scenarios")
async def phase_three_b_scenarios(
    mall_id: str,
    user: dict = Depends(current_user),
):
    """List the latest mall scenarios and their bounded action plans."""
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    try:
        return BigDataPhaseThreeBService(db).list_scenarios(mall_id)
    except Exception as exc:
        _raise_scenario_storage_error(exc)


@router.post("/intelligence/phase-three-b/scenarios")
async def phase_three_b_create_scenario(
    mall_id: str,
    history_start: date,
    as_of: date,
    payload: ScenarioCreatePayload,
    user: dict = Depends(current_user),
):
    """Persist a reviewed simulation and its initial action plan."""
    _date_range(history_start, as_of)
    _require_big_data_manager(mall_id, user)
    _require_feature(mall_id, "BIG_DATA_FORECAST")
    try:
        return BigDataPhaseThreeBService(db).create_scenario(
            mall_id=mall_id,
            user_id=user["id"],
            history_start=history_start,
            as_of=as_of,
            name=payload.name,
            scenario_type=payload.scenario_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            adjustment_percent=payload.adjustment_percent,
            notes=payload.notes,
            actions=[
                {
                    "title": action.title,
                    "owner_name": action.owner_name,
                    "due_date": action.due_date,
                    "notes": action.notes,
                }
                for action in payload.actions
            ],
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        _raise_scenario_storage_error(exc)


@router.patch("/intelligence/phase-three-b/scenarios/{scenario_id}/status")
async def phase_three_b_update_scenario_status(
    scenario_id: str,
    mall_id: str,
    payload: ScenarioStatusPayload,
    user: dict = Depends(current_user),
):
    """Advance one scenario through its explicit approval workflow."""
    _require_big_data_manager(mall_id, user)
    _require_feature(mall_id, "BIG_DATA_FORECAST")
    try:
        return BigDataPhaseThreeBService(db).update_scenario_status(
            mall_id, scenario_id, payload.status
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        _raise_scenario_storage_error(exc)


@router.delete("/intelligence/phase-three-b/scenarios/{scenario_id}")
async def phase_three_b_delete_scenario(
    scenario_id: str,
    mall_id: str,
    user: dict = Depends(current_user),
):
    """Delete an accidental draft or cancelled scenario."""
    _require_big_data_manager(mall_id, user)
    _require_feature(mall_id, "BIG_DATA_FORECAST")
    try:
        return BigDataPhaseThreeBService(db).delete_scenario(mall_id, scenario_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        _raise_scenario_storage_error(exc)


@router.patch("/intelligence/phase-three-b/actions/{action_id}/status")
async def phase_three_b_update_action_status(
    action_id: str,
    mall_id: str,
    payload: ScenarioActionStatusPayload,
    user: dict = Depends(current_user),
):
    """Track execution of one action without rewriting the scenario snapshot."""
    _require_big_data_manager(mall_id, user)
    _require_feature(mall_id, "BIG_DATA_FORECAST")
    try:
        return BigDataPhaseThreeBService(db).update_action_status(
            mall_id, action_id, payload.status
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        _raise_scenario_storage_error(exc)


def _operational_query(
    table: str,
    mall_id: str,
    *,
    limit: int,
    offset: int,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    local_id: Optional[str] = None,
    item_type: Optional[str] = None,
    source: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    query = db.table(table).select("*", count="exact").eq("mall_id", mall_id)
    if status and table in {"operational_findings", "operational_patterns"}:
        query = query.eq("status", status.upper())
    elif status and table == "operations_events":
        query = query.eq("processing_status", status.upper())
    if severity and table in {"operational_findings", "operations_events"}:
        query = query.eq("severity", severity.upper())
    if local_id:
        query = query.eq("local_id", local_id)
    if item_type:
        type_column = {
            "operational_findings": "type",
            "operations_events": "event_type",
            "operations_agent_observations": "observation_type",
            "operational_patterns": "pattern_type",
        }[table]
        query = query.eq(type_column, item_type)
    if source and table in {"operational_findings", "operations_events"}:
        query = query.eq("source", source)
    order_column = {
        "operational_findings": "detected_at",
        "operations_events": "created_at",
        "operations_agent_observations": "created_at",
        "operational_patterns": "last_seen",
    }[table]
    if start_date:
        query = query.gte(order_column, start_date.isoformat())
    if end_date:
        query = query.lt(order_column, (end_date + timedelta(days=1)).isoformat())
    return query.order(order_column, desc=True).range(offset, offset + limit - 1).execute()


@router.get("/forecast/mall")
async def mall_forecast(
    mall_id: str,
    as_of: Optional[date] = None,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    return BigDataSprint2Service(db).forecast(mall_id, as_of or date.today())


@router.get("/forecast/categories")
async def category_forecasts(
    mall_id: str,
    as_of: Optional[date] = None,
    limit: int = Query(20, ge=1, le=50),
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    as_of = as_of or date.today()
    month_start = as_of.replace(day=1)
    rows = (
        db.table("big_data_daily_aggregates")
        .select("dimension_key,category_id,category_name")
        .eq("mall_id", mall_id)
        .eq("grain", "category")
        .gte("period_date", month_start.isoformat())
        .lte("period_date", as_of.isoformat())
        .limit(1000)
        .execute()
        .data
        or []
    )
    dimensions = list(
        {
            str(row.get("dimension_key")): row
            for row in rows
            if row.get("dimension_key")
        }.values()
    )[:limit]
    service = BigDataSprint2Service(db)
    return {
        "data": [
            {
                **service.forecast(
                    mall_id,
                    as_of,
                    grain="category",
                    dimension_key=str(row["dimension_key"]),
                ),
                "category_id": row.get("category_id"),
                "category_name": row.get("category_name"),
            }
            for row in dimensions
        ]
    }


@router.get("/forecast/stores/{local_id}")
async def store_forecast(
    local_id: str,
    mall_id: str,
    as_of: Optional[date] = None,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    as_of = as_of or date.today()
    local = (
        db.table("locales")
        .select("id")
        .eq("id", local_id)
        .eq("mall_id", mall_id)
        .maybe_single()
        .execute()
        .data
    )
    if not local:
        raise HTTPException(404, "Local no encontrado en el mall seleccionado")
    return BigDataSprint2Service(db).forecast(
        mall_id, as_of, grain="local", dimension_key=local_id
    )


@router.get("/executive-summary")
async def executive_summary(
    mall_id: str,
    start_date: date,
    end_date: date,
    user: dict = Depends(current_user),
):
    _date_range(start_date, end_date)
    _capability_context(mall_id, user, "BIG_DATA_FORECAST")
    return BigDataSprint2Service(db).executive_summary(mall_id, start_date, end_date)


@router.get("/operations/items/{collection}")
async def operations_collection(
    collection: str,
    mall_id: str,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    status: Optional[str] = None,
    severity: Optional[str] = None,
    local_id: Optional[str] = None,
    item_type: Optional[str] = Query(None, alias="type"),
    source: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_OPERATIONS")
    if start_date and end_date:
        _date_range(start_date, end_date)
    tables = {
        "events": "operations_events",
        "findings": "operational_findings",
        "anomalies": "operational_findings",
        "observations": "operations_agent_observations",
        "patterns": "operational_patterns",
    }
    table = tables.get(collection)
    if not table:
        raise HTTPException(404, "Colección operacional no válida")
    if collection == "anomalies":
        item_type = item_type
    response = _operational_query(
        table,
        mall_id,
        limit=limit,
        offset=offset,
        status=status,
        severity=severity,
        local_id=local_id,
        item_type=item_type,
        source="BIG_DATA_ANOMALY" if collection == "anomalies" else source,
        start_date=start_date,
        end_date=end_date,
    )
    data = response.data or []
    return {
        "data": data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": getattr(response, "count", None),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/operations/status")
async def operations_status(mall_id: str, user: dict = Depends(current_user)):
    _capability_context(mall_id, user, "BIG_DATA_OPERATIONS")
    findings = (
        db.table("operational_findings")
        .select("id,severity,status,type,detected_at")
        .eq("mall_id", mall_id)
        .in_("status", ["OPEN", "ACKNOWLEDGED"])
        .limit(1000)
        .execute()
        .data
        or []
    )
    counts: dict[str, int] = {}
    for finding in findings:
        key = str(finding.get("severity") or "INFO")
        counts[key] = counts.get(key, 0) + 1
    return {
        "mall_id": mall_id,
        "open_findings": len(findings),
        "by_severity": counts,
        "data_incomplete": any(row.get("type") == "DATA_INCOMPLETE" for row in findings),
        "updated_at": max(
            (row.get("detected_at") for row in findings if row.get("detected_at")),
            default=None,
        ),
    }


def _finding_action(
    mall_id: str,
    finding_id: str,
    user: dict,
    status: str,
    comment: Optional[str],
) -> dict[str, Any]:
    current = (
        db.table("operational_findings")
        .select("id,status,comments")
        .eq("id", finding_id)
        .eq("mall_id", mall_id)
        .maybe_single()
        .execute()
        .data
    )
    if not current:
        raise HTTPException(404, "Hallazgo no encontrado")
    now = datetime.now(timezone.utc).isoformat()
    comments = list(current.get("comments") or [])
    if comment:
        comments.append({"text": comment, "user_id": user["id"], "created_at": now})
    changes: dict[str, Any] = {"status": status, "updated_at": now, "comments": comments}
    if status == "ACKNOWLEDGED":
        changes.update({"reviewed_at": now, "reviewed_by": user["id"]})
    if status == "RESOLVED":
        changes.update({"resolved_at": now, "resolved_by": user["id"]})
    if status == "OPEN":
        changes.update({"resolved_at": None, "resolved_by": None})
    updated = (
        db.table("operational_findings")
        .update(changes)
        .eq("id", finding_id)
        .eq("mall_id", mall_id)
        .execute()
        .data
        or []
    )
    db.table("operations_events").insert(
        {
            "mall_id": mall_id,
            "event_type": f"FINDING_{status}",
            "source": "BIG_DATA_API",
            "severity": "INFO",
            "processing_status": "PENDING",
            "payload": {
                "finding_id": finding_id,
                "previous_status": current.get("status"),
                "new_status": status,
                "operator_id": user["id"],
                "has_comment": bool(comment),
            },
        }
    ).execute()
    return (updated or [{**current, **changes}])[0]


@router.post("/operations/findings/{finding_id}/review")
async def review_finding(
    finding_id: str,
    mall_id: str,
    action: FindingAction,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_OPERATIONS")
    return _finding_action(mall_id, finding_id, user, "ACKNOWLEDGED", action.comment)


@router.post("/operations/findings/{finding_id}/resolve")
async def resolve_finding(
    finding_id: str,
    mall_id: str,
    action: FindingAction,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_OPERATIONS")
    return _finding_action(mall_id, finding_id, user, "RESOLVED", action.comment)


@router.post("/operations/findings/{finding_id}/reopen")
async def reopen_finding(
    finding_id: str,
    mall_id: str,
    action: FindingAction,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_OPERATIONS")
    return _finding_action(mall_id, finding_id, user, "OPEN", action.comment)


@router.post("/operations/findings/{finding_id}/comments")
async def comment_finding(
    finding_id: str,
    mall_id: str,
    body: FindingComment,
    user: dict = Depends(current_user),
):
    _capability_context(mall_id, user, "BIG_DATA_OPERATIONS")
    current = (
        db.table("operational_findings")
        .select("status")
        .eq("id", finding_id)
        .eq("mall_id", mall_id)
        .maybe_single()
        .execute()
        .data
    )
    if not current:
        raise HTTPException(404, "Hallazgo no encontrado")
    return _finding_action(
        mall_id, finding_id, user, str(current.get("status") or "OPEN"), body.comment
    )


@router.get("/copilot-context")
async def copilot_context(
    mall_id: str,
    start_date: date,
    end_date: date,
    user: dict = Depends(current_user),
):
    _date_range(start_date, end_date)
    _capability_context(mall_id, user, "BIG_DATA_COPILOT")
    context = BigDataSprint2Service(db).executive_summary(mall_id, start_date, end_date)
    db.table("operations_events").insert(
        {
            "mall_id": mall_id,
            "event_type": "COPILOT_BIG_DATA_CONTEXT_ACCESSED",
            "source": "COPILOT",
            "severity": "INFO",
            "processing_status": "PENDING",
            "payload": {
                "user_id": user["id"],
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            },
        }
    ).execute()
    return context
