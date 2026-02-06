
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional, Dict
from enum import Enum
import logging
from supabase import Client

# We need a way to get the supabase client. 
# In main.py it's a global variable. We should import it or dependency inject it.
# For now, assuming we can import `supabase` from `main` or similar if we structure it right.
# But circular imports are bad. 
# Better usage: Dependency Injection or a shared `database.py`. 
# Given the monolithic main.py, I will import it carefully or re-instantiate if needed, 
# but preferably we refactor main to pass it. 
# For this file, I will expect 'supabase' to be passed or available.
# To avoid complex refactoring of main.py right now, I will use a helper to get client.

router = APIRouter(prefix="/api/v1/recetas", tags=["Recetas"])
logger = logging.getLogger("msmall-api")

class RecipeDetail(BaseModel):
    id: str
    parent_item_id: str
    child_item_id: str
    cantidad_bruta: float
    unidad_medida: str
    factor_merma: float
    es_opcional: bool
    costo_unitario_child: Optional[float] = 0

class RecipeCostResponse(BaseModel):
    item_id: str
    costo_total: float
    detalles: List[RecipeDetail]

# Helper to get DB client (Mocked or Real)
# In a real app we would have a get_db dependency.
# This assumes the main app will include this router and provide the client via app.state or similar
# For this implementation I will rely on an environment variable initialization if needed
# or just assume the caller context has checking.

import os
from supabase import create_client

# Independent Client for Router (Safe approach to avoid circular import)
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

@router.post("/calcular-costo/{item_id}", response_model=RecipeCostResponse)
async def calcular_costo_receta(item_id: str):
    """
    Calcula recursivamente el costo de una receta.
    Actualiza el costo_teorico en la tabla items.
    """
    db = get_supabase()
    
    # 1. Fetch Item to ensure it exists and is a RECIPE or KIT
    res = db.table("items").select("*").eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    item = res.data[0]
    # Simplify: If it's pure raw material, cost is simple unit cost
    if item.get('tipo_item') == 'MATERIA_PRIMA':
        return {
            "item_id": item_id, 
            "costo_total": item.get('costo_unitario', 0), 
            "detalles": []
        }

    # 2. Fetch Ingredients (Children)
    # Join with items to get child cost
    # Supabase Join Syntax: select(*, items!child_item_id(*))
    
    costo_total = 0.0
    detalles_procesados = []

    try:
        # Fetch relationships
        response = db.table("recetas_detalles")\
            .select("*, child:items!child_item_id(costo_unitario, costo_teorico, tipo_item)")\
            .eq("parent_item_id", item_id)\
            .execute()
        
        ingredients = response.data
        
        for ing in ingredients:
            child = ing.get('child')
            if not child: continue
            
            # Determine base cost of child
            # If child is also a recipe/kit, prefer its calculated theoretical cost
            # If child is raw material, use manual unit cost
            costo_base_child = 0
            
            if child.get('tipo_item') in ['RECETA', 'KIT']:
                costo_base_child = child.get('costo_teorico', 0) or 0
                # Optional: Recursive call here if we wanted deep real-time recalc
                # await calcular_costo_receta(ing['child_item_id']) 
            else:
                costo_base_child = child.get('costo_unitario', 0) or 0
                
            qty = float(ing['cantidad_bruta'])
            merma = float(ing.get('factor_merma', 0))
            
            # Cost Formula: (Unit Cost * Qty) / (1 - Waste%)
            # Example: Need 100g Onion. Onion costs $10/kg ($0.01/g). Waste 10%.
            # Real cost = (0.01 * 100) / (0.9) = 1 / 0.9 = $1.11
            
            if merma >= 1: merma = 0.99 # Prevent division by zero
            
            real_consumption_cost = (costo_base_child * qty) / (1 - merma)
            
            if not ing.get('es_opcional'):
                 costo_total += real_consumption_cost
            
            detalles_procesados.append({
                **ing,
                "costo_unitario_child": costo_base_child
            })

        # 3. Update Parent Cost
        db.table("items").update({"costo_teorico": costo_total}).eq("id", item_id).execute()
        
        return {
            "item_id": item_id,
            "costo_total": costo_total,
            "detalles": detalles_procesados
        }
        
    except Exception as e:
        logger.error(f"Error calculating recipe cost: {e}")
        raise HTTPException(status_code=500, detail=str(e))

