"""Authenticated Big Data read contracts. All analytical reads use aggregate RPCs."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

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
    response = db.rpc("validate_mall_access", {"current_user": user["id"], "requested_mall_id": mall_id}).execute()
    if response.data is not True:
        raise HTTPException(403, "No tienes acceso a este mall")


def _require_core(mall_id: str) -> None:
    enabled = db.rpc("is_mall_feature_enabled", {"requested_mall_id": mall_id, "requested_feature": "BIG_DATA_CORE"}).execute().data
    if enabled is not True:
        raise HTTPException(403, "Big Data no está activado para este mall")


def _context(mall_id: str, start_date: date, end_date: date, user: dict) -> None:
    _date_range(start_date, end_date)
    _authorize(mall_id, user)
    _require_core(mall_id)


def _rpc(name: str, mall_id: str, start_date: date, end_date: date) -> list[dict]:
    return db.rpc(name, {"p_mall_id": mall_id, "p_start_date": start_date.isoformat(), "p_end_date": end_date.isoformat()}).execute().data or []


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
    watermark = db.table("big_data_watermarks").select("*").eq("mall_id", mall_id).maybe_single().execute().data or {}
    logs = db.table("logs_carga").select("estado").eq("mall_id", mall_id).gte("fecha_hora", start_date.isoformat()).lte("fecha_hora", (end_date + timedelta(days=1)).isoformat()).execute().data or []
    expected = (end_date - start_date).days + 1
    present = _rpc("big_data_daily_evolution", mall_id, start_date, end_date)
    return {"last_analytics_update": watermark.get("last_successful_refresh_at"), "last_sale_processed": watermark.get("last_processed_sale_date"),
            "coverage_percent": len(present) / expected * 100 if expected else 0, "days_incomplete": max(expected - len(present), 0),
            "failed_imports": sum(1 for log in logs if str(log.get("estado")).lower() == "error"), "status": "updated" if watermark else "pending"}


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
    classifications = db.table("local_commercial_classifications").select("category_id").eq("local_id", local_id).maybe_single().execute().data or {}
    category_id = classifications.get("category_id")
    if not category_id:
        return {"status": "insufficient_data", "reason": "El local no tiene categoría homologada."}
    category_rows = db.table("big_data_daily_aggregates").select("sales_net").eq("mall_id", mall_id).eq("grain", "local").gte("period_date", start_date.isoformat()).lte("period_date", end_date.isoformat()).execute().data or []
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
    profile = db.table("profiles").select("role").eq("id", user["id"]).maybe_single().execute().data or {}
    if user["email"] not in _system_admins and str(profile.get("role") or "").lower() not in {"admin", "administrador", "it", "tic"}:
        raise HTTPException(403, "La reconstrucción requiere rol administrador o IT")
    rows = [{"mall_id": mall_id, "affected_date": (start_date + timedelta(days=offset)).isoformat(), "requested_by": user["id"]} for offset in range((end_date-start_date).days + 1)]
    db.table("big_data_refresh_queue").upsert(rows, on_conflict="mall_id,affected_date").execute()
    return {"status": "queued", "dates": len(rows)}
