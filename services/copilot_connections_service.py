"""Read-only, mall-scoped connection inventory for Copilot (no credentials)."""

from typing import Any, Dict


CONNECTION_COLUMNS = "id,nombre,codigo_interno,sftp_protocol"
CONNECTION_TYPES = ("FTP", "SFTP", "API", "WEBSERVICE", "LOCAL", "SIN_CONFIGURAR", "OTRO")


def load_copilot_connection_inventory(supabase: Any, mall_id: str) -> Dict[str, Any]:
    if not mall_id:
        raise ValueError("El inventario requiere un mall.")

    groups = {protocol: [] for protocol in CONNECTION_TYPES}
    after_id = None
    while True:
        query = (
            supabase.table("locales")
            .select(CONNECTION_COLUMNS)
            .eq("mall_id", mall_id)
            .order("id")
            .limit(500)
        )
        if after_id is not None:
            query = query.gt("id", after_id)
        rows = query.execute().data or []
        # Read until empty, including when the server caps pages below 500.
        if not rows:
            break
        next_id = rows[-1].get("id")
        if next_id is None or next_id == after_id:
            raise ValueError("No se pudo completar el inventario de conexiones.")
        after_id = next_id
        for row in rows:
            protocol = str(row.get("sftp_protocol") or "").strip().upper()
            protocol = protocol.replace("_", "").replace("-", "").replace(" ", "")
            if not protocol:
                protocol = "SIN_CONFIGURAR"
            elif protocol not in CONNECTION_TYPES[:5]:
                protocol = "OTRO"
            groups[protocol].append({
                "nombre": row.get("nombre"),
                "codigo": row.get("codigo_interno"),
            })

    for locales in groups.values():
        locales.sort(key=lambda row: (str(row["nombre"] or "").casefold(), str(row["codigo"] or "")))
    return {
        "status": "disponible",
        "fuente": "locales.sftp_protocol",
        "mall_id": mall_id,
        "alcance": "Todos los locales del mall seleccionado; tipo registrado, no estado de conectividad.",
        "total_locales": sum(len(locales) for locales in groups.values()),
        "por_tipo": {
            protocol: {"total": len(locales), "locales": locales}
            for protocol, locales in groups.items()
        },
    }
