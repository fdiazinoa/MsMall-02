-- Lock down PostgREST exposure for remote_connections.
-- This table stores remote host credentials, including raw password values.
-- Client roles must not access it directly through the Data API.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code
-- - frontend must continue using backend endpoints that sanitize password output

ALTER TABLE IF EXISTS public.remote_connections
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.remote_connections
FORCE ROW LEVEL SECURITY;
