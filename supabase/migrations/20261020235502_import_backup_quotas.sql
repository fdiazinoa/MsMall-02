-- Backend-only accounting. No sales/import/POS tables are altered.
create table public.import_backup_policy (
    id boolean primary key default true check (id),
    user_concurrency integer not null default 1 check (user_concurrency between 1 and 10),
    mall_concurrency integer not null default 2 check (mall_concurrency between 1 and 50),
    min_interval_seconds integer not null default 60 check (min_interval_seconds between 1 and 86400),
    user_daily_downloads integer not null default 10 check (user_daily_downloads between 1 and 10000),
    max_file_mb integer not null default 50 check (max_file_mb between 1 and 1000),
    user_daily_mb integer not null default 200 check (user_daily_mb between 1 and 100000),
    mall_daily_mb integer not null default 1000 check (mall_daily_mb between 1 and 1000000),
    max_range_days integer not null default 90 check (max_range_days between 1 and 3660),
    updated_at timestamptz not null default now()
);
insert into public.import_backup_policy (id) values (true);

create table public.import_backup_usage (
    scope text not null check (scope in ('user', 'mall')),
    subject_id uuid not null,
    quota_day date not null,
    downloads integer not null default 0 check (downloads >= 0),
    used_bytes bigint not null default 0 check (used_bytes >= 0),
    reserved_bytes bigint not null default 0 check (reserved_bytes >= 0),
    primary key (scope, subject_id, quota_day)
);

create table public.import_backup_jobs (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    mall_id uuid not null references public.malls(id) on delete cascade,
    quota_day date not null,
    status text not null default 'generating' check (status in ('generating','streaming','completed','failed','expired')),
    reserved_bytes bigint not null check (reserved_bytes >= 0),
    output_bytes bigint not null default 0 check (output_bytes >= 0),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    finished_at timestamptz
);
create index import_backup_jobs_expiry on public.import_backup_jobs (expires_at)
    where status in ('generating','streaming');
create index import_backup_jobs_user_active on public.import_backup_jobs (user_id)
    where status in ('generating','streaming');
create index import_backup_jobs_mall_active on public.import_backup_jobs (mall_id)
    where status in ('generating','streaming');
create index import_backup_jobs_user_created on public.import_backup_jobs (user_id, created_at desc);

alter table public.import_backup_policy enable row level security;
alter table public.import_backup_usage enable row level security;
alter table public.import_backup_jobs enable row level security;
revoke all on public.import_backup_policy, public.import_backup_usage, public.import_backup_jobs from public, anon, authenticated;
grant all on public.import_backup_policy, public.import_backup_usage, public.import_backup_jobs to service_role;

create or replace function public.import_backup_quota_control(
    p_action text, p_user_id uuid, p_mall_id uuid,
    p_request_id uuid default null, p_bytes bigint default 0,
    p_days integer default 1, p_policy jsonb default null
) returns jsonb
language plpgsql security invoker set search_path = ''
as $$
declare
    v_now timestamptz;
    v_day date;
    v_reset timestamptz;
    v_policy public.import_backup_policy%rowtype;
    v_user public.import_backup_usage%rowtype;
    v_mall public.import_backup_usage%rowtype;
    v_job public.import_backup_jobs%rowtype;
    v_user_active integer;
    v_mall_active integer;
    v_last timestamptz;
    v_cooldown integer;
    v_reason text;
    v_allowed boolean := true;
    v_retry integer := 0;
    v_budget bigint := 0;
    v_charge bigint;
    v_snapshot jsonb;
