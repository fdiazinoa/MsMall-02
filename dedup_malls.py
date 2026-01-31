
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CORRECT_MALL_ID = "ce12312e-220d-4200-aa36-a959bf7d271c" # The one with stores
WRONG_MALL_ID = "3b72db15-063a-4f77-a2df-4fa16b2b2d8d"   # The one likely empty

print(f"Migrating users from {WRONG_MALL_ID} to {CORRECT_MALL_ID}...")

# 1. Update user assignments
assignments = supabase.table("usuarios_malls").select("*").eq("mall_id", WRONG_MALL_ID).execute().data
count = 0
for a in assignments:
    print(f"Updating user {a['usuario_id']}...")
    # Check if assignment already exists for target
    exists = supabase.table("usuarios_malls").select("*").eq("usuario_id", a['usuario_id']).eq("mall_id", CORRECT_MALL_ID).execute().data
    
    if not exists:
        supabase.table("usuarios_malls").update({"mall_id": CORRECT_MALL_ID}).eq("id", a['id']).execute()
        count += 1
    else:
        # Delete duplicate assignment
        supabase.table("usuarios_malls").delete().eq("usuario_id", a['usuario_id']).eq("mall_id", WRONG_MALL_ID).execute()

print(f"Migrated {count} assignments.")

# 2. Delete the wrong mall
print(f"Deleting Mall {WRONG_MALL_ID}...")
# Ensure no stores are linked (should be none based on previous check)
stores = supabase.table("locales").select("id").eq("mall_id", WRONG_MALL_ID).execute().data
if stores:
    print("WARNING: Wrong mall has stores! Aborting delete.")
    print(stores)
else:
    supabase.table("malls").delete().eq("id", WRONG_MALL_ID).execute()
    print("Wrong mall deleted.")

print("Done.")
