alter table if exists public.api_tokens
  add column if not exists access_never_expires boolean not null default false;

update public.api_tokens
set access_never_expires = true
where access_never_expires is false
  and (
    access_expires_at is null
    or access_expires_at >= timestamptz '9999-01-01 00:00:00+00'
  );

comment on column public.api_tokens.access_never_expires is
  'Preserves the access-token expiration policy across refresh and regeneration.';
