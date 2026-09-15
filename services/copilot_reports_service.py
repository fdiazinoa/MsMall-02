"""Complete, mall-scoped operational exports; no LLM is used to invent records."""
import csv
import io
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from services.sales_gap_service import expected_sales_dates, load_actual_sales_dates_by_local
from services.sensitive_ops_service import sanitize_error_text

PAGE_SIZE = 500
MAX_ROWS = 20000


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c))


def report_intent(message, log_text=''):
    text = normalized(message)
    export = any(word in text for word in ('reporte', 'export', 'excel', 'csv', 'descarg'))
    if not export:
        return None
    kind = None
    if 'log' in text and any(w in text for w in ('error', 'causa', 'fall')):
        kind = 'errores'
    elif any(w in text for w in ('conexion', 'conexiones', 'importacion ftp', 'importacion automatizada')):
        kind = 'conexiones'
    elif any(w in text for w in ('falt', 'brecha', 'sin venta')) and any(w in text for w in ('venta', 'cubo')):
        kind = 'cubo_faltantes'
    elif any(w in text for w in ('fall', 'parcial', 'error')):
        kind = 'cargas_fallidas'
    if not kind and log_text:
        kind = 'errores'
    if not kind:
        return None
    # When both formats are offered, Excel preserves the requested colors.
    fmt = 'csv' if 'csv' in text and not any(w in text for w in ('excel', 'xlsx')) else 'xlsx'
    return {'type': kind, 'format': fmt}


def pages(query):
    rows = []
    offset = 0
    while offset <= MAX_ROWS:
        batch = query.range(offset, offset + PAGE_SIZE - 1).execute().data or []
        rows.extend(batch)
        if len(rows) > MAX_ROWS:
            raise HTTPException(422, 'El reporte supera 20,000 filas. Reduce el período; no se generó un archivo incompleto.')
        if not batch:
            return rows
        offset += len(batch)
    return rows


def resolve_mall(client, selected_id, message, operator, ensure_access):
    ensure_access(operator, selected_id)
    malls = pages(client.table('malls').select('id,nombre').order('id'))
    text = normalized(message)
    if 'todos los malls' in text or 'todos los centros comerciales' in text:
        raise HTTPException(422, 'Genera un reporte por Mall usando el selector o indicando su nombre.')
    matches = [m for m in malls if normalized(m['nombre']) in text]
    # Accept common mall-name variants only when the distinguishing word is unique.
    if not matches:
        ignored = {'mall', 'center', 'centro', 'comercial', 'sdq', 'sqd', 'plaza'}
        candidates = []
        for mall in malls:
            words = set(re.findall(r'\w+', normalized(mall['nombre']))) - ignored
            if words and all(re.search(r'\b' + re.escape(w) + r'\b', text) for w in words):
                candidates.append(mall)
        matches = candidates
    if len(matches) > 1:
        raise HTTPException(422, 'El nombre coincide con varios Malls. Indica el nombre exacto o selecciona uno.')
    if matches:
        mall = matches[0]
    else:
        if re.search(r'\b(?:de|del|para|en)\s+(?:el\s+)?[\w ]{1,50}\bmall\b', text):
            raise HTTPException(422, 'No pude identificar el Mall solicitado. Usa su nombre exacto o el selector.')
        mall = next((m for m in malls if m['id'] == selected_id), None)
    if not mall:
        raise HTTPException(404, 'Mall no encontrado.')
    ensure_access(operator, mall['id'])
    return mall


def period(message, start=None, end=None, now=None):
    today = (now or datetime.now(ZoneInfo('America/Santo_Domingo'))).date()
    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', message)
    if not start and not end and len(dates) == 2:
        start, end = dates
    if bool(start) != bool(end):
        raise HTTPException(422, 'Indica fecha inicial y final.')
    try:
        if start:
            first, last = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
        else:
            match = re.search(r'ultimos?\s+(\d+)\s+dias', normalized(message))
            days = int(match.group(1)) if match else 7
            last = today - timedelta(days=1)
            first = last - timedelta(days=days - 1)
        if not 0 <= (last - first).days < 366:
            raise ValueError()
        return first.isoformat(), last.isoformat()
    except (ValueError, TypeError):
        raise HTTPException(422, 'Período inválido. Usa fechas YYYY-MM-DD y un máximo de 366 días.')


def clean(value):
    text = str(value or '')
    text = re.sub(r'''(?i)(password|token|secret|api[_-]?key|authorization)[\"']?\s*[:=]\s*[\"']?[^\s,;\"']+''', r'\1=[REDACTED]', text)
    text = re.sub(r'((?:https?|s?ftp)://)[^/\s@]+@', r'\1[REDACTED]@', text)
    text = re.sub(r'(?i)bearer\s+[^\s,;"\']+', 'Bearer [REDACTED]', text)
    return sanitize_error_text(text, max_len=30000)


