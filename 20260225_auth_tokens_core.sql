-- Central token auth backend for MsMall + MsExportador
-- Uses mall_id (not tenant_id)

create extension if not exists pgcrypto;

create table if not exists service_accounts (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null,
  local_id uuid null,
  token_type text not null check (token_type in ('app','exporter')),
  client_id text not null unique,
  client_secret_hash text not null,
  scopes jsonb not null default '[]'::jsonb,
  status text not null default 'active' check (status in ('active','disabled','revoked')),
  created_by text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint service_accounts_exporter_local_ck check (token_type <> 'exporter' or local_id is not null)
);

create index if not exists idx_service_accounts_mall_local on service_accounts (mall_id, local_id);
create index if not exists idx_service_accounts_status on service_accounts (status);

create table if not exists api_tokens (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null,
  local_id uuid null,
  token_type text not null check (token_type in ('app','exporter')),
  scopes jsonb not null default '[]'::jsonb,
  jti uuid not null unique,
  access_expires_at timestamptz not null,
  refresh_token_hash text not null,
  refresh_expires_at timestamptz not null,
  status text not null default 'active' check (status in ('active','disabled','revoked')),
  created_by text null,
  last_used_at timestamptz null,
  last_used_ip text null,
  last_used_ua text null,
  revoked_at timestamptz null,
  revoked_by text null,
  revoke_reason text null,
  service_account_id uuid null references service_accounts(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint api_tokens_exporter_local_ck check (token_type <> 'exporter' or local_id is not null)
);

create index if not exists idx_api_tokens_mall_local on api_tokens (mall_id, local_id);
create index if not exists idx_api_tokens_status on api_tokens (status);
create index if not exists idx_api_tokens_type on api_tokens (token_type);
create index if not exists idx_api_tokens_last_used on api_tokens (last_used_at desc);

create table if not exists token_audit_log (
  id bigserial primary key,
  token_id uuid null references api_tokens(id) on delete set null,
  event_type text not null check (event_type in ('issued','refreshed','revoked','used','failed')),
  mall_id uuid null,
  local_id uuid null,
  ip text null,
  ua text null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_token_audit_log_token_id on token_audit_log (token_id);
create index if not exists idx_token_audit_log_mall_local on token_audit_log (mall_id, local_id);
create index if not exists idx_token_audit_log_event_created on token_audit_log (event_type, created_at desc);
