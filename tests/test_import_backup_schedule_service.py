import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from services.import_backup_schedule_service import BackupSchedule, ImportBackupScheduleService, next_slot, sale_period, MAX_STORED_BYTES
from test_import_backup import ASGIClient, MALL, OTHER_MALL, LOCAL


@pytest.mark.parametrize('frequency,after,slot,start,end', [
 ('weekly','2026-10-21T00:00:00+00:00','2026-10-26T06:00:00+00:00','2026-10-19','2026-10-25'),
 ('weekly','2026-10-26T06:00:00+00:00','2026-11-02T06:00:00+00:00','2026-10-26','2026-11-01'),
 ('fortnightly','2026-10-01T05:00:00+00:00','2026-10-01T06:00:00+00:00','2026-09-16','2026-09-30'),
 ('fortnightly','2026-10-01T06:00:00+00:00','2026-10-16T06:00:00+00:00','2026-10-01','2026-10-15'),
 ('monthly','2028-02-01T06:00:00+00:00','2028-03-01T06:00:00+00:00','2028-02-01','2028-02-29'),
 ('monthly','2026-12-31T23:59:59+00:00','2027-01-01T06:00:00+00:00','2026-12-01','2026-12-31'),
])
def test_calendar(frequency, after, slot, start, end):
    actual = next_slot(frequency, 2, datetime.fromisoformat(after))
    assert actual.isoformat() == slot
    assert tuple(map(str, sale_period(frequency, actual))) == (start, end)


@pytest.mark.parametrize('values', [dict(folder='../public'),dict(folder='/root'),dict(folder='https://example.com'),dict(local_ids=[]),dict(run_hour=24),dict(retention_days=999),dict(frequency='daily')])
def test_invalid_config(values):
    with pytest.raises(ValidationError):
        BackupSchedule(**values)


def test_disabled_worker_never_queries_database(monkeypatch):
    monkeypatch.delenv('ENABLE_SCHEDULED_IMPORT_BACKUPS', raising=False)
    db = MagicMock()
    assert ImportBackupScheduleService(db).run_due()['reason'] == 'disabled'
    db.table.assert_not_called()


@pytest.fixture
def scheduled_api(monkeypatch):
    import main
    context = {'user_id':'owner','role':'custom','has_role_assignment':True,
        'permissions':{'import_backup':{'view':True},'backup_schedules':{'view':True,'create':True,'update':True,'delete':True}}}
    async def access(_): return context
    monkeypatch.setattr(main,'_get_access_context',access)
    monkeypatch.setattr(main,'_get_user_mall_ids',lambda _: [MALL])
    monkeypatch.setitem(main.app.dependency_overrides,main.get_current_user_id,lambda:'owner')
    service = MagicMock()
    service.schedule.return_value = None
    service.list.return_value = {'schedule':None,'artifacts':[]}
    service.save.return_value = service.delete.return_value = service.list.return_value
    monkeypatch.setattr(main,'ImportBackupScheduleService',lambda _:service)
    return ASGIClient(main.app),context,service


@pytest.mark.parametrize('action,method,path', [('view','GET','schedule'),('view','POST','artifacts/00000000-0000-0000-0000-000000000001/csv'),('delete','DELETE','schedule')])
def test_routes_reject_revoked_permission_before_storage(scheduled_api,action,method,path):
    client,context,service=scheduled_api
    context['permissions']['backup_schedules'][action]=False
    assert client.request(method,'/api/v1/export/import-backup/'+path,headers={'X-Mall-Id':MALL}).status_code==403
    service.download.assert_not_called()
    service.delete.assert_not_called()


def test_read_is_always_scoped_to_authenticated_owner_and_mall(scheduled_api):
    client,_,service=scheduled_api
    response=client.get('/api/v1/export/import-backup/schedule',headers={'X-Mall-Id':MALL})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    service.list.assert_called_once_with('owner',MALL)
    assert client.get('/api/v1/export/import-backup/schedule',headers={'X-Mall-Id':OTHER_MALL}).status_code==403


@pytest.mark.parametrize('exists,action',[(False,'create'),(True,'update')])
def test_schedule_save_requires_correct_action(scheduled_api,exists,action):
    client,context,service=scheduled_api
    service.schedule.return_value={'id':'schedule'} if exists else None
    context['permissions']['backup_schedules'][action]=False
    response=client.request('PUT','/api/v1/export/import-backup/schedule',headers={'X-Mall-Id':MALL},json={})
    assert response.status_code==403
    service.save.assert_not_called()


def test_missing_download_permission_blocks_scheduling(scheduled_api):
    client,context,service=scheduled_api
    context['permissions']['import_backup']['view']=False
    assert client.get('/api/v1/export/import-backup/schedule',headers={'X-Mall-Id':MALL}).status_code==403
    service.list.assert_not_called()


def test_artifact_not_found_is_not_an_unprotected_signed_url(scheduled_api):
    client,_,service=scheduled_api
    service.download.side_effect=FileNotFoundError('No disponible')
    response=client.post('/api/v1/export/import-backup/artifacts/00000000-0000-0000-0000-000000000001/csv',headers={'X-Mall-Id':MALL})
    assert response.status_code==404
    service.download.assert_called_once_with('owner',MALL,'00000000-0000-0000-0000-000000000001')


