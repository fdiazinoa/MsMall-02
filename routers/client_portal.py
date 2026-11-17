"""Client uploads are isolated from staff ingestion and FTP configuration."""
import hashlib
import json
import logging
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from services.client_portal_service import MAX_BYTES, parse_upload, prepare_import

logger = logging.getLogger(__name__)


class ClientAccount(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    local_id: UUID


class Grant(BaseModel):
    user_id: UUID
    local_id: UUID


def create_client_portal_router(*, get_db, authenticate, admin_create, admin_update, process_content, analyze_content, log_upload, ensure_mall_access, user_mall_ids):
    router = APIRouter(tags=['Portal de clientes'])

    def db():
        if os.getenv('CLIENT_PORTAL_ENABLED', '').lower() not in ('true', '1'):
            raise HTTPException(404, 'Portal de clientes no habilitado.')
        client = get_db()
        if client is None:
            raise HTTPException(503, 'Portal temporalmente no disponible.')
        return client

    def assigned_local(client, user_id):
        grants = client.table('client_portal_grants').select('local_id').eq('user_id', user_id).execute().data or []
        if len(grants) != 1:
            raise HTTPException(403, 'Tu cuenta debe tener un único local asignado. Contacta al administrador.')
        return load_local(client, grants[0]['local_id'])

    def load_local(client, local_id):
        rows = client.table('locales').select('id,nombre,codigo_interno,mall_id,activo,fecha_corte_importacion').eq('id', str(local_id)).execute().data
        if not rows or rows[0].get('activo') is False:
            raise HTTPException(404, 'Local no disponible.')
        return rows[0]

    async def read_file(file, table_index, has_header):
        raw = await file.read(MAX_BYTES + 1)
        try:
            parsed = await run_in_threadpool(parse_upload, raw, file.filename, table_index, has_header)
            return raw, parsed
        except (ValueError, TypeError, RecursionError) as exc:
            raise HTTPException(422, str(exc)) from exc

    def prepare(parsed, mapping_text, options_text, local):
        try:
            mapping, options = json.loads(mapping_text), json.loads(options_text)
            if not isinstance(options, dict) or set(options) - {'date_format', 'decimal_separator'}:
                raise ValueError('Opciones de mapeo inválidas.')
            content, config, errors = prepare_import(parsed, mapping, options, local)
            if errors:
                return content, config, mapping, options, 0, errors
            count, errors = process_content(content, 'portal.csv', config, 'preview', local['mall_id'], dry_run=True)
            return content, config, mapping, options, count, errors
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get('/api/v1/portal/local')
    def my_local(user_id: str = Depends(authenticate)):
        local = assigned_local(db(), user_id)
        return {key: local[key] for key in ('id', 'nombre', 'codigo_interno', 'mall_id')}

    @router.get('/api/v1/portal/history')
    def history(user_id: str = Depends(authenticate)):
        client = db()
        local = assigned_local(client, user_id)
        return client.table('client_portal_uploads').select('id,filename,status,records_processed,errors,created_at').eq('user_id', user_id).eq('local_id', local['id']).order('created_at', desc=True).limit(30).execute().data or []

    @router.post('/api/v1/portal/analyze')
    async def analyze(file: UploadFile = File(...), table_index: int = Form(0),
                      has_header: bool = Form(True), user_id: str = Depends(authenticate)):
        client = db()
        local = assigned_local(client, user_id)
        local_id = local['id']
        _, parsed = await read_file(file, table_index, has_header)
        # Suggest using the existing mapping analyzer against canonical JSON rows.
        analysis = analyze_content(json.dumps(parsed['rows'][:10]), 'portal.json', 'JSON')
        saved = client.table('client_portal_mappings').select('mapping,options').eq('user_id', user_id).eq('local_id', str(local_id)).eq('signature', parsed['signature']).execute().data or []
        return {**{k: parsed[k] for k in ('headers', 'format', 'signature', 'tables')},
                'sample': parsed['rows'][:5], 'row_count': len(parsed['rows']),
                'suggested_mapping': analysis.get('suggested_mapping', {}), 'saved': saved[0] if saved else None}

    @router.post('/api/v1/portal/validate')
    async def validate(file: UploadFile = File(...), mapping: str = Form(...),
                       options: str = Form('{}'), table_index: int = Form(0), has_header: bool = Form(True),
                       user_id: str = Depends(authenticate)):
        client = db()
        local = assigned_local(client, user_id)
        local_id = local['id']
        _, parsed = await read_file(file, table_index, has_header)
        _, _, _, _, count, errors = await run_in_threadpool(prepare, parsed, mapping, options, local)
        return {'valid': bool(count) and not errors, 'records': count, 'error_count': len(errors), 'errors': errors[:100]}

    @router.post('/api/v1/portal/import')
    async def import_file(request_id: UUID = Form(...), file: UploadFile = File(...),
                          mapping: str = Form(...), options: str = Form('{}'), table_index: int = Form(0),
                          has_header: bool = Form(True), user_id: str = Depends(authenticate)):
        client = db()
        local = assigned_local(client, user_id)
        local_id = local['id']
        raw, parsed = await read_file(file, table_index, has_header)
        content, config, clean_mapping, clean_options, count, errors = await run_in_threadpool(prepare, parsed, mapping, options, local)
        if errors or not count:
            return {'status': 'invalid', 'records_processed': 0, 'error_count': len(errors), 'errors': errors[:100]}
        fingerprint = hashlib.sha256(raw + json.dumps([str(local_id), clean_mapping, clean_options, table_index, has_header], sort_keys=True).encode()).hexdigest()
        existing = client.table('client_portal_uploads').select('*').eq('id', str(request_id)).execute().data or []
        if existing:
            previous = existing[0]
            if previous['user_id'] != user_id or previous['fingerprint'] != fingerprint:
                raise HTTPException(409, 'El identificador de envío ya fue utilizado.')
            return previous
        record = {'id': str(request_id), 'user_id': user_id, 'local_id': str(local_id),
                  'filename': (file.filename or 'archivo')[:255], 'fingerprint': fingerprint, 'status': 'processing'}
        try:
            client.table('client_portal_uploads').insert(record).execute()
        except Exception as exc:
            # A concurrent duplicate never gets permission to process a second time.
            raise HTTPException(409, 'El envío ya está en proceso o no pudo registrarse. Consulta el historial.') from exc
        try:
            count, errors = await run_in_threadpool(process_content, content, 'portal.csv', config, str(request_id), local['mall_id'])
            result = {'status': 'partial' if count and errors else 'success' if count else 'error',
                      'records_processed': count, 'errors': errors[:100]}
            log_upload(local['nombre'], file.filename, 'exito' if result['status'] == 'success' else 'parcial' if count else 'error',
                       f'Portal de clientes: {count} registros procesados.', str(request_id), errors[:100],
                       mall_id=local['mall_id'], local_id=str(local_id), canal='Portal', records_processed=count,
                       error_count=len(errors), metadata={'source': 'client_portal', 'user_id': user_id})
            client.table('client_portal_uploads').update(result).eq('id', str(request_id)).execute()
            if count and not errors:
                client.table('client_portal_mappings').upsert({'user_id': user_id, 'local_id': str(local_id),
                    'signature': parsed['signature'], 'mapping': clean_mapping, 'options': clean_options},
                    on_conflict='user_id,local_id,signature').execute()
            return {'id': str(request_id), **result}
        except Exception as exc:
            logger.exception('Client portal import failed: %s', request_id)
            raise HTTPException(503, 'No se pudo completar el envío. Consulta el historial antes de reintentar.') from exc

    @router.get('/api/v1/admin/portal/locals')
    def admin_locals(mall_id: UUID, ctx=Depends(admin_update)):
        client = db()
        ensure_mall_access(ctx, str(mall_id))
        return client.table('locales').select('id,nombre,codigo_interno,mall_id').eq('activo', True).eq('mall_id', str(mall_id)).execute().data or []

    @router.get('/api/v1/admin/portal/grants')
    def grants(user_id: UUID, ctx=Depends(admin_update)):
        return db().table('client_portal_grants').select('local_id').eq('user_id', str(user_id)).execute().data or []

    @router.post('/api/v1/admin/portal/grants')
    def grant(payload: Grant, ctx=Depends(admin_update)):
        client = db()
        local = load_local(client, payload.local_id)
        ensure_mall_access(ctx, local['mall_id'])
        target = client.auth.admin.get_user_by_id(str(payload.user_id)).user
        if not (getattr(target, 'app_metadata', None) or {}).get('portal_client'):
            raise HTTPException(400, 'Sólo se pueden vincular cuentas exclusivas del portal.')
        existing = client.table('client_portal_grants').select('local_id').eq('user_id', str(payload.user_id)).execute().data or []
        if existing:
            raise HTTPException(409, 'La cuenta ya tiene un local. Retira su vínculo actual antes de cambiarlo.')
        try:
            client.table('client_portal_grants').insert({'user_id': str(payload.user_id), 'local_id': str(payload.local_id)}).execute()
        except Exception as exc:
            raise HTTPException(409, 'No se pudo vincular el local; verifica si la cuenta ya tiene uno asignado.') from exc
        return {'status': 'success'}

    @router.delete('/api/v1/admin/portal/grants')
    def revoke(payload: Grant, ctx=Depends(admin_update)):
        client = db()
        local = load_local(client, payload.local_id)
        ensure_mall_access(ctx, local['mall_id'])
        client.table('client_portal_grants').delete().eq('user_id', str(payload.user_id)).eq('local_id', str(payload.local_id)).execute()
        return {'status': 'success'}

    @router.post('/api/v1/admin/portal/clients')
    def create_client(payload: ClientAccount, ctx=Depends(admin_create)):
        client = db()
        local = load_local(client, payload.local_id)
        ensure_mall_access(ctx, local['mall_id'])
        try:
            user = client.auth.admin.create_user({'email': payload.email.strip().lower(), 'password': payload.password,
                    'email_confirm': True, 'app_metadata': {'portal_client': True}}).user
        except Exception as exc:
            raise HTTPException(400, 'No se pudo crear la cuenta. Verifica el correo o si ya existe.') from exc
        try:
            client.table('client_portal_grants').insert({'user_id': user.id, 'local_id': str(payload.local_id)}).execute()
        except Exception:
            client.auth.admin.delete_user(user.id)
            raise HTTPException(503, 'No se pudo asignar el local; la cuenta fue retirada.')
        return {'id': user.id, 'email': user.email}

    return router
