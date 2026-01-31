
# Backend: FastAPI API para MSMALL Audit
import csv
import io
import logging
import time
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Depends, Query, status, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from thefuzz import process, fuzz
import paramiko
import json
import xmltodict
from ftplib import FTP
import stat
from worker_importacion import run_worker
from analytics import generate_sales_cube
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


app = FastAPI(title="MSMALL Sales Audit API", version="1.0.0")

async def scheduler_loop():
    await asyncio.sleep(10) # Initial delay
    while True:
        logger.info("[Scheduler] Iniciando ciclo de importación automática...")
        try:
            await asyncio.to_thread(run_worker)
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

def process_file_content(content: str, filename: str, config: Dict[str, Any], batch_id: str):
    """
    Parses content based on config mapping and inserts into Supabase 'ventas' table.
    Returns (success_count, errors_list).
    """
    mapping = config.get("mapping", {})
    constants = config.get("constants", {})
    tipo_archivo = config.get("tipo_archivo", "CSV")
    local_nombre = config.get("nombre", "Desconocido")
    
    records_to_insert = []
    errors = []
    
    # Intento de refrescar caché de esquema haciendo una consulta dummy
    try:
        supabase.table("ventas").select("count", count="exact").limit(0).execute()
    except:
        pass
    
    try:
        if tipo_archivo == "CSV" or tipo_archivo == "TXT":
            f = io.StringIO(content)
            # Detect delimiter
            sample = content[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample)
                delimiter = dialect.delimiter
            except:
                delimiter = ","
            
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delimiter)
            
            # Log CSV headers for debugging
            if reader.fieldnames:
                logger.info(f"Headers del CSV: {reader.fieldnames}")
            
            # Validar mapeo básico - un campo puede estar en mapping o constants
            req_sys_fields = ['factura_numero', 'fecha_venta', 'local_codigo', 'total_bruto']
            missing_mapping = []
            for field in req_sys_fields:
                # Field is valid if it exists in mapping (and has a value) OR in constants
                has_mapping = field in mapping and mapping[field]
                has_constant = field in constants and constants[field]
                if not (has_mapping or has_constant):
                    missing_mapping.append(field)
            
            if missing_mapping:
                logger.error(f"Mapeo incompleto. Faltan: {', '.join(missing_mapping)}")
                logger.error(f"Mapping recibido: {mapping}")
                logger.error(f"Constants recibidos: {constants}")
                return 0, [{"linea": 0, "error": f"Mapeo incompleto. Faltan: {', '.join(missing_mapping)}"}]

            for i, row in enumerate(reader):
                try:
                    record = {}
                    # 1. Apply Mapping
                    for sys_field, csv_header in mapping.items():
                        if csv_header in row:
                            record[sys_field] = row[csv_header]
                    
                    # 2. Apply Constants
                    for k, v in constants.items():
                        record[k] = v
                    
                    # Log first record for debugging
                    if i == 0:
                        logger.info(f"Primer registro procesado: {record}")
                    
                    # 3. Validation & Type Casting
                    if not record.get('factura_numero') or not record.get('fecha_venta'):
                        errors.append({"linea": i+2, "error": "Faltan datos obligatorios (Factura o Fecha)"})
                        continue

                    # Normalize Date Format to YYYY-MM-DD
                    if record.get('fecha_venta'):
                        try:
                            raw_date = str(record['fecha_venta']).strip()
                            # Try common formats
                            parsed_date = None
                            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                                try:
                                    parsed_date = datetime.strptime(raw_date, fmt)
                                    break
                                except ValueError:
                                    continue
                            
                            if parsed_date:
                                record['fecha_venta'] = parsed_date.strftime('%Y-%m-%d')
                            else:
                                # Fallback: try Dateutil if available or keep raw (might error in DB)
                                pass 
                        except Exception as e:
                            logger.warning(f"Error parseando fecha {record['fecha_venta']}: {e}")
                    
                    # Ensure numeric types
                    for num_field in ['total_bruto', 'total_impuestos', 'total_neto']:
                        if record.get(num_field):
                            try:
                                val = str(record[num_field]).replace(',', '')
                                record[num_field] = float(val)
                            except:
                                record[num_field] = 0.0
                    
                    records_to_insert.append(record)
                except Exception as row_e:
                    errors.append({"linea": i+2, "error": str(row_e)})

                except Exception as row_e:
                    errors.append({"linea": i+2, "error": str(row_e)})

        elif tipo_archivo == "JSON":
            try:
                data = json.loads(content)
                if not isinstance(data, list):
                    # Try to find list inside
                    for k, v in data.items():
                        if isinstance(v, list):
                            data = v
                            break
                
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        record = {}
                        for sys_field, json_key in mapping.items():
                            if json_key in item: record[sys_field] = item[json_key]
                        for k, v in constants.items(): record[k] = v
                        records_to_insert.append(record)
            except Exception as e:
                errors.append({"linea": 0, "error": f"Invalid JSON: {str(e)}"})

        # --- DB SCHEMA MAPPING & RESOLUTION ---
        final_records = []
        
        # 1. Resolve Local UUIDs cache
        local_codigos = set(r.get('local_codigo') for r in records_to_insert if r.get('local_codigo'))
        local_map = {} # codigo -> uuid
        
        if local_codigos and supabase:
            try:
                # Query locales table to find UUIDs for these codes
                # La columna correcta es 'codigo_interno'
                res = supabase.table("locales").select("id, codigo_interno").in_("codigo_interno", list(local_codigos)).execute()
                for loc in res.data:
                    local_map[loc['codigo_interno']] = loc['id']
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
            
            # La columna en BD es 'total_impuestos' (plural), así que NO renombramos.
            # if 'total_impuestos' in new_r:
            #     new_r['total_impuesto'] = new_r.pop('total_impuestos')

            # Normalizar campos de hora (hora, hora_transaccion)
            for time_col in ['hora', 'hora_transaccion']:
                if time_col in new_r and new_r[time_col]:
                    val = str(new_r[time_col]).strip()
                    # Si es solo un número (ej: "10"), asumir hora en punto
                    if val.isdigit():
                        if int(val) < 24:
                            new_r[time_col] = f"{int(val):02d}:00:00"
                    # Si viene como "10:30" agregar segundos
                    elif val.count(':') == 1:
                        new_r[time_col] = f"{val}:00"
                    # Si tiene AM/PM, intentar parsear (básico)
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

            # Resolve Local ID
            l_code = new_r.get('local_codigo')
            if l_code:
                if l_code in local_map:
                    new_r['local_id'] = local_map[l_code]
                    del new_r['local_codigo'] # Remove text code, keep UUID
                else:
                    # Warning: Local not found. 
                    # If local_id is nullable, we can proceed. If required, this will fail.
                    # We'll try to keep local_codigo just in case the DB accepts it (unlikely) 
                    # OR we remove it to avoid "column not found" error if column doesn't exist.
                    # The image shows local_id is likely required or FK.
                    logger.warning(f"No UUID found for local_codigo: {l_code}")
                    del new_r['local_codigo'] 
            
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
    api_key: str = Depends(verify_api_key)
):
    """
    Endpoint principal para que los locales envíen sus ventas diarias.
    Acepta un archivo y procesa según la configuración del local (basado en el API Key o headers).
    """
    batch_id = str(uuid4())
    try:
        content_bytes = await file.read()
        content = content_bytes.decode('utf-8', errors='replace')
        
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
        
        count, errors = process_file_content(content, file.filename, config, batch_id)
        
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

