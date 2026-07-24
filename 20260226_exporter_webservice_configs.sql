-- Configuracion formal por local para recepcion de ERP via webservice exporter.
-- Permite habilitar/deshabilitar y controlar granularidad/contrato esperado.

create extension if not exists pgcrypto;

create table if not exists public.exporter_webservice_configs (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null,
  local_id uuid not null references public.locales(id) on delete cascade,
  enabled boolean not null default true,
  contract_type text not null default 'msmall_sales_v1',
  default_granularity text not null default 'transaction',
  allow_transaction boolean not null default true,
  allow_daily boolean not null default true,
  strict_validation boolean not null default true,
  notes text,
  updated_by text,
  last_ingest_at timestamptz,
  last_ingest_status text,
  last_ingest_message text,
  last_ingest_granularity text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint exporter_webservice_configs_local_unique unique (local_id),
  constraint exporter_webservice_configs_contract_type_chk check (contract_type in ('msmall_sales_v1')),
  constraint exporter_webservice_configs_default_granularity_chk check (default_granularity in ('transaction', 'daily'))
);

create index if not exists idx_exporter_webservice_configs_mall
  on public.exporter_webservice_configs (mall_id);

create index if not exists idx_exporter_webservice_configs_enabled
  on public.exporter_webservice_configs (enabled);

