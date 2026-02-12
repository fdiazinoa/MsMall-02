from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from datetime import datetime
from supabase import create_client, Client
import os

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Tools"])
logger = logging.getLogger("msmall-api")
PRIVILEGED_ROLES = {"ADMIN", "IT", "TIC", "SUPERADMIN", "SUPER_ADMIN", "ADMINISTRADOR"}

# Supabase Client setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Optional[Client] = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client in admin_tools: {e}")

def get_supabase() -> Client:
    if not supabase:
        raise HTTPException(
            status_code=500,
            detail="Supabase no configurado: define SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY",
        )
    return supabase

security = HTTPBearer()

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        db = get_supabase()
        user = db.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error in admin_tools: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

class PurgeRequest(BaseModel):
    local_id: str
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    confirmacion: str

def normalize_role(role: Optional[str]) -> str:
    return (role or "").strip().upper().replace(" ", "_").replace("-", "_")

def has_privileged_role(role: Optional[str]) -> bool:
    return normalize_role(role) in PRIVILEGED_ROLES

async def check_admin_access(user_id: str, mall_id: str):
    """
    Checks if the user has privileged role either:
    - explicitly for the current mall (usuarios_malls), or
    - globally in profiles.role (fallback).
    """
    try:
        db = get_supabase()
        logger.info(f"Checking privileged access for user={user_id}, mall={mall_id}")
        res = db.table("usuarios_malls") \
            .select("rol") \
            .eq("usuario_id", user_id) \
            .eq("mall_id", mall_id) \
            .execute()

        rows = res.data or []
        if any(has_privileged_role(r.get("rol")) for r in rows):
            return True

        # Fallback: global role in profiles (legacy setups often keep authority there).
        try:
            profile = db.table("profiles").select("role").eq("id", user_id).maybe_single().execute()
            global_role = (profile.data or {}).get("role") if profile else None
            if has_privileged_role(global_role):
                return True
        except Exception as profile_err:
            logger.warning(f"Could not verify global profile role for user={user_id}: {profile_err}")

        logger.warning(f"Access denied for user={user_id} in mall={mall_id}. Roles found: {[r.get('rol') for r in rows]}")
        return False
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking admin access: {e}")
        return False

@router.delete("/sales/purge")
async def purge_sales_refined(
    request: PurgeRequest,
    x_mall_id: Optional[str] = Header(None, alias="X-Mall-Id"),
    user_id: str = Depends(get_current_user_id)
):
    print(f"🔥 [BACKEND] PURGE ENDPOINT HIT! User: {user_id}, Mall: {x_mall_id}")
    db = get_supabase()

    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if not x_mall_id:
        raise HTTPException(status_code=400, detail="X-Mall-Id header is required")

    # 1. Check Role
    is_admin = await check_admin_access(user_id, x_mall_id)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions. Admin o IT/TIC role required.")

    # 2. Check Security Code
    if request.confirmacion != "BORRAR":
        raise HTTPException(status_code=400, detail="Confirmation keyword 'BORRAR' is required.")

    # 3. Build Query - STRICT filtering by mall_id and local_id
    # Use returning='minimal' to avoid fetching deleted rows (prevents timeout/crash on large datasets)
    query = db.table("ventas").delete(count='exact', returning='minimal').eq("mall_id", x_mall_id).eq("local_id", request.local_id)
    
    if request.fecha_inicio:
        query = query.gte("fecha", request.fecha_inicio)
    if request.fecha_fin:
        query = query.lte("fecha", request.fecha_fin)

    # 4. Execute Deletion
    try:
        logger.info(f"Executing PURGE for local_id={request.local_id}, mall_id={x_mall_id}")
        
        # Use count='exact' and returning='minimal' to avoid fetching thousands of rows
        # Note: Valid values for returning are 'minimal', 'representation'
        res = query.execute() 
        
        # Determine count from response metadata since we are not returning data
        count = res.count if res.count is not None else 0
        logger.info(f"Purge successful. Deleted {count} rows (from metadata).")
        
        # 5. Audit Log
        range_str = f"{request.fecha_inicio or 'BEGIN'} to {request.fecha_fin or 'TODAY'}"
        audit_detail = f"Purge executed for local_id {request.local_id}. Range: {range_str}. Rows affected: {count}"
        
        try:
            db.table("system_audit_logs").insert({
                "usuario_id": user_id,
                "mall_id": x_mall_id,
                "accion": "PURGE_DATA",
                "detalle": audit_detail,
                "metadata": {
                    "request": request.dict(),
                    "rows_affected": count,
                    "timestamp": datetime.now().isoformat()
                }
            }).execute()
        except Exception as audit_err:
             logger.warning(f"Audit log failed (non-critical): {audit_err}")

        return {
            "status": "success",
            "message": f"Se eliminaron {count} registros correctamente.",
            "detalle": audit_detail
        }

    except Exception as e:
        logger.error(f"Error purging sales: {e}")
        raise HTTPException(status_code=500, detail=f"Error durante el borrado: {str(e)}")
