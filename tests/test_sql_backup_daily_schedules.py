"""Real local SQL exports and in-memory private storage; never uses production."""
import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

import services.sql_backup_schedule_service as schedules
from services.sql_backup_schedule_service import SQLBackupScheduleService, SQLBackupSchedule, next_daily, utc_now
from services.sql_backup_traffic_service import TrafficQuotaError
from test_sql_backup_weekly_traffic import database
from test_database_backup import local_postgres
from test_import_backup import MALL, OTHER_MALL, api


class PrivateStorage:
    def __init__(self): self.objects={}; self.created=False; self.hook=None
    def get_bucket(self,bucket):
        assert bucket=='sql-backups'
        if not self.created: raise FileNotFoundError()
        return SimpleNamespace(public=False)
    def create_bucket(self,bucket,options):
        assert options['public'] is False
        self.created=True
    def from_(self,bucket): assert bucket=='sql-backups'; return self
    def upload(self,key,data,options):
        assert len(data)<=schedules.CHUNK_BYTES and key not in self.objects
        self.objects[key]=data
        if self.hook: self.hook()
    def download(self,key): return self.objects[key]
    def list(self,prefix,options): return [{'name':key[len(prefix)+1:]} for key in self.objects if key.startswith(prefix+'/')]
    def remove(self,keys):
        for key in keys: self.objects.pop(key,None)


@pytest.fixture(scope='module')
def schema(database):
    root=Path(__file__).parents[1]/'supabase/migrations'
    with psycopg.connect(database) as conn:
        for pattern in ('*_database_backup_differential.sql','*_sql_backup_daily_schedules.sql'):
            conn.execute(next(root.glob(pattern)).read_text())
    return database


@pytest.fixture
def service(schema,monkeypatch):
    for name in ('ENABLE_DATABASE_BACKUPS','ENABLE_DIFFERENTIAL_BACKUPS','ENABLE_SQL_BACKUP_WEEKLY_QUOTA','ENABLE_SCHEDULED_SQL_BACKUPS'):
        monkeypatch.setenv(name,'true')
    monkeypatch.setenv('BACKUP_DATABASE_URL',schema)
    monkeypatch.setattr(schedules,'CHUNK_BYTES',1024)
    with psycopg.connect(schema) as conn:
        conn.execute('''TRUNCATE msmall_backup.sql_artifacts,msmall_backup.sql_schedules,
          msmall_backup.traffic_jobs,msmall_backup.traffic_usage,msmall_backup.traffic_malls,
          msmall_backup.traffic_plans,msmall_backup.row_fingerprints,msmall_backup.baselines''')
        conn.execute("INSERT INTO msmall_backup.traffic_plans VALUES ('pair',100000000,5000000,true)")
        conn.execute("INSERT INTO msmall_backup.traffic_malls VALUES (%s,'pair'),(%s,'pair')",(MALL,OTHER_MALL))
    db=SimpleNamespace(storage=PrivateStorage())
    return SQLBackupScheduleService(db)


def due(service):
    service.query("UPDATE msmall_backup.sql_schedules SET next_run_at=now()-interval '1 second',claim_until=null RETURNING mall_id")


def test_initial_complete_daily_differential_private_download_and_cleanup(service,schema):
    service.save(MALL,SQLBackupSchedule(enabled=True,run_hour=2))
    due(service)
    first=service.run_due()
    assert first['executed'] and first['mode']=='base'
    second=service.run_due()
    assert second['executed'] and second['mode']=='differential'
    assert service.run_due()['reason']=='not_due'
    state=service.state(MALL)
    assert len(state['artifacts'])==2 and state['schedule']['enabled']
    full=next(a for a in state['artifacts'] if a['mode']=='base')
    diff=next(a for a in state['artifacts'] if a['mode']=='differential')
    assert full['base_id']==diff['base_id']
    content,lease,row=service.download(MALL,str(uuid4()),full['id'])
    try: data=b''.join(content)
    finally: lease.close()
    assert len(data)==row['bytes']
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert json.loads(archive.read('manifest.json'))['mode']=='base'
        assert b'FOREIGN_SALE' not in archive.read('data.sql')
    with pytest.raises(FileNotFoundError): service.download(OTHER_MALL,str(uuid4()),full['id'])
    # Pause and change hour via the same configuration used by the API.
    updated=service.save(MALL,SQLBackupSchedule(enabled=False,run_hour=5))
    assert updated['schedule']['run_hour']==5 and not updated['schedule']['enabled']
    assert service.run_due()['reason']=='not_due'
    # An expired full is retained while it is still the live base.
    service.query("UPDATE msmall_backup.sql_artifacts SET expires_at=now()-interval '1 day' WHERE mode='base' RETURNING id")
    service.cleanup()
    assert next(a for a in service.state(MALL)['artifacts'] if a['mode']=='base')['status']=='completed'
    assert service.db.storage.objects


