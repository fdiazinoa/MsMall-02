-- Private, prepaid traffic reservations. No billing or overage path exists.
create table msmall_backup.traffic_plans (
    id text primary key,
    weekly_bytes bigint not null check (weekly_bytes > 0),
    max_file_bytes bigint not null default 5000000000 check (max_file_bytes between 1 and 5000000000),
    enabled boolean not null default false
);
create table msmall_backup.traffic_malls (
    mall_id uuid primary key,
    plan_id text not null references msmall_backup.traffic_plans(id)
);
create table msmall_backup.traffic_usage (
    plan_id text not null references msmall_backup.traffic_plans(id),
    week_start date not null,
    used_bytes bigint not null default 0 check (used_bytes >= 0),
    reserved_bytes bigint not null default 0 check (reserved_bytes >= 0),
    primary key (plan_id, week_start)
);
create table msmall_backup.traffic_jobs (
    id uuid primary key,
    plan_id text not null references msmall_backup.traffic_plans(id),
    mall_id uuid not null,
    actor_id uuid,
    mode text not null check (mode in ('period','base','differential','download')),
    week_start date not null,
    reserved_bytes bigint not null check (reserved_bytes >= 0),
    charged_bytes bigint not null default 0 check (charged_bytes >= 0),
    status text not null check (status in ('generating','prepared','completed','failed','expired')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);
create index traffic_jobs_active on msmall_backup.traffic_jobs(plan_id,expires_at)
    where status in ('generating','prepared');
alter table msmall_backup.traffic_plans enable row level security;
alter table msmall_backup.traffic_malls enable row level security;
alter table msmall_backup.traffic_usage enable row level security;
alter table msmall_backup.traffic_jobs enable row level security;
revoke all on all tables in schema msmall_backup from public, anon, authenticated, service_role;

create function msmall_backup.traffic_control(
    p_action text, p_mall uuid, p_actor uuid default null, p_job uuid default null,
    p_mode text default 'period', p_bytes bigint default 0, p_days integer default 1
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_plan msmall_backup.traffic_plans%rowtype;
    v_usage msmall_backup.traffic_usage%rowtype;
    v_job msmall_backup.traffic_jobs%rowtype;
    v_expired msmall_backup.traffic_jobs%rowtype;
    v_now timestamptz;
    v_week date;
    v_reset timestamptz;
    v_remaining bigint;
    v_budget bigint := 0;
    v_allowed boolean := true;
    v_reason text;
begin
    if p_action not in ('status','reserve','renew','prepare','finish','fail')
       or p_mode not in ('period','base','differential','download') or p_bytes < 0 then
        raise exception 'Invalid SQL traffic operation' using errcode='22023';
    end if;
    if p_action in ('renew','prepare','finish','fail') then
        select j.* into v_job from msmall_backup.traffic_jobs j
        where j.id=p_job and j.mall_id=p_mall and j.actor_id is not distinct from p_actor;
        if not found then
            return jsonb_build_object('configured',true,'allowed',false,'reason','lease_expired');
        end if;
        select * into v_plan from msmall_backup.traffic_plans where id=v_job.plan_id;
    else
        select p.* into v_plan from msmall_backup.traffic_plans p
        join msmall_backup.traffic_malls m on m.plan_id=p.id where m.mall_id=p_mall;
        if not found then return jsonb_build_object('configured',false); end if;
    end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('sql-backup-traffic:'||v_plan.id,0));
    v_now := pg_catalog.clock_timestamp();
    v_week := pg_catalog.date_trunc('week',v_now at time zone 'America/Santo_Domingo')::date;
    v_reset := (v_week+7)::timestamp at time zone 'America/Santo_Domingo';
    -- Interrupted jobs retain their full reservation, so crashes cannot refund traffic.
    for v_expired in select * from msmall_backup.traffic_jobs
      where plan_id=v_plan.id and status in ('generating','prepared') and expires_at<=v_now for update
    loop
        update msmall_backup.traffic_usage set used_bytes=used_bytes+v_expired.reserved_bytes,
            reserved_bytes=reserved_bytes-v_expired.reserved_bytes
        where plan_id=v_plan.id and week_start=v_expired.week_start;
        update msmall_backup.traffic_jobs set status='expired',
            charged_bytes=charged_bytes+reserved_bytes,reserved_bytes=0 where id=v_expired.id;
    end loop;
    insert into msmall_backup.traffic_usage(plan_id,week_start) values(v_plan.id,v_week) on conflict do nothing;

    if p_action in ('renew','prepare','finish','fail') then
        select * into v_job from msmall_backup.traffic_jobs where id=p_job for update;
        if v_job.status not in ('generating','prepared') then
            v_allowed:=false; v_reason:='lease_expired';
        elsif p_action='renew' then
            if not v_plan.enabled or v_job.week_start<>v_week then
                v_allowed:=false; v_reason:='weekly_reset';
            else
                update msmall_backup.traffic_jobs set expires_at=least(v_now+interval '2 minutes',v_reset) where id=p_job;
            end if;
        elsif p_action='prepare' and (v_job.status<>'generating' or p_bytes>v_job.reserved_bytes or v_job.week_start<>v_week or not v_plan.enabled) then
            v_allowed:=false; v_reason:='weekly_bytes';
        else
            if v_job.status='generating' then
                update msmall_backup.traffic_usage set
                    used_bytes=used_bytes+least(p_bytes,v_job.reserved_bytes),
                    reserved_bytes=reserved_bytes-v_job.reserved_bytes
                where plan_id=v_plan.id and week_start=v_job.week_start;
                update msmall_backup.traffic_jobs set charged_bytes=least(p_bytes,reserved_bytes),reserved_bytes=0 where id=p_job;
            end if;
            update msmall_backup.traffic_jobs set status=case p_action when 'prepare' then 'prepared' when 'finish' then 'completed' else 'failed' end,
                expires_at=least(v_now+interval '2 minutes',v_reset) where id=p_job;
        end if;
    end if;
    select * into v_usage from msmall_backup.traffic_usage where plan_id=v_plan.id and week_start=v_week;
    v_remaining:=greatest(0,v_plan.weekly_bytes-v_usage.used_bytes-v_usage.reserved_bytes);
    if p_action='reserve' then
        v_reason:=case
          when not v_plan.enabled then 'disabled'
          when p_job is null then 'invalid_request'
          when p_days<1 or p_days>coalesce((select max_range_days from public.import_backup_policy where id),90) then 'date_range'
          when exists(select 1 from msmall_backup.traffic_jobs where mall_id=p_mall and status in ('generating','prepared')) then 'mall_concurrency'
          when v_remaining < case when p_mode='download' then 1 else 2 end then 'weekly_bytes'
          when p_actor is not null and p_mode<>'download' and exists(select 1 from msmall_backup.traffic_jobs
            where mall_id=p_mall and actor_id is not null and mode<>'download'
            and created_at>v_now-pg_catalog.make_interval(secs=>coalesce((select min_interval_seconds from public.import_backup_policy where id),60))) then 'frequency'
          when p_actor is not null and p_mode<>'download' and (select count(*) from msmall_backup.traffic_jobs
            where mall_id=p_mall and actor_id is not null and mode<>'download'
            and created_at>=(v_now at time zone 'America/Santo_Domingo')::date::timestamp at time zone 'America/Santo_Domingo')
            >= coalesce((select user_daily_downloads from public.import_backup_policy where id),10) then 'daily_downloads'
          else null end;
        v_allowed:=v_reason is null;
        if v_allowed then
            -- Generation budgets cover uncompressed SQL plus the outgoing ZIP.
            v_budget:=least(v_plan.max_file_bytes, v_remaining / case when p_mode='download' then 1 else 2 end);
            insert into msmall_backup.traffic_jobs(id,plan_id,mall_id,actor_id,mode,week_start,reserved_bytes,status,expires_at)
            values(p_job,v_plan.id,p_mall,p_actor,p_mode,v_week,
              v_budget*case when p_mode='download' then 1 else 2 end,'generating',least(v_now+interval '2 minutes',v_reset));
            update msmall_backup.traffic_usage set reserved_bytes=reserved_bytes+v_budget*case when p_mode='download' then 1 else 2 end
              where plan_id=v_plan.id and week_start=v_week;
        end if;
    end if;
    select * into v_usage from msmall_backup.traffic_usage where plan_id=v_plan.id and week_start=v_week;
    return jsonb_build_object('configured',true,'allowed',v_allowed,'reason',v_reason,'max_bytes',v_budget,
        'quota',jsonb_build_object('weekly_bytes',v_plan.weekly_bytes,'used_bytes',v_usage.used_bytes,
          'reserved_bytes',v_usage.reserved_bytes,'remaining_bytes',greatest(0,v_plan.weekly_bytes-v_usage.used_bytes-v_usage.reserved_bytes),
          'resets_at',v_reset,'week_start',v_week,'max_file_bytes',v_plan.max_file_bytes,'enabled',v_plan.enabled,
          'price',0,'timezone','America/Santo_Domingo','shared',true));
end $$;
revoke all on function msmall_backup.traffic_control(text,uuid,uuid,uuid,text,bigint,integer)
from public,anon,authenticated,service_role;
