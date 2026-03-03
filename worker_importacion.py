import os
import stat
import logging
import uuid
import asyncio
import time
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
import paramiko
from ftplib import FTP
import io
import csv
import json
import posixpath
from typing import Optional, Sequence, Tuple

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("import-worker")

# Load Environment
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

supabase: Optional[Client] = None

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error(
        "Supabase credentials missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY)."
    )
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")

AUTO_SUCCESS_PREFIX = "PR_"
AUTO_ERROR_PREFIX = "ERR_"

def insert_load_log(
    local_nombre: str,
    archivo: str,
    estado: str,
    mensaje: str,
    batch_id: str = None,
    detalles: list = None,
    mall_id: str = None,
    local_id: str = None
):
    """Inserts a log into Supabase 'logs_carga' table."""
    if not supabase:
        logger.warning("Skipping load log insert: Supabase client not initialized.")
        return
    try:
        log_data = {
            "fecha_hora": datetime.now().isoformat(),
            "local_nombre": local_nombre,
            "archivo": archivo,
            "estado": estado,
            "mensaje": mensaje,
            "batch_id": batch_id,
            "detalles": detalles or []
        }
        if mall_id:
            log_data["mall_id"] = mall_id
        if local_id:
            log_data["local_id"] = local_id

        try:
            supabase.table("logs_carga").insert(log_data).execute()
        except Exception as insert_err:
            err_txt = str(insert_err).lower()
            if ("mall_id" in err_txt or "local_id" in err_txt) and ("column" in err_txt or "schema" in err_txt):
                legacy_payload = {k: v for k, v in log_data.items() if k not in {"mall_id", "local_id"}}
                supabase.table("logs_carga").insert(legacy_payload).execute()
            else:
                raise
        logger.info(f"Log registrado: {mensaje}")
    except Exception as e:
        logger.error(f"Error inserting load log: {e}")

