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

# Supabase Client setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

security = HTTPBearer()

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Note: using the local supabase client
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user.id
    except Exception as e:
        logger.error(f"Auth error in admin_tools: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

class PurgeRequest(BaseModel):
    local_id: str
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    confirmacion: str

async def check_admin_access(user_id: str, mall_id: str):
    """
    Checks if the user has ADMIN or TIC role for the specific mall.
    """
    try:
        res = supabase.table("usuarios_malls") \
            .select("rol") \
            .eq("usuario_id", user_id) \
            .eq("mall_id", mall_id) \
            .execute()
        
        if not res.data:
            return False
            
        role = res.data[0]['rol']
        return role in ['ADMIN', 'TIC']
    except Exception as e:
        logger.error(f"Error checking admin access: {e}")
        return False

@router.delete("/sales/purge")
async def purge_sales_refined(
    request: PurgeRequest,
    x_mall_id: Optional[str] = Header(None, alias="X-Mall-Id"),
    user_id: str = Depends(get_current_user_id)
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if not x_mall_id:
        raise HTTPException(status_code=400, detail="X-Mall-Id header is required")

    # 1. Check Role
    is_admin = await check_admin_access(user_id, x_mall_id)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions. Admin or TIC role required.")

    # 2. Check Security Code
    if request.confirmacion != "BORRAR":
        raise HTTPException(status_code=400, detail="Confirmation keyword 'BORRAR' is required.")

    # 3. Build Query - STRICT filtering by mall_id and local_id
    # Use returning='minimal' to avoid fetching deleted rows (prevents timeout/crash on large datasets)
    query = supabase.table("ventas").delete(count='exact', returning='minimal').eq("mall_id", x_mall_id).eq("local_id", request.local_id)
    
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
            supabase.table("system_audit_logs").insert({
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