def observation(error):
    text = normalized(error)
    for needles, advice in [
        (('connectionterminated', 'timeout', 'timed out', 'connection refused', 'getaddrinfo'), 'Posible fallo de conexión o disponibilidad. Revisar servidor, red y tiempos de espera.'),
        (('authentication', 'unauthorized', '401', 'invalid credential', 'permission denied'), 'Posible problema de autenticación o permisos. Validar credenciales y acceso al recurso.'),
        (('not found', 'no such file', '404', 'no se encontro'), 'Posible archivo o ruta no disponible. Verificar ruta remota y nombre del archivo.'),
        (('mapping', 'mapeo', 'columna', 'formato', 'parse', 'invalid date'), 'Posible incompatibilidad de formato o mapeo. Revisar columnas, fechas y campos obligatorios.'),
        (('duplicate', 'duplicad', 'unique'), 'Posible registro duplicado. Revisar identificadores y reglas de actualización.'),
    ]:
        if any(n in text for n in needles):
            return advice
    return 'Causa no determinada por el log. Revisar el detalle y contrastar con el archivo de origen.'


def supplied_logs(text):
    if not text.strip():
        raise HTTPException(422, 'Pega el log en «Log para analizar» (CSV, JSON o texto) y vuelve a solicitar el reporte.')
    try:
        if text.lstrip().startswith(('[', '{')):
            parsed = json.loads(text)
            rows = parsed if isinstance(parsed, list) else parsed.get('logs', [parsed])
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                raise ValueError()
            return [{normalized(k).strip(): v for k, v in row.items()} for row in rows]
        first = text.splitlines()[0]
        if any(k in normalized(first) for k in ('fecha', 'local', 'error')) and any(c in first for c in (';', '\t', ',')):
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=';,\t')
            return [{normalized(k or '').strip(): v for k, v in row.items()} for row in csv.DictReader(io.StringIO(text), dialect=dialect)]
        rows = []
        for line in text.splitlines():
            if not line.strip(): continue
            timestamp = re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?', line)
            local = re.search(r'(?i)\blocal\s*[:=]\s*([^;|]+)', line)
            rows.append({'mensaje': line, 'fecha_hora': timestamp.group(0).replace(',', '.') if timestamp else '', 'local': local.group(1).strip() if local else ''})
        return rows
    except (ValueError, csv.Error):
        raise HTTPException(422, 'No se pudo leer el log. Revisa el JSON o las columnas del CSV.')


def log_rows(logs):
    output = []
    for row in logs:
        timestamp = str(row.get('fecha_hora') or '')
        date, hour = row.get('fecha') or 'No indicada', row.get('hora') or row.get('hora de ejecucion') or 'No indicada'
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(ZoneInfo('America/Santo_Domingo'))
                date, hour = dt.date().isoformat(), dt.strftime('%H:%M:%S')
            except ValueError:
                date = timestamp
        error = clean(row.get('mensaje') or row.get('error') or 'Sin mensaje')
        if row.get('detalles'): error += ' | ' + clean(json.dumps(row['detalles'], ensure_ascii=False))
        output.append([date, hour, clean(row.get('local_nombre') or row.get('local') or 'No indicado'), error, observation(error)])
    return output


def failed(row):
    return normalized(row.get('estado', '')) in {'error', 'fallido', 'failed', 'parcial', 'partial', 'carga parcial'} or int(row.get('error_count') or 0) > 0


