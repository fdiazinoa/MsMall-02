"""Read-only CSV backups of stored sales, with bounded memory usage."""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO, Dict, List, Optional


CSV_COLUMNS = (
    "id_registro", "mall_id", "mall_nombre", "local_id", "codigo_local", "local_nombre",
    "fecha_venta", "hora_transaccion", "numero_transaccion", "tipo_registro",
    "total_bruto", "total_impuestos", "total_neto", "fecha_creacion_registro",
    "fecha_importacion", "canal_importacion", "archivo_origen", "batch_id",
)
SALES_FIELDS = (
    "id,local_id,fecha,hora,hora_transaccion,factura_no,total_bruto,"
    "total_impuestos,total_neto,created_at,metadata"
)
PAGE_SIZE = 1000
STORE_BATCH_SIZE = 100


class InvalidBackupSelection(ValueError):
    pass


class BackupSizeExceeded(ValueError):
    pass


@dataclass
class GeneratedBackup:
    file: BinaryIO
    records: int
    local_ids: List[str]


def _text(value: Any) -> str:
    """Escape spreadsheet formulas in text cells; numeric cells use _amount."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def _amount(value: Any) -> str:
    if value is None or value == "":
        return ""
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Importe no finito en un registro de venta.")
    return format(number, "f")


class ImportBackupService:
    def __init__(self, db: Any):
        self.db = db

    def list_stores(self, mall_id: str) -> List[Dict[str, Any]]:
        stores = []
        last_id = None
        while True:
            query = self.db.table("locales").select("id,codigo_interno,nombre,activo").eq("mall_id", mall_id)
            if last_id:
                query = query.gt("id", last_id)
            page = query.order("id").limit(PAGE_SIZE).execute().data or []
            stores.extend(page)
            if len(page) < PAGE_SIZE:
                break
            next_id = page[-1]["id"]
            if next_id == last_id:
                raise RuntimeError("No se pudo avanzar en la lista de locales.")
            last_id = next_id
        return sorted(stores, key=lambda row: (str(row.get("nombre") or "").casefold(), row["id"]))

    def _trace_by_batch(self, mall_id: str, rows: List[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
        batch_ids = list({str(row["metadata"]["batch_id"]) for row in rows
                          if isinstance(row.get("metadata"), dict) and row["metadata"].get("batch_id")})
        traces = {}
        for offset in range(0, len(batch_ids), STORE_BATCH_SIZE):
            last_id = None
            while True:
                query = (self.db.table("logs_carga")
                         .select("id,local_id,batch_id,fecha_hora,archivo,canal,estado")
                         .eq("mall_id", mall_id)
                         .in_("local_id", list({row["local_id"] for row in rows}))
                         .in_("batch_id", batch_ids[offset:offset + STORE_BATCH_SIZE]))
                if last_id:
                    query = query.gt("id", last_id)
                page = query.order("id").limit(PAGE_SIZE).execute().data or []
                for log in page:
                    if str(log.get("estado") or "").lower() not in {"exito", "parcial"}:
                        continue
                    key = (log["local_id"], str(log["batch_id"]))
                    previous = traces.get(key)
                    if previous is None or str(log.get("fecha_hora") or "") > str(previous.get("fecha_hora") or ""):
                        traces[key] = log
                if len(page) < PAGE_SIZE:
                    break
                next_id = page[-1]["id"]
                if next_id == last_id:
                    raise RuntimeError("No se pudo avanzar en la trazabilidad de importaciones.")
                last_id = next_id
        return traces

    def select_stores(self, mall_id: str, local_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
        stores = self.list_stores(mall_id)
        stores_by_id = {row["id"]: row for row in stores}
        if local_ids is not None:
            if not local_ids or any(local_id not in stores_by_id for local_id in local_ids):
                raise InvalidBackupSelection("Selecciona locales que pertenezcan al Mall activo.")
            requested_ids = set(local_ids)
            stores = [row for row in stores if row["id"] in requested_ids]
        return stores

    def generate(self, mall_id: str, start: str, end: str, local_ids: Optional[List[str]],
                 *, stores=None, max_bytes=None, on_progress=None, check_active=None) -> GeneratedBackup:
        stores = self.select_stores(mall_id, local_ids) if stores is None else stores
        stores_by_id = {row["id"]: row for row in stores}
        selected_ids = [row["id"] for row in stores]
        malls = self.db.table("malls").select("nombre").eq("id", mall_id).limit(1).execute().data or []
        mall_name = malls[0].get("nombre") if malls else ""
        output = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        records = 0

        def flush():
            data = buffer.getvalue().encode("utf-8")
            if max_bytes is not None and output.tell() + len(data) > max_bytes:
                raise BackupSizeExceeded("El CSV supera el tamaño permitido o la cuota disponible. Reduce el período o los locales.")
            output.write(data)
            buffer.seek(0)
            buffer.truncate(0)
            if on_progress:
                on_progress(output.tell())

        try:
            if max_bytes is not None and max_bytes < 3:
                raise BackupSizeExceeded("La cuota disponible no alcanza para este CSV.")
            output.write(b"\xef\xbb\xbf")  # Excel-compatible UTF-8.
            writer.writerow(CSV_COLUMNS)
            flush()
            for offset in range(0, len(selected_ids), STORE_BATCH_SIZE):
                scoped_ids = selected_ids[offset:offset + STORE_BATCH_SIZE]
                cursor = None
                while True:
                    if check_active:
                        check_active()
                    # The verified parent locales define tenancy, including legacy sales
                    # whose denormalized ventas.mall_id may be missing.
                    query = (self.db.table("ventas").select(SALES_FIELDS)
                             .in_("local_id", scoped_ids).gte("fecha", start).lte("fecha", end))
                    if cursor:
                        query = query.or_(f"fecha.gt.{cursor[0]},and(fecha.eq.{cursor[0]},id.gt.{cursor[1]})")
                    page = query.order("fecha").order("id").limit(PAGE_SIZE).execute().data or []
                    traces = self._trace_by_batch(mall_id, page)
                    for sale in page:
                        store = stores_by_id[sale["local_id"]]
                        meta = sale.get("metadata") if isinstance(sale.get("metadata"), dict) else {}
                        batch_id = meta.get("batch_id")
                        trace = traces.get((sale["local_id"], str(batch_id)), {})
                        granularity = {"daily": "resumen_diario", "daily_summary": "resumen_diario",
                                       "transaction": "transaccion"}.get(str(meta.get("granularity") or "").lower(), "")
                        channel = meta.get("canal_importacion") or trace.get("canal")
                        if not channel and meta.get("source") == "exporter_webservice":
                            channel = "WebService"
                        values = [sale.get("id"), mall_id, mall_name, sale["local_id"], store.get("codigo_interno"),
                                  store.get("nombre"), sale.get("fecha"), sale.get("hora_transaccion") or sale.get("hora"),
                                  sale.get("factura_no"), granularity]
                        writer.writerow([*map(_text, values),
                                         *(_amount(sale.get(key)) for key in ("total_bruto", "total_impuestos", "total_neto")),
                                         *map(_text, [sale.get("created_at"), meta.get("fecha_importacion") or trace.get("fecha_hora"),
                                                      channel, meta.get("archivo_origen") or trace.get("archivo"), batch_id])])
                        records += 1
                    flush()
                    if len(page) < PAGE_SIZE:
                        break
                    next_cursor = (page[-1]["fecha"], page[-1]["id"])
                    if next_cursor == cursor:
                        raise RuntimeError("No se pudo avanzar en la paginación de ventas.")
                    cursor = next_cursor
            output.seek(0)
            return GeneratedBackup(output, records, selected_ids)
        except BaseException:
            output.close()
            raise
        finally:
            buffer.close()
