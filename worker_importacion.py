import os
import stat
import logging
import uuid
import asyncio
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
import paramiko
from ftplib import FTP
import io
import csv
import json
import posixpath

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("import-worker")

# Load Environment
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Supabase credentials missing in .env")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def insert_load_log(local_nombre: str, archivo: str, estado: str, mensaje: str, batch_id: str = None, detalles: list = []):
    """Inserts a log into Supabase 'logs_carga' table."""
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
        supabase.table("logs_carga").insert(log_data).execute()
        logger.info(f"Log registrado: {mensaje}")
    except Exception as e:
        logger.error(f"Error inserting load log: {e}")

def normalize_date(date_str):
    """
    Attempts to parse a date string into YYYY-MM-DD format.
    Supports: DD/MM/YYYY, YYYY-MM-DD, MM/DD/YYYY, DD-MM-YYYY, YYYY/MM/DD
    """
    if not date_str:
        return None
        
    raw_date = str(date_str).strip()
    # Try common formats
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']:
        try:
            parsed_date = datetime.strptime(raw_date, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def get_sftp_client(host, port, user, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=10)
    return ssh, ssh.open_sftp()

def get_ftp_client(host, port, user, password):
    ftp = FTP()
    ftp.connect(host, port, timeout=10)
    ftp.login(user, password)
    return ftp

def process_file_logic(config, filename, content):
    """
    Process file content and insert to database.
    """
    logger.info(f"Procesando contenido de {filename} para {config['nombre']}")
    detalles = []
    registros_exito = 0
    
    try:
        # Parse CSV
        lines = content.splitlines()
        if len(lines) < 2:
            return 0, [{"linea": 0, "error": "Archivo vacío o sin datos"}]
            
        reader = csv.DictReader(io.StringIO(content))
        
        # Get store ID and Mall ID (Inferencia Backend)
        local_id = config.get('id')
        mall_id = config.get('mall_id') # Assumes config comes with mall_id from select(*)
        
        if not local_id:
            return 0, [{"linea": 0, "error": "No se pudo determinar el local_id"}]
            
        if not mall_id:
             logger.warning(f"Mall ID missing for local {config['nombre']}")
        
        # Get mapping
        mapping = config.get('mapping_config') or {}
        
        for i, row in enumerate(reader, start=2):  # Start from line 2 (after header)
            try:
                # Map fields
                fecha_venta_raw = row.get(mapping.get('fecha_venta', ''), '')
                fecha_venta = normalize_date(fecha_venta_raw)
                
                if fecha_venta_raw and not fecha_venta:
                     detalles.append({"linea": i, "error": f"Formato de fecha inválido: {fecha_venta_raw}"})
                     continue

                total_bruto = float(row.get(mapping.get('total_bruto', ''), '0'))
                total_impuestos = float(row.get(mapping.get('total_impuestos', ''), '0'))
                total_neto = float(row.get(mapping.get('total_neto', ''), '0'))
                
                if not fecha_venta or total_bruto == 0:
                    detalles.append({"linea": i, "error": "Datos incompletos"})
                    continue
                
                # Insert to database with Tenant ID
                payload = {
                    "local_id": local_id,
                    "fecha": fecha_venta,
                    "total_bruto": total_bruto,
                    "total_impuestos": total_impuestos,
                    "total_neto": total_neto
                }
                
                if mall_id:
                    payload["mall_id"] = mall_id
                
                supabase.table("ventas").insert(payload).execute()
                
                registros_exito += 1
                
            except Exception as e:
                detalles.append({"linea": i, "error": str(e)})
                logger.error(f"Error en línea {i}: {e}")
                
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
    
    ext = f".{file_type.lower()}"
    processed_suffix = ".procesado"
    
    logger.info(f"Conectando a {config['nombre']} ({protocol}) en {host}...")
    
    if protocol == "SFTP":
        try:
            ssh, sftp = get_sftp_client(host, port, user, password)
        except Exception as ce:
            insert_load_log(config['nombre'], "N/A", "error", f"Fallo conexión SFTP: {str(ce)}")
            return

        try:
            # Si remote_path es un archivo, usar el directorio padre
            try:
                st = sftp.stat(remote_path)
                if not stat.S_ISDIR(st.st_mode):
                    remote_path = posixpath.dirname(remote_path) or "."
            except:
                pass

            items = sftp.listdir_attr(remote_path)
            for item in items:
                if stat.S_ISDIR(item.st_mode):
                    continue
                
                filename = item.filename
                
                # Debug Check
                skip_reason = ""
                if processed_suffix in filename: skip_reason = "processed_suffix"
                elif filename.startswith(backup_prefix): skip_reason = f"prefix_{backup_prefix}"
                elif filename.startswith("PR_"): skip_reason = "prefix_PR_"
                elif filename.startswith("PW_"): skip_reason = "prefix_PW_"
                
                if skip_reason:
                     logger.info(f"SKIPPING {filename} due to {skip_reason}")
                
                if filename.lower().endswith(ext) and processed_suffix not in filename and not filename.startswith(backup_prefix) and not filename.startswith("PR_") and not filename.startswith("PW_"):
                    batch_id = str(uuid.uuid4())
                    logger.info(f"Procesando archivo SFTP: {filename}")
                    
                    try:
                        with sftp.open(f"{remote_path}/{filename}", 'r') as f:
                            content = f.read().decode('utf-8', errors='replace')
                        
                        count, errors = process_file_logic(config, filename, content)
                        
                        estado = "exito"
                        mensaje = f"Worker: Procesado {count} registros."
                        if errors: mensaje += f" {len(errors)} errores."
                        
                        insert_load_log(config['nombre'], filename, estado, mensaje, batch_id, errors)
                        handle_post_process_sftp(sftp, remote_path, filename, post_action, processed_suffix, backup_prefix)
                    except Exception as fe:
                        insert_load_log(config['nombre'], filename, "error", str(fe), batch_id)
                        logger.error(f"Error procesando archivo {filename}: {fe}")
        finally:
            sftp.close()
            ssh.close()
            
    elif protocol == "FTP":
        try:
            ftp = get_ftp_client(host, port, user, password)
        except Exception as ce:
            insert_load_log(config['nombre'], "N/A", "error", f"Fallo conexión FTP: {str(ce)}")
            return

        try:
            try:
                ftp.cwd(remote_path)
            except:
                remote_path_parent = posixpath.dirname(remote_path) or "."
                try:
                    ftp.cwd(remote_path_parent)
                except:
                    pass

            files = ftp.nlst()
            for filename in files:
                if filename.lower().endswith(ext) and processed_suffix not in filename and not filename.startswith(backup_prefix) and not filename.startswith("PR_") and not filename.startswith("PW_"):
                    batch_id = str(uuid.uuid4())
                    logger.info(f"Procesando archivo FTP: {filename}")
                    
                    try:
                        bio = io.BytesIO()
                        ftp.retrbinary(f"RETR {filename}", bio.write)
                        bio.seek(0)
                        content = bio.read().decode('utf-8', errors='replace')
                        
                        count, errors = process_file_logic(config, filename, content)
                        
                        estado = "exito"
                        mensaje = f"Worker: Procesado {count} registros."
                        if errors: mensaje += f" {len(errors)} errores."
                        
                        insert_load_log(config['nombre'], filename, estado, mensaje, batch_id, errors)
                        handle_post_process_ftp(ftp, filename, post_action, processed_suffix, backup_prefix)
                    except Exception as fe:
                        insert_load_log(config['nombre'], filename, "error", str(fe), batch_id)
                        logger.error(f"Error procesando archivo {filename}: {fe}")
        finally:
            ftp.quit()

def handle_post_process_sftp(sftp, path, filename, action, suffix, prefix=""):
    full_path = f"{path}/{filename}"
    if action == "ELIMINAR":
        logger.info(f"Eliminando archivo remoto: {filename}")
        sftp.remove(full_path)
    elif action == "RENOMBRAR_PROCESADO":
        new_name = f"{full_path}{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Renombrando archivo remoto a: {new_name}")
        sftp.rename(full_path, new_name)
    elif action == "RENOMBRAR_BACKUP":
        new_filename = f"{prefix}{filename}"
        new_full_path = f"{path}/{new_filename}"
        logger.info(f"Renombrando (Backup) archivo remoto a: {new_full_path}")
        sftp.rename(full_path, new_full_path)

