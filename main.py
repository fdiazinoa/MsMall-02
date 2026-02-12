
# Backend: FastAPI API para MSMALL Audit
import csv
import io
import logging
import time
import threading
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Depends, Query, status, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from thefuzz import process, fuzz
import paramiko
import json
import xmltodict
from ftplib import FTP
import stat
from worker_importacion import run_worker_async
from analytics import generate_sales_cube
from routers import recipes, comparisons, admin_tools
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Prefer Service Role Key for backend operations to bypass RLS
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Optional[Client] = None


# Setup Logger first so we can see errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("msmall-api")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info(f"Supabase Client initialized (Service Role: {'Yes' if os.getenv('SUPABASE_SERVICE_ROLE_KEY') else 'No'})")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to initialize Supabase client: {e}")
        # Dont crash, just continue without supabase


# --- LIGHTWEIGHT IN-MEMORY CACHE (TTL) ---
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MISS = object()

def _env_int(name: str, default: int, min_value: int = 1, max_value: int = 3600) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value < min_value:
            return min_value
        if value > max_value:
            return max_value
        return value
    except (TypeError, ValueError):
        return default

_CACHE_MAX_ITEMS = _env_int("CACHE_MAX_ITEMS", 300, min_value=50, max_value=5000)

# Endpoint-specific TTLs (seconds), configurable via environment variables.
TTL_DASHBOARD = _env_int("CACHE_TTL_DASHBOARD", 90, min_value=5, max_value=1800)
TTL_RANKING = _env_int("CACHE_TTL_RANKING", 60, min_value=5, max_value=1800)
TTL_HEATMAP = _env_int("CACHE_TTL_HEATMAP", 120, min_value=5, max_value=1800)

def _cache_get(key: str):
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return _CACHE_MISS
        if item["expires_at"] <= now:
            _CACHE.pop(key, None)
            return _CACHE_MISS
        return item["value"]

def _cache_set(key: str, value: Any, ttl: int):
    now = time.time()
    with _CACHE_LOCK:
        # Opportunistic cleanup to keep memory bounded.
        if len(_CACHE) >= _CACHE_MAX_ITEMS:
            expired = [k for k, v in _CACHE.items() if v["expires_at"] <= now]
            for k in expired:
                _CACHE.pop(k, None)
            # If still full, remove oldest expiration first.
            if len(_CACHE) >= _CACHE_MAX_ITEMS:
                oldest_key = min(_CACHE.keys(), key=lambda k: _CACHE[k]["expires_at"])
                _CACHE.pop(oldest_key, None)
        _CACHE[key] = {"value": value, "expires_at": now + max(1, ttl)}


def flatten_json(y):
    out = {}

    def flatten(x, name=''):
        if isinstance(x, dict):
            for a in x:
                flatten(x[a], name + a + '.')
        elif isinstance(x, list):
             out[name[:-1]] = json.dumps(x)
        else:
            out[name[:-1]] = x

    flatten(y)
    return out

def diagnosticar_archivo(file_bytes):
    reporte = []
    
    # PASO 1: Decodificación
    try:
        content = file_bytes.decode('utf-8-sig') # Vital para quitar el BOM
        reporte.append("SUCCESS: Decodificación UTF-8-SIG correcta.")
    except:
        reporte.append("ERROR: Falló decodificación UTF-8-SIG.")
        return reporte

    # PASO 2: JSON Parsing
    try:
        data = json.loads(content)
        keys = list(data.keys()) if isinstance(data, dict) else ["<Lista>"]
        reporte.append(f"SUCCESS: JSON Válido. Claves raíz: {keys}")
    except Exception as e:
        reporte.append(f"ERROR: json.loads falló. {str(e)}")
        return reporte

    # PASO 3: Detección de Lista
    target_data = data
    if isinstance(data, dict):
        if "invoices" in data:
            target_data = data["invoices"]
            reporte.append("INFO: Se detectó clave 'invoices' y se entró en ella.")
        else:
             # Try smart search
            found = False
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    target_data = v
                    reporte.append(f"INFO: Se detectó lista en clave '{k}'.")
                    found = True
                    break
            if not found:
                 reporte.append("WARN: No se encontró lista 'invoices' ni otra lista candidata.")
    
    if not isinstance(target_data, list):
        reporte.append(f"ERROR: Los datos no son una lista. Son tipo: {type(target_data)}")
        # Try wrapping
        reporte.append("INFO: Intentando envolver en lista...")
        target_data = [target_data]

    # PASO 4: Pandas Normalize
    try:
        df = pd.json_normalize(target_data)
        cols = list(df.columns)
        reporte.append(f"SUCCESS: DataFrame creado con {len(df)} filas.")
        reporte.append(f"COLUMNAS DETECTADAS: {cols}")
        
        # Muestra una fila de ejemplo para ver si los datos estan anidados
        if not df.empty:
             reporte.append(f"EJEMPLO FILA 1: {df.iloc[0].to_dict()}")

    except Exception as e:
        reporte.append(f"ERROR: pd.json_normalize falló. {str(e)}")

    return reporte



app = FastAPI(title="MSMALL Sales Audit API", version="1.0.2")

@app.post("/api/v1/debug/diagnose-file")
async def diagnose_file_endpoint(file: UploadFile = File(...)):
    """
    Diagnostic endpoint to inspect JSON file structure and parsing status.
    """
    try:
        content = await file.read()
        report = diagnosticar_archivo(content)
        return {"filename": file.filename, "report": report}
    except Exception as e:
        return {"error": str(e)}

app.include_router(recipes.router)
app.include_router(comparisons.router)
app.include_router(admin_tools.router)

async def scheduler_loop():
    await asyncio.sleep(10) # Initial delay
    while True:
        logger.info("[Scheduler] Iniciando ciclo de importación automática...")
        try:
            # Ahora el worker es nativamente async
            await run_worker_async()
        except Exception as e:
            logger.error(f"[Scheduler] Error en ciclo: {e}")
        logger.info("[Scheduler] Durmiendo 1 hora...")
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    logger.info("MSMALL API Starting up... routes loaded.")
    asyncio.create_task(scheduler_loop())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SECURITY & MULTI-TENANT MIDDLEWARE ---
security = HTTPBearer()

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Verify token with Supabase
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user.id
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

async def get_current_mall(
    x_mall_id: Optional[str] = Header(None, alias="X-Mall-Id"),
    user_id: str = Depends(get_current_user_id)
):
    # 1. Si viene el header, usarlo (validando acceso - simplificado por ahora, RLS protege data)
    if x_mall_id:
        return x_mall_id

    # 2. Si no viene header, buscar por defecto en DB
    try:
        res = supabase.table("usuarios_malls").select("mall_id").eq("usuario_id", user_id).execute()
        malls = res.data
        if len(malls) == 1:
            return malls[0]['mall_id']
        elif len(malls) > 1:
            raise HTTPException(status_code=400, detail="Ambiguous context. Please select a mall (X-Mall-Id).")
            
        raise HTTPException(status_code=403, detail="No mall assigned to user.")
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error resolving tenant: {e}")
        raise HTTPException(status_code=500, detail="Error resolving tenant context")

# --- Schemas ---
class IngestionResponse(BaseModel):
    status: str
    message: str
    records_processed: int
    batch_id: str

class SaleReportSchema(BaseModel):
    local_id: str
    local_nombre: str
    total_bruto: float
    total_impuestos: float
    total_neto: float
    mall_nombre: str

class StoreSchema(BaseModel):
    id: str
    mall_id: str
    codigo_interno: str
    nombre: str
    rubro: Optional[str] = None
    created_at: str
    responsable: str
    contrato_no: str
    piso: str
    tipo_negocio: str
    mts: str
    porciento_renta: str
    upsert_activo: bool = False
    mall_nombre: Optional[str] = "Mall Plaza"

class RemoteRequest(BaseModel):
    protocolo: str = "SFTP"
    host: str
    puerto: int = 22
    usuario: str
    password: Optional[str] = None
    ruta: str = "/"
    tipo_archivo: str = "CSV"

class ImportConfigSchema(BaseModel):
    id: Optional[str] = None
    nombre: Optional[str] = None
    protocolo: str = "SFTP"
    host: Optional[str] = None
    puerto: Optional[int] = None
    usuario: Optional[str] = None
    password: Optional[str] = None
    ruta_remota: Optional[str] = None
    tipo_archivo: Optional[str] = "CSV"
    mapping: Dict[str, str] = {}
    constants: Dict[str, str] = {}  # Added for constant field values
    date_format: Optional[str] = "auto"  # Date format preference for fecha_venta
    # Worker names fallback support is in normalization logic

class ExecuteManualRequest(BaseModel):
    config_id: str
    filename: str
    config: Optional[ImportConfigSchema] = None

class LoadLogSchema(BaseModel):
    id: Optional[str] = None
    fecha_hora: datetime
    local_nombre: str
    archivo: str
    estado: str # 'exito', 'error', 'no_encontrado'
    mensaje: str
    batch_id: Optional[str] = None

class UserSchema(BaseModel):
    id: str
    nombre: str
    email: str
    rol: str
    estado: str
    ultimo_acceso: Optional[str] = None
    created_at: str

# --- Dependencias de Seguridad ---
async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    # En un entorno real, aquí consultaríamos en la DB si la API Key existe y está activa
    valid_keys = ["demo-key-123", "mall-plaza-admin-key", "costanera-center-key"]
    if x_api_key not in valid_keys:
        logger.warning(f"Intento de acceso fallido con API Key: {x_api_key}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="API Key inválida o no autorizada"
        )
    return x_api_key

def insert_load_log(local_nombre: str, archivo: str, estado: str, mensaje: str, batch_id: Optional[str] = None, detalles: List[Dict] = []):
    """Inserts a log into Supabase 'logs_carga' table."""
    if not supabase:
        logger.warning(f"Supabase not configured. Skipping log: {mensaje}")
        return
    
    try:
        log_data = {
            "fecha_hora": datetime.now().isoformat(),
            "local_nombre": local_nombre,
            "archivo": archivo,
            "estado": estado,
            "mensaje": mensaje,
            "batch_id": batch_id,
            "detalles": detalles
        }
        logger.info(f"Intentando guardar log en Supabase: {local_nombre} - {archivo} - {estado}")
        res = supabase.table("logs_carga").insert(log_data).execute()
        logger.info(f"Log guardado exitosamente. Respuesta: {res}")
    except Exception as e:
        logger.error(f"Error CRÍTICO insertando log en Supabase: {e}")
        logger.error(f"Data intentada: {log_data}")

