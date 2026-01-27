
# Backend: FastAPI API para MSMALL Audit
import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("msmall-api")

app = FastAPI(title="MSMALL Sales Audit API", version="1.0.0")

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
    mall_nombre: Optional[str] = "Mall Plaza"

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
    Acepta un archivo CSV con el formato estándar de auditoría.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un CSV válido")

    try:
        content = await file.read()
        decoded = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded))
        
        # Validar encabezados mínimos requeridos
        required_headers = {'factura_numero', 'fecha_venta', 'local_codigo', 'total_bruto'}
        if not required_headers.issubset(set(csv_reader.fieldnames or [])):
            raise HTTPException(
                status_code=422, 
                detail=f"Faltan columnas requeridas. El formato debe incluir: {', '.join(required_headers)}"
            )

        records = []
        for row in csv_reader:
            # Aquí se realizaría la lógica de negocio y guardado en PostgreSQL (ventas table)
            records.append(row)
        
        logger.info(f"Ingesta exitosa: {len(records)} registros procesados para API Key {api_key[:5]}***")
        
        return {
            "status": "success",
            "message": "Archivo de ventas procesado y auditado correctamente",
            "records_processed": len(records),
            "batch_id": str(uuid4())
        }

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Error de codificación en el archivo. Use UTF-8.")
    except Exception as e:
        logger.error(f"Error procesando ingesta: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno al procesar el archivo")

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
        logger.error(f"Error explorando directorio {path}: {str(e)}")
        raise HTTPException(status_code=500, detail="No se pudo acceder al directorio")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
