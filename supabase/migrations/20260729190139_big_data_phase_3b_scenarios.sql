-- Big Data Phase 3B: commercial scenarios and accountable action plans.
-- Additive only. The browser never accesses these tables directly; FastAPI
-- validates the authenticated user, mall scope and BIG_DATA_FORECAST first.

begin;

create table public.big_data_scenarios (
    id uuid primary key default gen_random_uuid(),
    mall_id uuid not null references public.malls(id) on delete cascade,
    name text not null check (char_length(btrim(name)) between 2 and 160),
    scenario_type text not null check (
        scenario_type in (
            'PROMOTION',
            'HALLWAY_SALE',
            'MALL_ACTIVITY',
            'HOLIDAY',
            'EXTENDED_HOURS',
            'OTHER'
        )
    ),
    status text not null default 'DRAFT' check (
        status in ('DRAFT', 'APPROVED', 'ACTIVE', 'COMPLETED', 'CANCELLED')
    ),
    start_date date not null,
    end_date date not null,
    adjustment_percent numeric(7,2) not null check (
        adjustment_percent between -60 and 80
    ),
    baseline_sales numeric(18,2) not null,
    scenario_sales numeric(18,2) not null,
    incremental_sales numeric(18,2) not null,
    lower_bound numeric(18,2) not null,
    upper_bound numeric(18,2) not null,
    confidence text not null check (confidence in ('HIGH', 'MEDIUM', 'LOW')),
    model_version text not null,
    assumptions jsonb not null default '{}'::jsonb check (
        jsonb_typeof(assumptions) = 'object'
    ),
    notes text check (notes is null or char_length(notes) <= 2000),
    created_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint big_data_scenarios_valid_range check (end_date >= start_date),
    constraint big_data_scenarios_max_range check (end_date <= start_date + 89),
    constraint big_data_scenarios_bounds_order check (upper_bound >= lower_bound),
    constraint big_data_scenarios_id_mall_uk unique (id, mall_id)
);

create index big_data_scenarios_mall_created_idx
    on public.big_data_scenarios (mall_id, created_at desc);

create index big_data_scenarios_mall_range_idx
    on public.big_data_scenarios (mall_id, start_date, end_date);

create unique index big_data_scenarios_open_identity_idx
    on public.big_data_scenarios (
        mall_id,
        lower(btrim(name)),
        start_date,
        end_date
    )
    where status in ('DRAFT', 'APPROVED', 'ACTIVE');

create table public.big_data_scenario_actions (
    id uuid primary key default gen_random_uuid(),
    scenario_id uuid not null,
    mall_id uuid not null references public.malls(id) on delete cascade,
    title text not null check (char_length(btrim(title)) between 2 and 200),
    status text not null default 'PENDING' check (
        status in ('PENDING', 'IN_PROGRESS', 'DONE', 'CANCELLED')
    ),
    owner_name text check (
        owner_name is null or char_length(btrim(owner_name)) between 2 and 120
    ),
    due_date date,
    notes text check (notes is null or char_length(notes) <= 1000),
    sort_order integer not null default 0 check (sort_order between 0 and 100),
    created_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint big_data_scenario_actions_scenario_mall_fk
        foreign key (scenario_id, mall_id)
        references public.big_data_scenarios(id, mall_id)
        on delete cascade
);

create index big_data_scenario_actions_scenario_status_idx
    on public.big_data_scenario_actions (scenario_id, status, sort_order);

create index big_data_scenario_actions_mall_due_idx
    on public.big_data_scenario_actions (mall_id, due_date)
    where status in ('PENDING', 'IN_PROGRESS');

comment on table public.big_data_scenarios is
    'Phase 3B planning scenarios calculated from a Phase 3A forecast snapshot.';
comment on column public.big_data_scenarios.adjustment_percent is
    'Explicit planning assumption; it is not a causal estimate or guarantee.';
comment on table public.big_data_scenario_actions is
    'Accountable action plan attached to one mall-scoped planning scenario.';

alter table public.big_data_scenarios enable row level security;
alter table public.big_data_scenarios force row level security;
alter table public.big_data_scenario_actions enable row level security;
alter table public.big_data_scenario_actions force row level security;

revoke all on table public.big_data_scenarios
    from public, anon, authenticated;
revoke all on table public.big_data_scenario_actions
    from public, anon, authenticated;

grant select, insert, update, delete
    on table public.big_data_scenarios to service_role;
grant select, insert, update, delete
    on table public.big_data_scenario_actions to service_role;

commit;
