
import os
import time
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

print("Starting delete...")
start = time.time()
try:
    # Mimic main.py logic
    res = supabase.table("ventas").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    duration = time.time() - start
    count = len(res.data) if res.data else 0
    print(f"Deleted {count} records in {duration:.2f}s")
except Exception as e:
    print(f"Error: {e}")