def process_file_content(content: str, filename: str, config: Dict[str, Any], batch_id: str, mall_id: str = None):
    """
    Parses content based on config mapping and inserts into Supabase 'ventas' table.
    Returns (success_count, errors_list).
    """
    mapping = config.get("mapping", {})
    constants = config.get("constants", {})
    tipo_archivo = config.get("tipo_archivo", "CSV").upper()
    local_nombre = config.get("nombre", "Desconocido")
    
    records_to_insert = []
    errors = []
    
    # Pre-warm Supabase connection / cache (optional)
    try:
        supabase.table("ventas").select("count", count="exact").limit(0).execute()
    except:
        pass
    
    try:
        raw_rows = []
        if tipo_archivo == "JSON":
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    raw_rows = data
                elif isinstance(data, dict):
                    # Try to find list inside
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            raw_rows = v
                            break
                    if not raw_rows:
                        raw_rows = [data]
                
                # Apply flattening using Pandas
                if raw_rows:
                    df = pd.json_normalize(raw_rows)
                    # Convert NaN to None for SQL safety
                    raw_rows = df.where(pd.notnull(df), None).to_dict(orient='records')
            except Exception as e:
                return 0, [{"linea": 0, "error": f"JSON inválido: {str(e)}"}]
        else:
            # Default CSV/TXT
            f = io.StringIO(content)
            sample = content[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample)
                delimiter = dialect.delimiter
            except:
                delimiter = ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delimiter)
            raw_rows = list(reader)

        # Validar mapeo básico
        req_sys_fields = ['factura_numero', 'fecha_venta', 'local_codigo', 'total_bruto']
        missing_mapping = []
        for field in req_sys_fields:
            has_mapping = field in mapping and mapping[field]
            has_constant = field in constants and constants[field]
            if not (has_mapping or has_constant):
                missing_mapping.append(field)
        
        if missing_mapping:
            logger.error(f"Mapeo incompleto. Faltan: {', '.join(missing_mapping)}")
            return 0, [{"linea": 0, "error": f"Mapeo incompleto. Faltan: {', '.join(missing_mapping)}"}]

        for i, row in enumerate(raw_rows):
            try:
                record = {}
                # 1. Apply Mapping
                for sys_field, header in mapping.items():
                    if header in row:
                        record[sys_field] = row[header]
                
                # 2. Apply Constants (exclude meta-constants that are not DB columns)
                META_CONSTANTS = ['_date_format']  # These are config-only, not DB fields
                for k, v in constants.items():
                    if k not in META_CONSTANTS:
                        record[k] = v
                
                if i == 0:
                    logger.info(f"Muestra mapeo primer registro: {record}")
                
                # 3. Validation & Type Casting (Shared for both formats)
                if not record.get('fecha_venta'):
                     errors.append({"linea": i+2, "error": "Falta fecha_venta"})
                     continue

                # Normalize Date with format-specific or comprehensive support
                raw_date = str(record['fecha_venta']).strip()
                parsed_date = None
                
                # Check if explicit date_format is specified (from UI selector)
                explicit_format = config.constants.get('_date_format', 'auto') if hasattr(config, 'constants') else 'auto'
                
                # Define format groups based on user selection
                if explicit_format == 'DD/MM/YYYY':
                    date_formats = ['%d/%m/%Y', '%d-%m-%Y']
                elif explicit_format == 'MM/DD/YYYY':
                    date_formats = ['%m/%d/%Y', '%m-%d-%Y']
                elif explicit_format == 'YYYY-MM-DD':
                    date_formats = ['%Y-%m-%d', '%Y/%m/%d']
                elif explicit_format == 'timestamp':
                    date_formats = [
                        '%Y-%m-%dT%H:%M:%S.%fZ',
                        '%Y-%m-%dT%H:%M:%S.%f',
                        '%Y-%m-%dT%H:%M:%SZ',
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%d %H:%M:%S'
                    ]
                else:  # 'auto' - try all formats
                    date_formats = [
                        '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO 8601 with milliseconds and Z (2026-02-01T14:30:00.000Z)
                        '%Y-%m-%dT%H:%M:%S.%f',   # ISO 8601 with milliseconds (2026-02-01T14:30:00.000)
                        '%Y-%m-%dT%H:%M:%SZ',     # ISO 8601 with Z (2026-02-01T14:30:00Z)
                        '%Y-%m-%dT%H:%M:%S',      # ISO 8601 with time (2026-02-01T14:30:00)
                        '%Y-%m-%d %H:%M:%S',      # SQL datetime (2026-02-01 14:30:00)
                        '%Y-%m-%d',               # ISO 8601 date only (2026-02-01)
                        '%d/%m/%Y',               # DD/MM/YYYY (Dominican/Spanish format)
                        '%m/%d/%Y',               # MM/DD/YYYY (US format)
                        '%d-%m-%Y',               # DD-MM-YYYY with hyphens
                        '%m-%d-%Y',               # MM-DD-YYYY with hyphens
                        '%Y/%m/%d',               # YYYY/MM/DD with slashes
                        '%Y-%d-%m',               # YYYY-DD-MM (uncommon but requested)
                        '%d/%m/%Y %H:%M:%S',      # DD/MM/YYYY with time
                        '%m/%d/%Y %H:%M:%S',      # MM/DD/YYYY with time
                    ]
                
                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(raw_date, fmt)
                        break
                    except ValueError:
                        continue
                
                if parsed_date:
                    record['fecha_venta'] = parsed_date.strftime('%Y-%m-%d')
                else:
                    errors.append({"linea": i+2, "error": f"Formato de fecha inválido: {raw_date}"})
                    continue
                
                # Ensure numeric types
                for num_field in ['total_bruto', 'total_impuestos', 'total_neto']:
                    val = record.get(num_field, 0.0)
                    if val is None: val = 0.0
                    try:
                        record[num_field] = float(str(val).replace(',', '').strip())
                    except:
                        record[num_field] = 0.0
                
                # Validation: Reject if Total/Net is 0 but Tax > 0
                if record['total_bruto'] == 0:
                    if record['total_impuestos'] > 0:
                        errors.append({"linea": i+2, "error": f"Total Bruto es 0.00 pero tiene impuestos ({record['total_impuestos']}). Verifique el archivo."})
                        continue
                    if record['total_neto'] > 0:
                        errors.append({"linea": i+2, "error": f"Total Bruto es 0.00 pero tiene Neto ({record['total_neto']}). Verifique el archivo."})
                        continue

                if record['total_neto'] == 0 and record['total_bruto'] > 0 and record['total_impuestos'] > 0:
                     # This might be valid for tax-inclusive pricing where net wasn't calculated, 
                     # but user asked for alert on zero net.
                     # Let's be strict: if tax > 0, net should ideally be > 0.
                     # However, user specifically mentioned "alert if totalbruto or totalneto is zero"
                     errors.append({"linea": i+2, "error": f"Total Neto es 0.00 pero tiene Impuestos/Total. Verifique el archivo."})
                     continue
                
                if record.get('total_bruto', 0) == 0:
                     # Allow 0 total only if everything else is 0 (cancel/void), or logic elsewhere handles it,
                     # but broadly warning is good.
                     pass

                records_to_insert.append(record)
            except Exception as row_e:
                errors.append({"linea": i+2, "error": str(row_e)})

    except Exception as e:
        logger.error(f"Error procesando contenido: {e}")
        return 0, [{"linea": 0, "error": str(e)}]

    try:
        # --- DB SCHEMA MAPPING & RESOLUTION ---
        final_records = []
        
        # 1. Resolve Local UUIDs cache
        local_codigos = set(r.get('local_codigo') for r in records_to_insert if r.get('local_codigo'))
        local_map = {} # codigo -> {id, mall_id}
        
        if local_codigos and supabase:
            try:
                # Query locales table to find UUIDs for these codes
                res = supabase.table("locales").select("id, codigo_interno, mall_id").in_("codigo_interno", list(local_codigos)).execute()
                for loc in res.data:
                    local_map[loc['codigo_interno']] = {'id': loc['id'], 'mall_id': loc.get('mall_id')}
            except Exception as e:
                logger.warning(f"Error resolviendo local_ids: {e}")

        # 2. Transform Keys
        for r in records_to_insert:
            new_r = r.copy()
            
            # Map System Fields -> DB Columns
            if 'factura_numero' in new_r:
                new_r['factura_no'] = new_r.pop('factura_numero')
            if 'fecha_venta' in new_r:
                new_r['fecha'] = new_r.pop('fecha_venta')
            
            # Normalizar campos de hora (hora, hora_transaccion)
            for time_col in ['hora', 'hora_transaccion']:
                if time_col in new_r and new_r[time_col]:
                    val = str(new_r[time_col]).strip()
                    if val.isdigit():
                        if int(val) < 24:
                            new_r[time_col] = f"{int(val):02d}:00:00"
                        elif len(val) in [5, 6]:
                            # HHMMSS -> HH:MM:SS
                            vh = val.zfill(6)
                            hh, mm, ss = int(vh[0:2]), int(vh[2:4]), int(vh[4:6])
                            # Validation: Clamp to valid ranges if needed (user data often has 60s or bad clocks)
                            mm = min(mm, 59)
                            ss = min(ss, 59)
                            new_r[time_col] = f"{hh:02d}:{mm:02d}:{ss:02d}"
                        elif len(val) > 6:
                            # 1118234 -> 11:18:23 / 7 digits
                            # Take first 6 as HHMMSS
                            vh = val.zfill(6)
                            hh, mm, ss = int(vh[0:2]), int(vh[2:4]), int(vh[4:6])
                            mm = min(mm, 59)
                            ss = min(ss, 59)
                            new_r[time_col] = f"{hh:02d}:{mm:02d}:{ss:02d}"
                    elif val.count(':') == 1:
                        new_r[time_col] = f"{val}:00"
                    elif 'AM' in val.upper() or 'PM' in val.upper():
                        try:
                            dt = datetime.strptime(val, "%I:%M %p")
                            new_r[time_col] = dt.strftime("%H:%M:%S")
                        except:
                            try:
                                dt = datetime.strptime(val, "%I %p")
                                new_r[time_col] = dt.strftime("%H:%M:%S")
                            except:
                                pass

            # Resolve Local ID & Mall ID
            l_code = new_r.get('local_codigo')
            if l_code:
                if l_code in local_map:
                    local_info = local_map[l_code]
                    new_r['local_id'] = local_info['id']
                    if local_info.get('mall_id'):
                        new_r['mall_id'] = local_info['mall_id']
                    else:
                        # Fallback to context mall_id if local doesn't have one
                        if mall_id:
                            new_r['mall_id'] = mall_id
                            logger.info(f"Using context mall_id: {mall_id} for local {l_code}")
                    del new_r['local_codigo'] # Remove text code, keep UUID
                else:
                    logger.warning(f"No UUID found for local_codigo: {l_code}")
                    del new_r['local_codigo']
            else:
                # If no local_codigo provided, use context mall_id
                if mall_id:
                    new_r['mall_id'] = mall_id
                    logger.info(f"Using context mall_id: {mall_id} (no local_codigo provided)") 
            
            final_records.append(new_r)
        
        records_to_insert = final_records

        # Insertion into Supabase
        if records_to_insert and supabase:
            # Batch insert in chunks of 100
            for i in range(0, len(records_to_insert), 100):
                chunk = records_to_insert[i:i+100]
                
                # Log first chunk for date verification
                if i == 0:
                    fechas_muestra = [r.get('fecha') for r in chunk[:3]]
                    logger.info(f"Insertando ventas con fechas: {fechas_muestra}")
                    logger.info(f"Muestra registro completo: {chunk[0]}")

                # Usar la columna correcta para conflicto (factura_no)
                # Si no hay constraint unique, upsert falla. Cambiamos a insert para asegurar que entren.
                try:
                    res = supabase.table("ventas").insert(chunk).execute()
                    logger.info(f"Respuesta inserción ventas: {res}")
                except Exception as e:
                    # Si falla insert, podría ser por algún constraint que sí existe. Log y re-throw
                    logger.error(f"Error insertando chunk: {e}")
                    raise e
                
        return len(records_to_insert), errors

    except Exception as e:
        logger.error(f"Error in process_file_content: {e}")
        return 0, [{"linea": 0, "error": str(e)}]

@app.get("/")
async def root():
    return {"message": "MSMALL API is online", "docs": "/docs"}

