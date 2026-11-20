"""Configurable daily SQL artifacts, chunked in a private bucket with no signed URLs."""
import logging
import os
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from services.differential_backup_service import DifferentialBackupService, DifferentialSelectionError
from services.database_backup_service import DatabaseBackupUnavailable
from services.import_backup_service import BackupSizeExceeded
from services.import_backup_quota_service import BackupQuotaError
from services.sql_backup_traffic_service import SQLBackupTrafficService, TrafficQuotaError

TZ=ZoneInfo('America/Santo_Domingo')
BUCKET='sql-backups'
CHUNK_BYTES=8_000_000
log=logging.getLogger('sql-backup-scheduler')


class SQLBackupSchedule(BaseModel):
    enabled: bool=False
    run_hour: int=Field(default=2,ge=0,le=23)


def utc_now():
    return datetime.now(timezone.utc)


def next_daily(hour,after):
    local=after.astimezone(TZ)
    candidate=datetime.combine(local.date(),time(hour),TZ)
    if candidate<=local:
        candidate+=timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def automation_enabled():
    return os.getenv('ENABLE_SCHEDULED_SQL_BACKUPS','').lower() in {'true','1','yes'}


class SQLBackupScheduleService:
    def __init__(self,db,connect=None,generator=None):
        self.db=db
        self.connect=connect or psycopg.connect
        self.generator=generator or DifferentialBackupService()

    def query(self,query,args=()):
        with self.connect(os.environ['BACKUP_DATABASE_URL'],connect_timeout=10,row_factory=dict_row) as conn:
            return conn.execute(query,args).fetchall()

    def state(self,mall):
        schedules=self.query('SELECT enabled,run_hour,next_run_at,last_error FROM msmall_backup.sql_schedules WHERE mall_id=%s',(mall,))
        artifacts=self.query("SELECT id,mode,base_id,scheduled_day,bytes,status,error,created_at,expires_at FROM msmall_backup.sql_artifacts WHERE mall_id=%s AND status<>'expired' ORDER BY created_at DESC LIMIT 30",(mall,))
        return {'schedule':schedules[0] if schedules else None,'artifacts':artifacts,'automation_enabled':automation_enabled(),'timezone':str(TZ),'retention_days':7}

    def save(self,mall,config):
        if not SQLBackupTrafficService(mall).status().get('configured'):
            raise ValueError('Este Mall no tiene habilitado el plan gratuito de backups SQL.')
        self.query('''INSERT INTO msmall_backup.sql_schedules(mall_id,enabled,run_hour,next_run_at)
          VALUES (%s,%s,%s,%s) ON CONFLICT (mall_id) DO UPDATE SET enabled=excluded.enabled,
          run_hour=excluded.run_hour,next_run_at=excluded.next_run_at,updated_at=now(),last_error=null RETURNING mall_id''',
          (mall,config.enabled,config.run_hour,next_daily(config.run_hour,utc_now())))
        return self.state(mall)

    def _bucket(self):
        try:
            info=self.db.storage.get_bucket(BUCKET)
        except Exception:
            try:
                self.db.storage.create_bucket(BUCKET,options={'public':False,'file_size_limit':50_000_000,'allowed_mime_types':['application/octet-stream']})
            except Exception:
                # Concurrent first run may already have created it; verify its settings.
                pass
            info=self.db.storage.get_bucket(BUCKET)
        public=info.get('public') if isinstance(info,dict) else info.public
        if public is not False:
            raise RuntimeError('SQL bucket must be private')
        return self.db.storage.from_(BUCKET)

    def _remove(self,prefix):
        bucket=self._bucket()
        objects=bucket.list(prefix,{'limit':1000})
        if objects:
            bucket.remove([prefix+'/'+item['name'] for item in objects])

    def cleanup(self):
        # A completed upload survives a process crash; the quota lease charges its reservation.
        self.query("UPDATE msmall_backup.sql_artifacts SET status='completed' WHERE status='pending' AND uploaded AND created_at<now()-interval '20 minutes' RETURNING id")
        self.query("UPDATE msmall_backup.sql_artifacts SET status='failed',error='worker_interrupted',expires_at=now() WHERE status='pending' AND NOT uploaded AND created_at<now()-interval '20 minutes' RETURNING id")
        rows=self.query('''SELECT a.id,a.object_prefix FROM msmall_backup.sql_artifacts a
          WHERE a.status NOT IN ('pending','expired') AND a.expires_at<now()
          AND NOT (a.mode='base' AND a.status='completed' AND (
            EXISTS(SELECT 1 FROM msmall_backup.baselines b WHERE b.id=a.base_id)
            OR EXISTS(SELECT 1 FROM msmall_backup.sql_artifacts d WHERE d.base_id=a.base_id AND d.mode='differential' AND d.status='completed' AND d.expires_at>now())))
          LIMIT 10''')
        for row in rows:
            self._remove(row['object_prefix'])
            self.query("UPDATE msmall_backup.sql_artifacts SET status='expired' WHERE id=%s RETURNING id",(row['id'],))

    def run_due(self):
        if not automation_enabled():
            return {'executed':False,'reason':'disabled'}
        self.cleanup()
        rows=self.query('''UPDATE msmall_backup.sql_schedules s SET claim_until=now()+interval '15 minutes'
          WHERE s.mall_id=(SELECT x.mall_id FROM msmall_backup.sql_schedules x
            JOIN msmall_backup.traffic_malls m ON m.mall_id=x.mall_id
            JOIN msmall_backup.traffic_plans p ON p.id=m.plan_id
            WHERE x.enabled AND p.enabled AND x.next_run_at<=now() AND (x.claim_until IS NULL OR x.claim_until<now())
            ORDER BY x.next_run_at FOR UPDATE OF x SKIP LOCKED LIMIT 1)
          RETURNING s.*''')
        if not rows:
            return {'executed':False,'reason':'not_due'}
        config=rows[0]
        mall=str(config['mall_id'])
        artifact=None
        lease=backup=None
        prefix=None
        try:
            baseline=self.generator.baseline(mall)
            full_artifacts=self.query("SELECT id FROM msmall_backup.sql_artifacts WHERE mall_id=%s AND mode='base' AND status='completed' AND base_id=%s LIMIT 1",(mall,baseline['id'] if baseline else None))
            now=utc_now()
            month=now.astimezone(TZ).strftime('%Y-%m')
            mode='base' if not baseline or not full_artifacts or datetime.fromisoformat(baseline['created_at']).astimezone(TZ).strftime('%Y-%m')!=month else 'differential'
            day=now.astimezone(TZ).date()
            if mode=='differential' and self.query("SELECT id FROM msmall_backup.sql_artifacts WHERE mall_id=%s AND scheduled_day=%s AND mode=%s AND status='completed'",(mall,day,mode)):
                self._finish_schedule(config,next_daily(config['run_hour'],now))
                return {'executed':False,'reason':'already_generated'}
            lease=SQLBackupTrafficService(mall,mode=mode).reserve(1)
            lease.start()
            artifact=str(uuid4())
            prefix=f'{mall}/{artifact}'
            self.query('''INSERT INTO msmall_backup.sql_artifacts(id,mall_id,mode,scheduled_day,object_prefix,expires_at)
              VALUES (%s,%s,%s,%s,%s,%s) RETURNING id''',(artifact,mall,mode,day,prefix,now+timedelta(days=7)))

            def store(reader,manifest,check):
                bucket=self._bucket()
                size=count=0
                while chunk:=reader.read(CHUNK_BYTES):
                    check()
                    bucket.upload(f'{prefix}/{count:06d}.bin',chunk,{'content-type':'application/octet-stream','upsert':'false'})
                    size+=len(chunk)
                    count+=1
                self.query('''UPDATE msmall_backup.sql_artifacts SET base_id=%s,bytes=%s,chunks=%s,uploaded=true
                  WHERE id=%s AND status='pending' RETURNING id''',(manifest['base_id'],size,count,artifact))
                current=self.query('SELECT enabled,updated_at FROM msmall_backup.sql_schedules WHERE mall_id=%s',(mall,))[0]
                if not current['enabled'] or current['updated_at']!=config['updated_at']:
                    raise RuntimeError('schedule_changed')

            backup=self.generator.generate_snapshot(mode,mall,base_id=baseline['id'] if mode=='differential' else None,
              max_bytes=lease.max_bytes,on_progress=lease.progress,check_active=lease.check,
              on_archive_ready=store,on_ready=lease.prepare)
            self.query("UPDATE msmall_backup.sql_artifacts SET status='completed' WHERE id=%s RETURNING id",(artifact,))
            # A new complete is followed by today's differential on the next scheduler tick.
            self._finish_schedule(config,now if mode=='base' else next_daily(config['run_hour'],now))
            lease.close()
            return {'executed':True,'artifact_id':artifact,'mode':mode}
        except Exception as exc:
            reason=('quota_'+exc.reason) if isinstance(exc,BackupQuotaError) else 'generation_failed'
            if artifact:
                self.query("UPDATE msmall_backup.sql_artifacts SET status='failed',error=%s,expires_at=now() WHERE id=%s RETURNING id",(reason,artifact))
            retry=utc_now()+timedelta(hours=1)
            if isinstance(exc,BackupQuotaError) and exc.reason=='weekly_bytes':
                quota=SQLBackupTrafficService(mall).status()['quota']
                reset=datetime.fromisoformat(quota['resets_at'])
                retry=next_daily(config['run_hour'],reset-timedelta(seconds=1))
            self._finish_schedule(config,retry,reason)
            safe_detail=str(exc) if isinstance(exc,(DatabaseBackupUnavailable,DifferentialSelectionError,BackupSizeExceeded)) else ''
            log.warning('SQL backup deferred mall=%s reason=%s error_type=%s detail=%s',mall,reason,type(exc).__name__,safe_detail)
            if lease: lease.close(failed=True)
            return {'executed':False,'reason':reason}
        finally:
            if backup: backup.file.close()

    def _finish_schedule(self,config,next_run,error=None):
        self.query('''UPDATE msmall_backup.sql_schedules SET claim_until=null,
          next_run_at=CASE WHEN updated_at=%s THEN %s ELSE next_run_at END,last_error=%s
          WHERE mall_id=%s RETURNING mall_id''',(config['updated_at'],next_run,error,config['mall_id']))

    def download(self,mall,actor,artifact_id):
        artifact_id=str(UUID(str(artifact_id)))
        rows=self.query("SELECT * FROM msmall_backup.sql_artifacts WHERE id=%s AND mall_id=%s AND status='completed'",(artifact_id,mall))
        if not rows:
            raise FileNotFoundError('Archivo SQL no disponible.')
        row=rows[0]
        # Current bases remain downloadable while they anchor retained differentials.
        if row['expires_at']<=utc_now() and row['mode']!='base':
            raise FileNotFoundError('Archivo SQL vencido.')
        lease=SQLBackupTrafficService(mall,actor,mode='download').reserve(1)
        try:
            lease.start()
            if row['bytes']>lease.max_bytes:
                raise TrafficQuotaError('weekly_bytes')
            lease.prepare(row['bytes'])
        except BaseException:
            lease.close(failed=True)
            raise
        def chunks():
            size=0
            bucket=self._bucket()
            for index in range(row['chunks']):
                lease.check()
                content=bucket.download(f"{row['object_prefix']}/{index:06d}.bin")
                expected=min(CHUNK_BYTES,row['bytes']-size)
                if len(content)!=expected:
                    raise RuntimeError('Invalid SQL artifact chunk')
                size+=len(content)
                yield content
            if size!=row['bytes']:
                raise RuntimeError('Incomplete SQL artifact')
        return chunks(),lease,row


if __name__=='__main__':
    from supabase import create_client
    logging.basicConfig(level=logging.INFO)
    if automation_enabled():
        client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
        try:
            for _ in range(4):
                result=SQLBackupScheduleService(client).run_due()
                log.info('SQL schedule result=%s',result)
                if not result.get('executed'):
                    break
        except Exception as exc:
            log.error('SQL scheduler unavailable error_type=%s',type(exc).__name__)
            raise SystemExit(1)
