alter table if exists api_tokens
  alter column access_expires_at drop not null;
