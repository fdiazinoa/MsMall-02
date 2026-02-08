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

try:
    res = supabase.table("malls").select("*").limit(1).execute()
    if res.data:
        print("Columns in malls:", res.data[0].keys())
    else:
        print("No data in malls, cannot determine columns easily.")
except Exception as e:
    print(f"Error: {e}")
