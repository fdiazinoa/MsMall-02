"""Manual, tenant-scoped snapshots. Credentials are deliberately not selected."""
import csv
import io
import json
import re
from datetime import datetime, timezone
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit, urlunsplit

from services.import_backup_service import (
    BackupSizeExceeded, GeneratedBackup, ImportBackupService, PAGE_SIZE, STORE_BATCH_SIZE, _text,
)

STORE_FIELDS = (
    'id', 'mall_id', 'codigo_interno', 'nombre', 'activo', 'responsable', 'email',
    'email_secundario', 'contrato_no', 'piso', 'tipo_negocio', 'rubro', 'mts',
    'porciento_renta', 'renta_fija', 'breakpoint_venta', 'porcentaje_variable',
    'fecha_inactivacion', 'motivo_inactivacion', 'fecha_corte_importacion', 'created_at',
)
IMPORT_FIELDS = (
    'sftp_protocol', 'sftp_host', 'sftp_port', 'sftp_path', 'file_type',
    'tipo_ejecucion', 'frecuencia_cron', 'hora_especifica', 'accion_post_procesado',
    'prefijo_backup', 'mapping_config', 'constants_config', 'fecha_corte_importacion',
)
RECEIVER_FIELDS = (
    'enabled', 'contract_type', 'default_granularity', 'allow_transaction',
    'allow_daily', 'strict_validation', 'created_at', 'updated_at',
)
KINDS = ('locales', 'importadores', 'ftp', 'webservice')
IDENTITY = ('tipo_configuracion', 'id', 'mall_id', 'local_id', 'codigo_local', 'local_nombre')
COLUMNS = {
    'locales': ('fecha_backup', *STORE_FIELDS),
    'importadores': ('fecha_backup', *IDENTITY, *IMPORT_FIELDS),
    'ftp': ('fecha_backup', *IDENTITY, *IMPORT_FIELDS, 'nombre_conexion', 'protocolo', 'host', 'puerto', 'ruta_base'),
    'webservice': ('fecha_backup', *IDENTITY, *IMPORT_FIELDS, *RECEIVER_FIELDS),
}
# Configuration JSON can contain credentials at arbitrary depths. Never include
# auth material, request headers/bodies or URL query strings in a downloadable CSV.
PRIVATE_KEY = re.compile(r'password|passwd|passphrase|secret|token|auth|credential|api.?key|headers?|body|cookie|sftp_pass|signature|private.?key|user|usuario|login|bearer|access.?key|clave|contrase[nñ]a', re.I)


def public_value(value):
    if isinstance(value, dict):
        return {key: public_value(item) for key, item in value.items() if not PRIVATE_KEY.search(str(key))}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, str):
        if value.startswith('/') and ('?' in value or '#' in value):
            return value.split('?', 1)[0].split('#', 1)[0]
        if '://' in value:
            try:
                url = urlsplit(value)
                if not url.hostname:
                    return '[omitido]'
                host = url.hostname
                if ':' in host:
                    host = f'[{host}]'
                return urlunsplit((url.scheme, host + (f':{url.port}' if url.port else ''), url.path, '', ''))
            except ValueError:
                return '[omitido]'
        if re.search(r'(?i)(bearer\s+|(?:password|token|secret|api[_-]?key)\s*[:=]|sb_secret_|eyJ[\w-]+\.)', value):
            return '[omitido]'
    return value


class ConfigurationBackupService:
    def __init__(self, db):
        self.db = db

    def _pages(self, table, fields, mall, ids=None, check=None):
        last = None
        while True:
            if check:
                check()
            query = self.db.table(table).select(','.join(fields)).eq('mall_id', mall)
            if ids is not None:
                query = query.in_('local_id' if table == 'exporter_webservice_configs' else 'id', ids)
            if last:
                query = query.gt('id', last)
            page = query.order('id').limit(PAGE_SIZE).execute().data or []
            yield from page
            if len(page) < PAGE_SIZE:
                break
            if page[-1]['id'] == last:
                raise RuntimeError('No se pudo avanzar en la configuración.')
            last = page[-1]['id']

    def generate(self, mall, kind, local_ids, *, stores=None, max_bytes=None, on_progress=None, check_active=None):
        if kind not in KINDS:
            raise ValueError('Tipo de backup inválido.')
        stores = ImportBackupService(self.db).select_stores(mall, local_ids) if stores is None else stores
        ids = [row['id'] for row in stores]
        columns = COLUMNS[kind]
        output = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
        snapshot = datetime.now(timezone.utc).isoformat()
        count = 0

        def write(values):
            buffer = io.StringIO(newline='')
            csv.writer(buffer).writerow(values)
            data = buffer.getvalue().encode('utf-8')
            buffer.close()
            if max_bytes is not None and output.tell() + len(data) > max_bytes:
                raise BackupSizeExceeded('El CSV supera el tamaño permitido o la cuota disponible. Reduce los locales.')
            output.write(data)
            if on_progress:
                on_progress(output.tell())

        def emit(row):
            nonlocal count
            if check_active:
                check_active()
            row = {'fecha_backup': snapshot, **row}
            values = []
            for field in columns:
                value = public_value(row.get(field)) if field in {*IMPORT_FIELDS, 'host', 'ruta_base'} else row.get(field)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                values.append(_text(value))
            write(values)
            count += 1

        try:
            if max_bytes is not None and max_bytes < 3:
                raise BackupSizeExceeded('La cuota disponible no alcanza para este CSV.')
            output.write(b'\xef\xbb\xbf')
            write(columns)
            for offset in range(0, len(ids), STORE_BATCH_SIZE):
                batch = ids[offset:offset + STORE_BATCH_SIZE]
                fields = STORE_FIELDS if kind == 'locales' else ('id', 'mall_id', 'codigo_interno', 'nombre', *IMPORT_FIELDS)
                for row in self._pages('locales', fields, mall, batch, check_active):
                    if kind == 'locales':
                        emit(row)
                        continue
                    protocol = str(row.get('sftp_protocol') or 'SFTP').upper()
                    selected = (kind == 'ftp' and protocol in {'FTP', 'SFTP'}
                                or kind == 'webservice' and protocol == 'WEBSERVICE'
                                or kind == 'importadores' and protocol not in {'FTP', 'SFTP', 'WEBSERVICE'})
                    if selected and row.get('sftp_host'):
                        emit({**row, 'tipo_configuracion': 'importador_local', 'local_id': row['id'],
                              'codigo_local': row.get('codigo_interno'), 'local_nombre': row.get('nombre')})
                if kind == 'webservice':
                    by_id = {row['id']: row for row in stores}
                    for row in self._pages('exporter_webservice_configs', ('id', 'mall_id', 'local_id', *RECEIVER_FIELDS), mall, batch, check_active):
                        store = by_id[row['local_id']]
                        emit({**row, 'tipo_configuracion': 'receptor_erp', 'codigo_local': store.get('codigo_interno'), 'local_nombre': store.get('nombre')})
            if kind == 'ftp' and local_ids is None:
                for row in self._pages('remote_connections', ('id', 'mall_id', 'nombre', 'protocolo', 'host', 'puerto', 'ruta_base'), mall, check=check_active):
                    if str(row.get('protocolo') or '').upper() in {'FTP', 'SFTP'}:
                        emit({**row, 'tipo_configuracion': 'conexion_compartida', 'nombre_conexion': row.get('nombre')})
            output.seek(0)
            return GeneratedBackup(output, count, ids)
        except BaseException:
            output.close()
            raise
