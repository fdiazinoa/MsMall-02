import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Error: Missing Supabase credentials.")
    exit()

supabase = create_client(url, key)

MALL_ID = "ce12312e-220d-4200-aa36-a959bf7d271c"

print(f"Checking stores for Mall ID: {MALL_ID}")

try:
    res = supabase.table("locales").select("*").eq("mall_id", MALL_ID).execute()
    stores = res.data

    print(f"Found {len(stores)} stores.")
    print("-" * 80)
    print(f"{'Name':<20} | {'Renta Fija':<12} | {'Breakpoint':<12} | {'% Var':<10} | {'% Renta':<10}")
    print("-" * 80)
    for s in stores:
        print(f"{s.get('nombre', 'N/A'):<20} | {s.get('renta_fija', 'N/A'):<12} | {s.get('breakpoint_venta', 'N/A'):<12} | {s.get('porcentaje_variable', 'N/A'):<10} | {s.get('porciento_renta', 'N/A'):<10}")
except Exception as e:
    print(f"Error querying database: {e}")