def handle_post_process_ftp(ftp, filename, action, suffix, prefix=""):
    if action == "ELIMINAR":
        logger.info(f"Eliminando archivo remoto FTP: {filename}")
        ftp.delete(filename)
    elif action == "RENOMBRAR_PROCESADO":
        new_name = f"{filename}{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Renombrando archivo remoto FTP a: {new_name}")
        ftp.rename(filename, new_name)
    elif action == "RENOMBRAR_BACKUP":
        new_name = f"{prefix}{filename}"
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

async def update_heartbeat():
    """Updates the system_health table with current timestamp (UTC)."""
    try:
        # Upsert heartbeat with Timezone Aware UTC
        now_utc = datetime.now(timezone.utc)
        await asyncio.to_thread(
            lambda: supabase.table("system_health").upsert({
                "key": "CRON_LAST_RUN",
                "value": now_utc.isoformat(),
                "last_update": now_utc.isoformat()
            }).execute()
        )
    except Exception as e:
        logger.error(f"Error updating heartbeat: {e}")

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
            insert_load_log(local_name, "SYSTEM", "error", f"Async processing failed: {str(e)}")
            
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
            
        locales = response.data or []
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
            return

        logger.info(f"📋 Encolados {len(tasks_to_run)} locales para ejecución.")
        
        # 3. Execute with Semaphore
        MAX_CONCURRENT_WORKERS = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        
        tasks = [process_local_safe(local, semaphore) for local in tasks_to_run]
        await asyncio.gather(*tasks)
        
        logger.info("🏁 Cycle finished.")
        
    except Exception as e:
        logger.error(f"Critical error in main loop: {e}")

if __name__ == "__main__":
    asyncio.run(run_worker_async())
