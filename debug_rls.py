
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Use ANON key to simulate frontend
url = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL")
key = os.getenv("VITE_SUPABASE_ANON_KEY")

if not url or not key:
    print("Error: Credentials not found")
    exit(1)

print(f"Connecting to {url} with ANON key...")
supabase = create_client(url, key)

try:
    print("\n--- TEST: READ ---")
    res = supabase.table("logs_carga").select("*").limit(1).execute()
    print(f"Read success. Count: {len(res.data)}")
except Exception as e:
    print(f"Read FAILED: {e}")

try:
    print("\n--- TEST: INSERT ---")
    test_log = {
        "local_nombre": "TEST_RLS",
        "archivo": "test.csv",
        "estado": "test",
        "mensaje": "Testing RLS"
    }
    res = supabase.table("logs_carga").insert(test_log).execute()
    print("Insert success.")
except Exception as e:
    print(f"Insert FAILED: {e}")

try:
    print("\n--- TEST: DELETE ---")
    res = supabase.table("logs_carga").delete().eq("local_nombre", "TEST_RLS").execute()
    print("Delete success.")
except Exception as e:
    print(f"Delete FAILED: {e}")
