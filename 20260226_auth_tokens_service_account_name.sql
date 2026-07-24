-- Add human-friendly display name for exporter service accounts used by the admin UI
alter table if exists service_accounts
  add column if not exists name text;

create index if not exists idx_service_accounts_name on service_accounts (name);
