
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("--- MALLS ---")
malls = supabase.table("malls").select("id, nombre").execute().data
for m in malls:
    print(f"ID: {m['id']} | Name: {m['nombre']}")

print("\n--- STORES (Locales) ---")
stores = supabase.table("locales").select("id, nombre, mall_id").execute().data
for s in stores:
    mall_name = next((m['nombre'] for m in malls if m['id'] == s['mall_id']), "UNKNOWN")
    print(f"Store: {s['nombre']} | Mall: {mall_name} ({s['mall_id']})")