def test_weekly_exhaustion_blocks_generation_and_download_without_charges(service):
    service.save(MALL,SQLBackupSchedule(enabled=True))
    due(service)
    assert service.run_due()['executed']
    full=service.state(MALL)['artifacts'][0]
    service.query("UPDATE msmall_backup.traffic_usage SET used_bytes=100000000 RETURNING plan_id")
    assert service.run_due()['reason']=='quota_weekly_bytes'
    with pytest.raises(TrafficQuotaError,match='sin cargos|No se generarán cargos'):
        service.download(MALL,str(uuid4()),full['id'])
    assert service.query('SELECT sum(used_bytes) AS used FROM msmall_backup.traffic_usage')[0]['used']==100000000


def test_pause_during_upload_preserves_previous_base_and_fails_closed(service):
    service.save(MALL,SQLBackupSchedule(enabled=True))
    due(service)
    assert service.run_due()['mode']=='base'
    old=service.generator.baseline(MALL)['id']
    service.query("UPDATE msmall_backup.baselines SET created_at=created_at-interval '40 days' RETURNING id")
    def pause():
        service.db.storage.hook=None
        service.query('UPDATE msmall_backup.sql_schedules SET enabled=false,updated_at=clock_timestamp() RETURNING mall_id')
    service.db.storage.hook=pause
    assert service.run_due()['reason']=='generation_failed'
    assert service.generator.baseline(MALL)['id']==old
    assert any(a['status']=='failed' for a in service.state(MALL)['artifacts'])


def test_uploaded_artifact_is_recovered_after_worker_interrupt(service):
    service.save(MALL,SQLBackupSchedule(enabled=True))
    due(service)
    assert service.run_due()['executed']
    row=service.state(MALL)['artifacts'][0]
    service.query("UPDATE msmall_backup.sql_artifacts SET status='pending',created_at=now()-interval '30 minutes' WHERE id=%s RETURNING id",(row['id'],))
    service.cleanup()
    assert service.state(MALL)['artifacts'][0]['status']=='completed'


def test_daily_slot_uses_santo_domingo_and_validates_hour():
    now=utc_now().astimezone(schedules.TZ).replace(hour=1,minute=0,second=0,microsecond=0)
    assert next_daily(2,now).astimezone(schedules.TZ).hour==2
    assert next_daily(2,now.replace(hour=3)).astimezone(schedules.TZ).date()==now.date()+timedelta(days=1)
    with pytest.raises(ValueError): SQLBackupSchedule(run_hour=24)


def test_api_denies_nonadmins_and_preserves_mall_context(api,monkeypatch):
    monkeypatch.setattr(api.main,'sql_weekly_quota_ready',lambda:True)
    monkeypatch.setattr(api.main,'_backup_is_admin',lambda _:False)
    assert api.client.get('/api/v1/export/import-backup/database/schedule',headers={'X-Mall-Id':MALL}).status_code==403
    monkeypatch.setattr(api.main,'_backup_is_admin',lambda _:True)
    calls=[]
    monkeypatch.setattr(api.main.SQLBackupScheduleService,'state',lambda _self,mall:calls.append(mall) or {'schedule':None,'artifacts':[]})
    response=api.client.get('/api/v1/export/import-backup/database/schedule',headers={'X-Mall-Id':MALL})
    assert response.status_code==200 and calls==[MALL]
    assert response.headers['cache-control']=='no-store'
    assert api.client.get('/api/v1/export/import-backup/database/schedule',headers={'X-Mall-Id':OTHER_MALL}).status_code==403


def test_api_stored_download_streams_zip_and_releases_lease(api,monkeypatch):
    monkeypatch.setattr(api.main,'sql_weekly_quota_ready',lambda:True)
    monkeypatch.setattr(api.main,'_backup_is_admin',lambda _:True)
    closed=[]
    lease=SimpleNamespace(close=lambda failed=False:closed.append(failed))
    def download(_self,mall,actor,artifact):
        assert mall==MALL and actor==api.access['user_id']
        def content(): yield b'zip-content'
        return content(),lease,{'mode':'base','bytes':11}
    monkeypatch.setattr(api.main.SQLBackupScheduleService,'download',download)
    result=api.client.get('/api/v1/export/import-backup/database/artifacts/'+str(uuid4()),headers={'X-Mall-Id':MALL})
    assert result.status_code==200 and result.content==b'zip-content'
    assert result.headers['content-type']=='application/zip' and result.headers['cache-control']=='no-store'
    assert closed==[False]