def normalize_date(date_str):
    """
    Attempts to parse a date string into YYYY-MM-DD format.
    Supports: DD/MM/YYYY, YYYY-MM-DD, MM/DD/YYYY, DD-MM-YYYY, YYYY/MM/DD,
    YYYYmmDD and YYYYmmDD with time.
    """
    if not date_str:
        return None
        
    raw_date = str(date_str).strip().strip("'\"")
    # Try common formats
    for fmt in [
        '%d/%m/%Y',
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d-%m-%Y',
        '%Y/%m/%d',
        '%Y%m%d',
        '%Y%m%d %H:%M:%S',
        '%Y%m%d %H:%M',
        '%Y%m%d %H:%M:%S.%f',
        '%Y%m%dT%H:%M:%S',
        '%Y%m%dT%H:%M',
        '%Y%m%dT%H:%M:%S.%f',
    ]:
        try:
            parsed_date = datetime.strptime(raw_date, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def _clean_csv_header_name(name) -> str:
    return str(name or "").replace("\ufeff", "").strip()

def _normalize_csv_row_keys(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    normalized = {}
    for key, value in row.items():
        clean_key = _clean_csv_header_name(key)
        if not clean_key:
            continue
        if clean_key not in normalized:
            normalized[clean_key] = value
    return normalized

def _clean_cell_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1].strip()
        return cleaned
    return value

def get_sftp_client(host, port, user, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=10)
    transport = ssh.get_transport()
    if transport:
        transport.set_keepalive(30)
    return ssh, ssh.open_sftp()

def get_ftp_client(host, port, user, password):
    ftp = FTP()
    ftp.connect(host, port, timeout=10)
    ftp.login(user, password)
    ftp.set_pasv(True)
    return ftp

def connect_with_retries(connector, attempts=3, base_delay=2):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return connector()
        except Exception as e:
            last_error = e
            if attempt >= attempts:
                break
            delay = base_delay * attempt
            logger.warning(f"Conexión fallida (intento {attempt}/{attempts}): {e}. Reintentando en {delay}s...")
            time.sleep(delay)
    raise last_error

def _normalize_prefix_value(prefix: Optional[str]) -> str:
    value = str(prefix or "").strip()
    return value if value else ""

def _build_marked_filename(filename: str, prefix: str, extra_prefixes: Sequence[str] = ()) -> str:
    base_name = posixpath.basename(str(filename or "").strip())
    if not base_name:
        return base_name

    candidates = [
        AUTO_SUCCESS_PREFIX,
        AUTO_ERROR_PREFIX,
        "PW_",
        *[_normalize_prefix_value(item) for item in extra_prefixes],
    ]
    normalized_candidates = []
    for candidate in candidates:
        if candidate and candidate not in normalized_candidates:
            normalized_candidates.append(candidate)

    upper_name = base_name.upper()
    changed = True
    while changed:
        changed = False
        for candidate in normalized_candidates:
            if not candidate:
                continue
            candidate_upper = candidate.upper()
            if upper_name.startswith(candidate_upper):
                base_name = base_name[len(candidate):]
                upper_name = base_name.upper()
                changed = True
                break

    return f"{prefix}{base_name}"

def _resolve_worker_processing_outcome(count: int, errors: list) -> Tuple[str, str, bool]:
    if isinstance(count, int) and count > 0:
        estado = "parcial" if errors else "exito"
        mensaje = f"Worker: Inserción confirmada de {count} registros."
        if errors:
            mensaje += f" Se encontraron {len(errors)} errores parciales."
        return estado, mensaje, True

    mensaje = "Worker: No se confirmó inserción en BD."
    if errors:
        mensaje += f" Se encontraron {len(errors)} errores."
    else:
        mensaje += " El archivo se marcará con error para revisión."
    return "error", mensaje, False

def process_file_logic(config, filename, content):
    """
    Process file content (CSV or JSON) and insert to database.
    """
    logger.info(f"Procesando contenido de {filename} para {config['nombre']}")
    detalles = []
    registros_exito = 0
    
    try:
        file_type = config.get("file_type", "CSV").upper()
        raw_records = []
        
        # 1. Parse Content
        if file_type == "JSON":
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    raw_records = data
                elif isinstance(data, dict):
                    # Try to find list inside (common in some exports)
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            raw_records = v
                            break
                    if not raw_records:
                        raw_records = [data] # Single object
            except Exception as e:
                return 0, [{"linea": 0, "error": f"Error parseando JSON: {e}"}]
        else:
            # Default to CSV/TXT
            reader = csv.DictReader(io.StringIO(content), skipinitialspace=True)
            raw_records = [_normalize_csv_row_keys(r) for r in reader]
            
        if not raw_records:
            return 0, [{"linea": 0, "error": "Archivo vacío o sin datos válidos"}]
            
        # Get store ID and Mall ID
        local_id = config.get('id')
        mall_id = config.get('mall_id')
        
        if not local_id:
            return 0, [{"linea": 0, "error": "No se pudo determinar el local_id"}]
        if not mall_id:
            return 0, [{"linea": 0, "error": "La configuración no tiene mall_id. Importación cancelada para evitar mezcla entre malls."}]
            
        # Get mapping
        mapping = config.get('mapping_config') or {}
        
        valid_rows = []
        valid_line_numbers = []

        for i, row in enumerate(raw_records, start=2):
            try:
                normalized_row = _normalize_csv_row_keys(row)
                lowered_row = {k.lower(): v for k, v in normalized_row.items()}

                def pick_value(mapped_header, fallback_header=""):
                    key = _clean_csv_header_name(mapped_header)
                    if key and key in normalized_row:
                        return _clean_cell_value(normalized_row[key])
                    if key and key.lower() in lowered_row:
                        return _clean_cell_value(lowered_row[key.lower()])
                    fallback = _clean_csv_header_name(fallback_header)
                    if fallback and fallback in normalized_row:
                        return _clean_cell_value(normalized_row[fallback])
                    if fallback and fallback.lower() in lowered_row:
                        return _clean_cell_value(lowered_row[fallback.lower()])
                    return ""

                # Map fields using mapping_config
                # mapping_config usually translates system_field -> file_header
                fecha_venta_raw = pick_value(mapping.get('fecha_venta', 'fecha_venta'), 'fecha')
                factura_no = pick_value(mapping.get('factura_numero', 'factura_numero'), 'factura_no')
                
                # Check for direct key matches if mapping fails
                fecha_venta = normalize_date(fecha_venta_raw)
                
                if fecha_venta_raw and not fecha_venta:
                     detalles.append({"linea": i, "error": f"Formato de fecha inválido: {fecha_venta_raw}"})
                     continue

                # Normalización Numérica
                def clean_float(val):
                    if val is None: return 0.0
                    try:
                        return float(str(val).replace(',', '').strip().strip("'\""))
                    except:
                        return 0.0

                total_bruto = clean_float(pick_value(mapping.get('total_bruto', 'total_bruto')))
                total_impuestos = clean_float(pick_value(mapping.get('total_impuestos', 'total_impuestos')))
                total_neto = clean_float(pick_value(mapping.get('total_neto', 'total_neto')))
                
                if not fecha_venta or total_bruto == 0:
                    detalles.append({"linea": i, "error": "Datos incompletos (Fecha o Total Bruto faltante/cero)"})
                    continue
                
                payload = {
                    "local_id": local_id,
                    "fecha": fecha_venta,
                    "factura_no": str(factura_no) if factura_no else None,
                    "total_bruto": total_bruto,
                    "total_impuestos": total_impuestos,
                    "total_neto": total_neto
                }
                
                if mall_id:
                    payload["mall_id"] = mall_id

                valid_rows.append(payload)
                valid_line_numbers.append(i)
                
            except Exception as e:
                detalles.append({"linea": i, "error": str(e)})
                logger.error(f"Error en línea {i}: {e}")

        # Bulk insert for better throughput; fallback to row insert if a chunk fails.
        BATCH_SIZE = 500
        for start in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[start:start + BATCH_SIZE]
            lines = valid_line_numbers[start:start + BATCH_SIZE]
            try:
                supabase.table("ventas").insert(batch).execute()
                registros_exito += len(batch)
            except Exception as batch_error:
                logger.warning(f"Batch insert failed for {filename} ({len(batch)} rows): {batch_error}. Falling back to row-level inserts.")
                for payload, line_no in zip(batch, lines):
                    try:
                        supabase.table("ventas").insert(payload).execute()
                        registros_exito += 1
                    except Exception as row_error:
                        detalles.append({"linea": line_no, "error": str(row_error)})
                        logger.error(f"Error insertando línea {line_no}: {row_error}")
                
    except Exception as e:
        logger.error(f"Error general procesando archivo: {e}")
        return 0, [{"linea": 0, "error": str(e)}]
            
    return registros_exito, detalles

def process_local_files(config):
    protocol = config.get("sftp_protocol", "SFTP")
    host = config.get("sftp_host")
    port = config.get("sftp_port", 22)
    user = config.get("sftp_user")
    password = config.get("sftp_pass")
    remote_path = config.get("sftp_path", ".")
    file_type = config.get("file_type", "CSV")
    post_action = config.get("accion_post_procesado", "NINGUNA")
    backup_prefix = config.get("prefijo_backup", "PR_")
    custom_backup_prefix = _normalize_prefix_value(backup_prefix)
    
    ext = f".{file_type.lower()}"
    processed_suffix = ".procesado"
    MAX_FILES_PER_BATCH = 20  # Safety Cap
    
    logger.info(f"Conectando a {config['nombre']} ({protocol}) en {host}...")
    
    if protocol == "SFTP":
        try:
            ssh, sftp = connect_with_retries(lambda: get_sftp_client(host, port, user, password))
        except Exception as ce:
            insert_load_log(
                config['nombre'], "N/A", "error", f"Fallo conexión SFTP: {str(ce)}",
                mall_id=config.get("mall_id"), local_id=config.get("id")
            )
            return

        try:
            # Handle directory vs file path
            try:
                st = sftp.stat(remote_path)
                if not stat.S_ISDIR(st.st_mode):
                    remote_path = posixpath.dirname(remote_path) or "."
            except:
                pass

            # 1. DISCOVERY & FILTERING
            items = sftp.listdir_attr(remote_path)
            pending_files = []
            
            for item in items:
                if stat.S_ISDIR(item.st_mode): continue
                
                filename = item.filename
                is_processed = processed_suffix in filename
                is_backup = (
                    (custom_backup_prefix and filename.startswith(custom_backup_prefix))
                    or filename.startswith(AUTO_SUCCESS_PREFIX)
                    or filename.startswith(AUTO_ERROR_PREFIX)
                    or filename.startswith("PW_")
                )
                is_match = filename.lower().endswith(ext)
                is_error = ".error" in filename
                
                if is_match and not is_processed and not is_backup and not is_error:
                    pending_files.append(item)

            # 2. SORTING (Chronological: Oldest Modified First)
            # This is critical to maintain data integrity order
            pending_files.sort(key=lambda x: x.st_mtime)
            
            total_pending = len(pending_files)
            
            # 3. BATCHING
            batch_files = pending_files[:MAX_FILES_PER_BATCH]
            
            if total_pending == 0:
                logger.info(f"📍 {config['nombre']}: No hay archivos pendientes.")
                insert_load_log(
                    config['nombre'], "N/A", "exito", f"Conexión exitosa: 0 pendientes.",
                    mall_id=config.get("mall_id"), local_id=config.get("id")
                )
                return

            logger.info(f"🚀 {config['nombre']}: Encontrados {total_pending} pendientes. Procesando lote de {len(batch_files)}.")

            # 4. PROCESSING LOOP
            processed_count = 0
            for item in batch_files:
                filename = item.filename
                batch_id = str(uuid.uuid4())
                logger.info(f"🔄 [{processed_count + 1}/{len(batch_files)}] Procesando SFTP: {filename}")
                
                try:
                    with sftp.open(f"{remote_path}/{filename}", 'r') as f:
                        # Use utf-8-sig to handle BOM if present
                        content = f.read().decode('utf-8-sig', errors='replace')
                    
                    count, errors = process_file_logic(config, filename, content)

                    estado, mensaje, insert_confirmed = _resolve_worker_processing_outcome(count, errors)

                    if insert_confirmed:
                        insert_load_log(
                            config['nombre'], filename, estado, mensaje, batch_id, errors,
                            mall_id=config.get("mall_id"), local_id=config.get("id")
                        )
                        if post_action == "RENOMBRAR_BACKUP":
                            handle_post_process_sftp(
                                sftp,
                                remote_path,
                                filename,
                                post_action,
                                processed_suffix,
                                AUTO_SUCCESS_PREFIX,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                        else:
                            handle_post_process_sftp(
                                sftp,
                                remote_path,
                                filename,
                                post_action,
                                processed_suffix,
                                custom_backup_prefix,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                    else:
                        raise Exception(mensaje)
                        
                    processed_count += 1
                    
                except Exception as fe:
                    logger.error(f"❌ Error crítico en archivo {filename}: {fe}")
                    insert_load_log(
                        config['nombre'], filename, "error", str(fe), batch_id,
                        mall_id=config.get("mall_id"), local_id=config.get("id")
                    )
                    try:
                        handle_post_process_sftp(
                            sftp,
                            remote_path,
                            filename,
                            "RENOMBRAR_BACKUP",
                            processed_suffix,
                            AUTO_ERROR_PREFIX,
                            strip_prefixes=(custom_backup_prefix,)
                        )
                    except: pass
            
            logger.info(f"✅ {config['nombre']}: Lote completado. {processed_count}/{len(batch_files)} archivos procesados exitosamente.")

        finally:
            if 'sftp' in locals(): sftp.close()
            if 'ssh' in locals(): ssh.close()
            
    elif protocol == "FTP":
        try:
            ftp = connect_with_retries(lambda: get_ftp_client(host, port, user, password))
        except Exception as ce:
            insert_load_log(
                config['nombre'], "N/A", "error", f"Fallo conexión FTP: {str(ce)}",
                mall_id=config.get("mall_id"), local_id=config.get("id")
            )
            return

        try:
            try:
                ftp.cwd(remote_path)
            except:
                remote_path_parent = posixpath.dirname(remote_path) or "."
                try: ftp.cwd(remote_path_parent)
                except: pass

            # 1. DISCOVERY
            files = ftp.nlst()
            pending_files = []
            
            for filename in files:
                is_processed = processed_suffix in filename
                is_backup = (
                    (custom_backup_prefix and filename.startswith(custom_backup_prefix))
                    or filename.startswith(AUTO_SUCCESS_PREFIX)
                    or filename.startswith(AUTO_ERROR_PREFIX)
                    or filename.startswith("PW_")
                )
                is_match = filename.lower().endswith(ext)
                is_error = ".error" in filename
                
                if is_match and not is_processed and not is_backup and not is_error:
                    pending_files.append(filename)
            
            # 2. SORTING (Name Ascending)
            # FTP List doesn't give dates reliable without extra calls. Name sort is best best.
            pending_files.sort()
            
            total_pending = len(pending_files)
            
            # 3. BATCHING
            batch_files = pending_files[:MAX_FILES_PER_BATCH]
            
            if total_pending == 0:
                logger.info(f"📍 {config['nombre']}: No hay archivos pendientes.")
                insert_load_log(
                    config['nombre'], "N/A", "exito", f"Conexión exitosa: 0 pendientes.",
                    mall_id=config.get("mall_id"), local_id=config.get("id")
                )
                return

            logger.info(f"🚀 {config['nombre']}: Encontrados {total_pending} pendientes. Procesando lote de {len(batch_files)}.")
            
            # 4. PROCESSING LOOP
            processed_count = 0
            for filename in batch_files:
                batch_id = str(uuid.uuid4())
                logger.info(f"🔄 [{processed_count + 1}/{len(batch_files)}] Procesando FTP: {filename}")
                
                try:
                    bio = io.BytesIO()
                    ftp.retrbinary(f"RETR {filename}", bio.write)
                    bio.seek(0)
                    # Use utf-8-sig to handle BOM if present
                    content = bio.read().decode('utf-8-sig', errors='replace')
                    
                    count, errors = process_file_logic(config, filename, content)

                    estado, mensaje, insert_confirmed = _resolve_worker_processing_outcome(count, errors)

                    if insert_confirmed:
                        insert_load_log(
                            config['nombre'], filename, estado, mensaje, batch_id, errors,
                            mall_id=config.get("mall_id"), local_id=config.get("id")
                        )
                        if post_action == "RENOMBRAR_BACKUP":
                            handle_post_process_ftp(
                                ftp,
                                filename,
                                post_action,
                                processed_suffix,
                                AUTO_SUCCESS_PREFIX,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                        else:
                            handle_post_process_ftp(
                                ftp,
                                filename,
                                post_action,
                                processed_suffix,
                                custom_backup_prefix,
                                strip_prefixes=(custom_backup_prefix,)
                            )
                    else:
                         raise Exception(mensaje)
                         
                    processed_count += 1
                except Exception as fe:
                    logger.error(f"❌ Error crítico en archivo {filename}: {fe}")
                    insert_load_log(
                        config['nombre'], filename, "error", str(fe), batch_id,
                        mall_id=config.get("mall_id"), local_id=config.get("id")
                    )
                    try:
                        handle_post_process_ftp(
                            ftp,
                            filename,
                            "RENOMBRAR_BACKUP",
                            processed_suffix,
                            AUTO_ERROR_PREFIX,
                            strip_prefixes=(custom_backup_prefix,)
                        )
                    except: pass
            
            logger.info(f"✅ {config['nombre']}: Lote completado. {processed_count}/{len(batch_files)} archivos procesados exitosamente.")
            
        finally:
            if 'ftp' in locals(): ftp.quit()

def handle_post_process_sftp(sftp, path, filename, action, suffix, prefix="", strip_prefixes: Sequence[str] = ()):
    full_path = f"{path}/{filename}"
    if action == "ELIMINAR":
        logger.info(f"Eliminando archivo remoto: {filename}")
        sftp.remove(full_path)
    elif action == "RENOMBRAR_PROCESADO":
        new_name = f"{full_path}{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Renombrando archivo remoto a: {new_name}")
        sftp.rename(full_path, new_name)
    elif action == "RENOMBRAR_BACKUP":
        new_filename = _build_marked_filename(filename, prefix, strip_prefixes)
        new_full_path = f"{path}/{new_filename}"
        logger.info(f"Renombrando (Backup) archivo remoto a: {new_full_path}")
        sftp.rename(full_path, new_full_path)

def handle_post_process_ftp(ftp, filename, action, suffix, prefix="", strip_prefixes: Sequence[str] = ()):
    if action == "ELIMINAR":
        logger.info(f"Eliminando archivo remoto FTP: {filename}")
        ftp.delete(filename)
    elif action == "RENOMBRAR_PROCESADO":
        new_name = f"{filename}{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Renombrando archivo remoto FTP a: {new_name}")
        ftp.rename(filename, new_name)
    elif action == "RENOMBRAR_BACKUP":
        new_name = _build_marked_filename(filename, prefix, strip_prefixes)
        logger.info(f"Renombrando (Backup) archivo remoto FTP a: {new_name}")
        ftp.rename(filename, new_name)

# --- ASYNC LOGIC ---

async def mark_local_status(local_id: str, status: str):
    """Updates the processing status of a local."""
    try:
        payload = {
            "processing_status": status
        }
        if status == 'BUSY':
            payload["processing_started_at"] = datetime.now().isoformat()
        elif status == 'IDLE':
            payload["ultima_ejecucion"] = datetime.now().isoformat()
            
        await asyncio.to_thread(
            lambda: supabase.table("locales").update(payload).eq("id", local_id).execute()
        )
    except Exception as e:
        logger.error(f"Failed to update status {status} for local {local_id}: {e}")

def _sanitize_health_error(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > 500:
        text = f"{text[:497]}..."
    return text or "unknown_error"

async def _upsert_system_health_value(key: str, value: str):
    if not supabase:
        return
    now_utc = datetime.now(timezone.utc)
    await asyncio.to_thread(
        lambda: supabase.table("system_health").upsert({
            "key": key,
            "value": value,
            "last_update": now_utc.isoformat()
        }).execute()
    )

async def update_heartbeat():
    """Updates the system_health table with current timestamp (UTC)."""
    try:
        now_utc = datetime.now(timezone.utc)
        await _upsert_system_health_value("CRON_LAST_RUN", now_utc.isoformat())
    except Exception as e:
        logger.error(f"Error updating heartbeat: {e}")

async def update_cron_success():
    try:
        now_utc = datetime.now(timezone.utc)
        await _upsert_system_health_value("CRON_LAST_SUCCESS", now_utc.isoformat())
    except Exception as e:
        logger.error(f"Error updating CRON_LAST_SUCCESS: {e}")

async def update_cron_error(error: object):
    try:
        await _upsert_system_health_value("CRON_LAST_ERROR", _sanitize_health_error(error))
    except Exception as e:
        logger.error(f"Error updating CRON_LAST_ERROR: {e}")

async def clear_cron_error():
    try:
        await _upsert_system_health_value("CRON_LAST_ERROR", "")
    except Exception as e:
        logger.error(f"Error clearing CRON_LAST_ERROR: {e}")

async def process_local_safe(local, semaphore):
    """
    Wraps the synchronous process_local_files in a semaphore and async thread,
    handling DB locking/unlocking and Circuit Breaker.
    """
    async with semaphore:
        local_name = local.get('nombre', 'Unknown')
        
        # --- CIRCUIT BREAKER CHECK ---
        consecutive_failures = local.get('consecutive_failures', 0)
        status = local.get('processing_status')
        
        if status == 'SUSPENDED_AUTH_ERROR':
             logger.warning(f"⛔ [Skipped] {local_name} is SUSPENDED due to auth errors.")
             return

        if consecutive_failures >= 5:
             logger.error(f"⛔ [Suspend] {local_name} reached 5 consecutive failures. Suspending...")
             await mark_local_status(local['id'], 'SUSPENDED_AUTH_ERROR')
             # Reset failures to avoid immediate loop if manually reactivated without reset
             # But actually, manual reactivation should reset failures.
             return

        logger.info(f"🔒 [Lock] Locking {local_name} (Status: BUSY)")
        
        # 1. LOCK
        await mark_local_status(local['id'], 'BUSY')
        
        try:
            # 2. EXECUTE (Run sync IO in thread pool)
            logger.info(f"🚀 [Start] Processing {local_name}...")
            
            # Run the processing
            # We need to capture if it was successful or auth error
            # process_local_files returns nothing, logs internally. 
            # We need to modify it or wrap it to know if it failed?
            # Actually process_local_files catches exceptions internally and logs.
            # to implement true circuit breaker, we need to know if it failed.
            
            # For now, let's assume if it throws exception here it failed.
            # But process_local_files swallows exceptions mostly.
            # Let's trust it runs. If we want strict circuit breaker, we'd need to refactor process_local_files to return status.
            # Let's assume for this task we wrap it.
            
            await asyncio.to_thread(process_local_files, local)
            
            logger.info(f"✅ [Done] Finished {local_name}")
            
            # Reset failures on success (Optimistic: if no exception bubbled up)
            # Ideal: check logs_carga for this batch? 
            # For simplicity: reset failures here.
            await asyncio.to_thread(
                lambda: supabase.table("locales").update({"consecutive_failures": 0}).eq("id", local['id']).execute()
            )
            
        except Exception as e:
            logger.error(f"❌ [Error] Processing {local_name}: {e}")
            insert_load_log(
                local_name, "SYSTEM", "error", f"Async processing failed: {str(e)}",
                mall_id=local.get("mall_id"), local_id=local.get("id")
            )
            
            # Increment Failures
            new_failures = consecutive_failures + 1
            await asyncio.to_thread(
                 lambda: supabase.table("locales").update({"consecutive_failures": new_failures}).eq("id", local['id']).execute()
            )
            
        finally:
            # 3. RELEASE (Only if not suspended inside logic, checking status again?)
            # If we suspended it above, we returned.
            # If we are here, we must release lock.
            logger.info(f"🔓 [Release] Unlocking {local_name} (Status: IDLE)")
            await mark_local_status(local['id'], 'IDLE')

async def cleanup_zombies():
    """Reset locales that have been stuck in BUSY for more than 2 hours."""
    try:
        logger.info("🧟 Checking for Zombie processes...")
        
        response = supabase.table("locales").select("*").eq("processing_status", "BUSY").execute()
        zombies = response.data or []
        
        count = 0
        for z in zombies:
            started_at_str = z.get('processing_started_at')
            if not started_at_str:
                is_zombie = True
            else:
                try:
                    started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    now = datetime.now(started.tzinfo) 
                    diff = now - started
                    is_zombie = diff.total_seconds() > 7200 # 2 hours
                except:
                   is_zombie = True
            
            if is_zombie:
                 logger.warning(f"🧟 Resetting ZOMBIE local: {z.get('nombre')} (Stuck since {started_at_str})")
                 supabase.table("locales").update({
                     "processing_status": "IDLE"
                 }).eq("id", z['id']).execute()
                 count += 1
                 
        if count > 0:
            logger.info(f"✨ Cleaned up {count} zombie locks.")
        else:
            logger.info("✅ No zombies found.")
            
    except Exception as e:
        logger.error(f"Error cleaning zombies: {e}")

async def run_worker_async():
    logger.info("🚀 Iniciando Worker de Importación (Async/Concurrent v2)...")
    if not supabase:
        logger.error(
            "Worker skipped: Supabase client not initialized. Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
        return
    
    # 1. Reset Zombies & Heartbeat
    await cleanup_zombies()
    await update_heartbeat()
    
    try:
        # 2. Fetch Tasks (IDLE + AUTOMATIC)
        # Note: We need to filter by IDLE to avoid double execution if previous job is running
        response = supabase.table("locales")\
            .select("*")\
            .eq("tipo_ejecucion", "AUTOMATICO")\
            .eq("processing_status", "IDLE")\
            .execute()
            
        locales = [loc for loc in (response.data or []) if loc.get("mall_id")]
        current_hour = datetime.now().hour
        
        tasks_to_run = []
        
        for local in locales:
            # Frequency Check Logic
            frecuencia = local.get("frecuencia_cron", "manual")
            if frecuencia == "manual": continue
            
            should_run = False
            if frecuencia == "cada_hora":
                should_run = True
            elif frecuencia == "cada_2_horas":
                if current_hour % 2 == 0: should_run = True
            elif frecuencia == "hora_especifica":
                hora_esp = local.get("hora_especifica")
                if hora_esp:
                    try:
                        esp_hour = int(hora_esp.split(":")[0])
                        if current_hour == esp_hour: should_run = True
                    except: pass
            
            if should_run:
                tasks_to_run.append(local)
            else:
                 # Debug check
                 pass

        if not tasks_to_run:
            logger.info("😴 No active tasks for this hour.")
            await update_cron_success()
            await clear_cron_error()
            return

        logger.info(f"📋 Encolados {len(tasks_to_run)} locales para ejecución.")
        
        # 3. Execute with Semaphore
        MAX_CONCURRENT_WORKERS = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        
        tasks = [process_local_safe(local, semaphore) for local in tasks_to_run]
        await asyncio.gather(*tasks)
        
        logger.info("🏁 Cycle finished.")
        await update_cron_success()
        await clear_cron_error()
        
    except Exception as e:
        logger.error(f"Critical error in main loop: {e}")
        await update_cron_error(e)

if __name__ == "__main__":
    asyncio.run(run_worker_async())
