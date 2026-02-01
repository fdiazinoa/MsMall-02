from main import supabase
import json

def check_stores():
    res = supabase.table("malls").select("id, nombre").execute()
    if not res.data:
        print("No malls found")
        return
    
    for mall in res.data:
        print(f"\n--- Mall: {mall['nombre']} ({mall['id']}) ---")
        stores_res = supabase.table("locales").select("*").eq("mall_id", mall['id']).execute()
        if not stores_res.data:
            print("  No stores found")
            continue
            
        for s in stores_res.data:
            print(f"  Store: {s['nombre']} | Renta Fija: {s.get('renta_fija')} | Renta Var %: {s.get('porcentaje_variable') or s.get('porciento_renta')} | Breakpoint: {s.get('breakpoint_venta')}")

if __name__ == "__main__":
    check_stores()
