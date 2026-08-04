create table if not exists public.system_audit_logs (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    usuario_id uuid null references auth.users(id) on delete set null,
    mall_id uuid null references public.malls(id) on delete set null,
    accion text not null,
    detalle text null,
    metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_system_audit_logs_mall_created_at
    on public.system_audit_logs (mall_id, created_at desc);

create index if not exists idx_system_audit_logs_action_created_at
    on public.system_audit_logs (accion, created_at desc);

alter table public.system_audit_logs enable row level security;

revoke all on table public.system_audit_logs from anon;
revoke all on table public.system_audit_logs from authenticated;
grant select on table public.system_audit_logs to authenticated;
grant all on table public.system_audit_logs to service_role;

drop policy if exists system_audit_logs_select_by_mall_admin
    on public.system_audit_logs;

create policy system_audit_logs_select_by_mall_admin
on public.system_audit_logs
for select
to authenticated
using (
    mall_id is not null
    and exists (
        select 1
        from public.usuarios_malls membership
        where membership.usuario_id = (select auth.uid())
          and membership.mall_id = system_audit_logs.mall_id
          and lower(coalesce(membership.rol, '')) in ('admin', 'tic', 'it')
    )
);