def test_storage_failure_closes_and_charges_generated_bytes(monkeypatch):
    import services.import_backup_schedule_service as module
    from services.import_backup_service import GeneratedBackup
    db=MagicMock()
    service=ImportBackupScheduleService(db)
    monkeypatch.setattr(service,'_authorized_owner',lambda *_:True)
    lease=MagicMock(max_bytes=999999999)
    monkeypatch.setattr(module,'ImportBackupQuotaService',lambda *_:SimpleNamespace(reserve=lambda _:lease))
    file=BytesIO(b'csv data')
    generator=MagicMock()
    generator.generate.return_value=GeneratedBackup(file,0,[])
    monkeypatch.setattr(module,'ImportBackupService',lambda _:generator)
    db.storage.from_.return_value.upload.side_effect=RuntimeError('SECRET_TOKEN')
    service.generate({'owner_id':'owner','mall_id':MALL,'local_ids':None}, {'id':'artifact','start_date':'2026-10-01','end_date':'2026-10-31','object_path':'key'})
    assert generator.generate.call_args.kwargs['max_bytes']==MAX_STORED_BYTES
    lease.close.assert_called_once_with(failed=True)
    assert file.closed
    assert 'SECRET_TOKEN' not in str(db.table.return_value.update.call_args_list)


def test_revoked_owner_does_not_reserve_or_upload(monkeypatch):
    import services.import_backup_schedule_service as module
    db=MagicMock();service=ImportBackupScheduleService(db)
    monkeypatch.setattr(service,'_authorized_owner',lambda *_:False)
    quota=MagicMock();monkeypatch.setattr(module,'ImportBackupQuotaService',quota)
    service.generate({'owner_id':'owner','mall_id':MALL}, {'id':'artifact','object_path':'key'})
    quota.assert_not_called();db.storage.from_.assert_not_called()


def test_worker_exception_is_isolated(monkeypatch):
    import worker_importacion as worker
    monkeypatch.setattr(worker,'supabase',object())
    service=MagicMock();service.run_due.side_effect=RuntimeError('storage unavailable')
    monkeypatch.setattr(worker,'ImportBackupScheduleService',lambda _:service)
    assert asyncio.run(worker.run_import_backup_schedules_if_due())['reason']=='error'


def test_generate_list_and_download_use_private_storage_and_account_both_transfers(monkeypatch):
    import services.import_backup_schedule_service as module
    from backup_schedule_fakes import ScheduleDatabase
    from test_import_backup import sale
    from datetime import timedelta
    db=ScheduleDatabase([sale()]);service=ImportBackupScheduleService(db)
    config={'id':'schedule','owner_id':'owner','mall_id':MALL,'local_ids':[LOCAL],'enabled':True,'updated_at':'version'}
    artifact={'id':'00000000-0000-0000-0000-000000000001','owner_id':'owner','mall_id':MALL,'object_path':'private/owner/key.csv','status':'pending',
        'start_date':'2026-01-01','end_date':'2026-01-31','created_at':module.utc_now().isoformat(),
        'expires_at':(module.utc_now()+timedelta(days=30)).isoformat(),'filename':'backup.csv'}
    db.rows['import_backup_schedules']=[config]
    db.rows['import_backup_artifacts']=[artifact]
    monkeypatch.setattr(service,'_authorized_owner',lambda *_:True)
    leases=[]
    def quota(*_):
        lease=MagicMock(max_bytes=MAX_STORED_BYTES);leases.append(lease)
        return SimpleNamespace(reserve=lambda _:lease)
    monkeypatch.setattr(module,'ImportBackupQuotaService',quota)
    service.generate(config,artifact)
    assert artifact['status']=='completed' and artifact['records']==1
    assert artifact['bytes']==len(db.storage.objects[artifact['object_path']])
    leases[0].close.assert_called_once_with(failed=False)
    # Foreign owners or Malls cannot list/download another user's key.
    assert service.list('another',MALL)['artifacts']==[]
    with pytest.raises(FileNotFoundError): service.download('another',MALL,artifact['id'])
    assert len(leases)==1
    backup,lease,row=service.download('owner',MALL,artifact['id'])
    try:
        assert backup.file.read()==db.storage.objects[artifact['object_path']]
        leases[1].prepare.assert_called_once_with(artifact['bytes'])
    finally:
        backup.file.close();lease.close()
    artifact['expires_at']=(module.utc_now()-timedelta(seconds=1)).isoformat()
    with pytest.raises(FileNotFoundError): service.download('owner',MALL,artifact['id'])
    service.cleanup()
    assert not db.storage.objects and artifact['status']=='expired'


def test_save_schedule_validates_stores_and_uses_insert_for_creation(monkeypatch):
    from backup_schedule_fakes import ScheduleDatabase
    from test_import_backup import FOREIGN
    db=ScheduleDatabase();service=ImportBackupScheduleService(db)
    with pytest.raises(Exception): service.save('owner',MALL,BackupSchedule(local_ids=[FOREIGN]))
    assert not db.rows.get('import_backup_schedules')
    state=service.save('owner',MALL,BackupSchedule(local_ids=[LOCAL],enabled=True))
    assert state['schedule']['local_ids']==[LOCAL]
    assert state['schedule']['folder']=='importaciones'
    updated=service.save('owner',MALL,BackupSchedule(frequency='monthly',enabled=False),state['schedule'])
    assert len(db.rows['import_backup_schedules'])==1 and not updated['schedule']['enabled']
    assert service.delete('owner',MALL)['schedule'] is None
