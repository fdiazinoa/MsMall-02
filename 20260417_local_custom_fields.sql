create table if not exists public.local_custom_field_definitions (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null references public.malls(id) on delete cascade,
  key text not null,
  label text not null,
  data_type text not null check (data_type in ('text', 'number', 'date', 'select')),
  widget_type text not null check (widget_type in ('textbox', 'select', 'drilldown')),
  required boolean not null default false,
  active boolean not null default true,
  sort_order integer not null default 0,
  parent_field_id uuid null references public.local_custom_field_definitions(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint uq_local_custom_field_definitions_mall_key unique (mall_id, key)
);

create table if not exists public.local_custom_field_options (
  id uuid primary key default gen_random_uuid(),
  field_definition_id uuid not null references public.local_custom_field_definitions(id) on delete cascade,
  label text not null,
  value text not null,
  sort_order integer not null default 0,
  active boolean not null default true,
  parent_option_id uuid null references public.local_custom_field_options(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint uq_local_custom_field_options_value unique (field_definition_id, value)
);

create table if not exists public.local_custom_field_values (
  id uuid primary key default gen_random_uuid(),
  local_id uuid not null references public.locales(id) on delete cascade,
  field_definition_id uuid not null references public.local_custom_field_definitions(id) on delete cascade,
  value_text text null,
  value_number numeric null,
  value_date date null,
  selected_option_id uuid null references public.local_custom_field_options(id) on delete set null,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint uq_local_custom_field_values_local_field unique (local_id, field_definition_id)
);

create index if not exists idx_local_custom_field_definitions_mall on public.local_custom_field_definitions (mall_id, active, sort_order);
create index if not exists idx_local_custom_field_options_field on public.local_custom_field_options (field_definition_id, sort_order);
create index if not exists idx_local_custom_field_values_local on public.local_custom_field_values (local_id);
create index if not exists idx_local_custom_field_values_field on public.local_custom_field_values (field_definition_id);
