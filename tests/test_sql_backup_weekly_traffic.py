"""Quota correctness and races, using only a disposable local PostgreSQL cluster."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from services.import_backup_quota_service import BackupQuotaError
from services.sql_backup_traffic_service import SQLBackupTrafficService, TrafficLease
from test_database_backup import local_postgres
from test_import_backup import MALL, OTHER_MALL, api

ACTOR=str(uuid4())


@pytest.fixture(scope='module')
def database(local_postgres):
    migration=next((Path(__file__).parents[1]/'supabase/migrations').glob('*_sql_backup_weekly_traffic.sql'))
    with psycopg.connect(local_postgres) as conn:
        conn.execute('CREATE SCHEMA msmall_backup; CREATE TABLE import_backup_policy (id boolean, max_range_days int, min_interval_seconds int DEFAULT 60, user_daily_downloads int DEFAULT 10); INSERT INTO import_backup_policy (id,max_range_days) VALUES (true,90)')
        for role in ('anon','authenticated','service_role'):
            conn.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        conn.execute(migration.read_text())
    return local_postgres


@pytest.fixture(autouse=True)
def reset(database):
    with psycopg.connect(database) as conn:
        conn.execute('TRUNCATE msmall_backup.traffic_jobs, msmall_backup.traffic_usage, msmall_backup.traffic_malls, msmall_backup.traffic_plans')
        conn.execute("INSERT INTO msmall_backup.traffic_plans VALUES ('pair',1000,300,true)")
        conn.execute("INSERT INTO msmall_backup.traffic_malls VALUES (%s,'pair'),(%s,'pair')",(MALL,OTHER_MALL))


def rpc(dsn,action='status',mall=MALL,job=None,size=0,actor=None,mode='base'):
    with psycopg.connect(dsn) as conn:
        return conn.execute('SELECT msmall_backup.traffic_control(%s,%s,%s,%s,%s,%s,%s)',(action,mall,actor,job,mode,size,1)).fetchone()[0]


def test_shared_quota_blocks_at_limit_without_overages_and_restarts_new_week(database):
    first,second=str(uuid4()),str(uuid4())
    assert rpc(database,'reserve',job=first)['max_bytes']==300
    assert rpc(database,'prepare',job=first,size=600)['allowed']
    assert rpc(database,'finish',job=first)['allowed']
    assert rpc(database,mall=OTHER_MALL)['quota']['used_bytes']==600
    assert rpc(database,'reserve',mall=OTHER_MALL,job=second)['max_bytes']==200
    assert rpc(database,'prepare',mall=OTHER_MALL,job=second,size=400)['allowed']
    rpc(database,'finish',mall=OTHER_MALL,job=second)
    denied=rpc(database,'reserve',job=str(uuid4()))
    assert not denied['allowed'] and denied['reason']=='weekly_bytes'
    assert denied['quota']['remaining_bytes']==0 and denied['quota']['price']==0
    assert not rpc(database,'reserve',mall=OTHER_MALL,actor=str(uuid4()),job=str(uuid4()))['allowed']
    # Move only these test ledger rows to the previous week; a fresh week has its own balance.
    with psycopg.connect(database) as conn:
        conn.execute('UPDATE msmall_backup.traffic_usage SET week_start=week_start-7')
        conn.execute('UPDATE msmall_backup.traffic_jobs SET week_start=week_start-7')
    fresh=rpc(database)
    assert fresh['quota']['used_bytes']==0 and fresh['quota']['remaining_bytes']==1000


def test_reservations_prevent_parallel_overspending(database):
    requests=[(MALL if i%2==0 else OTHER_MALL,str(uuid4())) for i in range(12)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        results=list(pool.map(lambda args:rpc(database,'reserve',mall=args[0],job=args[1]),requests))
    allowed=[r for r in results if r['allowed']]
    assert len(allowed)==2
    assert sum(r['max_bytes']*2 for r in allowed)==1000
    state=rpc(database)['quota']
    assert state['used_bytes']+state['reserved_bytes']==1000


def test_failed_jobs_charge_partial_traffic_and_crashes_keep_reservation(database):
    first,second=str(uuid4()),str(uuid4())
    rpc(database,'reserve',job=first)
    rpc(database,'fail',job=first,size=100)
    assert rpc(database)['quota']['used_bytes']==100
    rpc(database,'reserve',job=second)
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE msmall_backup.traffic_jobs SET expires_at=now()-interval '1 second' WHERE id=%s",(second,))
    state=rpc(database)['quota']
    assert state['used_bytes']==700 and state['reserved_bytes']==0
    assert not rpc(database,'prepare',job=second,size=1)['allowed']


def test_prepare_cannot_exceed_reservation_or_close_another_actor_job(database):
    job=str(uuid4())
    rpc(database,'reserve',job=job,actor=ACTOR)
    assert not rpc(database,'prepare',job=job,size=601,actor=ACTOR)['allowed']
    assert not rpc(database,'finish',job=job,actor=str(uuid4()))['allowed']
    assert rpc(database)['quota']['reserved_bytes']==600
    rpc(database,'prepare',job=job,size=100,actor=ACTOR)
    rpc(database,'fail',job=job,size=600,actor=ACTOR)
    assert rpc(database)['quota']['used_bytes']==100
    assert not rpc(database,'prepare',job=job,size=1,actor=ACTOR)['allowed']


def test_bigint_capacity_and_unassigned_malls_are_independent(database):
    with psycopg.connect(database) as conn:
        conn.execute('UPDATE msmall_backup.traffic_plans SET weekly_bytes=40000000000,max_file_bytes=5000000000')
    result=rpc(database,'reserve',job=str(uuid4()))
    assert result['max_bytes']==5000000000
    assert result['quota']['weekly_bytes']==40000000000
    assert result['quota']['reserved_bytes']==10000000000
    assert rpc(database,mall=str(uuid4()))=={'configured':False}


def test_private_quota_is_not_executable_by_client_roles(database):
    with psycopg.connect(database) as conn:
        for role in ('anon','authenticated','service_role'):
            assert not conn.execute("SELECT has_function_privilege(%s,'msmall_backup.traffic_control(text,uuid,uuid,uuid,text,bigint,integer)','EXECUTE')",(role,)).fetchone()[0]
        assert conn.execute("SELECT bool_and(relrowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='msmall_backup' AND c.relkind='r'").fetchone()[0]


def test_manual_generation_retains_cooldown_and_daily_abuse_protection(database):
    first=str(uuid4())
    rpc(database,'reserve',job=first,actor=ACTOR,mode='differential')
    rpc(database,'prepare',job=first,actor=ACTOR,size=1)
    rpc(database,'finish',job=first,actor=ACTOR)
    assert rpc(database,'reserve',job=str(uuid4()),actor=ACTOR)['reason']=='frequency'
    with psycopg.connect(database) as conn:
        conn.execute('UPDATE public.import_backup_policy SET min_interval_seconds=0')
    try:
        for _ in range(9):
            actor,job=str(uuid4()),str(uuid4())
            assert rpc(database,'reserve',job=job,actor=actor)['allowed']
            rpc(database,'prepare',job=job,actor=actor,size=1)
            rpc(database,'finish',job=job,actor=actor)
        assert rpc(database,'reserve',job=str(uuid4()),actor=str(uuid4()))['reason']=='daily_downloads'
        assert rpc(database,'reserve',job=str(uuid4()),actor=None)['allowed']
    finally:
        with psycopg.connect(database) as conn:
            conn.execute('UPDATE public.import_backup_policy SET min_interval_seconds=60')


def test_python_lease_accounts_sql_and_zip_and_blocks_week_boundary():
    class Service:
        mode='base'
        def __init__(self): self.calls=[]
        def call(self,action,**kwargs): self.calls.append((action,kwargs))
    service=Service()
    lease=TrafficLease(service,str(uuid4()),300,(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    lease.progress(200)
    lease.progress(150)
    lease.prepare(50)
    assert service.calls[0][1]['bytes']==250
    lease.close()
    lease.close()
    assert [c[0] for c in service.calls]==['prepare','finish']
    expired=TrafficLease(service,str(uuid4()),300,(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    with pytest.raises(BackupQuotaError): expired.check()


def test_api_weekly_denial_prevents_sql_generation_without_bypassing_daily_fallback(api,monkeypatch):
    from services.sql_backup_traffic_service import TrafficQuotaError
    monkeypatch.setattr(api.main,'sql_weekly_quota_ready',lambda:True)
    monkeypatch.setattr(api.main,'database_backup_ready',lambda:True)
    monkeypatch.setattr(api.main,'differential_backup_ready',lambda:True)
    monkeypatch.setattr(api.main,'_backup_is_admin',lambda _:True)
    monkeypatch.setattr(api.main.SQLBackupTrafficService,'status',lambda _: {'configured':True,'quota':{'remaining_bytes':0,'price':0}})
    def deny(*_a,**_k): raise TrafficQuotaError('weekly_bytes')
    monkeypatch.setattr(api.main.SQLBackupTrafficService,'reserve',deny)
    monkeypatch.setattr(api.main.DifferentialBackupService,'generate_snapshot',lambda *_a,**_k:pytest.fail('must not generate'))
    response=api.client.post('/api/v1/export/import-backup/database/mall?mode=base',headers={'X-Mall-Id':MALL})
    assert response.status_code==429 and 'No se generarán cargos' in response.text
    result=api.client.get('/api/v1/export/import-backup/database/traffic',headers={'X-Mall-Id':MALL})
    assert result.json()['quota']['price']==0
    api.access['permissions']={}
    assert api.client.get('/api/v1/export/import-backup/database/traffic',headers={'X-Mall-Id':MALL}).status_code==403
