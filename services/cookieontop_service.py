"""Citrus CookieOnTop: company-scoped Bearer authentication, invoice-level sales."""
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

import httpx

ENDPOINT = "https://api.citrus.com.do/cookieontop/ventas"
MAX_RECORDS = 10000


def is_cookieontop_config(config):
    constants = config.get("constants_config") or config.get("constants") or {}
    provider = str(constants.get("provider") or config.get("provider") or "").lower()
    host = str(config.get("sftp_host") or config.get("host") or "").rstrip("/")
    return provider == "cookieontop" or host in {ENDPOINT, ENDPOINT.removesuffix("/ventas")}


def _fields(row):
    if not isinstance(row, dict):
        raise ValueError("CookieOnTop: factura invalida; se esperaba un objeto")
    return {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in row.items()}


def _decimal(value, field):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return number
    except (InvalidOperation, ValueError):
        raise ValueError(f"CookieOnTop: campo {field} ausente o invalido") from None


def map_sale(config, raw):
    row = _fields(raw)
    identifier = str(row.get("idtransaccion") or "")
    if not re.fullmatch(r"[1-9][0-9]*", identifier):
        raise ValueError("CookieOnTop: id_transaccion ausente o invalido")
    try:
        day = date.fromisoformat(str(row.get("fecha"))).isoformat()
        hour = time.fromisoformat(str(row["hora"])).isoformat() if row.get("hora") else None
    except ValueError:
        raise ValueError("CookieOnTop: fecha u hora invalida") from None
    rate = _decimal(row.get("tasa"), "tasa")
    if rate <= 0:
        raise ValueError("CookieOnTop: tasa debe ser mayor que cero")
    payload = {
        "local_id": config.get("id"), "mall_id": config.get("mall_id"),
        "fecha": day, "factura_no": f"COOKIEONTOP-{identifier}",
        "comprobante": str(row.get("ncf") or "").strip() or None,
        "hora_transaccion": hour,
    }
    # numserie identifies a customer, never an invoice. Transaction ID is stable.
    for source, target in (("totalbruto", "total_bruto"), ("totalimpuestos", "total_impuestos"), ("totalneto", "total_neto")):
        payload[target] = float((_decimal(row.get(source), source) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return payload


def fetch_sales(config, start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or (last - first).days >= 366:
        raise ValueError("CookieOnTop: consulta un rango de hasta 366 dias")
    host = str(config.get("sftp_host") or config.get("host") or ENDPOINT).rstrip("/")
    if host not in {ENDPOINT, ENDPOINT.removesuffix("/ventas")}:
        raise ValueError("CookieOnTop: utiliza el endpoint HTTPS oficial de Citrus")
    token = str(config.get("sftp_pass") or config.get("password") or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError("CookieOnTop: token Bearer requerido o invalido")
    tpv = str(config.get("sftp_path") or config.get("ruta_remota") or "").strip()
    if tpv == ".":
        tpv = ""
    if tpv and not re.fullmatch(r"[1-9][0-9]*", tpv):
        raise ValueError("CookieOnTop: ID TPV debe ser un entero mayor que cero")

    def query(client, lo, hi):
        params = {"fecha": lo.isoformat()} if lo == hi else {"FechaDesde": lo.isoformat(), "FechaHasta": hi.isoformat()}
        if tpv:
            params["idTpv"] = tpv
        try:
            response = client.get(ENDPOINT, params=params)
        except httpx.RequestError:
            raise RuntimeError("CookieOnTop: no se pudo conectar con Citrus; reintente mas tarde") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        message = str(data.get("mensaje") or "").lower() if isinstance(data, dict) else ""
        if response.status_code == 404 and "tpv" not in message and any(s in message for s in ("no hay ventas", "no se encontraron ventas", "no existen ventas")):
            return []
        if response.status_code == 400 and "10000" in message and "registros" in message and lo < hi:
            midpoint = lo + (hi - lo) // 2
            return query(client, lo, midpoint) + query(client, midpoint + timedelta(days=1), hi)
        if response.status_code != 200:
            hints = {401: "token invalido o revocado", 404: "ventas o TPV no encontrados; revise el filtro", 429: "limite de solicitudes; reintente pasado un minuto", 400: "parametros invalidos o limite de registros; reduzca el rango", 500: "servicio Citrus no disponible; reintente mas tarde"}
            raise RuntimeError(f"CookieOnTop HTTP {response.status_code}: {hints.get(response.status_code, 'respuesta inesperada del proveedor')}")
        if not isinstance(data, list) or len(data) > MAX_RECORDS:
            raise ValueError("CookieOnTop: respuesta invalida o superior a 10000 registros")
        return data

    with httpx.Client(headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=20, follow_redirects=False) as client:
        raw_rows = query(client, first, last)
    rows = {}
    for raw in raw_rows:
        row = map_sale(config, raw)
        if not start <= row["fecha"] <= end:
            raise ValueError("CookieOnTop: el proveedor devolvio ventas fuera del periodo solicitado")
        key = row["factura_no"]
        if key in rows and rows[key] != row:
            raise ValueError("CookieOnTop: transaccion repetida con datos distintos")
        rows[key] = row
    return list(rows.values()), f"CookieOnTop {start}..{end}"
