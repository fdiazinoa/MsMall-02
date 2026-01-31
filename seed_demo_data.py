
import os
import random
from datetime import date, timedelta
from uuid import uuid4
from dotenv import load_dotenv
from supabase import create_client

# Load Env
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: Missing Supabase Credentials")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MALL_NAME = "Mega Mall Demo"
START_DATE = date(2022, 1, 1)
END_DATE = date(2026, 1, 31)

DEMO_STORES = [
    {"nombre": "Zara Demo", "rubro": "Moda", "renta_fija": 5000, "porciento": 8},
    {"nombre": "Starbucks Demo", "rubro": "Alimentos", "renta_fija": 3000, "porciento": 6},
    {"nombre": "Nike Demo", "rubro": "Deportes", "renta_fija": 4500, "porciento": 7},
    {"nombre": "Cinema Demo", "rubro": "Entretenimiento", "renta_fija": 12000, "porciento": 10},
    {"nombre": "Farmacia Demo", "rubro": "Salud", "renta_fija": 2000, "porciento": 5}
]

def get_or_create_mall():
    res = supabase.table("malls").select("id").eq("nombre", MALL_NAME).execute()
    if res.data:
        print(f"Mall '{MALL_NAME}' found: {res.data[0]['id']}")
        return res.data[0]['id']
    
    print(f"Creating '{MALL_NAME}'...")
    res = supabase.table("malls").insert({
        "nombre": MALL_NAME,
        "api_secret_key": str(uuid4())
    }).execute()
    return res.data[0]['id']

def create_stores(mall_id):
    store_ids = []
    print("Checking/Creating stores...")
    for s_data in DEMO_STORES:
        res = supabase.table("locales").select("id").eq("mall_id", mall_id).eq("nombre", s_data["nombre"]).execute()
        if res.data:
            store_ids.append(res.data[0]['id'])
        else:
            new_store = {
                "mall_id": mall_id,
                "nombre": s_data["nombre"],
                "rubro": s_data["rubro"],
                "codigo_interno": f"DEMO-{random.randint(100,999)}",
                "renta_fija": 0.0, # Not in DB apparently, or ignored if passed? No, caused error.
                # "renta_fija": s_data["renta_fija"], # Removed
                "porciento_renta": s_data["porciento"],
                "responsable": "Demo User",
                "tipo_negocio": "Retail",
                "contrato_no": f"CTR-{random.randint(1000,9999)}",
                "piso": "1",
                "mts": "50"
            }
            # Remove keys that might cause errors if not in DB
            if "renta_fija" in new_store: del new_store["renta_fija"]
            res = supabase.table("locales").insert(new_store).execute()
            store_ids.append(res.data[0]['id'])
    return store_ids

def seed_data(mall_id, store_ids):
    print(f"Seeding data from {START_DATE} to {END_DATE}...")
    
    current = START_DATE
    batch = []
    total_records = 0
    
    while current <= END_DATE:
        is_weekend = current.weekday() >= 5
        season_multiplier = 1.0
        if current.month == 12: season_multiplier = 2.5 # December peak
        
        for sid in store_ids:
            # Generate random sale
            base_sale = random.uniform(500, 5000)
            if is_weekend: base_sale *= 1.5
            daily_sale = base_sale * season_multiplier
            
            record = {
                "local_id": sid,
                "mall_id": mall_id,
                "fecha": current.isoformat(),
                "hora": "12:00:00",
                "factura_no": f"DEMO-{current.strftime('%Y%m%d')}-{sid[:4]}",
                "total_bruto": round(daily_sale * 1.18, 2), # +Tax
                "total_neto": round(daily_sale, 2),
                "total_impuestos": round(daily_sale * 0.18, 2)
            }
            batch.append(record)
            
        # Insert in batches of 1000
        if len(batch) >= 500:
            supabase.table("ventas").insert(batch).execute()
            total_records += len(batch)
            print(f"Inserted to {current}: {total_records} records total")
            batch = []
            
        current += timedelta(days=1)
        
    if batch:
        supabase.table("ventas").insert(batch).execute()
        total_records += len(batch)
        
    print(f"DONE! Total Records Inserted: {total_records}")

if __name__ == "__main__":
    mall_id = get_or_create_mall()
    store_ids = create_stores(mall_id)
    seed_data(mall_id, store_ids)
