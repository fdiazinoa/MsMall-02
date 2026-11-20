create table msmall_backup.sql_schedules (
    mall_id uuid primary key references msmall_backup.traffic_malls(mall_id),
    enabled boolean not null default false,
    run_hour integer not null default 2 check (run_hour between 0 and 23),
    next_run_at timestamptz not null,
    claim_until timestamptz,
    updated_at timestamptz not null default now(),
    last_error text
);
create table msmall_backup.sql_artifacts (
    id uuid primary key,
    mall_id uuid not null,
    mode text not null check (mode in ('base','differential')),
    base_id uuid,
    scheduled_day date not null,
    object_prefix text not null unique,
    bytes bigint not null default 0 check (bytes between 0 and 5000000000),
    chunks integer not null default 0 check (chunks >= 0),
    uploaded boolean not null default false,
    status text not null default 'pending' check (status in ('pending','completed','failed','expired')),
    error text,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);
create unique index sql_artifact_daily on msmall_backup.sql_artifacts(mall_id,scheduled_day,mode)
    where status in ('pending','completed') and mode='differential';
alter table msmall_backup.sql_schedules enable row level security;
alter table msmall_backup.sql_artifacts enable row level security;
revoke all on msmall_backup.sql_schedules,msmall_backup.sql_artifacts from public,anon,authenticated,service_role;