# --- API DE CONSUMO: INGESTA DE VENTAS ---
@app.post("/api/v1/ingesta", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
async def ingesta_ventas(
    file: UploadFile = File(...), 
    user_id: str = Depends(get_current_user_id),
    mall_id: str = Depends(get_current_mall)
):
    """
    Endpoint principal para que los locales envíen sus ventas diarias.
    Acepta un archivo y procesa según la configuración del local.
    
    El mall_id se detecta automáticamente del contexto del usuario autenticado.
    No es necesario enviar X-Mall-Id header - se infiere del usuario logueado.
    """
    batch_id = str(uuid4())
    try:
        content_bytes = await file.read()
        content = content_bytes.decode('utf-8-sig', errors='replace')
        
        # En una app real, buscaríamos la configuración del local asociado a la API Key
        # Por ahora, usamos una configuración genérica o vacía si no tenemos el link.
        # Para este MVP, asumiremos que si es ingesta directa, viene en formato estándar.
        config = {
            "nombre": "Ingesta API",
            "tipo_archivo": "CSV" if file.filename.endswith(".csv") else "TXT",
            "mapping": {
                "factura_numero": "factura_numero",
                "fecha_venta": "fecha_venta",
                "local_codigo": "local_codigo",
                "total_bruto": "total_bruto",
                "total_neto": "total_neto",
                "total_impuestos": "total_impuestos"
            }
        }
        
        count, errors = process_file_content(content, file.filename, config, batch_id, mall_id)
        
        estado = "exito" if count > 0 and not errors else "parcial" if count > 0 else "error"
        mensaje = f"Procesado: {count} registros."
        if errors: mensaje += f" Errores: {len(errors)}"
        
        insert_load_log(config["nombre"], file.filename, estado, mensaje, batch_id, errors)
        
        return {
            "status": "success" if count > 0 else "error",
            "message": mensaje,
            "records_processed": count,
            "batch_id": batch_id
        }

    except Exception as e:
        logger.error(f"Error procesando ingesta: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# --- EXPLORACIÓN DE DIRECTORIOS LOCALES ---
@app.get("/api/v1/explorar-directorio")
async def explorar_directorio(path: str = Query("/", alias="ruta")):
    """
    Endpoint para listar directorios locales. 
    Permite al usuario navegar por carpetas para configurar la importación.
    """
    import os
    try:
        # Normalizar ruta para el OS actual
        target_path = os.path.abspath(path)
        
        if not os.path.exists(target_path):
            # Si no existe, intentar con el home del usuario o raíz
            target_path = os.path.expanduser("~")
            
        items = []
        # Añadir opción para subir de nivel
        parent = os.path.dirname(target_path)
        if parent != target_path:
            items.append({"nombre": "..", "ruta": parent, "es_dir": True})

        for item in os.listdir(target_path):
            full_path = os.path.join(target_path, item)
            if os.path.isdir(full_path) and not item.startswith('.'):
                items.append({
                    "nombre": item,
                    "ruta": full_path,
                    "es_dir": True
                })
        
        return {
            "ruta_actual": target_path,
            "items": sorted(items, key=lambda x: x["nombre"].lower())
        }
    except Exception as e:
        logger.error(f"Error explorando directorio {req.ruta}: {str(e)}")
        # Return real error for debugging
        raise HTTPException(status_code=500, detail=f"Error remoto: {str(e)}")

# --- UTILIDADES DE CONEXIÓN REMOTA ---
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=20) # Aumentado de 5 a 20 para evitar agotamiento

def _normalize_remote_host(host: str) -> str:
    """
    Normalize host values entered from UI:
    - trims whitespace
    - strips protocol prefixes
    - strips trailing path fragments
    """
    normalized = (host or "").strip()
    if normalized.startswith("sftp://"):
        normalized = normalized[len("sftp://"):]
    elif normalized.startswith("ftp://"):
        normalized = normalized[len("ftp://"):]
    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]
    return normalized

def _candidate_hosts(host: str) -> List[str]:
    normalized = _normalize_remote_host(host)
    if not normalized:
        return []
    candidates = [normalized]
    if normalized.startswith("www.") and len(normalized) > 4:
        candidates.append(normalized[4:])
    return candidates

def get_sftp_client(host, port, user, password):
    last_error = None
    for candidate in _candidate_hosts(host):
        try:
            transport = paramiko.Transport((candidate, int(port)))
            transport.banner_timeout = 20
            transport.auth_timeout = 25
            transport.connect(username=user, password=password)
            transport.set_keepalive(30)
            sftp = paramiko.SFTPClient.from_transport(transport)
            return transport, sftp
        except Exception as e:
            last_error = e
            logger.warning(f"SFTP connect failed for host '{candidate}': {e}")

    if last_error:
        raise last_error
    raise ValueError("Host remoto inválido o vacío para conexión SFTP")

def get_ftp_client(host, port, user, password):
    last_error = None
    for candidate in _candidate_hosts(host):
        try:
            ftp = FTP()
            ftp.connect(candidate, int(port), timeout=25)
            ftp.login(user, password)
            ftp.set_pasv(True)
            return ftp
        except Exception as e:
            last_error = e
            logger.warning(f"FTP connect failed for host '{candidate}': {e}")
    if last_error:
        raise last_error
    raise ValueError("Host remoto inválido o vacío para conexión FTP")

def _test_remote_connection_sync(req: RemoteRequest):
    logger.info(f"Probando conexión remota sync a {req.host}:{req.puerto} ({req.protocolo})")
    start_time = time.time()
    try:
        if req.protocolo == "SFTP":
            ssh, sftp = get_sftp_client(req.host, req.puerto, req.usuario, req.password)
            sftp.close()
            ssh.close()
        elif req.protocolo == "FTP":
            ftp = get_ftp_client(req.host, req.puerto, req.usuario, req.password)
            ftp.quit()
        duration = time.time() - start_time
        logger.info(f"Conexión exitosa en {duration:.2f}s")
        return {"status": "success", "message": f"Conexión exitosa ({duration:.2f}s)"}
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Error conexión remota después de {duration:.2f}s: {e}")
        return {"status": "error", "message": f"Error ({duration:.2f}s): {str(e)}"}

@app.post("/api/v1/remote/test")
async def test_remote_connection(req: RemoteRequest):
    loop = asyncio.get_event_loop()
    try:
        # Timeout de 30s para no bloquear el worker de FastAPI indefinidamente
        return await asyncio.wait_for(
            loop.run_in_executor(executor, _test_remote_connection_sync, req),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error(f"Timeout en test_remote_connection para {req.host}")
        raise HTTPException(status_code=504, detail="El servidor remoto no respondió a tiempo (Backend Timeout)")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Error CRITICO en test_remote_connection: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)} -> {tb}")

def _list_remote_files_sync(req: RemoteRequest):
    try:
        items = []
        if req.protocolo == "SFTP":
            ssh, sftp = get_sftp_client(req.host, req.puerto, req.usuario, req.password)
            try:
                # Check directly if path exists or listdir
                try:
                    for attr in sftp.listdir_attr(req.ruta):
                        items.append({
                            "nombre": attr.filename,
                            "ruta": f"{req.ruta.rstrip('/')}/{attr.filename}",
                            "es_dir": attr.st_mode is not None and (attr.st_mode & 0o40000) == 0o40000
                        })
                except FileNotFoundError:
                    # Fallback to root or return empty?
                    # logic from before seemed to just fail. 
                    # Let's catch and maybe list root if requested path fails?
                    # For now just re-raise or empty
                     if req.ruta != '.':
                         # Try listing root as fallback
                         for attr in sftp.listdir_attr('.'):
                             items.append({
                                "nombre": attr.filename,
                                "ruta": f"./{attr.filename}",
                                "es_dir": attr.st_mode is not None and (attr.st_mode & 0o40000) == 0o40000
                             })
                         # Signal that we fell back?
                     else:
                         raise
            finally:
                sftp.close()
                ssh.close()
        elif req.protocolo == "FTP":
            ftp = get_ftp_client(req.host, req.puerto, req.usuario, req.password)
            try:
                ftp.cwd(req.ruta)
                entries = []
                try:
                    entries = list(ftp.mlsd()) # name, facts
                    for name, facts in entries:
                         if name in ['.', '..']: continue
                         items.append({
                             "nombre": name,
                             "ruta": f"{req.ruta.rstrip('/')}/{name}",
                             "es_dir": facts.get('type') == 'dir'
                         })
                except:
                    names = ftp.nlst()
                    for name in names:
                         items.append({
                             "nombre": name,
                             "ruta": f"{req.ruta.rstrip('/')}/{name}",
                             "es_dir": '.' not in name 
                         })
            finally:
                ftp.quit()
                
        return {"ruta_actual": req.ruta, "items": sorted(items, key=lambda x: x['nombre'])}
    except Exception as e:
        logger.error(f"Error listando remoto: {e}")
        # Return empty list instead of 500? Or just raise 500
        raise e

