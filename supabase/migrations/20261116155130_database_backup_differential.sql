-- No triggers or writes are added to operational tables. One replaceable baseline per Mall.
create schema if not exists msmall_backup;
revoke all on schema msmall_backup from public, anon, authenticated, service_role;

create table msmall_backup.baselines (
    id uuid primary key,
    mall_id uuid not null unique,
    created_at timestamptz not null default now(),
    schema_hash text not null,
    row_count bigint not null default 0,
    sql_bytes bigint not null default 0
);
create table msmall_backup.row_fingerprints (
    baseline_id uuid not null references msmall_backup.baselines(id) on delete cascade,
    table_name text not null,
    row_key jsonb not null,
    row_hash bytea not null,
    primary key (baseline_id, table_name, row_key)
);
alter table msmall_backup.baselines enable row level security;
alter table msmall_backup.row_fingerprints enable row level security;
revoke all on all tables in schema msmall_backup from public, anon, authenticated, service_role;
comment on schema msmall_backup is 'Private SQL backup baselines. Access only through the backend PostgreSQL backup role.';
