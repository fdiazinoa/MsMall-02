-- PR-5: Connection monitoring + retry audit tables
-- Safe to run on Supabase/PostgreSQL (idempotent)

create table if not exists connection_runs (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null references malls(id) on delete cascade,
  local_id uuid null references locales(id) on delete set null,
  connection_id uuid null references remote_connections(id) on delete set null,
  run_type text not null check (run_type in ('scheduled', 'manual')),
  status text not null check (status in ('ok', 'fail', 'partial')),
  error_code text null check (error_code is null or error_code in ('auth_error', 'timeout', 'endpoint_down', 'validation_error', 'unknown_error')),
  error_message text null,
  started_at timestamptz not null,
  finished_at timestamptz not null,
  duration_ms integer not null default 0 check (duration_ms >= 0),
  created_by uuid null,
  created_at timestamptz not null default now()
);

create index if not exists idx_connection_runs_mall_started_at
  on connection_runs (mall_id, started_at desc);

create index if not exists idx_connection_runs_connection_started_at
  on connection_runs (connection_id, started_at desc);

create index if not exists idx_connection_runs_status_date
  on connection_runs (status, started_at desc);

create table if not exists retry_attempts (
  id uuid primary key default gen_random_uuid(),
  connection_run_id uuid not null references connection_runs(id) on delete cascade,
  attempt_no integer not null check (attempt_no >= 1),
  status text not null check (status in ('ok', 'fail')),
  error_code text null check (error_code is null or error_code in ('auth_error', 'timeout', 'endpoint_down', 'validation_error', 'unknown_error')),
  error_message text null,
  attempted_at timestamptz not null,
  duration_ms integer not null default 0 check (duration_ms >= 0),
  -- denormalized tenant/connection keys to simplify policy queries and RBAC-safe filters
  mall_id uuid null references malls(id) on delete set null,
  connection_id uuid null references remote_connections(id) on delete set null
);

create index if not exists idx_retry_attempts_run_attempt_no
  on retry_attempts (connection_run_id, attempt_no desc);

create index if not exists idx_retry_attempts_connection_attempted_at
  on retry_attempts (connection_id, attempted_at desc);

create index if not exists idx_retry_attempts_mall_attempted_at
  on retry_attempts (mall_id, attempted_at desc);
