import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("VITE_SUPABASE_URL")
key = os.environ.get("VITE_SUPABASE_ANON_KEY")

if not url or not key:
    print("Error: Missing credentials")
    exit(1)

supabase = create_client(url, key)

response = supabase.table("locales").select("nombre, codigo_interno").execute()

print(f"Found {len(response.data)} stores:")
for store in response.data:
    print(f"- Name: '{store['nombre']}', Code: '{store['codigo_interno']}'")