def build_report(client, intent, mall, message, start=None, end=None, log_text=''):
    kind = intent['type']
    first, last = period(message, start, end) if kind in {'cargas_fallidas', 'cubo_faltantes'} else ('', '')
    definition = {'title': '', 'subtitle': f"{mall['nombre']} | {first} al {last} | America/Santo_Domingo", 'filename_base': f'msmall_{kind}', 'generated_at': datetime.now(timezone.utc).isoformat(), 'sources': [], 'rows': [], 'summary': []}
    if kind == 'errores':
        definition.update(title='Análisis del log facilitado', headers=['Fecha', 'Hora de ejecución', 'Local', 'Error', 'Observación'], rows=log_rows(supplied_logs(log_text)), sources=['Log facilitado por el usuario'], subtitle=f"{mall['nombre']} | Fechas del log facilitado; causas probables, no confirmadas")
        return definition
    if kind == 'cargas_fallidas':
        tz = ZoneInfo('America/Santo_Domingo')
        lower = datetime.fromisoformat(first).replace(tzinfo=tz).isoformat()
        upper = (datetime.fromisoformat(last) + timedelta(days=1)).replace(tzinfo=tz).isoformat()
        logs = pages(client.table('logs_carga').select('id,fecha_hora,local_nombre,estado,mensaje,detalles,error_count').eq('mall_id', mall['id']).gte('fecha_hora', lower).lt('fecha_hora', upper).order('fecha_hora').order('id'))
        logs = [r for r in logs if failed(r)]
        rows = [r[:3] + [clean(log.get('estado'))] + r[3:] for log, r in zip(logs, log_rows(logs))]
        definition.update(title='Cargas fallidas y parciales', headers=['Fecha', 'Hora de ejecución', 'Local', 'Estado', 'Error', 'Observación'], rows=rows, sources=['logs_carga'], summary=[['Ejecuciones fallidas o parciales', len(rows)], ['Locales distintos', len({r[2] for r in rows})]])
        return definition
    columns = 'id,nombre,activo'
    if kind == 'conexiones':
        columns += ',sftp_host,sftp_port,sftp_user,sftp_path,sftp_protocol,file_type,mapping_config,ultima_ejecucion,processing_status,tipo_ejecucion'
    locales = pages(client.table('locales').select(columns).eq('mall_id', mall['id']).order('id'))
    if kind == 'conexiones':
        rows = []
        for local in locales:
            if not local.get('sftp_host'):
                continue
            mapping = local.get('mapping_config') or {}
            if isinstance(mapping, str):
                try: mapping = json.loads(mapping)
                except ValueError: mapping = {}
            protocol = local.get('sftp_protocol') or 'SFTP'
            access = f"{clean(local['sftp_host'])}:{local.get('sftp_port') or (443 if protocol in {'API', 'WEBSERVICE'} else 22)} | {clean(local.get('sftp_user'))}"
            mapped = '; '.join(clean(k) + ' → ' + (clean(v) if not any(t in normalized(k) for t in ('password', 'token', 'secret', 'key')) else '[REDACTED]') for k, v in mapping.items()) if isinstance(mapping, dict) else 'No disponible'
            state = 'Inactivo' if local.get('activo') is False else local.get('processing_status') or 'Activo'
            rows.append([clean(local['nombre']), local.get('file_type') or 'CSV', protocol, access, clean(local.get('sftp_path') or '.'), local.get('ultima_ejecucion') or 'Sin ejecución registrada', mapped, state])
        definition.update(title='Conexiones de Importación Automatizada', subtitle=f"{mall['nombre']} | Configuración actual", headers=['Nombre del local', 'Tipo de formato', 'Protocolo', 'Acceso', 'Ruta remota', 'Última conexión', 'Campos mapeados', 'Estado'], rows=rows, sources=['locales'], summary=[['Última conexión', 'Se usa la última ejecución registrada; no certifica una conexión exitosa.'], ['Acceso', 'Servidor y usuario; sin contraseñas ni tokens.']])
        return definition
    locales = [r for r in locales if r.get('activo') is not False]
    expected = sorted(expected_sales_dates(first, last))
    if len(locales) * (len(expected) + 3) > 250000:
        raise HTTPException(422, 'El cubo supera 250,000 celdas. Reduce el período para exportarlo completo.')
    actual = load_actual_sales_dates_by_local(client, local_ids=[r['id'] for r in locales], fecha_inicio=first, fecha_fin=last) if locales else {}
    rows, red_cells = [], []
    for i, local in enumerate(locales):
        dates = actual.get(str(local['id']), set())
        missing = [d for d in expected if d not in dates]
        rows.append([clean(local['nombre']), len(missing), 'FALTAN VENTAS' if missing else 'COMPLETO'] + ['SIN VENTAS' if d in missing else 'CON VENTAS' for d in expected])
        red_cells.extend((i, j + 3) for j, d in enumerate(expected) if d in missing)
        if missing: red_cells.extend([(i, 0), (i, 1), (i, 2)])
    definition.update(title='Cubo: cobertura de ventas por local y día', headers=['Local', 'Días faltantes', 'Estado'] + expected, rows=rows, red_cells=red_cells, sources=['locales', 'ventas'], summary=[['Criterio', 'Ausencia de registros de venta por día; venta cero registrada cuenta como información.'], ['Alcance', 'Locales activos. No equivale a una auditoría de días de apertura.']])
    return definition


def safe_cell(value):
    # Neutralize spreadsheet formula injection in CSV and Excel alike.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def csv_bytes(definition):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(definition['headers'])
    writer.writerows([safe_cell(v) for v in row] for row in definition['rows'])
    return output.getvalue().encode('utf-8-sig')
