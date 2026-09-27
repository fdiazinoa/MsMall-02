create table if not exists public.copilot_scheduled_tasks (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null references public.malls(id) on delete cascade,
  created_by uuid not null references auth.users(id) on delete cascade,
  recipient_email text not null,
  task_type text not null default 'missing_sales_consecutive'
    check (task_type in ('missing_sales_consecutive')),
  status text not null default 'scheduled'
    check (status in ('scheduled', 'running', 'completed', 'failed', 'cancelled')),
  scheduled_for timestamptz not null,
  timezone text not null default 'America/Santo_Domingo',
  lookback_days integer not null default 7 check (lookback_days between 1 and 90),
  consecutive_days integer not null default 7 check (consecutive_days between 1 and 90),
  instruction text not null,
  idempotency_key text not null unique,
  attempt_count integer not null default 0 check (attempt_count between 0 and 10),
  last_error text,
  result jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  check (consecutive_days <= lookback_days),
  check (char_length(recipient_email) between 3 and 320),
  check (char_length(instruction) between 1 and 1400)
);

create index if not exists copilot_scheduled_tasks_due_idx
  on public.copilot_scheduled_tasks (scheduled_for, id)
  where status = 'scheduled';

create index if not exists copilot_scheduled_tasks_owner_mall_idx
  on public.copilot_scheduled_tasks (created_by, mall_id, created_at desc);

alter table public.copilot_scheduled_tasks enable row level security;

revoke all on table public.copilot_scheduled_tasks from anon, authenticated;
grant all on table public.copilot_scheduled_tasks to service_role;

comment on table public.copilot_scheduled_tasks is
  'Tareas confirmadas desde Copilot. Solo el backend service_role puede leerlas o modificarlas.';
comment on column public.copilot_scheduled_tasks.mall_id is
  'Mall fijado al confirmar la tarea; nunca se resuelve nuevamente desde texto libre.';
comment on column public.copilot_scheduled_tasks.recipient_email is
  'Correo del usuario autenticado que confirmó la tarea.';
comment on column public.copilot_scheduled_tasks.idempotency_key is
  'Evita crear dos tareas cuando se repite una confirmación.';
