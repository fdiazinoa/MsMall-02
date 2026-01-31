
import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

def check_dates():
    # 1. Get Skechers ID
    print("Finding Skechers ID...")
    res = supabase.table("locales").select("id").ilike("nombre", "%skechers%").execute()
    if not res.data:
        print("Skechers not found!")
        return
    
    skechers_id = res.data[0]['id']
    print(f"Skechers ID: {skechers_id}")
    
    # 2. Get Sales Dates
    print("Fetching sales dates...")
    sales = supabase.table("ventas")\
        .select("fecha, total_bruto")\
        .eq("local_id", skechers_id)\
        .limit(20)\
        .execute()
        
    if not sales.data:
        print("No sales found for Skechers!")
    else:
        print(f"Found {len(sales.data)} sales (showing first 20):")
        for s in sales.data:
            print(f"Date: {s['fecha']}, Amount: {s['total_bruto']}")

if __name__ == "__main__":
    check_dates()
