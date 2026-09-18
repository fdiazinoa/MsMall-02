"""Annual audit facts, using import timestamps rather than sale dates."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def load_annual_audit_status(client, mall_id, stores, now=None):
    current = now or datetime.now(ZoneInfo("America/Santo_Domingo"))
    today = current.astimezone(ZoneInfo("America/Santo_Domingo")).date()
    start = today.replace(month=1, day=1).isoformat()
    end = (today - timedelta(days=1)).isoformat()
    if not stores:
        return []
    rows = client.rpc("audit_annual_status", {
        "p_mall_id": mall_id,
        "p_local_ids": [str(store["id"]) for store in stores],
        "p_start": start,
        "p_end": end,
    }).execute().data or []
    by_local = {str(row["local_id"]): row for row in rows}
    total_days = (today - today.replace(month=1, day=1)).days
    result = []
    for store in stores:
        row = by_local.get(str(store["id"]))
        if row is None:
            raise ValueError("El resumen anual no devolvió todos los locales solicitados")
        result.append({
            "local_id": store["id"], "local_nombre": store["nombre"],
            "ultima_importacion_datos": row.get("ultima_importacion_datos"),
            "audit_year": today.year,
            "dias_faltantes_anio": max(0, total_days - int(row.get("dias_reportados") or 0)),
        })
    return result


def annual_audit_text(row):
    timestamp = row.get("ultima_importacion_datos")
    latest = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Santo_Domingo")).strftime("%d/%m/%Y") if timestamp else "Sin ventas reportadas"
    return f"Última importación con datos: {latest}.\nDías faltantes del período {row['audit_year']}: {row['dias_faltantes_anio']}."
