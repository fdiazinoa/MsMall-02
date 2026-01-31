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

# Configurations for Demo Stores
# Logic: Breakpoint should be slightly lower than expected sales to trigger variable rent for some
financial_updates = {
    "Zara Demo": {
        "renta_fija": 5000, 
        "breakpoint_venta": 80000,  # Expected sales ~100k+
        "porcentaje_variable": 8.0,
        "porciento_renta": 8.0
    },
    "Starbucks Demo": {
        "renta_fija": 2000,
        "breakpoint_venta": 30000,
        "porcentaje_variable": 6.0,
        "porciento_renta": 6.0
    },
    "Nike Demo": {
        "renta_fija": 4000,
        "breakpoint_venta": 60000,
        "porcentaje_variable": 7.0,
        "porciento_renta": 7.0
    },
    "Cinema Demo": {
        "renta_fija": 10000,
        "breakpoint_venta": 150000,
        "porcentaje_variable": 10.0,
        "porciento_renta": 10.0
    },
    "Farmacia Demo": {
        "renta_fija": 3000,
        "breakpoint_venta": 40000,
        "porcentaje_variable": 5.0,
        "porciento_renta": 5.0
    }
}

print("Updating financial parameters...")

for name, params in financial_updates.items():
    try:
        data, count = supabase.table("locales").update(params)\
            .eq("mall_id", MALL_ID).eq("nombre", name).execute()
        print(f"Updated {name}: {params}")
    except Exception as e:
        print(f"Error updating {name}: {e}")

print("Update complete.")
