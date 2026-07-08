-- Lock down PostgREST exposure for retry_attempts.
-- This table stores internal retry telemetry for connection monitoring and is
-- not meant to be accessed directly by client roles through the Data API.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code

ALTER TABLE IF EXISTS public.retry_attempts
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.retry_attempts
FORCE ROW LEVEL SECURITY;
