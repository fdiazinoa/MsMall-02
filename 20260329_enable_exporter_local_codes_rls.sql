-- Lock down PostgREST exposure for exporter_local_codes.
-- This table stores tenant/store-level exporter code mappings and is resolved
-- by backend logic, not by direct client access through the Data API.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code

ALTER TABLE IF EXISTS public.exporter_local_codes
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.exporter_local_codes
FORCE ROW LEVEL SECURITY;
