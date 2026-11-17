-- Portal data is only accessible through authenticated, grant-checked backend routes.
create table public.client_portal_grants (
    user_id uuid not null references auth.users(id) on delete cascade,
    local_id uuid not null references public.locales(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, local_id),
    unique (user_id)
);
create table public.client_portal_mappings (
    user_id uuid not null,
    local_id uuid not null,
    signature text not null,
    mapping jsonb not null,
    options jsonb not null default '{}',
    primary key (user_id, local_id, signature),
    foreign key (user_id, local_id) references public.client_portal_grants(user_id, local_id) on delete cascade
);
create table public.client_portal_uploads (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    local_id uuid not null references public.locales(id) on delete cascade,
    filename text not null,
    fingerprint text not null,
    status text not null check (status in ('processing', 'success', 'error', 'partial')),
    records_processed integer not null default 0,
    errors jsonb not null default '[]',
    created_at timestamptz not null default now()
);
create index client_portal_uploads_history on public.client_portal_uploads(user_id, local_id, created_at desc);
alter table public.client_portal_grants enable row level security;
alter table public.client_portal_mappings enable row level security;
alter table public.client_portal_uploads enable row level security;
revoke all on public.client_portal_grants, public.client_portal_mappings, public.client_portal_uploads from public, anon, authenticated;
grant select, insert, update, delete on public.client_portal_grants, public.client_portal_mappings, public.client_portal_uploads to service_role;
