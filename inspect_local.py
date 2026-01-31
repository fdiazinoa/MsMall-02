
import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

res = supabase.table("locales").select("*").eq("nombre", "skechers").execute()
if res.data:
    local = res.data[0]
    prefix = local.get("prefijo_backup")
    print(f"Local: {local['nombre']}")
    print(f"Prefijo Backup (Raw): '{prefix}'")
    print(f"Type: {type(prefix)}")
else:
    print("Local not found")
