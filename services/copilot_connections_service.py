"""Read-only, mall-scoped connection inventory for Copilot (no credentials)."""

from typing import Any, Dict


CONNECTION_COLUMNS = "id,nombre,codigo_interno,sftp_protocol"
EXPORTER_COLUMNS = "id,local_id,enabled"
CONNECTION_SOURCES = ["locales.sftp_protocol", "exporter_webservice_configs"]
CONNECTION_TYPES = ("FTP", "SFTP", "API", "WEBSERVICE", "LOCAL", "SIN_CONFIGURAR", "OTRO")


def _load_rows(supabase: Any, table: str, columns: str, mall_id: str):
    after_id = None
    while True:
        query = (
            supabase.table(table)
            .select(columns)
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
        yield from rows


def load_copilot_connection_inventory(supabase: Any, mall_id: str) -> Dict[str, Any]:
    if not mall_id:
        raise ValueError("El inventario requiere un mall.")

    locales_by_id = {row["id"]: row for row in _load_rows(supabase, "locales", CONNECTION_COLUMNS, mall_id)}
    # Incoming ERP webservices are configured separately from outbound imports.
    # Load all pages before reporting totals: a failed source must not look empty.
    exporters = list(_load_rows(supabase, "exporter_webservice_configs", EXPORTER_COLUMNS, mall_id))
    enabled_exporters = {row["local_id"] for row in exporters if row.get("enabled") is True}
    groups = {protocol: [] for protocol in CONNECTION_TYPES}
    multiple_types = 0
    for local_id, row in locales_by_id.items():
        protocol = str(row.get("sftp_protocol") or "").strip().upper()
        protocol = protocol.replace("_", "").replace("-", "").replace(" ", "")
        if not protocol:
            protocol = "SIN_CONFIGURAR"
        elif protocol not in CONNECTION_TYPES[:5]:
            protocol = "OTRO"
        protocols = {protocol: ["locales.sftp_protocol"]}
        if local_id in enabled_exporters:
            protocols.pop("SIN_CONFIGURAR", None)
            protocols.setdefault("WEBSERVICE", []).append("exporter_webservice_configs")
        multiple_types += len(protocols) > 1
        for configured_protocol, sources in protocols.items():
            groups[configured_protocol].append({
                "nombre": row.get("nombre"),
                "codigo": row.get("codigo_interno"),
                "fuentes": sources,
            })

    for locales in groups.values():
        locales.sort(key=lambda row: (str(row["nombre"] or "").casefold(), str(row["codigo"] or "")))
    return {
        "status": "disponible",
        "fuente": ", ".join(CONNECTION_SOURCES),
        "mall_id": mall_id,
        "alcance": "Todos los locales del mall: protocolos de importacion y webservices receptores habilitados. No indica conectividad ni uso efectivo.",
        "nota_conteo": "Un local puede figurar en varios tipos. No sumar categorias para obtener el total de locales unicos.",
        "total_locales": len(locales_by_id),
        "locales_con_varios_tipos": multiple_types,
        "webservices_receptores_deshabilitados": sum(
            1 for row in exporters if row.get("enabled") is False and row["local_id"] in locales_by_id
        ),
        "por_tipo": {
            protocol: {"total": len(locales), "locales": locales}
            for protocol, locales in groups.items()
        },
    }
