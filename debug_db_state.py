
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Error: credentials not found")
    exit(1)

supabase = create_client(url, key)

print("--- MALLS ---")
malls = supabase.table("malls").select("*").execute().data
for m in malls:
    print(f"Mall: {m['id']} - {m['nombre']}")

print("\n--- LOCALES PER MALL ---")
locales = supabase.table("locales").select("id, nombre, mall_id").execute().data
mall_counts = {}
for l in locales:
    mid = l['mall_id']
    mall_counts[mid] = mall_counts.get(mid, 0) + 1
    # print(f"  Local {l['nombre']} -> Mall {mid}")

for mid, count in mall_counts.items():
    print(f"Mall {mid}: {count} locales")

print("\n--- USUARIOS MALLS ---")
perms = supabase.table("usuarios_malls").select("*").execute().data
for p in perms:
    print(f"User {p['usuario_id']} linked to Mall {p['mall_id']} as {p['rol']}")

if not perms:
    print("WARNING: Table usuarios_malls is EMPTY!")
