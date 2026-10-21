"""Calendar scheduling and private, quota-accounted CSV artifacts."""
import logging
import os
import shutil
from datetime import date, datetime, time, timedelta, timezone
from tempfile import NamedTemporaryFile, SpooledTemporaryFile
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from services.import_backup_service import ImportBackupService, GeneratedBackup
from services.import_backup_quota_service import ImportBackupQuotaService, BackupQuotaError

TZ = ZoneInfo('America/Santo_Domingo')
BUCKET = 'import-backups'
MAX_STORED_BYTES = 50_000_000
log = logging.getLogger('import-backup-scheduler')


def automation_enabled():
    return os.getenv('ENABLE_SCHEDULED_IMPORT_BACKUPS', 'false').lower() in {'1', 'true', 'yes'}


class BackupSchedule(BaseModel):
    frequency: Literal['weekly', 'fortnightly', 'monthly'] = 'weekly'
    run_hour: int = Field(default=2, ge=0, le=23)
    folder: str = Field(default='importaciones', min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*$')
    local_ids: list[UUID] | None = None
    retention_days: int = Field(default=30, ge=7, le=90)
    enabled: bool = False

    @field_validator('local_ids')
    @classmethod
    def nonempty_selection(cls, value):
        if value is not None and not value:
            raise ValueError('Selecciona al menos un local.')
        return value


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def next_slot(frequency, hour, after):
    """Weekly = Monday; fortnightly = 1st/16th; monthly = 1st."""
    local = after.astimezone(TZ)
    for offset in range(0, 33):
        day = local.date() + timedelta(days=offset)
        matches = (frequency == 'weekly' and day.weekday() == 0
                   or frequency == 'fortnightly' and day.day in (1, 16)
                   or frequency == 'monthly' and day.day == 1)
        candidate = datetime.combine(day, time(hour), TZ)
        if matches and candidate > local:
            return candidate.astimezone(timezone.utc)
    raise ValueError('No se pudo calcular la próxima ejecución.')


def sale_period(frequency, scheduled_at):
    day = scheduled_at.astimezone(TZ).date()
    end = day - timedelta(days=1)
    if frequency == 'weekly':
        start = day - timedelta(days=7)
    elif frequency == 'fortnightly' and day.day == 16:
        start = day.replace(day=1)
    elif frequency == 'fortnightly':
        start = end.replace(day=16)
    else:
        start = end.replace(day=1)
    return start, end


class ImportBackupScheduleService:
    def __init__(self, db):
        self.db = db

    def schedule(self, user, mall):
        rows = self.db.table('import_backup_schedules').select('*').eq('owner_id', user).eq('mall_id', mall).limit(1).execute().data or []
        return rows[0] if rows else None

    def list(self, user, mall):
        rows = self.db.table('import_backup_artifacts').select(
            'id,start_date,end_date,status,filename,bytes,records,error,created_at,expires_at'
        ).eq('owner_id', user).eq('mall_id', mall).order('created_at', desc=True).limit(50).execute().data or []
        return {'schedule': self.schedule(user, mall), 'artifacts': rows, 'automation_enabled': automation_enabled(),
                'timezone': str(TZ), 'max_file_mb': 50}

    def save(self, user, mall, config, existing=None):
        # Validate store ownership even if the schedule is currently paused.
        ids = [str(value) for value in config.local_ids] if config.local_ids is not None else None
        ImportBackupService(self.db).select_stores(mall, ids)
        values = config.model_dump(mode='json')
        values.update(owner_id=user, mall_id=mall, next_run_at=next_slot(config.frequency, config.run_hour, utc_now()).isoformat(), updated_at=utc_now().isoformat())
        if existing:
            self.db.table('import_backup_schedules').update(values).eq('id', existing['id']).eq('owner_id', user).eq('mall_id', mall).execute()
        else:
            # A concurrent creator gets a unique conflict, never an unauthorized update.
            self.db.table('import_backup_schedules').insert(values).execute()
        return self.list(user, mall)

    def delete(self, user, mall):
        self.db.table('import_backup_schedules').delete().eq('owner_id', user).eq('mall_id', mall).execute()
        return self.list(user, mall)

    def _authorized_owner(self, user, mall):
        # Only server-owned RBAC assignments can authorize unattended jobs.
        assignment = self.db.table('profile_role_assignments').select('role_id').eq('user_id', user).limit(1).execute().data or []
        if not assignment:
            return False
        role_id = assignment[0]['role_id']
        permissions = self.db.table('app_role_permissions').select('module_key,can_view,can_create').eq('role_id', role_id).execute().data or []
        permissions = {p['module_key']: p for p in permissions}
        if not (permissions.get('import_backup', {}).get('can_view') and permissions.get('backup_schedules', {}).get('can_view') and permissions.get('backup_schedules', {}).get('can_create')):
            return False
        role = self.db.table('app_roles').select('key').eq('id', role_id).limit(1).execute().data or []
        if role and role[0]['key'] == 'admin':
            return True
        return bool(self.db.table('usuarios_malls').select('mall_id').eq('usuario_id', user).eq('mall_id', mall).limit(1).execute().data)

    def run_due(self):
        if not automation_enabled():
            return {'executed': False, 'reason': 'disabled'}
        self.cleanup()
        now = utc_now()
        candidates = self.db.table('import_backup_schedules').select('*').eq('enabled', True).lte('next_run_at', now.isoformat()).order('next_run_at').limit(1).execute().data or []
        if not candidates:
            return {'executed': False, 'reason': 'not_due'}
        candidate = candidates[0]
        start, end = sale_period(candidate['frequency'], parse_time(candidate['next_run_at']))
        claimed = self.db.rpc('claim_import_backup_schedule', {
            'p_id': candidate['id'], 'p_expected': candidate['next_run_at'], 'p_version': candidate['updated_at'],
            'p_next': next_slot(candidate['frequency'], candidate['run_hour'], now).isoformat(),
            'p_run_id': str(uuid4()), 'p_start': start.isoformat(), 'p_end': end.isoformat()
        }).execute().data
        if not claimed:
            return {'executed': False, 'reason': 'already_claimed'}
        config, artifact = claimed['schedule'], claimed['artifact']
        self.generate(config, artifact)
        return {'executed': True, 'artifact_id': artifact['id']}

    def generate(self, config, artifact):
        lease = backup = None
        uploaded = False
        success = False
        try:
            if not self._authorized_owner(config['owner_id'], config['mall_id']):
                raise PermissionError('permissions_revoked')
            lease = ImportBackupQuotaService(self.db, config['owner_id'], config['mall_id']).reserve(
                (date.fromisoformat(artifact['end_date']) - date.fromisoformat(artifact['start_date'])).days + 1)
            lease.start()
            backup = ImportBackupService(self.db).generate(config['mall_id'], artifact['start_date'], artifact['end_date'], config['local_ids'],
                max_bytes=min(MAX_STORED_BYTES, lease.max_bytes), on_progress=lease.progress, check_active=lease.check)
            size = backup.file.seek(0, 2)
            backup.file.seek(0)
            # storage-py accepts BufferedReader; stage on disk rather than loading the CSV into memory.
            with NamedTemporaryFile() as temporary:
                shutil.copyfileobj(backup.file, temporary)
                temporary.flush()
                with open(temporary.name, 'rb') as reader:
                    self.db.storage.from_(BUCKET).upload(artifact['object_path'], reader, {'content-type': 'text/csv', 'upsert': 'false'})
            uploaded = True
            lease.check()
            # Recheck authorization after generation/upload before publishing the artifact.
            current = self.schedule(config['owner_id'], config['mall_id'])
            if (not self._authorized_owner(config['owner_id'], config['mall_id']) or not current
                    or not current['enabled'] or current['updated_at'] != config['updated_at']):
                raise PermissionError('schedule_or_permissions_changed')
            lease.prepare(size)
            result = self.db.table('import_backup_artifacts').update({'status': 'completed', 'bytes': size, 'records': backup.records}).eq('id', artifact['id']).eq('status', 'pending').execute()
            if not result.data:
                raise RuntimeError('artifact_expired')
            success = True
        except Exception as exc:
            # Never persist credentials, database errors or remote URLs in user-visible history.
            reason = str(exc) if isinstance(exc, PermissionError) else ('quota_' + exc.reason if isinstance(exc, BackupQuotaError) else 'generation_failed')
            self.db.table('import_backup_artifacts').update({'status': 'failed', 'error': reason}).eq('id', artifact['id']).eq('status', 'pending').execute()
            log.warning('Scheduled backup failed artifact=%s reason=%s', artifact['id'], reason)
        finally:
            if uploaded and not success:
                try:
                    self.db.storage.from_(BUCKET).remove([artifact['object_path']])
                except Exception:
                    log.warning('Deferred artifact cleanup: %s', artifact['id'])
            if backup:
                backup.file.close()
            if lease:
                lease.close(failed=not success)

    def cleanup(self):
        now = utc_now()
        # A crashed worker leaves a pending row with a deterministic private key.
        self.db.table('import_backup_artifacts').update({'status': 'failed', 'error': 'worker_interrupted', 'expires_at': now.isoformat()}).eq('status', 'pending').lt('created_at', (now - timedelta(hours=2)).isoformat()).execute()
        rows = self.db.table('import_backup_artifacts').select('id,object_path').neq('status', 'expired').lt('expires_at', now.isoformat()).limit(10).execute().data or []
        for row in rows:
            self.db.storage.from_(BUCKET).remove([row['object_path']])
            self.db.table('import_backup_artifacts').update({'status': 'expired'}).eq('id', row['id']).execute()

    def download(self, user, mall, artifact_id):
        rows = self.db.table('import_backup_artifacts').select('*').eq('owner_id', user).eq('mall_id', mall).eq('id', artifact_id).eq('status', 'completed').limit(1).execute().data or []
        if not rows or parse_time(rows[0]['expires_at']) <= utc_now():
            raise FileNotFoundError('Archivo no disponible o vencido.')
        row = rows[0]
        lease = ImportBackupQuotaService(self.db, user, mall).reserve((date.fromisoformat(row['end_date']) - date.fromisoformat(row['start_date'])).days + 1)
        output = None
        try:
            lease.start()
            if row['bytes'] > lease.max_bytes:
                raise BackupQuotaError('user_daily_bytes')
            content = self.db.storage.from_(BUCKET).download(row['object_path'])
            if len(content) != row['bytes'] or len(content) > MAX_STORED_BYTES:
                raise ValueError('Invalid stored backup size')
            output = SpooledTemporaryFile(max_size=1024 * 1024, mode='w+b')
            output.write(content)
            output.seek(0)
            lease.progress(len(content))
            lease.prepare(len(content))
            return GeneratedBackup(output, row['records'], []), lease, row
        except Exception:
            if output:
                output.close()
            lease.close(failed=True)
            raise
