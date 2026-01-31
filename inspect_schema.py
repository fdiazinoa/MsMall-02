import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

print("--- COLUMNAS DE LOCALES ---")
try:
    res = supabase.table("locales").select("*").limit(1).execute()
    if res.data:
        print("Columnas encontradas:")
        print(sorted(list(res.data[0].keys())))
    else:
        print("Tabla vacía o sin acceso.")
except Exception as e:
    print(f"Error: {e}")
