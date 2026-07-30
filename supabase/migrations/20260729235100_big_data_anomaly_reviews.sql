-- Big Data anomaly investigation workflow.
-- Additive only. FastAPI validates the authenticated user, mall scope and
-- BIG_DATA_CORE before using this backend-only table.

begin;

create table public.big_data_anomaly_reviews (
    id uuid primary key default gen_random_uuid(),
    mall_id uuid not null references public.malls(id) on delete cascade,
    anomaly_date date not null,
    status text not null default 'IN_REVIEW' check (
        status in ('IN_REVIEW', 'EXPLAINED', 'DISMISSED')
    ),
    cause_type text not null default 'UNKNOWN' check (
        cause_type in (
            'UNKNOWN',
            'COMMERCIAL_EVENT',
            'DATA_IMPORT',
            'STORE_ACTIVITY',
            'OPERATIONS',
            'EXTERNAL_FACTOR',
            'DATA_CORRECTION',
            'FALSE_POSITIVE',
            'OTHER'
        )
    ),
    explanation text not null check (
        char_length(btrim(explanation)) between 5 and 2000
    ),
    evidence text check (
        evidence is null or char_length(btrim(evidence)) between 2 and 2000
    ),
    owner_name text check (
        owner_name is null or char_length(btrim(owner_name)) between 2 and 120
    ),
    anomaly_snapshot jsonb not null check (
        jsonb_typeof(anomaly_snapshot) = 'object'
    ),
    created_by uuid references auth.users(id) on delete set null,
    updated_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    resolved_at timestamptz,
    constraint big_data_anomaly_reviews_mall_date_uk
        unique (mall_id, anomaly_date),
    constraint big_data_anomaly_reviews_terminal_cause_check check (
        status = 'IN_REVIEW' or cause_type <> 'UNKNOWN'
    ),
    constraint big_data_anomaly_reviews_resolution_time_check check (
        (
            status = 'IN_REVIEW'
            and resolved_at is null
        )
        or (
            status in ('EXPLAINED', 'DISMISSED')
            and resolved_at is not null
        )
    )
);

create index big_data_anomaly_reviews_open_idx
    on public.big_data_anomaly_reviews (mall_id, updated_at desc)
    where status = 'IN_REVIEW';

comment on table public.big_data_anomaly_reviews is
    'Human investigation and resolution of mall-level analytical anomalies.';
comment on column public.big_data_anomaly_reviews.cause_type is
    'Reviewed cause category; UNKNOWN is only valid while the investigation remains open.';
comment on column public.big_data_anomaly_reviews.anomaly_snapshot is
    'Observed, expected, difference, direction, confidence and model version reviewed by the operator.';

alter table public.big_data_anomaly_reviews enable row level security;
alter table public.big_data_anomaly_reviews force row level security;

revoke all on table public.big_data_anomaly_reviews
    from public, anon, authenticated;

grant select, insert, update, delete
    on table public.big_data_anomaly_reviews to service_role;

commit;
