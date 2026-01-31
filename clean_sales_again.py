
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

print("Clearing 'ventas' table...")
# Delete all rows (neq id 0 is a hack for delete all if no other filter)
supabase.table("ventas").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

res = supabase.table("ventas").select("*", count="exact").execute()
print(f"Sales Count after clear: {res.count}")