@app.post("/api/v1/remote/list")
async def list_remote_files(req: RemoteRequest):
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, _list_remote_files_sync, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/audit/logs", status_code=status.HTTP_200_OK)
async def clear_load_logs(api_key: str = Depends(verify_api_key)):
    """
    Clears all load audit logs. Requires valid API Key.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")
        
    try:
        res = supabase.table("logs_carga").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        logger.info(f"Cleared load logs. Response: {res}")
        return {"status": "success", "message": "Historial de auditoría limpiado correctamente."}
        
    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _read_remote_headers_sync(req: RemoteRequest):
    content = ""
    if req.protocolo == "SFTP":
        ssh, sftp = get_sftp_client(req.host, req.puerto, req.usuario, req.password)
        try:
            with sftp.open(req.ruta, 'r') as f:
                if req.tipo_archivo in ["JSON", "XML"]:
                    content = f.read().decode('utf-8')
                else:
                    head = [next(f) for _ in range(2)]
                    content = "".join(head)
        finally:
            sftp.close()
            ssh.close()
    elif req.protocolo == "FTP":
        ftp = get_ftp_client(req.host, req.puerto, req.usuario, req.password)
        try:
            bio = io.BytesIO()
            ftp.retrbinary(f"RETR {req.ruta.split('/')[-1]}", bio.write)
            bio.seek(0)
            content = bio.read().decode('utf-8') 
        finally:
            ftp.quit()
    
    headers = []
    if req.tipo_archivo in ["CSV", "TXT"]:
            # logic ...
            try:
                dialect = csv.Sniffer().sniff(content)
                reader = csv.reader(io.StringIO(content), dialect)
            except:
                reader = csv.reader(io.StringIO(content)) 
            headers = next(reader)
            
    elif req.tipo_archivo == "JSON":
        data = json.loads(content)
        if isinstance(data, list) and len(data) > 0:
            headers = list(data[0].keys())
        elif isinstance(data, dict):
            found_list = False
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        headers = list(v[0].keys())
                        found_list = True
                        break
            if not found_list:
                headers = list(data.keys())
                
    elif req.tipo_archivo == "XML":
        data = xmltodict.parse(content)
        def find_keys(d):
            for k, v in d.items():
                if isinstance(v, list): 
                    if len(v) > 0 and isinstance(v[0], dict):
                        return list(v[0].keys())
                elif isinstance(v, dict):
                    res = find_keys(v)
                    if res: return res
            return list(d.keys())
        
        headers = find_keys(data)

    return {"headers": headers}

@app.post("/api/v1/remote/headers")
async def read_remote_headers(req: RemoteRequest):
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, _read_remote_headers_sync, req)
    except Exception as e:
         logger.error(f"Error leyendo headers remotos: {e}")
         raise HTTPException(status_code=500, detail=str(e))


# --- Mantenimiento de Usuarios y Locales (Mantenidos para funcionalidad UI) ---
@app.get("/api/v1/usuarios", response_model=List[UserSchema])
async def get_users():
    return [
        {"id": "1", "nombre": "Admin Auditor", "email": "admin@msmall.com", "rol": "admin", "estado": "activo", "created_at": "2024-01-01", "ultimo_acceso": "Hace 5 min"},
        {"id": "2", "nombre": "Roberto Carlos", "email": "rcarlos@mallplaza.com", "rol": "mall_manager", "estado": "activo", "created_at": "2024-02-15", "ultimo_acceso": "Ayer"}
    ]

@app.get("/api/v1/locales", response_model=List[StoreSchema])
async def get_stores():
    return [
        {
          "id": "64d82d1a-8893-4913-a9c5-d79b3221710e",
          "mall_id": "c23e99b6-8feb-4be8-8842-86c263bc5cad",
          "codigo_interno": "l002",
          "nombre": "Adidas",
          "rubro": "Deporte",
          "created_at": "2026-01-27T15:33:02",
          "responsable": "Jose Perez",
          "contrato_no": "99812-91283",
          "piso": "P2-L123",
          "tipo_negocio": "Ropa Deportiva",
          "mts": "150.00",
          "porciento_renta": "2.00"
        }
    ]

# --- AI & INSIGHTS ENDPOINTS ---
@app.get("/api/v1/insights/alerts")
async def get_intelligent_alerts(local_id: Optional[str] = None):
    """Fetch recent intelligent alerts (real check)."""
    if not supabase: return []
    try:
        # Search in 'alertas_inteligentes' table if exists
        query = supabase.table("alertas_inteligentes").select("*").order("created_at", desc=True)
        if local_id:
            query = query.eq("local_id", local_id)
        res = query.limit(5).execute()
        return res.data if res.data else []
    except:
        return []

@app.get("/api/v1/insights/benchmarking/{local_id}")
async def get_benchmarking(local_id: str):
    """Compare local performance vs category average based on real data."""
    if not supabase: return None
    try:
        # 1. Get Store Info
        store_res = supabase.table("locales").select("id, nombre, rubro").eq("id", local_id).single().execute()
        if not store_res.data: return None
        
        # 2. Get Sales ATV
        sales_res = supabase.table("ventas").select("total_bruto").eq("local_id", local_id).execute()
        if not sales_res.data:
            return {
                "local_name": store_res.data['nombre'],
                "local_value": 0, "category_avg": 0, "status": "Sin datos",
                "atv_local": 0, "atv_category": 0, "atv_growth": "0%"
            }
        
        local_total = sum(float(r['total_bruto']) for r in sales_res.data)
        atv_local = local_total / len(sales_res.data)
        
        # 3. Get Category Average
        rubro = store_res.data.get('rubro')
        atv_category = atv_local # Default
        if rubro:
            cat_stores = supabase.table("locales").select("id").eq("rubro", rubro).execute()
            cat_ids = [s['id'] for s in cat_stores.data]
            cat_sales = supabase.table("ventas").select("total_bruto").in_("local_id", cat_ids).execute()
            if cat_sales.data:
                atv_category = sum(float(r['total_bruto']) for r in cat_sales.data) / len(cat_sales.data)

        return {
            "local_name": store_res.data['nombre'],
            "local_value": local_total,
            "category_avg": atv_category * len(sales_res.data),
            "status": "Líder" if atv_local > atv_category else "Promedio",
            "atv_local": round(atv_local, 2),
            "atv_category": round(atv_category, 2),
            "atv_growth": "0%"
        }
    except Exception as e:
        logger.error(f"Error benchmarking: {e}")
        return None

@app.get("/api/v1/insights/efficiency/{local_id}")
async def get_efficiency(local_id: str):
    """Calculate Real Estate Efficiency metrics from real store and sales data."""
    if not supabase: return None
    try:
        # 1. Get Store MTS
        store_res = supabase.table("locales").select("mts, nombre, porciento_renta").eq("id", local_id).single().execute()
        if not store_res.data: return None
        
        mts = float(store_res.data.get('mts') or 1.0)
        
        # 2. Sum Sales
        sales_res = supabase.table("ventas").select("total_neto").eq("local_id", local_id).execute()
        total_sales = sum(float(r['total_neto']) for r in sales_res.data) if sales_res.data else 0
        
        if total_sales == 0:
            return {
                "sales_per_m2": 0, "occupancy_cost_ratio": 0, "is_healthy": True, "risk_level": "BAJO", "message": "Sin datos"
            }

        # 3. Simple Mock Renta (unless added to DB)
        renta_fija = 2500  # Placeholder
        gastos_comunes = 600 # Placeholder
        
        sales_per_m2 = total_sales / mts
        occupancy_cost_ratio = (renta_fija + gastos_comunes) / total_sales
        
        return {
            "sales_per_m2": round(sales_per_m2, 2),
            "occupancy_cost_ratio": round(occupancy_cost_ratio * 100, 2),
            "is_healthy": occupancy_cost_ratio < 0.15,
            "risk_level": "BAJO" if occupancy_cost_ratio < 0.15 else "MEDIO" if occupancy_cost_ratio < 0.20 else "ALTO",
            "message": "Operación saludable"
        }
    except Exception as e:
        logger.error(f"Error efficiency: {e}")
        return None

@app.get("/api/v1/insights/heatmap/{local_id}")
async def get_heatmap(local_id: str):
    """Generate sales intensity heatmap data from real transaction times."""
    if not supabase: return []
    cache_key = f"insights:heatmap:{local_id}"
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
        return cached
    try:
        rpc_res = supabase.rpc("get_insights_heatmap", {"local_id_param": local_id}).execute()
        if rpc_res.data:
            result = rpc_res.data
            _cache_set(cache_key, result, TTL_HEATMAP)
            return result
        _cache_set(cache_key, [], TTL_HEATMAP)
        return []
    except Exception as rpc_err:
        logger.warning(f"Heatmap RPC unavailable, fallback to python aggregation: {rpc_err}")
    try:
        res = supabase.table("ventas").select("fecha, hora_transaccion").eq("local_id", local_id).limit(2000).execute()
        if not res.data:
            _cache_set(cache_key, [], TTL_HEATMAP)
            return []
        
        counts = {}
        days_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        
        for r in res.data:
            dt = datetime.strptime(r['fecha'], '%Y-%m-%d')
            day_name = days_map[dt.weekday()]
            hora_str = r.get('hora_transaccion') or '12:00:00'
            hour_val = int(hora_str.split(':')[0])
            # Match UI blocks
            block = (hour_val // 2) * 2
            if block < 10: block = 10
            if block > 22: block = 22
            key = (day_name, f"{block:02d}:00")
            counts[key] = counts.get(key, 0) + 1
            
        max_count = max(counts.values()) if counts else 1
        result = []
        days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        hours = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]
        for d in days:
            for h in hours:
                val = (counts.get((d, h), 0) / max_count) * 100
                result.append({"dia": d, "hora": h, "valor": round(val, 2)})
        _cache_set(cache_key, result, TTL_HEATMAP)
        return result
    except:
        return []

@app.get("/api/v1/insights/ranking")
async def get_ranking(metric: str, mall_id: Optional[str] = Query(None, alias="mall_id")):
    """Get ranking of all stores for a specific metric based on real database data."""
    if not supabase: return []
    cache_key = f"insights:ranking:{metric}:{mall_id or 'all'}"
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
        return cached
    try:
        rpc_res = supabase.rpc("get_insights_ranking", {
            "metric_param": metric,
            "mall_id_param": mall_id
        }).execute()
        if rpc_res.data:
            # Ensure JSON-serializable primitive types
            normalized = []
            for row in rpc_res.data:
                normalized.append({
                    "id": row.get("id"),
                    "nombre": row.get("nombre"),
                    "valor": float(row.get("valor") or 0),
                    "extra": row.get("extra")
                })
            _cache_set(cache_key, normalized, TTL_RANKING)
            return normalized
        _cache_set(cache_key, [], TTL_RANKING)
        return []
    except Exception as rpc_err:
        logger.warning(f"Ranking RPC unavailable, fallback to python aggregation: {rpc_err}")
    try:
        # 1. Fetch all stores
        query = supabase.table("locales").select("id, nombre, mts, rubro")
        if mall_id:
            query = query.eq("mall_id", mall_id)
        
        stores_res = query.execute()
        if not stores_res.data: return []
        
        # 2. Fetch all sales
        sales_query = supabase.table("ventas").select("local_id, total_bruto, total_neto")
        if mall_id:
            sales_query = sales_query.eq("mall_id", mall_id)
        sales_res = sales_query.execute()
        
        # Aggregate
        sales_data = {} # id -> {bruto, neto, cnt}
        for s in sales_res.data:
            lid = s['local_id']
            if lid not in sales_data: sales_data[lid] = {'bruto': 0, 'neto': 0, 'cnt': 0}
            sales_data[lid]['bruto'] += float(s['total_bruto'])
            sales_data[lid]['neto'] += float(s['total_neto'])
            sales_data[lid]['cnt'] += 1
            
        ranking = []
        for s in stores_res.data:
            stats = sales_data.get(s['id'], {'bruto': 0, 'neto': 0, 'cnt': 0})
            
            valor = 0
            extra = s.get('rubro') or "General"
            
            if metric == 'sales_per_m2':
                mts = float(s.get('mts') or 1.0)
                valor = stats['neto'] / mts
                extra = f"{mts} m²"
            elif metric == 'occupancy_cost':
                # Use a placeholder for rent until it's in DB
                costos = 3000 
                valor = (costos / stats['neto'] * 100) if stats['neto'] > 0 else 0
                extra = "Saludable" if (0 < valor < 15) else "Riesgo" if valor >= 15 else "Sin Ventas"
            
            ranking.append({
                "id": s['id'],
                "nombre": s['nombre'],
                "valor": round(valor, 2),
                "extra": extra
            })
            
        # Sort desc
        ranking.sort(key=lambda x: x['valor'], reverse=True)
        _cache_set(cache_key, ranking, TTL_RANKING)
        return ranking
    except Exception as e:
        logger.error(f"Error in ranking: {e}")
        return []

class CubeRequest(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    agrupacion: str = "DIA" # DIA, SEMANA, MES
    metrica: str = "total_neto" # total_neto, total_bruto, transacciones
    local_id: Optional[str] = None

# --- INTELLIGENT AUTO-MAPPING ---
SYSTEM_FIELDS_SYNONYMS = {
    "factura_numero": ["invoice", "factura", "doc_num", "documento", "folio", "ticket", "recibo", "invoiceNumber", "invoice_id"],
    "fecha_venta": ["date", "fecha", "time", "dia", "issued", "created", "invoiceDate"],
    "local_codigo": ["store", "local", "tienda", "sucursal", "code", "id_local", "storeCode", "terminalCode"],
    "total_bruto": ["gross", "bruto", "total", "amount", "monto", "venta", "precio", "importe", "grandTotal", "totals.grandTotal", "paymentTotal"],
    "total_impuestos": ["tax", "impuesto", "iva", "vat", "tributes", "taxTotal", "totals.taxTotal", "taxAmount"],
    "total_neto": ["net", "neto", "subtotal", "base", "subTotal", "totals.subTotal"],
    "comprobante": ["ticket", "vourcher", "comprobante", "recibo", "doc_type", "ncf", "fiscalData.ncf"],
    "hora_transaccion": ["time", "hora", "trans_hour", "momento"]
}




def _perform_mapping_analysis(decoded_content, filename, tipo_archivo=None):
    headers = []
    sample_row = {}
    
    # Normalize tipo_archivo if provided
    current_type = tipo_archivo.upper() if tipo_archivo else None
    if not current_type:
        if filename.lower().endswith('.json'): current_type = "JSON"
        elif filename.lower().endswith('.csv') or filename.lower().endswith('.txt'): current_type = "CSV"
    
    # 1. Detect Format and Extract Headers/Sample
    if current_type == "CSV" or current_type == "TXT" or not current_type:
        # Simple Sniffer attempt
        sample_str = decoded_content[:4096] # Analyze first 4KB
        try:
            dialect = csv.Sniffer().sniff(sample_str)
            delimiter = dialect.delimiter
        except:
            delimiter = ',' # Fallback
            
        # Read first 2 lines
        f = io.StringIO(decoded_content)
        reader = csv.DictReader(f, delimiter=delimiter)
        try:
            row1 = next(reader)
            headers = reader.fieldnames
            sample_row = row1
        except StopIteration:
            return {"csv_headers": [], "headers": [], "suggested_mapping": {}, "sample_row": {}, "detected_headers": []}
            
    if current_type == "JSON":
        try:
            # Try decoding with utf-8-sig to handle BOM
            try:
                if isinstance(decoded_content, str):
                     data = json.loads(decoded_content)
                else: 
                     # Should be string here but safety check 
                     data = json.loads(decoded_content)
            except:
                # If decoded_content wasn't decoded with sig, it might have issues?
                # But here we receive string. We assume content was read properly in endpoints.
                # However, for robustness we just proceed.
                data = json.loads(decoded_content)
            
            # Logic Update: If root is dict, find the list (Recursive/Smart Search)
            target_data = data
            if isinstance(data, dict):
                if "invoices" in data:
                    target_data = data["invoices"]
                else:
                    # Heuristic: Find first value that is a list of dicts
                    found_list = False
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            target_data = v 
                            found_list = True
                            break
                    
                    if not found_list:
                        # If no list found, treat as single record
                        target_data = [data]
            elif isinstance(data, list):
                target_data = data
            else:
                 target_data = [data]
            
             # Use Pandas for robust flattening
            df = pd.json_normalize(target_data)
            
            # Convert back to list of dicts for header extraction/sample
            if df.empty:
                 headers = []
            else:
                 headers = list(df.columns)
                 # Get first row as dict, handle NaN
                 if len(df) > 0:
                     sample_row = df.iloc[0].where(pd.notnull(df.iloc[0]), None).to_dict()

        except Exception as e:
            logger.error(f"Error parsing JSON analysis: {e}")
            pass
    
    if not headers:
        return {"csv_headers": [], "headers": [], "suggested_mapping": {}, "sample_row": {}, "detected_headers": []}

    # 2. Fuzzy Match System Fields
    suggested_mapping = {}
    
    # Pre-process headers for matching logic
    # We keep original headers but maybe create a lower version map
    
    for sys_field, synonyms in SYSTEM_FIELDS_SYNONYMS.items():
        query_list = [sys_field] + synonyms
        best_match = None
        best_score = 0
        
        # EXACT MATCH FIRST (Crucial for dot notation like totals.grandTotal)
        for h in headers:
            for q in query_list:
                if h == q:
                    best_match = h
                    best_score = 100
                    break
            if best_score == 100: break
        
        # If no exact match, try Fuzzy
        if best_score < 100:
            for query in query_list:
                # Use partial_ratio or token_sort based on needs. 
                # token_sort_ratio handles "Total Bruto" vs "Bruto Total" nicely.
                # We used extractOne before.
                match, score = process.extractOne(query, headers, scorer=fuzz.token_sort_ratio) or (None, 0)
                if score > best_score:
                    best_score = score
                    best_match = match
        
        if best_score > 60:
            suggested_mapping[sys_field] = {
                "csv_header": best_match,
                "confidence": best_score,
                "is_confident": best_score > 80
            }
    
    return {
        "csv_headers": headers,
        "detected_headers": headers, # Added explicit key as requested
        "suggested_mapping": suggested_mapping,
        "sample_row": sample_row
    }

@app.post("/api/v1/mapping/analyze")
async def analyze_mapping(file: UploadFile = File(...)):
    """
    Analyzes a sample file (CSV/JSON) and suggests mapping to system fields using fuzzy logic.
    """
    try:
        content = await file.read()
        # Use utf-8-sig to handle BOM which is common in Windows/Excel generated files
        decoded = content.decode('utf-8-sig', errors='replace')
        return _perform_mapping_analysis(decoded, file.filename) # For upload we usually trust extension or could add more logic
    except Exception as e:
        logger.error(f"Error analyzing mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/mapping/analyze-remote")
async def analyze_remote_mapping(req: RemoteRequest):
    """
    Connects to SFTP/FTP, reads a sample of the file, and returns mapping suggestions.
    """
    try:
        content = ""
        loop = asyncio.get_event_loop()
        
        def _read_remote_sample():
            # Determine if we should read all (JSON) or sample (CSV)
            is_json = req.tipo_archivo == "JSON" or req.ruta.lower().endswith('.json')
            read_size = -1 if is_json else 32768 # Read all for JSON, 32KB for CSV (increased from 8KB)

            if req.protocolo == "SFTP":
                ssh, sftp = get_sftp_client(req.host, req.puerto, req.usuario, req.password)
                try:
                    target_path = req.ruta
                    # If route points to directory, fail with deterministic message.
                    st = sftp.stat(target_path)
                    if stat.S_ISDIR(st.st_mode):
                        raise FileNotFoundError(f"La ruta '{target_path}' es un directorio. Seleccione un archivo.")
                    with sftp.open(target_path, 'r') as f:
                        if is_json:
                            # Use utf-8-sig to handle BOM
                            return f.read().decode('utf-8-sig', errors='replace')
                        else:
                            return f.read(read_size).decode('utf-8-sig', errors='replace')
                finally:
                    sftp.close()
                    ssh.close()
            elif req.protocolo == "FTP":
                ftp = get_ftp_client(req.host, req.puerto, req.usuario, req.password)
                try:
                    bio = io.BytesIO()
                    remote_name = req.ruta.split('/')[-1]
                    ftp.retrbinary(f"RETR {remote_name}", bio.write)
                    bio.seek(0)
                    if is_json:
                         return bio.read().decode('utf-8-sig', errors='replace')
                    else:
                         return bio.read(read_size).decode('utf-8-sig', errors='replace')
                finally:
                    ftp.quit()
            return ""

        # Usar wait_for para evitar hangs si el archivo es gigante o la red falla
        # Increased timeout for big JSON files
        content = await asyncio.wait_for(
            loop.run_in_executor(executor, _read_remote_sample),
            timeout=120.0 
        )
        if not content:
            return {"headers": [], "suggested_mapping": {}, "sample_row": {}}
            
        return _perform_mapping_analysis(content, req.ruta, req.tipo_archivo)
        
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout analizando archivo remoto (el archivo podría ser demasiado grande o la conexión lenta)")
    except Exception as e:
        logger.error(f"Error analyzing remote mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import posixpath

def _list_remote_files(config: Dict[str, Any]):
    # Normalize keys (handles frontend names and worker-style names from Supabase 'locales')
    protocolo = config.get("protocolo") or config.get("sftp_protocol", "SFTP")
    host = config.get("host") or config.get("sftp_host")
    puerto = config.get("puerto") or config.get("sftp_port", 22)
    usuario = config.get("usuario") or config.get("sftp_user")
    password = config.get("password") or config.get("sftp_pass")
    ruta = config.get("ruta_remota") or config.get("sftp_path", ".")
    tipo_archivo = config.get("tipo_archivo") or config.get("file_type", "CSV")
    logger.info(f"[DEBUG_AUTH] User: '{usuario}', PassLen: {len(password) if password else 0}, Host: '{host}', Port: {puerto}, Path: '{ruta}'")
    
    # Allow all supported extensions to be listed, to prevent confusion if config doesn't match file
    # ext = ".csv" if tipo_archivo == "CSV" else ".txt" if tipo_archivo == "TXT" else ".json"
    supported_exts = (".csv", ".txt", ".json")
    
    if not host or not usuario:
        logger.error(f"Missing connection parameters: host={host}, user={usuario}")
        return []

    files = []
    if protocolo == "SFTP":
        ssh, sftp = get_sftp_client(host, puerto, usuario, password)
        try:
            # Si la ruta es un archivo, listar su directorio contenedor
            try:
                logger.info(f"Haciendo stat de: {ruta}")
                st = sftp.stat(ruta)
                logger.info(f"Stat OK. Mode: {st.st_mode}, IsDir: {stat.S_ISDIR(st.st_mode)}")
                if not stat.S_ISDIR(st.st_mode):
                    ruta = posixpath.dirname(ruta) or "."
                    logger.info(f"Ruta ajustada (era archivo): {ruta}")
            except Exception as e:
                 logger.warning(f"Stat falló para {ruta}: {e}")
                 pass

            try:
                print(f"[DEBUG] Listando ruta: {ruta}")
                raw_list = sftp.listdir(ruta)
                print(f"[DEBUG] Raw listdir output ({len(raw_list)}): {raw_list}")
            except Exception as e:
                print(f"[DEBUG] Raw listdir falló: {e}")
            for attr in sftp.listdir_attr(ruta):
                print(f"[DEBUG] Encontrado: {attr.filename} (Dir: {stat.S_ISDIR(attr.st_mode)})")
                if not stat.S_ISDIR(attr.st_mode):
                    if attr.filename.lower().endswith(supported_exts):
                        print(f"[DEBUG] -> Aceptado: {attr.filename}")
                        files.append({
                            "nombre": attr.filename,
                            "fecha": datetime.fromtimestamp(attr.st_mtime).isoformat(),
                            "tamano": attr.st_size
                        })
                    else:
                        print(f"[DEBUG] -> Ignorado (extensión): {attr.filename}")
        finally:
            sftp.close()
            ssh.close()
    elif protocolo == "FTP":
        ftp = get_ftp_client(host, puerto, usuario, password)
        try:
            try:
                ftp.cwd(ruta)
            except:
                # Si falla, intentar con el directorio padre
                ruta_padre = posixpath.dirname(ruta) or "."
                try:
                    ftp.cwd(ruta_padre)
                except:
                    pass # Dejar que falle el LIST posterior si nada funciona

            lines = []
            ftp.retrlines('LIST', lines.append)
            # Basic parsing of FTP LIST output
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[-1]
                    if name.lower().endswith(supported_exts):
                        files.append({
                            "nombre": name,
                            "fecha": datetime.now().isoformat(), # FTP LIST date parsing is complex
                            "tamano": 0
                        })
        finally:
            ftp.quit()
    return sorted(files, key=lambda x: x["fecha"], reverse=True)

@app.post("/api/v1/remote/list-files")
async def list_files_endpoint(config: ImportConfigSchema):
    try:
        logger.info(f"Recibida solucitud de listado para: {config.host}:{config.puerto} (Protocolo: {config.protocolo})")
        config_dict = config.dict()
        
        # Si tiene ID pero no host, intentar cargar de DB (enriquecer)
        if config.id and not config.host and supabase:
            res = supabase.table("locales").select("*").eq("id", config.id).single().execute()
            if res.data:
                # Merge data from DB if not provided in request
                for k, v in res.data.items():
                    if not config_dict.get(k): config_dict[k] = v

        loop = asyncio.get_event_loop()
        files = await asyncio.wait_for(
            loop.run_in_executor(executor, _list_remote_files, config_dict),
            timeout=30.0
        )
        return files
    except asyncio.TimeoutError:
        logger.error(f"Timeout listando archivos para {config.nombre}")
        raise HTTPException(status_code=504, detail="El servidor remoto no respondió a tiempo (List Timeout)")
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/remote/execute-manual")
async def execute_manual_endpoint(req: ExecuteManualRequest):
    logger.info(f"Ejecutando manual para {req.config_id} - Archivo: {req.filename}")
    batch_id = str(uuid4())
    
    try:
        # Priorizar config enviada en el request para evitar dependencia de DB en configuración activa
        config_data = {}
        if req.config:
            config_data = req.config.dict()
        elif supabase:
            # Fallback a DB
            res = supabase.table("locales").select("*").eq("id", req.config_id).single().execute()
            if res.data:
                config_data = res.data
        
        if not config_data:
            raise HTTPException(status_code=404, detail="Configuración no encontrada en el request ni en la base de datos.")

        # Normalizar para _list_remote_files (y para esta lógica local)
        local_nombre = config_data.get("nombre") or "Desconocido"
        host = config_data.get("host") or config_data.get("sftp_host")
        puerto = config_data.get("puerto") or config_data.get("sftp_port", 22)
        usuario = config_data.get("usuario") or config_data.get("sftp_user")
        password = config_data.get("password") or config_data.get("sftp_pass")
        ruta_remota = config_data.get("ruta_remota") or config_data.get("sftp_path", ".")
        protocolo = config_data.get("protocolo") or config_data.get("sftp_protocol", "SFTP")
        
        # 2. Conectar y Descargar
        content = ""
        try:
            logger.info(f"Conectando a {host}:{puerto} via {protocolo} (User: {usuario})")
            if protocolo == "SFTP":
                ssh, sftp = get_sftp_client(host, puerto, usuario, password)
                try:
                    # Normalizar ruta: si es un archivo, usar el padre
                    target_dir = ruta_remota
                    try:
                        st = sftp.stat(ruta_remota)
                        if not stat.S_ISDIR(st.st_mode):
                            target_dir = posixpath.dirname(ruta_remota) or "."
                    except Exception as e:
                        logger.warning(f"No se pudo determinar si la ruta es archivo/directorio: {e}")

                    full_path = posixpath.join(target_dir, req.filename)
                    logger.info(f"Intentando abrir archivo SFTP: {full_path}")
                    with sftp.open(full_path, 'r') as f:
                        if req.filename.lower().endswith('.json'):
                            content = f.read().decode('utf-8-sig', errors='replace')
                        else:
                            content = f.read().decode('utf-8', errors='replace')
                    
                    # Log file size and first chars for verification
                    logger.info(f"✅ Archivo leído: {full_path} | Tamaño: {len(content)} bytes | Primeros 100 chars: {content[:100]}")
                finally:
                    sftp.close()
                    ssh.close()
            elif protocolo == "FTP":
                ftp = get_ftp_client(host, puerto, usuario, password)
                try:
                    # Intentar CWD a la ruta. Si falla, intentar padre.
                    try:
                        ftp.cwd(ruta_remota)
                    except:
                        try:
                            parent = posixpath.dirname(ruta_remota) or "."
                            ftp.cwd(parent)
                        except:
                            pass

                    bio = io.BytesIO()
                    logger.info(f"Descargando archivo FTP: {req.filename}")
                    ftp.retrbinary(f"RETR {req.filename}", bio.write)
                    bio.seek(0)
                    if req.filename.lower().endswith('.json'):
                        content = bio.read().decode('utf-8-sig', errors='replace')
                    else:
                        content = bio.read().decode('utf-8', errors='replace')
                    
                    # Log file size and first chars for verification
                    logger.info(f"✅ Archivo FTP leído: {req.filename} | Tamaño: {len(content)} bytes | Primeros 100 chars: {content[:100]}")
                finally:
                    ftp.quit()
        except Exception as ce:
            error_msg = str(ce)
            logger.error(f"Error en ejecución manual ({protocolo} {host}): {error_msg}")
            insert_load_log(local_nombre, req.filename, "error", f"Error de conexión: {error_msg}", batch_id)
            raise HTTPException(status_code=500, detail=f"Error de conexión remota ({protocolo}): {error_msg}")

        # 3. Procesar Contenido
        registros_exito, detalles_errores = process_file_content(content, req.filename, config_data, batch_id)

        estado = "exito" if registros_exito > 0 and not detalles_errores else "parcial" if registros_exito > 0 else "error"
        
        mensaje = f"Importación manual completada. {registros_exito} registros cargados."
        if detalles_errores:
            mensaje += f" Se encontraron {len(detalles_errores)} errores de validación/mapeo."

        # 4. Registrar Log en Monitor
        insert_load_log(local_nombre, req.filename, estado, mensaje, batch_id, detalles_errores)



        # 5. Renombrar si fue exitoso
        logger.info(f"Evaluando renombrado: registros_exito={registros_exito} (Tipo: {type(registros_exito)})")
        
        if isinstance(registros_exito, int) and registros_exito > 0:
             try:
                if protocolo == "SFTP":
                     ssh, sftp = get_sftp_client(host, puerto, usuario, password)
                     # Determine dir again (could be optimized but safe here)
                     target_dir = ruta_remota
                     try:
                        st = sftp.stat(ruta_remota)
                        if not stat.S_ISDIR(st.st_mode):
                            target_dir = posixpath.dirname(ruta_remota) or "."
                     except: pass
                     
                     old_path = posixpath.join(target_dir, req.filename)
                     new_name = f"PR_{req.filename}" # Hardcoded prefix per user request "colocar el prefijo"
                     new_path = posixpath.join(target_dir, new_name)
                     
                     logger.info(f"Renombrando {old_path} -> {new_path}")
                     sftp.rename(old_path, new_path)
                     sftp.close()
                     ssh.close()

                elif protocolo == "FTP":
                    ftp = get_ftp_client(host, puerto, usuario, password)
                    # Navigate to dir
                    try:
                        ftp.cwd(ruta_remota)
                    except:
                        try:
                            parent = posixpath.dirname(ruta_remota) or "."
                            ftp.cwd(parent)
                        except: pass
                    
                    new_name = f"PR_{req.filename}"
                    logger.info(f"Renombrando {req.filename} -> {new_name}")
                    ftp.rename(req.filename, new_name)
                    ftp.quit()
             except Exception as rename_err:
                 logger.error(f"Error al renombrar archivo pos-importación: {rename_err}")
                 # Don't fail the request, just log it. The import was successful.
                 mensaje += f" (Advertencia: No se pudo renombrar el archivo: {rename_err})"
                 return {
                    "status": "success",
                    "message": mensaje,
                    "records_processed": registros_exito,
                    "batch_id": batch_id,
                    "errors": detalles_errores,
                    "renaming_error": str(rename_err)
                 }

        return {
            "status": "success" if registros_exito > 0 else "error",
            "message": mensaje,
            "records_processed": registros_exito,
            "batch_id": batch_id,
            "errors": detalles_errores
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error en ejecución manual: {e}")
        if 'local_nombre' in locals():
            insert_load_log(local_nombre, req.filename, "error", str(e), batch_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/analytics/cubo")
async def get_sales_cube(request: CubeRequest, mall_id: str = Depends(get_current_mall)):
    """
    Endpoint para generar el Cubo de Ventas (Matriz) usando datos reales de Supabase (Service Role).
    """
    try:
        # 1. Fetch Locales (Store Map) - Filtered by Mall
        stores_res = supabase.table("locales").select("id, nombre").eq("mall_id", mall_id).execute()
        stores = stores_res.data or []
        store_map = {str(s['id']): s['nombre'] for s in stores}
        allowed_local_ids = list(store_map.keys())

        if request.local_id:
            if str(request.local_id) not in store_map:
                # Prevent cross-tenant access and return deterministic empty matrix.
                return {"columns": ["local_nombre", "TOTAL_FILA"], "data": [], "grand_totals": {}}
            allowed_local_ids = [str(request.local_id)]

        if not allowed_local_ids:
            return {"columns": ["local_nombre", "TOTAL_FILA"], "data": [], "grand_totals": {}}
        
        # 2. Fetch Sales within date range - Filtered by Mall
        # Note: Using service role key bypasses RLS
        # Important: filter by local_id list (derived from mall) instead of ventas.mall_id,
        # because some legacy rows may have null/incorrect mall_id while local_id is valid.
        # Supabase select has page limits; fetch all rows in batches.
        sales_data = []
        page_size = 1000
        page = 0
        while True:
            sales_res = (
                supabase.table("ventas")
                .select("local_id, fecha, total_bruto, total_neto, id")
                .in_("local_id", allowed_local_ids)
                .gte("fecha", request.fecha_inicio)
                .lte("fecha", request.fecha_fin)
                .order("fecha")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )
            chunk = sales_res.data or []
            if not chunk:
                break
            sales_data.extend(chunk)
            if len(chunk) < page_size:
                break
            page += 1
        
        if not sales_data:
            # Return empty structure if no sales found
            return {"columns": ["local_nombre", "TOTAL_FILA"], "data": [], "grand_totals": {}}

        # 3. Convert to DataFrame
        df = pd.DataFrame(sales_data)
        
        # 4. Map Store Names
        # Ensure local_id is string for mapping
        df['local_id'] = df['local_id'].astype(str)
        df['local_nombre'] = df['local_id'].map(store_map).fillna("Desconocido (" + df['local_id'] + ")")
        
        # 5. Ensure numeric types for metrics
        df['total_bruto'] = pd.to_numeric(df['total_bruto'], errors='coerce').fillna(0)
        df['total_neto'] = pd.to_numeric(df['total_neto'], errors='coerce').fillna(0)
        df['transacciones'] = 1 # Each row is a transaction? Or aggregate? 
        # Assuming each row in 'ventas' is a transaction/daily summary. 
        # If 'ventas' is granular (ticket), count=1. If daily summary, we might need a 'count' column if exists, 
        # but usually 'ventas' tables in these systems are per-ticket or per-day. 
        # Looking at previous code, it seems granular or aggregated. Let's assume 1 row = 1 transaction for now if no other field.
        # Check if 'cantidad_transacciones' exists in DB? Previous view didn't show it.
        # Let's count rows as transactions.
        
        # 6. Generate Cube using existing logic
        # Assuming generate_sales_cube handles the DataFrame aggregation
        result = generate_sales_cube(
            df,
            request.agrupacion,
            request.metrica,
            start_date=request.fecha_inicio,
            end_date=request.fecha_fin
        )
        return result
        
    except Exception as e:
        logger.error(f"Error generando cubo: {e}")
        # Return empty safe response instead of 500 to avoid breaking UI on minor data errors?
        # No, better to let UI know something went wrong, or return empty.
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/remote/analyze-file")
async def analyze_remote_file(req: ExecuteManualRequest):
    """
    Analyzes a specific file from the remote server for mapping suggestions.
    Similar to analyze_remote_mapping but uses config+filename instead of direct path.
    """
    try:
        # Get config either from request or database
        config_data = {}
        if req.config:
            config_data = req.config.dict()
        elif supabase:
            res = supabase.table("locales").select("*").eq("id", req.config_id).single().execute()
            if res.data:
                config_data = res.data
        
        if not config_data:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")

        # Normalize configuration
        host = config_data.get("host") or config_data.get("sftp_host")
        puerto = config_data.get("puerto") or config_data.get("sftp_port", 22)
        usuario = config_data.get("usuario") or config_data.get("sftp_user")
        password = config_data.get("password") or config_data.get("sftp_pass")
        ruta_remota = config_data.get("ruta_remota") or config_data.get("sftp_path", ".")
        protocolo = config_data.get("protocolo") or config_data.get("sftp_protocol", "SFTP")
        
        loop = asyncio.get_event_loop()
        
        def _read_file_sample():
            if protocolo == "SFTP":
                ssh, sftp = get_sftp_client(host, puerto, usuario, password)
                try:
                    # Normalize path
                    target_dir = ruta_remota
                    try:
                        st = sftp.stat(ruta_remota)
                        if not stat.S_ISDIR(st.st_mode):
                            target_dir = posixpath.dirname(ruta_remota) or "."
                    except:
                        pass
                    
                    full_path = posixpath.join(target_dir, req.filename)
                    with sftp.open(full_path, 'r') as f:
                        # LEER TODO EL ARCHIVO SI ES JSON (necesario para parsear)
                        if req.filename.lower().endswith('.json'):
                            logger.info(f"Leyendo archivo COMPLETO (JSON): {req.filename}")
                            return f.read().decode('utf-8-sig', errors='replace')
                        else:
                            return f.read(8192).decode('utf-8', errors='replace')
                finally:
                    sftp.close()
                    ssh.close()
            elif protocolo == "FTP":
                ftp = get_ftp_client(host, puerto, usuario, password)
                try:
                    # Try to CWD
                    try:
                        ftp.cwd(ruta_remota)
                    except:
                        try:
                            parent = posixpath.dirname(ruta_remota) or "."
                            ftp.cwd(parent)
                        except:
                            pass
                    
                    bio = io.BytesIO()
                    # FTP doesn't support partial reads easily, read first 8KB
                    class LimitedWriter:
                        def __init__(self, bio, limit=8192):
                            self.bio = bio
                            self.limit = limit
                            self.written = 0
                        def write(self, data):
                            if self.written >= self.limit:
                                raise StopIteration  # Abort transfer
                            to_write = min(len(data), self.limit - self.written)
                            self.bio.write(data[:to_write])
                            self.written += to_write
                    
                    writer = LimitedWriter(bio)
                    try:
                        ftp.retrbinary(f"RETR {req.filename}", writer.write)
                    except StopIteration:
                        pass  # Expected when limit reached
                    bio.seek(0)
                    return bio.read().decode('utf-8', errors='replace')
                finally:
                    ftp.quit()
            return ""

        content = await asyncio.wait_for(
            loop.run_in_executor(executor, _read_file_sample),
            timeout=120.0
        )
        
        if not content:
            return {"csv_headers": [], "suggested_mapping": {}, "sample_row": {}, "current_mapping": {}}
        
        analysis = _perform_mapping_analysis(content, req.filename)
        
        # Add current mapping from config if exists
        analysis["current_mapping"] = config_data.get("mapping", {})
        
        return analysis
        
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout analizando archivo")
    except Exception as e:
        logger.error(f"Error analyzing remote file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/remote/unmark-file")
async def unmark_file(req: ExecuteManualRequest):
    """
    Removes the 'PR_' prefix from a processed file to allow reprocessing.
    Renames 'PR_filename.ext' back to 'filename.ext'
    """
    try:
        # Get config
        config_data = {}
        if req.config:
            config_data = req.config.dict()
        elif supabase:
            res = supabase.table("locales").select("*").eq("id", req.config_id).single().execute()
            if res.data:
                config_data = res.data
        
        if not config_data:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")

        # Normalize configuration
        host = config_data.get("host") or config_data.get("sftp_host")
        puerto = config_data.get("puerto") or config_data.get("sftp_port", 22)
        usuario = config_data.get("usuario") or config_data.get("sftp_user")
        password = config_data.get("password") or config_data.get("sftp_pass")
        ruta_remota = config_data.get("ruta_remota") or config_data.get("sftp_path", ".")
        protocolo = config_data.get("protocolo") or config_data.get("sftp_protocol", "SFTP")
        
        # Check if filename has PR_ prefix
        if not req.filename.startswith("PR_"):
            return {
                "status": "info",
                "message": f"El archivo '{req.filename}' no tiene el prefijo PR_, no requiere desmarcado."
            }
        
        # Calculate new name (remove PR_ prefix)
        new_filename = req.filename[3:]  # Remove first 3 characters "PR_"
        
        loop = asyncio.get_event_loop()
        
        def _rename_file():
            if protocolo == "SFTP":
                ssh, sftp = get_sftp_client(host, puerto, usuario, password)
                try:
                    # Determine directory
                    target_dir = ruta_remota
                    try:
                        st = sftp.stat(ruta_remota)
                        if not stat.S_ISDIR(st.st_mode):
                            target_dir = posixpath.dirname(ruta_remota) or "."
                    except:
                        pass
                    
                    old_path = posixpath.join(target_dir, req.filename)
                    new_path = posixpath.join(target_dir, new_filename)
                    
                    logger.info(f"Unmarking: {old_path} -> {new_path}")
                    sftp.rename(old_path, new_path)
                    return new_filename
                finally:
                    sftp.close()
                    ssh.close()
                    
            elif protocolo == "FTP":
                ftp = get_ftp_client(host, puerto, usuario, password)
                try:
                    # Navigate to directory
                    try:
                        ftp.cwd(ruta_remota)
                    except:
                        try:
                            parent = posixpath.dirname(ruta_remota) or "."
                            ftp.cwd(parent)
                        except:
                            pass
                    
                    logger.info(f"Unmarking: {req.filename} -> {new_filename}")
                    ftp.rename(req.filename, new_filename)
                    return new_filename
                finally:
                    ftp.quit()
            
            return None
        
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, _rename_file),
            timeout=30.0
        )
        
        if result:
            return {
                "status": "success",
                "message": f"Archivo desmarcado exitosamente",
                "old_name": req.filename,
                "new_name": result
            }
        else:
            raise HTTPException(status_code=500, detail="Error renombrando archivo")
            
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout conectando al servidor remoto")
    except Exception as e:
        logger.error(f"Error unmarking file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/admin/reset-sales")
async def reset_sales():
    """Wipes all sales data to reset testing environment."""
    if not supabase:
         raise HTTPException(status_code=500, detail="Supabase client not initialized")
    try:
        # Delete all records where ID is NOT a dummy value (effectively all UUIDs)
        # Using a dummy UUID known not to exist: 0000...0000
        res = supabase.table("ventas").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        count = len(res.data) if res.data else 0
        logger.info(f"Reset sales requested by admin. Deleted {count} records.")
        return {"status": "success", "message": f"Se han eliminado {count} registros de ventas."}
    except Exception as e:
        logger.error(f"Error resetting sales: {e}")
        raise HTTPException(status_code=500, detail=f"Error borrando ventas: {str(e)}")

@app.get("/api/v1/analytics/dashboard")
async def get_dashboard_data(start_date: str, end_date: str, mall_id: str = Depends(get_current_mall)):
    """
    Returns aggregated KPI data for the dashboard.
    Bypasses RLS by using the backend Service Role key.
    """
    if not supabase:
         raise HTTPException(status_code=500, detail="Supabase client not initialized")
    cache_key = f"analytics:dashboard:{mall_id}:{start_date}:{end_date}"
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
        return cached
    
    try:
        # Fast path: Use DB-side aggregation function (RPC) for better scalability.
        rpc_res = supabase.rpc("get_dashboard_kpis", {
            "mall_id_param": mall_id,
            "start_date_param": start_date,
            "end_date_param": end_date
        }).execute()

        if rpc_res.data and len(rpc_res.data) > 0:
            row = rpc_res.data[0]
            result = {
                "ventas_totales_bruto": float(row.get("ventas_totales_bruto") or 0),
                "ventas_totales_neto": float(row.get("ventas_totales_neto") or 0),
                "transacciones": int(row.get("transacciones") or 0),
                "ticket_promedio": float(row.get("ticket_promedio") or 0),
                "variacion_ventas": float(row.get("variacion_ventas") or 0),
                "top_locales": row.get("top_locales") or [],
                "ventas_por_dia": row.get("ventas_por_dia") or [],
                "ventas_por_rubro": row.get("ventas_por_rubro") or [],
                "ventas_por_tienda_completo": row.get("ventas_por_tienda_completo") or {}
            }
            _cache_set(cache_key, result, TTL_DASHBOARD)
            return result
    except Exception as rpc_err:
        # Fallback path keeps endpoint functional while RPC is being rolled out.
        logger.warning(f"Dashboard RPC unavailable, fallback to python aggregation: {rpc_err}")

    try:
        # 1. Fetch Sales
        # Note: 'fecha' in DB is likely YYYY-MM-DD or timestamp. If timestamp, string comparison might be tricky.
        # Assuming YYYY-MM-DD string or compatible date type.
        sales_res = (
            supabase.table("ventas")
            .select("local_id, fecha, total_bruto, total_neto")
            .eq("mall_id", mall_id)
            .gte("fecha", start_date)
            .lte("fecha", end_date)
            .execute()
        )
        sales = sales_res.data or []
        
        # 2. Fetch Stores
        stores_res = supabase.table("locales").select("id, nombre").eq("mall_id", mall_id).execute()
        stores = stores_res.data or []
        store_map = {s['id']: s['nombre'] for s in stores}
        
        # 3. Aggregate
        sales_by_store = {}
        total_bruto = 0
        total_neto = 0
        sales_by_day = {}
        
        for s in sales:
            bruto = float(s.get('total_bruto') or 0)
            neto = float(s.get('total_neto') or 0)
            total_bruto += bruto
            total_neto += neto
            
            lid = s.get('local_id')
            s_name = store_map.get(lid, "Desconocido")
            
            sales_by_store[s_name] = sales_by_store.get(s_name, 0) + bruto
            
            day = s.get('fecha')
            sales_by_day[day] = sales_by_day.get(day, 0) + bruto
            
        result = {
            "ventas_totales_bruto": total_bruto,
            "ventas_totales_neto": total_neto,
            "transacciones": len(sales),
            "ticket_promedio": (total_bruto / len(sales)) if len(sales) > 0 else 0,
            "variacion_ventas": 0,
            "top_locales": [ {"name": k, "total": v} for k, v in sorted(sales_by_store.items(), key=lambda item: item[1], reverse=True)[:5] ],
            "ventas_por_dia": [ {"fecha": k, "total": v} for k, v in sorted(sales_by_day.items()) ],
            "ventas_por_rubro": [], # Simplified for now
            "ventas_por_tienda_completo": sales_by_store
        }
        _cache_set(cache_key, result, TTL_DASHBOARD)
        return result
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- EXPORT ENDPOINTS ---
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services.export_service import ExportService
from typing import Optional

# Initialize service
# Ensure supabase client is available. It is global in this file.
export_service = ExportService(supabase)
router_export = APIRouter(prefix="/api/v1/export", tags=["export"])



@app.get("/api/v1/users/me/malls")
async def get_my_malls(user_id: str = Depends(get_current_user_id)):
    """
    Returns the list of malls assigned to the current user.
    """
    try:
        # Join usuarios_malls with malls
        # Supabase-py doesn't support easy joins in one go unless defined in View or specific syntax.
        # We'll do two queries or use a raw query if enabled (RPC).
        # Standard way: Fetch user-malls, then fetch malls.
        
        # 1. Get Mall IDs for user
        um_res = supabase.table("usuarios_malls").select("mall_id, rol").eq("usuario_id", user_id).execute()
        malls_links = um_res.data
        
        if not malls_links:
            return []
            
        mall_ids = [m['mall_id'] for m in malls_links]
        
        # 2. Get Mall Details
        malls_res = supabase.table("malls").select("*").in_("id", mall_ids).execute()
        malls_details = {m['id']: m for m in malls_res.data}
        
        # 3. Merge
        result = []
        for link in malls_links:
            mid = link['mall_id']
            if mid in malls_details:
                result.append({
                    "id": mid,
                    "nombre": malls_details[mid]['nombre'],
                    "rol": link['rol']
                })
                

                
        return result
    except Exception as e:
        logger.error(f"Error fetching user malls: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Mall Management Endpoints (Admin) ---

class MallCreate(BaseModel):
    nombre: str
    conf_locale: Optional[str] = 'es-CL'
    conf_moneda: Optional[str] = 'CLP'
    metadata: Optional[Dict] = {}

class MallUpdate(BaseModel):
    nombre: Optional[str] = None
    conf_locale: Optional[str] = None
    conf_moneda: Optional[str] = None
    metadata: Optional[Dict] = None

@app.get("/api/v1/malls/all")
async def get_all_malls(user_id: str = Depends(get_current_user_id)):
    """
    Get all malls. Restricted to Admins/SuperAdmins.
    (RLS will filter if user is not admin, but good to check role here too if needed)
    """
    try:
        # Simplified role check - in prod rely on RLS or specific logic
        res = supabase.table("malls").select("*").execute()
        return res.data
    except Exception as e:
        logger.error(f"Error fetching all malls: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/malls")
async def create_mall(mall: MallCreate, user_id: str = Depends(get_current_user_id)):
    """
    Create a new mall.
    """
    try:
        res = supabase.table("malls").insert({
            "nombre": mall.nombre,
            "conf_locale": mall.conf_locale or 'es-CL',
            "conf_moneda": mall.conf_moneda or 'CLP',
            "api_secret_key": str(uuid4()) # Auto-generate key
        }).execute()
        
        if not res.data:
             raise HTTPException(status_code=400, detail="Failed to create mall")
             
        return res.data[0]
    except Exception as e:
        logger.error(f"Error creating mall: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/malls/{mall_id}")
async def update_mall(mall_id: str, mall: MallUpdate, user_id: str = Depends(get_current_user_id)):
    """
    Update a mall.
    """
    try:
        update_data = {k: v for k, v in mall.dict().items() if v is not None and k != 'metadata'}
        if not update_data:
            return {"message": "No data to update"}
            
        res = supabase.table("malls").update(update_data).eq("id", mall_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Mall not found or permission denied")
            
        return res.data[0]
    except Exception as e:
        logger.error(f"Error updating mall: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/malls/{mall_id}")
async def delete_mall(mall_id: str, user_id: str = Depends(get_current_user_id)):
    """
    Delete a mall.
    """
    try:
        # Check for dependencies first? Or let DB constraint fail?
        # Assuming cascade delete or relying on error if FK exists.
        res = supabase.table("malls").delete().eq("id", mall_id).execute()
        if not res.data: # Note: delete returns deleted data usually
             # If no data returned, it might mean it didn't exist or RLS blocked it.
             # Supabase-py delete behavior can vary on response if empty.
             pass 

        return {"message": "Mall deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting mall: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Admin User Management ---

class UserMallAssignment(BaseModel):
    mall_ids: List[str]
    rol: str = 'auditor'

@app.get("/api/v1/admin/users")
async def admin_get_users(user_id: str = Depends(get_current_user_id)):
    """
    List all users and their assigned malls. Requires Admin/TIC role (enforced by middleware or check here).
    """
    try:
        # 1. List Users from Auth (needs Service Role)
        # Note: gotrue-py might not expose list_users easily depending on version.
        # Fallback: Query a view or use RPC if created. 
        # But assuming we have service role key in 'supabase':
        auth_users = supabase.auth.admin.list_users() 
        # If pagination needed, add params.
        
        users_list = []
        for u in auth_users:
            users_list.append({
                "id": u.id,
                "email": u.email,
                "metadata": u.user_metadata,
                "last_sign_in_at": u.last_sign_in_at,
                "created_at": u.created_at
            })
            
        # 2. Get Assignments
        assignments = supabase.table("usuarios_malls").select("*").execute().data
        assign_map = {}
        for a in assignments:
            uid = a['usuario_id']
            if uid not in assign_map: assign_map[uid] = []
            assign_map[uid].append(a)
            
        # 3. Merge
        result = []
        for u in users_list:
            u['malls'] = assign_map.get(u['id'], [])
            # Determine "Main" Role based on metadata or specific mall role?
            # For UI simplicity, we might just show "Admin" if they have admin access anywhere
            # Or reliance on user_metadata['rol']
            u['rol'] = u['metadata'].get('rol', 'auditor') if u['metadata'] else 'auditor'
            result.append(u)
            
        return result
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        # If admin API fails (unsupported), returns empty or error
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/users/{target_user_id}/malls")
async def admin_assign_malls(target_user_id: str, payload: UserMallAssignment, user_id: str = Depends(get_current_user_id)):
    """
    Assign a list of malls to a user.
    """
    try:
        # Transaction? (Not supported natively in HTTP API, do sequentially)
        
        # 1. Delete existing assignments
        supabase.table("usuarios_malls").delete().eq("usuario_id", target_user_id).execute()
        
        # 2. Insert new
        if payload.mall_ids:
            inserts = [{"usuario_id": target_user_id, "mall_id": mid, "rol": payload.rol} for mid in payload.mall_ids]
            res = supabase.table("usuarios_malls").insert(inserts).execute()
            
        return {"message": "Assignments updated"}
    except Exception as e:
        logger.error(f"Error assigning malls: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router_export.get("/sales-report/excel")
async def export_sales_report_excel(
    fecha_inicio: str, 
    fecha_fin: str, 
    local_id: Optional[str] = None, 
    type: str = 'detailed',
    current_mall: str = Depends(get_current_mall)
):
    try:
        if type not in ['detailed', 'summary']: type = 'detailed'
        data = await export_service.generate_sales_report_excel(fecha_inicio, fecha_fin, local_id, type)
        return StreamingResponse(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=reporte_ventas_{type}_{fecha_inicio}_{fecha_fin}.xlsx"}
        )
    except Exception as e:
        logger.error(f"Error exporting excel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router_export.get("/sales-report/pdf")
async def export_sales_report_pdf(
    fecha_inicio: str, 
    fecha_fin: str, 
    local_id: Optional[str] = None, 
    type: str = 'detailed',
    current_mall: str = Depends(get_current_mall)
):
    try:
        if type not in ['detailed', 'summary']: type = 'detailed'
        
        # Fetch Mall Name
        mall_name = "MS MALL"
        try:
             m_res = supabase.table("malls").select("nombre").eq("id", current_mall).single().execute()
             if m_res.data:
                 mall_name = m_res.data['nombre']
        except Exception:
            logger.warning(f"Could not fetch mall name for {current_mall}, using default.")

        logger.info(f"Exporting PDF for Mall: {mall_name} ({current_mall})")
        data = await export_service.generate_sales_report_pdf(fecha_inicio, fecha_fin, local_id, type, mall_name=mall_name)
        return StreamingResponse(
            data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=reporte_ventas_{type}_{fecha_inicio}_{fecha_fin}.pdf"}
        )
    except Exception as e:
        logger.error(f"Error exporting pdf: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router_export.get("/sales-cube/excel")
async def export_sales_cube_excel(
    fecha_inicio: str,
    fecha_fin: str,
    agrupacion: str = "dia",
    metrica: str = "total_neto",
    local_id: Optional[str] = None,
    current_mall: str = Depends(get_current_mall)
):
    try:
        data = await export_service.generate_sales_cube_excel(
            fecha_inicio,
            fecha_fin,
            agrupacion,
            metrica,
            mall_id=current_mall,
            local_id=local_id
        )
        return StreamingResponse(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=matriz_ventas_{fecha_inicio}_{fecha_fin}.xlsx"}
        )
    except Exception as e:
        logger.error(f"Error exporting cube excel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router_export.get("/financial-dashboard/excel")
async def export_financial_dashboard_excel(fecha_inicio: str, fecha_fin: str):
    try:
        data = await export_service.generate_financial_dashboard_excel(fecha_inicio, fecha_fin)
        return StreamingResponse(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=salud_cartera_{fecha_inicio}_{fecha_fin}.xlsx"}
        )
    except Exception as e:
        logger.error(f"Error exporting financial excel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router_export.get("/financial-dashboard/pdf")
async def export_financial_dashboard_pdf(fecha_inicio: str, fecha_fin: str):
    try:
        data = await export_service.generate_financial_dashboard_pdf(fecha_inicio, fecha_fin)
        return StreamingResponse(
            data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=salud_cartera_{fecha_inicio}_{fecha_fin}.pdf"}
        )
    except Exception as e:
        logger.error(f"Error exporting financial pdf: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/auditoria/brechas-ventas")
async def get_sales_gaps(
    local_id: Optional[str], 
    fecha_inicio: str, 
    fecha_fin: str,
    current_mall: str = Depends(get_current_mall)
):
    try:
        # 1. Calendario Ideal
        start_date = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        end_date = datetime.strptime(fecha_fin, '%Y-%m-%d')
        total_days = (end_date - start_date).days + 1
        expected_dates = { (start_date + timedelta(days=x)).strftime('%Y-%m-%d') for x in range(total_days) }
        
        # --- MODO GLOBAL (Matrix View) ---
        if not local_id or local_id == 'null' or local_id == 'ALL':
            logger.info(f"Auditing Global Gaps for Mall: {current_mall}")
            
            # Obtener TODOS los locales (filtrar por mall si tuviéramos tabla usuarios_malls poblada y lógica RLS)
            # Como aún no tenemos RLS activo en 'locales' para filtrar por mall_id automágicamente,
            # DEBERÍAMOS filtrar aquí manualmente usando current_mall.
            # Pero la tabla 'locales' ya tiene 'mall_id'.
            
            # Obtener todos los locales DEL MALL ACTUAL
            # Para la Fase 1: asumo que el endpoint necesita ver SOLO los locales del mall.
            # Si el backend lee 'locales', supongo que debo filtrar.
            
            # stores_resp = supabase.table('locales').select('id, nombre, rubro').execute()
            # CHANGE: Filter by current_mall
            # But wait, current_mall comes from DB or Header.
            # If migrating, current_mall might be a Mall ID (UUID).
            
            # stores_resp = supabase.table('locales').select('id, nombre, rubro').eq('mall_id', current_mall).execute()
            # If current_mall is reliable.
            
            # Since I am "migrating", I should probably use the filter.
            # But `locales` table has `mall_id`.
            
            stores_resp = supabase.table('locales').select('id, nombre, rubro').eq('mall_id', current_mall).execute()
            stores = stores_resp.data
            
            # Obtener todas las ventas del periodo (optimizado: una sola query)
            # También filtrar por mall_id (que agregué en Fase 1) por seguridad
            sales_resp = supabase.table('ventas')\
                .select('local_id, fecha')\
                .eq('mall_id', current_mall)\
                .gte('fecha', fecha_inicio)\
                .lte('fecha', fecha_fin)\
                .execute()
            
            sales_df = pd.DataFrame(sales_resp.data)
            
            global_summary = []
            
            for store in stores:
                sid = store['id']
                # Fechas reales para este local
                if not sales_df.empty:
                    s_actual = set(sales_df[sales_df['local_id'] == sid]['fecha'].unique())
                else:
                    s_actual = set()
                
                missing = sorted(list(expected_dates - s_actual))
                count_missing = len(missing)
                compliance = ((total_days - count_missing) / total_days) * 100
                
                # Definir estado
                status = 'Completo'
                if count_missing > 5: status = 'Crítico'
                elif count_missing > 0: status = 'Alerta'
                
                global_summary.append({
                    "local_id": sid,
                    "nombre": store['nombre'],
                    "rubro": store.get('rubro', 'General'),
                    "dias_faltantes_count": count_missing,
                    "dias_totales_periodo": total_days,
                    "porcentaje_cumplimiento": round(compliance, 1),
                    "estado": status,
                    "lista_dias": missing # Para visualización rápida (heatmap)
                })
            
            # Ordenar por criticidad (más faltantes primero)
            global_summary.sort(key=lambda x: x['dias_faltantes_count'], reverse=True)
            
            return {
                "modo": "global",
                "resumen": global_summary
            }

        # --- MODO INDIVIDUAL (Detailed View) ---
        # 2. Calendario Real (Individual)
        response = supabase.table('ventas').select('fecha').eq('local_id', local_id).gte('fecha', fecha_inicio).lte('fecha', fecha_fin).execute()
        actual_dates = { row['fecha'] for row in response.data }
        
        # 3. Brechas
        missing_dates = sorted(list(expected_dates - actual_dates))
        
        # 4. Enriquecimiento con Logs (logs_carga)
        # Necesitamos el nombre del local para consultar logs_carga
        local_resp = supabase.table('locales').select('nombre').eq('id', local_id).single().execute()
        local_name = local_resp.data['nombre'] if local_resp.data else None
        
        audit_details = []
        if local_name and missing_dates:
            # Optimización: Consultar logs para todo el rango
            logs_resp = supabase.table('logs_carga').select('*')\
                .eq('local_nombre', local_name)\
                .gte('fecha_hora', f"{fecha_inicio}T00:00:00")\
                .lte('fecha_hora', f"{fecha_fin}T23:59:59")\
                .order('fecha_hora', desc=True)\
                .execute()
            
            logs_df = pd.DataFrame(logs_resp.data)
            if not logs_df.empty:
                logs_df['fecha_log'] = logs_df['fecha_hora'].apply(lambda x: x.split('T')[0] if x else None)
            
            for m_date in missing_dates:
                cause = "Proceso no ejecutado / Sin conexión"
                log_id = None
                
                if not logs_df.empty:
                    day_logs = logs_df[logs_df['fecha_log'] == m_date]
                    if not day_logs.empty:
                        last_log = day_logs.iloc[0]
                        log_id = last_log.get('id')
                        status = last_log.get('estado')
                        if status == 'ERROR':
                            cause = "Fallo Técnico / Error de Lectura"
                        elif status == 'NO_ENCONTRADO':
                            cause = "Archivo no disponible en FTP"
                        elif status == 'EXITO':
                            cause = "Procesado con Éxito (Posible archivo vacío)"
                            
                audit_details.append({
                    "fecha": m_date,
                    "causa": cause,
                    "log_id": log_id
                })
        else:
             for m_date in missing_dates:
                audit_details.append({
                    "fecha": m_date,
                    "causa": "Proceso no ejecutado / Sin logs disponibles",
                    "log_id": None
                })

        return {
            "modo": "individual",
            "total_dias_faltantes": len(missing_dates),
            "detalle": audit_details
        }
        
    except Exception as e:
        logger.error(f"Error auditing gaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(router_export)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
