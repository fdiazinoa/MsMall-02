"""Bounded parsing and mapping for untrusted client uploads; no database writes."""
import csv
import hashlib
import io
import json
import math
import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50000
MAX_COLUMNS = 200
FIELDS = ('factura_numero', 'fecha_venta', 'total_bruto', 'total_impuestos', 'total_neto', 'hora')
REQUIRED = FIELDS[:5]


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.rows, self.row, self.cell = [], None, None, None
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignored += 1
        if self.ignored:
            return
        if tag == 'table':
            if self.rows is not None:
                raise ValueError('No se admiten tablas HTML anidadas.')
            self.rows = []
        elif self.rows is not None:
            if tag == 'tr':
                self.row = []
            elif tag in ('td', 'th') and self.row is not None:
                if any(k in ('rowspan', 'colspan') and v != '1' for k, v in attrs):
                    raise ValueError('La tabla HTML contiene celdas combinadas; exporta una tabla simple.')
                self.cell = ''
            elif tag == 'br' and self.cell is not None:
                self.cell += ' '

    def handle_data(self, data):
        if not self.ignored and self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignored = max(0, self.ignored - 1)
        if self.ignored:
            return
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None
        elif tag == 'table' and self.rows is not None:
            if self.rows:
                self.tables.append(self.rows)
            self.rows = None


def _flatten(value, prefix=''):
    result = {}
    for key, item in value.items():
        path = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            if path in result:
                raise ValueError('JSON con nombres de campos ambiguos.')
            result[path] = item
    return result


def parse_upload(raw, filename, table_index=0, has_header=True):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('El archivo debe contener datos y pesar como máximo 10 MB.')
    suffix = Path(filename or '').suffix.lower()
    if suffix not in ('.csv', '.txt', '.json', '.html', '.htm'):
        raise ValueError('Formatos permitidos: CSV, TXT, JSON y HTML.')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        content = raw.decode('cp1252')
    tables = []
    if suffix == '.json':
        data = json.loads(content)
        if isinstance(data, dict):
            candidates = [v for v in data.values() if isinstance(v, list)]
            if len(candidates) > 1:
                raise ValueError('El JSON contiene varias listas; carga una sola lista de ventas.')
            data = candidates[0] if candidates else [data]
        if not isinstance(data, list) or not data or not all(isinstance(row, dict) for row in data):
            raise ValueError('El JSON debe contener una lista de objetos de ventas.')
        rows = [_flatten(row) for row in data]
        headers = list(dict.fromkeys(key for row in rows for key in row))
        kind = 'JSON'
    else:
        if suffix in ('.html', '.htm'):
            parser = TableParser()
            parser.feed(content)
            tables = [{'index': i, 'rows': max(0, len(t) - 1), 'columns': len(t[0])}
                      for i, t in enumerate(parser.tables)]
            if not 0 <= table_index < len(parser.tables):
                raise ValueError('No se encontró la tabla HTML seleccionada.')
            matrix = parser.tables[table_index]
            kind = 'HTML'
        else:
            try:
                delimiter = csv.Sniffer().sniff(content[:8192], delimiters=',;\t|').delimiter
            except csv.Error:
                delimiter = ','
            if len(content.splitlines()) == 1:
                # Sniffer cannot distinguish decimal commas from separators on one row.
                delimiter = max(',;\t|', key=lambda candidate: len(next(csv.reader([content], delimiter=candidate))))
            matrix = [row for row in csv.reader(io.StringIO(content), delimiter=delimiter, strict=True)
                      if any(str(cell).strip() for cell in row)]
            kind = 'CSV'
        if not matrix:
            raise ValueError('El archivo no contiene filas.')
        headers = [str(h).strip() for h in matrix[0]] if has_header else [f'col_{i+1}' for i in range(len(matrix[0]))]
        body = matrix[1:] if has_header else matrix
        if any(len(row) != len(headers) for row in body):
            raise ValueError('Hay filas con diferente cantidad de columnas.')
        rows = [dict(zip(headers, row)) for row in body]
    if not rows or len(rows) > MAX_ROWS or not headers or len(headers) > MAX_COLUMNS:
        raise ValueError('Se requieren entre 1 y 50,000 filas y un máximo de 200 columnas.')
    if any(not h or len(h) > 300 for h in headers) or len(set(headers)) != len(headers):
        raise ValueError('Las columnas deben tener nombres únicos, no vacíos y de hasta 300 caracteres.')
    signature = hashlib.sha256(json.dumps([kind, headers], ensure_ascii=False).encode()).hexdigest()
    return {'headers': headers, 'rows': rows, 'format': kind, 'signature': signature, 'tables': tables}


def prepare_import(parsed, mapping, options, local):
    if not isinstance(mapping, dict) or set(mapping) - set(FIELDS):
        raise ValueError('Mapeo inválido. El local se asigna desde la cuenta, no desde el archivo.')
    if any(not mapping.get(key) for key in REQUIRED):
        raise ValueError('Mapea factura, fecha, bruto, impuestos y neto.')
    if any(header not in parsed['headers'] for header in mapping.values() if header):
        raise ValueError('El formato cambió. Revisa el mapeo de columnas.')
    if options.get('date_format', 'auto') not in ('auto', 'dd/mm/yyyy', 'mm/dd/yyyy', 'yyyy-mm-dd'):
        raise ValueError('Formato de fecha inválido.')
    decimal = options.get('decimal_separator', '.')
    if decimal not in ('.', ','):
        raise ValueError('Separador decimal inválido.')
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(FIELDS))
    writer.writeheader()
    errors = []
    for i, row in enumerate(parsed['rows'], 1):
        record = {key: str(row.get(mapping[key], '') if row.get(mapping[key]) is not None else '').strip()
                  for key in FIELDS if mapping.get(key)}
        for key in REQUIRED:
            if not record.get(key):
                errors.append({'linea': i, 'error': f'Falta {key}.'})
        for key in ('total_bruto', 'total_impuestos', 'total_neto'):
            value = record.get(key, '')
            # Validate before using the legacy parser, which tolerates malformed numbers.
            group = ',' if decimal == '.' else '.'
            pattern = rf'[+-]?(?:\d+|\d{{1,3}}(?:{re.escape(group)}\d{{3}})+)(?:{re.escape(decimal)}\d+)?'
            try:
                number = Decimal(value.replace(group, '').replace(decimal, '.'))
                if not re.fullmatch(pattern, value) or not number.is_finite() or not math.isfinite(float(number)):
                    raise InvalidOperation
                record[key] = str(number)
            except InvalidOperation:
                errors.append({'linea': i, 'error': f'Importe inválido en {key}: {value[:80]}'})
        hour = record.get('hora')
        if hour and not re.fullmatch(r'(?:[01]?\d|2[0-3])(?::[0-5]\d(?::[0-5]\d)?)?', hour):
            errors.append({'linea': i, 'error': 'Hora inválida; usa HH, HH:MM o HH:MM:SS.'})
        writer.writerow(record)
    if not local.get('codigo_interno'):
        raise ValueError('El local asignado no tiene código interno; contacta al administrador.')
    config = {'nombre': local['nombre'], 'tipo_archivo': 'CSV', 'has_header': True,
              'mapping': {key: key for key in FIELDS},
              'constants': {'local_codigo': local['codigo_interno'], '_date_format': options.get('date_format', 'auto'),
                            '_decimal_separator': '.'},
              'fecha_corte_importacion': local.get('fecha_corte_importacion'), '_portal_local_id': local.get('id')}
    return output.getvalue(), config, errors
