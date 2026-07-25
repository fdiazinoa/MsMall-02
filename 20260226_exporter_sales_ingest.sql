-- Staging de ingesta para MsExportador -> MsMall (webservice sync_rows)
-- Reutiliza locales.codigo_interno como codigo_cliente resuelto por mall_id + local_id.

create extension if not exists pgcrypto;

create table if not exists public.exporter_sales_ingest (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null,
  local_id uuid not null references public.locales(id) on delete cascade,
  codigo_cliente text not null,
  contract_type text not null default 'msmall_sales_v1',
  granularity text not null check (granularity in ('transaction', 'daily')),
  batch_id text,
  chunk_index integer,
  chunk_total integer,
  row_index integer not null,
  dedup_key text not null unique,
  documento_tipo text,
  documento_numero text,
  resumen_id text,
  cantidad_documentos integer,
  fecha_venta date not null,
  hora_venta time,
  total_bruto numeric(18,2) not null,
  total_impuesto numeric(18,2) not null,
  total_neto numeric(18,2) not null,
  raw_row jsonb not null,
  raw_meta jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_exporter_sales_ingest_mall_local_fecha
  on public.exporter_sales_ingest (mall_id, local_id, fecha_venta);

create index if not exists idx_exporter_sales_ingest_granularity
  on public.exporter_sales_ingest (granularity);

create index if not exists idx_exporter_sales_ingest_batch
  on public.exporter_sales_ingest (batch_id);

