"""Annual audit facts, using import timestamps rather than sale dates."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from services.sales_gap_service import expected_sales_dates, load_actual_sales_dates_by_local


def load_annual_audit_status(client, mall_id, stores, now=None):
    current = now or datetime.now(ZoneInfo("America/Santo_Domingo"))
    today = current.astimezone(ZoneInfo("America/Santo_Domingo")).date()
    start = today.replace(month=1, day=1).isoformat()
    end = (today - timedelta(days=1)).isoformat()
    dates = load_actual_sales_dates_by_local(client, local_ids=[str(row["id"]) for row in stores], fecha_inicio=start, fecha_fin=end) if end >= start else {}
    expected = expected_sales_dates(start, end) if end >= start else set()
    result = []
    for store in stores:
        latest = None
        offset = 0
        while latest is None:
            rows = (client.table("logs_carga").select("fecha_hora,records_processed,metadata")
                    .eq("mall_id", mall_id).eq("local_id", store["id"])
                    .order("fecha_hora", desc=True).range(offset, offset + 999).execute()).data or []
            for row in rows:
                count = row.get("records_processed")
                if count is None:
                    count = (row.get("metadata") or {}).get("records_processed")
                if count is not None and int(count) > 0:
                    latest = row["fecha_hora"]
                    break
            if len(rows) < 1000:
                break
            offset += 1000
        result.append({"local_id": store["id"], "local_nombre": store["nombre"], "ultima_importacion_datos": latest, "audit_year": today.year, "dias_faltantes_anio": len(expected - dates.get(str(store["id"]), set()))})
    return result


def annual_audit_text(row):
    timestamp = row.get("ultima_importacion_datos")
    latest = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Santo_Domingo")).strftime("%d/%m/%Y") if timestamp else "Sin ventas reportadas"
    return f"Última importación con datos: {latest}.\nDías faltantes del período {row['audit_year']}: {row['dias_faltantes_anio']}."