begin
    if p_user_id is null or p_mall_id is null or p_bytes < 0
       or p_action not in ('status','reserve','renew','prepare','finish','fail','configure') then
        raise exception 'Invalid backup quota operation' using errcode = '22023';
    end if;
    -- This short lock serializes accounting across API instances. It is never
    -- held during sales queries, CSV generation, or network transmission.
    perform pg_catalog.pg_advisory_xact_lock(784316092410::bigint);
    v_now := pg_catalog.clock_timestamp();
    v_day := (v_now at time zone 'America/Santo_Domingo')::date;
    v_reset := (v_day + 1)::timestamp at time zone 'America/Santo_Domingo';

    -- A crashed worker cannot retain slots forever or silently refund its
    -- unknown consumption. Expired generation is charged its reserved budget.
    for v_job in select * from public.import_backup_jobs
        where status in ('generating','streaming') and expires_at <= v_now
    loop
        update public.import_backup_usage set
            used_bytes = used_bytes + v_job.reserved_bytes,
            reserved_bytes = reserved_bytes - v_job.reserved_bytes
        where quota_day = v_job.quota_day and
            ((scope = 'user' and subject_id = v_job.user_id) or (scope = 'mall' and subject_id = v_job.mall_id));
        update public.import_backup_jobs set status = 'expired',
            output_bytes = output_bytes + reserved_bytes, reserved_bytes = 0, finished_at = v_now
        where id = v_job.id;
    end loop;

    if p_action = 'configure' then
        if p_policy is null or jsonb_typeof(p_policy) <> 'object' then
            raise exception 'Invalid backup policy' using errcode = '22023';
        end if;
        update public.import_backup_policy set
            user_concurrency = coalesce((p_policy->>'user_concurrency')::integer, user_concurrency),
            mall_concurrency = coalesce((p_policy->>'mall_concurrency')::integer, mall_concurrency),
            min_interval_seconds = coalesce((p_policy->>'min_interval_seconds')::integer, min_interval_seconds),
            user_daily_downloads = coalesce((p_policy->>'user_daily_downloads')::integer, user_daily_downloads),
            max_file_mb = coalesce((p_policy->>'max_file_mb')::integer, max_file_mb),
            user_daily_mb = coalesce((p_policy->>'user_daily_mb')::integer, user_daily_mb),
            mall_daily_mb = coalesce((p_policy->>'mall_daily_mb')::integer, mall_daily_mb),
            max_range_days = coalesce((p_policy->>'max_range_days')::integer, max_range_days), updated_at = v_now
        where id;
    end if;
    select * into strict v_policy from public.import_backup_policy where id;
    insert into public.import_backup_usage (scope, subject_id, quota_day)
        values ('user', p_user_id, v_day), ('mall', p_mall_id, v_day) on conflict do nothing;
    select * into strict v_user from public.import_backup_usage where scope = 'user' and subject_id = p_user_id and quota_day = v_day;
    select * into strict v_mall from public.import_backup_usage where scope = 'mall' and subject_id = p_mall_id and quota_day = v_day;

    if p_action in ('renew','prepare','finish','fail') then
        select * into v_job from public.import_backup_jobs where id = p_request_id and user_id = p_user_id and mall_id = p_mall_id;
        if not found or v_job.status not in ('generating','streaming') then
            v_allowed := false;
            v_reason := 'lease_expired';
        elsif p_action = 'renew' then
            update public.import_backup_jobs set expires_at = v_now + interval '2 minutes' where id = v_job.id;
        else
            if p_action = 'prepare' and (v_job.status <> 'generating' or p_bytes > v_job.reserved_bytes) then
                raise exception 'Backup exceeds reserved budget' using errcode = '22023';
            end if;
            v_charge := least(p_bytes, v_job.reserved_bytes);
            update public.import_backup_usage set used_bytes = used_bytes + v_charge,
                reserved_bytes = reserved_bytes - v_job.reserved_bytes
            where quota_day = v_job.quota_day and
                ((scope = 'user' and subject_id = p_user_id) or (scope = 'mall' and subject_id = p_mall_id));
            update public.import_backup_jobs set reserved_bytes = 0, output_bytes = output_bytes + v_charge,
                status = case p_action when 'prepare' then 'streaming' when 'finish' then 'completed' else 'failed' end,
                expires_at = v_now + interval '2 minutes',
                finished_at = case when p_action = 'prepare' then null else v_now end
            where id = v_job.id;
        end if;
    end if;

    select count(*) into v_user_active from public.import_backup_jobs where user_id = p_user_id and status in ('generating','streaming');
    select count(*) into v_mall_active from public.import_backup_jobs where mall_id = p_mall_id and status in ('generating','streaming');
    select max(created_at) into v_last from public.import_backup_jobs where user_id = p_user_id;
    v_cooldown := greatest(0, ceil(extract(epoch from (v_last + make_interval(secs => v_policy.min_interval_seconds) - v_now)))::integer);

    if p_action = 'reserve' then
        if p_request_id is null then
            raise exception 'Request ID required' using errcode = '22023';
        end if;
        v_reason := case
            when p_days < 1 or p_days > v_policy.max_range_days then 'date_range'
            when v_cooldown > 0 then 'frequency'
            when v_user_active >= v_policy.user_concurrency then 'user_concurrency'
            when v_mall_active >= v_policy.mall_concurrency then 'mall_concurrency'
            when v_user.downloads >= v_policy.user_daily_downloads then 'daily_downloads'
            when v_user.used_bytes + v_user.reserved_bytes >= v_policy.user_daily_mb::bigint * 1000000 then 'user_daily_bytes'
            when v_mall.used_bytes + v_mall.reserved_bytes >= v_policy.mall_daily_mb::bigint * 1000000 then 'mall_daily_bytes'
            else null end;
        if v_reason is not null then
            v_allowed := false;
            v_retry := case when v_reason = 'frequency' then v_cooldown
                when v_reason in ('user_concurrency','mall_concurrency') then 20
                when v_reason = 'date_range' then 0
                else ceil(extract(epoch from (v_reset - v_now)))::integer end;
        else
            v_budget := least(v_policy.max_file_mb::bigint * 1000000,
                v_policy.user_daily_mb::bigint * 1000000 - v_user.used_bytes - v_user.reserved_bytes,
                v_policy.mall_daily_mb::bigint * 1000000 - v_mall.used_bytes - v_mall.reserved_bytes);
            insert into public.import_backup_jobs (id,user_id,mall_id,quota_day,reserved_bytes,created_at,expires_at)
                values (p_request_id,p_user_id,p_mall_id,v_day,v_budget,v_now,v_now + interval '2 minutes');
            update public.import_backup_usage set downloads = downloads + 1, reserved_bytes = reserved_bytes + v_budget
                where quota_day = v_day and ((scope = 'user' and subject_id = p_user_id) or (scope = 'mall' and subject_id = p_mall_id));
            v_user_active := v_user_active + 1;
            v_mall_active := v_mall_active + 1;
            v_cooldown := v_policy.min_interval_seconds;
        end if;
    end if;

    select * into strict v_user from public.import_backup_usage where scope = 'user' and subject_id = p_user_id and quota_day = v_day;
    select * into strict v_mall from public.import_backup_usage where scope = 'mall' and subject_id = p_mall_id and quota_day = v_day;
    v_snapshot := jsonb_build_object(
        'quota_day', v_day, 'resets_at', v_reset, 'timezone', 'America/Santo_Domingo',
        'limits', to_jsonb(v_policy) - 'id' - 'updated_at',
        'user', jsonb_build_object('downloads_used',v_user.downloads,
            'downloads_remaining',greatest(0,v_policy.user_daily_downloads - v_user.downloads),
            'used_bytes',v_user.used_bytes,'reserved_bytes',v_user.reserved_bytes,
            'remaining_bytes',greatest(0,v_policy.user_daily_mb::bigint * 1000000 - v_user.used_bytes - v_user.reserved_bytes),
            'active',v_user_active,'cooldown_seconds',v_cooldown),
        'mall', jsonb_build_object('used_bytes',v_mall.used_bytes,'reserved_bytes',v_mall.reserved_bytes,
            'remaining_bytes',greatest(0,v_policy.mall_daily_mb::bigint * 1000000 - v_mall.used_bytes - v_mall.reserved_bytes),
            'active',v_mall_active));
    return jsonb_build_object('allowed',v_allowed,'reason',v_reason,'retry_after',v_retry,
        'request_id',p_request_id,'max_bytes',v_budget,'quota',v_snapshot);
end;
$$;
revoke all on function public.import_backup_quota_control(text,uuid,uuid,uuid,bigint,integer,jsonb) from public, anon, authenticated;
grant execute on function public.import_backup_quota_control(text,uuid,uuid,uuid,bigint,integer,jsonb) to service_role;
