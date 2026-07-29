-- Contextual calendar for mall-specific events that can explain sales movements.
-- The frontend never accesses this table directly: authenticated writes go
-- through the FastAPI service, which uses the service role after mall/role checks.

create table public.big_data_calendar_events (
    id uuid primary key default gen_random_uuid(),
    mall_id uuid not null references public.malls(id) on delete cascade,
    name text not null check (char_length(btrim(name)) between 2 and 160),
    event_type text not null check (
        event_type in ('PROMOTION', 'HALLWAY_SALE', 'MALL_ACTIVITY', 'HOLIDAY', 'OTHER')
    ),
    start_date date not null,
    end_date date not null,
    expected_impact text not null default 'UP' check (
        expected_impact in ('UP', 'DOWN', 'NEUTRAL')
    ),
    notes text check (notes is null or char_length(notes) <= 1000),
    active boolean not null default true,
    created_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint big_data_calendar_events_valid_range check (end_date >= start_date),
    constraint big_data_calendar_events_max_range check (end_date <= start_date + 366)
);

comment on table public.big_data_calendar_events is
    'Mall-specific commercial context used to separate explained movements from unexplained anomalies.';

create index big_data_calendar_events_active_range_idx
    on public.big_data_calendar_events (mall_id, start_date, end_date)
    where active;

create unique index big_data_calendar_events_active_identity_idx
    on public.big_data_calendar_events (mall_id, lower(btrim(name)), start_date, end_date)
    where active;

alter table public.big_data_calendar_events enable row level security;

revoke all on table public.big_data_calendar_events from anon, authenticated;
grant select, insert, update, delete on table public.big_data_calendar_events to service_role;
