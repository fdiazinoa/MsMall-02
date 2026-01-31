
import os
import json
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
    res = supabase.table("logs_carga").select("*", count="exact").limit(1).execute()
    print(f"Read success. Data: {len(res.data)}, Count: {res.count}")
except Exception as e:
    print(f"Read FAILED: {e}")

try:
    print("\n--- TEST: INSERT ---")
    test_log = {
        "local_nombre": "TEST_RLS_VERBOSE",
        "archivo": "test_v.csv",
        "estado": "test",
        "mensaje": "Testing RLS Verbose"
    }
    # In python client, insert returns data by default or we check response
    res = supabase.table("logs_carga").insert(test_log).execute()
    if res.data:
        print(f"Insert success: {res.data[0]['id']}")
    else:
        print("Insert returned NO DATA (RLS blocking?)")
except Exception as e:
    print(f"Insert FAILED: {e}")

try:
    print("\n--- TEST: DELETE ---")
    # Delete the record we just inserted
    res = supabase.table("logs_carga").delete().eq("local_nombre", "TEST_RLS_VERBOSE").execute()
    if res.data:
        print(f"Delete success. Deleted {len(res.data)} rows.")
    else:
        print("Delete returned NO DATA (RLS blocking or no rows match?)")
except Exception as e:
    print(f"Delete FAILED: {e}")
