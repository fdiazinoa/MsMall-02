-- Lock down PostgREST exposure for service_accounts.
-- This table stores client credentials metadata and secret hashes.
-- It should not be readable or writable directly by client roles.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code

ALTER TABLE IF EXISTS public.service_accounts
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.service_accounts
FORCE ROW LEVEL SECURITY;
