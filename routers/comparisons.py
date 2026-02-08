from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import os
from supabase import create_client, Client

router = APIRouter(prefix="/api/v1/comparisons", tags=["Comparisons"])
logger = logging.getLogger("msmall-api")

# Supabase Client setup for router context
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase_client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except:
        pass

def get_supabase():
    if not supabase_client:
        raise HTTPException(status_code=500, detail="Database connection not available")
    return supabase_client

class ComparisonPeriod(BaseModel):
    label: str
    inicio: str
    fin: str
    datos: List[Dict[str, Any]]
    total_neto: float
    total_bruto: float
    transacciones: int
    ticket_promedio: float

class ComparisonResponse(BaseModel):
    mall_id: str
    timezone: str
    hoy_local: str
    periodo_actual: ComparisonPeriod
    periodo_anterior: ComparisonPeriod
    variacion_neto_porc: float
    tipo_comparativa: str # 'MoM' or 'YoY'

def calculate_periods(tipo: str, mall_tz: str):
    """
    Calcula los rangos de fechas basados en el timezone del mall.
    """
    tz = ZoneInfo(mall_tz)
    now = datetime.now(tz)
    hoy = now.date()
    
    if tipo == 'WoM' or tipo == 'WoW':
        # Semana Actual: Lunes de esta semana hasta hoy
        actual_inicio = hoy - timedelta(days=hoy.weekday())
        actual_fin = hoy
        
        # Semana Anterior
        prev_inicio = actual_inicio - timedelta(days=7)
        prev_fin = hoy - timedelta(days=7)
        
    elif tipo == 'YoY':
        # Periodo Actual: Inicio de mes hasta hoy
        actual_inicio = hoy.replace(day=1)
        actual_fin = hoy
        # Mismo mes año anterior
        try:
            prev_inicio = actual_inicio.replace(year=actual_inicio.year - 1)
            prev_fin = hoy.replace(year=hoy.year - 1)
        except ValueError: # Leap year case (Feb 29)
            prev_inicio = actual_inicio.replace(year=actual_inicio.year - 1)
            prev_fin = hoy.replace(year=hoy.year - 1, day=28)
            
    else: # MoM (Default)
        # Periodo Actual: Inicio de mes hasta hoy
        actual_inicio = hoy.replace(day=1)
        actual_fin = hoy
        # Mes Anterior: mismo rango de días en el mes previo
        first_of_this_month = actual_inicio
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        prev_inicio = last_of_prev_month.replace(day=1)
        
        try:
            prev_fin = prev_inicio.replace(day=hoy.day)
        except ValueError:
            prev_fin = last_of_prev_month

    return actual_inicio, actual_fin, prev_inicio, prev_fin

@router.get("/period-comparison", response_model=ComparisonResponse)
async def get_period_comparison(
    tipo: str = "MoM", # MoM, YoY, WoW
    x_mall_id: Optional[str] = Header(None, alias="X-Mall-Id")
):
    if not x_mall_id:
        raise HTTPException(status_code=400, detail="X-Mall-Id header is required")

    db = get_supabase()
    
    # 1. Obtener timezone del mall
    mall_tz = 'America/Santo_Domingo' # Default
    try:
        mall_res = db.table("malls").select("timezone").eq("id", x_mall_id).execute()
        if mall_res.data and 'timezone' in mall_res.data[0]:
            mall_tz = mall_res.data[0]['timezone'] or mall_tz
    except Exception as e:
        logger.warning(f"Error fetching timezone for mall {x_mall_id}, using default: {e}")
        pass
    
    # 2. Calcular fechas
    actual_inicio, actual_fin, prev_inicio, prev_fin = calculate_periods(tipo, mall_tz)
    
    # 3. Consultar datos via RPC (Actual)
    res_actual = db.rpc("get_metricas_periodo", {
        "mall_id_param": x_mall_id,
        "fecha_inicio_param": actual_inicio.isoformat(),
        "fecha_fin_param": actual_fin.isoformat()
    }).execute()
    
    data_actual = res_actual.data or []
    
    # 4. Consultar datos via RPC (Anterior)
    res_prev = db.rpc("get_metricas_periodo", {
        "mall_id_param": x_mall_id,
        "fecha_inicio_param": prev_inicio.isoformat(),
        "fecha_fin_param": prev_fin.isoformat()
    }).execute()
    
    data_prev = res_prev.data or []
    
    # 5. Totales
    total_neto_act = sum(item['out_total_neto'] for item in data_actual)
    total_bruto_act = sum(item['out_total_bruto'] for item in data_actual)
    transact_act = sum(item['out_transacciones'] for item in data_actual)
    tkt_act = total_neto_act / transact_act if transact_act > 0 else 0
    
    total_neto_prev = sum(item['out_total_neto'] for item in data_prev)
    total_bruto_prev = sum(item['out_total_bruto'] for item in data_prev)
    transact_prev = sum(item['out_transacciones'] for item in data_prev)
    tkt_prev = total_neto_prev / transact_prev if transact_prev > 0 else 0
    
    # 6. Variación
    if total_neto_prev == 0:
        variacion = 100.0 if total_neto_act > 0 else 0.0
    else:
        variacion = ((total_neto_act - total_neto_prev) / total_neto_prev) * 100.0

    # Labels dinámicos
    if tipo == 'WoW':
        label_act = "Semana Actual"
        label_prev = "Semana Anterior"
    elif tipo == 'YoY':
        label_act = "Año Actual"
        label_prev = "Año Anterior"
    else:
        label_act = "Mes Actual"
        label_prev = "Mes Anterior"

    return {
        "mall_id": x_mall_id,
        "timezone": mall_tz,
        "hoy_local": datetime.now(ZoneInfo(mall_tz)).isoformat(),
        "periodo_actual": {
            "label": label_act,
            "inicio": actual_inicio.isoformat(),
            "fin": actual_fin.isoformat(),
            "datos": data_actual,
            "total_neto": float(total_neto_act),
            "total_bruto": float(total_bruto_act),
            "transacciones": int(transact_act),
            "ticket_promedio": float(tkt_act)
        },
        "periodo_anterior": {
            "label": label_prev,
            "inicio": prev_inicio.isoformat(),
            "fin": prev_fin.isoformat(),
            "datos": data_prev,
            "total_neto": float(total_neto_prev),
            "total_bruto": float(total_bruto_prev),
            "transacciones": int(transact_prev),
            "ticket_promedio": float(tkt_prev)
        },
        "variacion_neto_porc": float(variacion),
        "tipo_comparativa": tipo
    }
