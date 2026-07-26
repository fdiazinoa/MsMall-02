-- Lock down PostgREST exposure for exporter_webservice_configs.
-- This table stores mall/local WebService ingest configuration and last-ingest
-- state. The frontend uses backend endpoints with explicit access checks, not
-- direct Data API access.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code

ALTER TABLE IF EXISTS public.exporter_webservice_configs
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.exporter_webservice_configs
FORCE ROW LEVEL SECURITY;
