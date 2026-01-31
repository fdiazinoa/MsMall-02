
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
# Try to specifically use the service role key for this test
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not url or not key:
    print("Error: Credentials not found")
    exit(1)

print(f"Connecting to {url}...")
# Verify key role if possible (by printing first few chars? No, assume it's correct from env)
supabase = create_client(url, key)

try:
    print("\n--- TEST: READ SALES COUNT ---")
    res = supabase.table("ventas").select("*", count="exact").limit(1).execute()
    print(f"Current Sales Count: {res.count}")
    
    if res.count > 0:
        print("\n--- TEST: DELETE ALL SALES ---")
        # Reproduce logic from main.py
        res = supabase.table("ventas").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        # In python client, execute() returns a response object.
        # Check if data is returned
        deleted_count = len(res.data) if res.data else 0
        print(f"Delete result data length: {deleted_count}")
        
        # Verify count again
        res2 = supabase.table("ventas").select("*", count="exact").limit(1).execute()
        print(f"Post-Delete Sales Count: {res2.count}")
    else:
        print("No sales to delete.")

except Exception as e:
    print(f"OPERATION FAILED: {e}")
    # Print details if available
    if hasattr(e, 'code'):
        print(f"Error Code: {e.code}")
    if hasattr(e, 'details'):
        print(f"Error Details: {e.details}")
