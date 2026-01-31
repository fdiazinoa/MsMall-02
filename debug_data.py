
import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

def analyze_data():
    print("--- Stores ---")
    stores = supabase.table("locales").select("id, nombre").execute().data
    store_map = {s['id']: s['nombre'] for s in stores}
    for s in stores:
        print(f"ID: {s['id']} -> {s['nombre']}")

    print("\n--- Sales by Local ID ---")
    # Fetch all sales (limited to 1000 for speed, usually enough to see pattern)
    sales = supabase.table("ventas").select("local_id, total_bruto").limit(2000).execute().data
    
    sums = {}
    for s in sales:
        lid = s['local_id']
        total = float(s['total_bruto'] or 0)
        sums[lid] = sums.get(lid, 0) + total
        
    for lid, total in sums.items():
        name = store_map.get(lid, "UNKNOWN_ID")
        print(f"Local ID: {lid} ({name}) -> Total: ${total:,.2f}")

if __name__ == "__main__":
    analyze_data()
