"""Restore the system's CSV snapshots without replacing existing records."""
import csv
import io
import json
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from uuid import UUID

from services.configuration_backup_service import COLUMNS, IMPORT_FIELDS, STORE_FIELDS, public_value
from services.import_backup_service import CSV_COLUMNS

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000


def unescape(value):
    # Reverse only the prefix emitted by import_backup_service._text.
    if value.startswith("'") and (value[1:].lstrip().startswith(('=', '+', '-', '@')) or value[1:2] in ('\t', '\r', '\n')):
        return value[1:]
    return value


def uid(value):
    return str(UUID(value))


def amount(value):
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError('Importe no finito.')
    return str(number)


class BackupRestoreService:
    def __init__(self, db):
        self.db = db

    def find(self, table, **filters):
        query = self.db.table(table).select('*')
        for key, value in filters.items():
            query = query.eq(key, value)
        return query.limit(1).execute().data or []

    def prepare(self, content, mall, kind):
        columns = CSV_COLUMNS if kind == 'ventas' else COLUMNS.get(kind)
        if not columns:
            raise ValueError('Tipo de backup inválido.')
        if len(content) > MAX_BYTES:
            raise ValueError('El archivo supera 5 MB. Divide el backup en archivos menores.')
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline=''), strict=True)
        if reader.fieldnames != list(columns):
            raise ValueError('Las columnas no corresponden al CSV descargado para este tipo de backup.')
        plan, errors, seen = [], [], set()
        for line, raw in enumerate(reader, 2):
            if line > MAX_ROWS + 1:
                raise ValueError('Máximo 2,000 filas por restauración. Divide el CSV conservando las columnas.')
            try:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError('La cantidad de columnas no coincide.')
                row = {key: unescape(value) for key, value in raw.items()}
                if uid(row['mall_id']) != mall:
                    raise ValueError('El registro pertenece a otro Mall.')
                table, payload, filters = self.record(row, mall, kind)
                key = (table, tuple(sorted(filters.items())))
                duplicate = key in seen or (table != 'importador' and bool(self.find(table, **filters)))
                # Identity is global: never overwrite an ID belonging to another tenant.
                if 'id' in payload and self.find(table, id=payload['id']):
                    duplicate = True
                seen.add(key)
                label = row.get('nombre') or row.get('local_nombre') or row.get('nombre_conexion') or row.get('codigo_local') or ''
                if kind == 'ventas':
                    label += f" · {row['fecha_venta']} · {row['numero_transaccion']} · Neto: {row['total_neto']}"
                plan.append({'line': line, 'label': label, 'table': table, 'payload': payload, 'filters': filters,
                             'duplicate': duplicate, 'status': 'omitido' if duplicate else 'pendiente'})
            except (ValueError, KeyError, InvalidOperation) as exc:
                errors.append({'line': line, 'error': str(exc)})
        if not plan and not errors:
            raise ValueError('El CSV no contiene registros.')
        return plan, errors

    def record(self, row, mall, kind):
        if kind == 'locales':
            payload = {key: row[key] or None for key in STORE_FIELDS if key not in {'created_at'}}
            payload['id'] = uid(row['id'])
            payload['mall_id'] = mall
            if not row['codigo_interno'].strip() or not row['nombre'].strip():
                raise ValueError('Código y nombre del local son obligatorios.')
            if row['activo'].lower() not in {'true', 'false'}:
                raise ValueError('El estado activo debe ser True o False.')
            payload['activo'] = row['activo'].lower() == 'true'
            for field in ('mts', 'porciento_renta', 'renta_fija', 'breakpoint_venta', 'porcentaje_variable'):
                if row[field]:
                    payload[field] = amount(row[field])
            for field in ('fecha_inactivacion', 'fecha_corte_importacion'):
                if row[field]:
                    payload[field] = date.fromisoformat(row[field]).isoformat()
            if row['created_at']:
                datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
                payload['created_at'] = row['created_at']
            payload.update(tipo_ejecucion='MANUAL', upsert_activo=False)
            return 'locales', payload, {'mall_id': mall, 'codigo_interno': row['codigo_interno']}

        if kind != 'ventas' and row['tipo_configuracion'] == 'conexion_compartida':
            if kind != 'ftp' or row['protocolo'] not in {'FTP', 'SFTP'}:
                raise ValueError('Tipo de conexión compartida inválido.')
            port = int(row['puerto'])
            if not 1 <= port <= 65535 or not row['nombre_conexion'] or not row['host']:
                raise ValueError('Nombre, host y puerto son obligatorios.')
            if public_value(row['host']) != row['host']:
                raise ValueError('Host con credenciales no permitido.')
            payload = dict(id=uid(row['id']), mall_id=mall, nombre=row['nombre_conexion'],
                           protocolo=row['protocolo'], host=row['host'], puerto=port,
                           ruta_base=row['ruta_base'], usuario='', password='')
            return 'remote_connections', payload, {'mall_id': mall, 'nombre': row['nombre_conexion']}

        local = uid(row['local_id'])
        if not self.find('locales', id=local, mall_id=mall):
            raise ValueError('Local no encontrado en este Mall. Restaura primero el CSV de locales.')
        if kind == 'ventas':
            sale_date = date.fromisoformat(row['fecha_venta']).isoformat()
            if row['tipo_registro'] not in {'', 'transaccion', 'resumen_diario'}:
                raise ValueError('Tipo de registro inválido.')
            metadata = {key: row[key] for key in ('fecha_importacion', 'canal_importacion', 'archivo_origen', 'batch_id') if row[key]}
            if row['tipo_registro']:
                metadata['granularity'] = 'transaction' if row['tipo_registro'] == 'transaccion' else 'daily'
            payload = dict(id=uid(row['id_registro']), mall_id=mall, local_id=local, fecha=sale_date,
                           factura_no=row['numero_transaccion'], metadata=metadata)
            for field in ('total_bruto', 'total_impuestos', 'total_neto'):
                payload[field] = amount(row[field]) if row[field] else None
            if row['fecha_creacion_registro']:
                datetime.fromisoformat(row['fecha_creacion_registro'].replace('Z', '+00:00'))
                payload['created_at'] = row['fecha_creacion_registro']
            if row['hora_transaccion']:
                time.fromisoformat(row['hora_transaccion'])
                payload['hora_transaccion'] = row['hora_transaccion']
            # Blank invoices cannot safely be deduplicated by the business key.
            filters = {'local_id': local, 'fecha': sale_date, 'factura_no': row['numero_transaccion']} if row['numero_transaccion'].strip() else {'id': payload['id']}
            return 'ventas', payload, filters

        if kind == 'webservice' and row['tipo_configuracion'] == 'receptor_erp':
            if row['contract_type'] != 'msmall_sales_v1' or row['default_granularity'] not in {'transaction', 'daily'}:
                raise ValueError('Contrato de receptor ERP inválido.')
            payload = dict(id=uid(row['id']), mall_id=mall, local_id=local, enabled=False,
                           contract_type=row['contract_type'], default_granularity=row['default_granularity'])
            for field in ('allow_transaction', 'allow_daily', 'strict_validation'):
                if row[field].lower() not in {'true', 'false'}:
                    raise ValueError('Opción de receptor ERP inválida.')
                payload[field] = row[field].lower() == 'true'
            return 'exporter_webservice_configs', payload, {'local_id': local, 'mall_id': mall}
        if row['tipo_configuracion'] != 'importador_local':
            raise ValueError('Este CSV incluye una conexión compartida o receptor ERP: recréalo desde su mantenimiento; no contiene credenciales.')
        payload = {key: row[key] or None for key in IMPORT_FIELDS}
        for field in ('mapping_config', 'constants_config'):
            payload[field] = json.loads(row[field]) if row[field] else {}
            if not isinstance(payload[field], dict) or public_value(payload[field]) != payload[field]:
                raise ValueError('El JSON debe ser un objeto de configuración sin credenciales.')
        if row['sftp_port']:
            payload['sftp_port'] = int(row['sftp_port'])
            if not 1 <= payload['sftp_port'] <= 65535:
                raise ValueError('Puerto inválido.')
        if row['fecha_corte_importacion']:
            date.fromisoformat(row['fecha_corte_importacion'])
        if row['sftp_protocol'] not in {'FTP', 'SFTP', 'API', 'LOCAL', 'WEBSERVICE'}:
            raise ValueError('Protocolo inválido.')
        if not row['sftp_host'] or public_value(row['sftp_host']) != row['sftp_host']:
            raise ValueError('Host inválido o con credenciales.')
        payload.update(tipo_ejecucion='MANUAL')
        return 'importador', payload, {'id': local, 'mall_id': mall}

    def run(self, content, mall, kind, apply=False):
        plan, errors = self.prepare(content, mall, kind)
        # Importer configuration lives on the existing local, so existence alone
        # is not a duplicate. Only fill an entirely unconfigured connection.
        for item in plan:
            if item['table'] == 'importador':
                current = self.find('locales', **item['filters'])[0]
                item['status'] = 'omitido' if item['duplicate'] or any(current.get(field) for field in ('sftp_host', 'sftp_user', 'sftp_pass', 'mapping_config', 'constants_config')) else 'pendiente'
        result = dict(total=len(plan) + len(errors), pendientes=sum(p['status'] == 'pendiente' for p in plan),
                      omitidos=sum(p['status'] == 'omitido' for p in plan), restaurados=0, errores=errors,
                      applied=False, preview=[{'line': p['line'], 'status': p['status'], 'label': p['label'], 'id': p['filters'].get('id') or p['payload'].get('id')} for p in plan[:20]])
        if not apply or errors:
            return result
        result['applied'] = True
        for item in plan:
            if item['status'] != 'pendiente':
                continue
            try:
                if item['table'] == 'importador':
                    # Optimistic predicates protect a connection configured since preview.
                    current = self.find('locales', **item['filters'])[0]
                    query = self.db.table('locales').update(item['payload'])
                    for field, value in item['filters'].items():
                        query = query.eq(field, value)
                    for field in ('sftp_host', 'sftp_user', 'sftp_pass', 'mapping_config', 'constants_config'):
                        value = current.get(field)
                        if value:
                            break
                        query = query.is_(field, 'null') if value is None else query.eq(field, value)
                    else:
                        rows = query.execute().data or []
                        result['restaurados' if rows else 'omitidos'] += 1
                        continue
                    result['omitidos'] += 1
                    continue
                if self.find(item['table'], **item['filters']):
                    result['omitidos'] += 1
                    continue
                rows = self.db.table(item['table']).upsert(item['payload'], ignore_duplicates=True).execute().data or []
                result['restaurados' if rows else 'omitidos'] += 1
            except Exception as exc:
                if str(getattr(exc, 'code', '')) == '23505':
                    result['omitidos'] += 1
                else:
                    # Never reflect database details/credentials to the browser.
                    result['errores'].append({'line': item['line'], 'error': 'No se pudo guardar el registro. Revisa sus datos y vuelve a intentar; los ya restaurados se omitirán.'})
        return result