def get_sftp_client(host, port, user, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # Aumentar timeouts y deshabilitar búsqueda de llaves locales para mayor velocidad
    client.connect(
        host, 
        port=port, 
        username=user, 
        password=password, 
        timeout=25, 
        banner_timeout=25, 
        auth_timeout=25,
        look_for_keys=False,
        allow_agent=False
    )
    return client, client.open_sftp()

def get_ftp_client(host, port, user, password):
    ftp = FTP()
    ftp.connect(host, port, timeout=25)
    ftp.login(user, password)
    return ftp

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
    try:
        res = supabase.table("ventas").select("fecha, hora_transaccion").eq("local_id", local_id).limit(2000).execute()
        if not res.data: return []
        
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
        return result
    except:
        return []

@app.get("/api/v1/insights/ranking")
async def get_ranking(metric: str):
    """Get ranking of all stores for a specific metric based on real database data."""
    if not supabase: return []
    try:
        # 1. Fetch all stores
        stores_res = supabase.table("locales").select("id, nombre, mts, rubro").execute()
        if not stores_res.data: return []
        
        # 2. Fetch all sales
        sales_res = supabase.table("ventas").select("local_id, total_bruto, total_neto").execute()
        
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
        return ranking
    except Exception as e:
        logger.error(f"Error in ranking: {e}")
        return []

class CubeRequest(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    agrupacion: str = "DIA" # DIA, SEMANA, MES
    metrica: str = "total_neto" # total_neto, total_bruto, transacciones

# --- INTELLIGENT AUTO-MAPPING ---
SYSTEM_FIELDS_SYNONYMS = {
    "factura_numero": ["invoice", "factura", "doc_num", "documento", "folio", "ticket", "recibo"],
    "fecha_venta": ["date", "fecha", "time", "dia", "issued", "created"],
    "local_codigo": ["store", "local", "tienda", "sucursal", "code", "id_local"],
    "total_bruto": ["gross", "bruto", "total", "amount", "monto", "venta", "precio", "importe"],
    "total_impuestos": ["tax", "impuesto", "iva", "vat", "tributes"],
    "total_neto": ["net", "neto", "subtotal", "base"],
    "comprobante": ["ticket", "vourcher", "comprobante", "recibo", "doc_type"],
    "hora_transaccion": ["time", "hora", "trans_hour", "momento"]
}

def _perform_mapping_analysis(decoded_content, filename):
    headers = []
    sample_row = {}
    
    # 1. Detect Format and Extract Headers/Sample
    if filename.lower().endswith('.csv') or filename.lower().endswith('.txt'):
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
            return {"headers": [], "suggested_mapping": {}, "sample_row": {}}
            
    elif filename.lower().endswith('.json'):
        try:
            data = json.loads(decoded_content)
            if isinstance(data, list) and len(data) > 0:
                headers = list(data[0].keys())
                sample_row = data[0]
            elif isinstance(data, dict):
                 # Try to find array inside
                found_list = False
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                         headers = list(v[0].keys())
                         sample_row = v[0]
                         found_list = True
                         break
                if not found_list:
                    headers = list(data.keys())
                    sample_row = data
        except:
             return {"headers": [], "suggested_mapping": {}, "sample_row": {}}
    
    if not headers:
        return {"headers": [], "suggested_mapping": {}, "sample_row": {}}

    # 2. Fuzzy Match System Fields
    suggested_mapping = {}
    
    for sys_field, synonyms in SYSTEM_FIELDS_SYNONYMS.items():
        query_list = [sys_field] + synonyms
        best_match = None
        best_score = 0
        
        for query in query_list:
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
        decoded = content.decode('utf-8', errors='replace')
        return _perform_mapping_analysis(decoded, file.filename)
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
            if req.protocolo == "SFTP":
                ssh, sftp = get_sftp_client(req.host, req.puerto, req.usuario, req.password)
                try:
                    with sftp.open(req.ruta, 'r') as f:
                        # Read first 8KB for analysis
                        return f.read(8192).decode('utf-8', errors='replace')
                finally:
                    sftp.close()
                    ssh.close()
            elif req.protocolo == "FTP":
                ftp = get_ftp_client(req.host, req.puerto, req.usuario, req.password)
                try:
                    bio = io.BytesIO()
                    # Use a custom rest/retr to only get a part? 
                    # FTP RETR usually gets the whole file. 
                    # For simplicity, we'll try to read enough or the whole if small.
                    # Warning: Big files on FTP might be slow here.
                    ftp.retrbinary(f"RETR {req.ruta.split('/')[-1]}", bio.write)
                    bio.seek(0)
                    return bio.read(8192).decode('utf-8', errors='replace') 
                finally:
                    ftp.quit()
            return ""

        # Usar wait_for para evitar hangs si el archivo es gigante o la red falla
        content = await asyncio.wait_for(
            loop.run_in_executor(executor, _read_remote_sample),
            timeout=45.0
        )
        if not content:
            return {"headers": [], "suggested_mapping": {}, "sample_row": {}}
            
        return _perform_mapping_analysis(content, req.ruta)
        
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
    
    ext = ".csv" if tipo_archivo == "CSV" else ".txt" if tipo_archivo == "TXT" else ".json"
    
    if not host or not usuario:
        logger.error(f"Missing connection parameters: host={host}, user={usuario}")
        return []

    files = []
    if protocolo == "SFTP":
        ssh, sftp = get_sftp_client(host, puerto, usuario, password)
        try:
            # Si la ruta es un archivo, listar su directorio contenedor
            try:
                st = sftp.stat(ruta)
                if not stat.S_ISDIR(st.st_mode):
                    ruta = posixpath.dirname(ruta) or "."
            except:
                pass

            for attr in sftp.listdir_attr(ruta):
                if not stat.S_ISDIR(attr.st_mode):
                    if attr.filename.lower().endswith(ext):
                        files.append({
                            "nombre": attr.filename,
                            "fecha": datetime.fromtimestamp(attr.st_mtime).isoformat(),
                            "tamano": attr.st_size
                        })
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
                    if name.lower().endswith(ext):
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
                        content = f.read().decode('utf-8', errors='replace')
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
                    ftp.retrbinary(f"RETR {req.filename}", bio.write)
                    bio.seek(0)
                    content = bio.read().decode('utf-8', errors='replace')
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
        if registros_exito > 0:
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
        logger.error(f"Error en ejecución manual: {e}")
        if 'local_nombre' in locals():
            insert_load_log(local_nombre, req.filename, "error", str(e), batch_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/analytics/cubo")
async def get_sales_cube(request: CubeRequest):
    """
    Endpoint para generar el Cubo de Ventas (Matriz) usando datos reales de Supabase (Service Role).
    """
    try:
        # 1. Fetch Locales (Store Map)
        stores_res = supabase.table("locales").select("id, nombre").execute()
        stores = stores_res.data or []
        store_map = {str(s['id']): s['nombre'] for s in stores}
        
        # 2. Fetch Sales within date range
        # Note: Using service role key bypasses RLS
        sales_res = supabase.table("ventas")\
            .select("local_id, fecha, total_bruto, total_neto, id")\
            .gte("fecha", request.fecha_inicio)\
            .lte("fecha", request.fecha_fin)\
            .execute()
        sales_data = sales_res.data or []
        
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
        result = generate_sales_cube(df, request.agrupacion, request.metrica)
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
            timeout=45.0
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
async def get_dashboard_data(start_date: str, end_date: str):
    """
    Returns aggregated KPI data for the dashboard.
    Bypasses RLS by using the backend Service Role key.
    """
    if not supabase:
         raise HTTPException(status_code=500, detail="Supabase client not initialized")
    
    try:
        # 1. Fetch Sales
        # Note: 'fecha' in DB is likely YYYY-MM-DD or timestamp. If timestamp, string comparison might be tricky.
        # Assuming YYYY-MM-DD string or compatible date type.
        sales_res = supabase.table("ventas").select("*").gte("fecha", start_date).lte("fecha", end_date).execute()
        sales = sales_res.data or []
        
        # 2. Fetch Stores
        stores_res = supabase.table("locales").select("*").execute()
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
            
        return {
            "ventas_totales_bruto": total_bruto,
            "ventas_totales_neto": total_neto,
            "transacciones": len(sales),
            "ticket_promedio": (total_bruto / len(sales)) if len(sales) > 0 else 0,
            "top_locales": [ {"name": k, "total": v} for k, v in sorted(sales_by_store.items(), key=lambda item: item[1], reverse=True)[:5] ],
            "ventas_por_dia": [ {"fecha": k, "total": v} for k, v in sorted(sales_by_day.items()) ],
            "ventas_por_rubro": [], # Simplified for now
            "ventas_por_tienda_completo": sales_by_store
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
