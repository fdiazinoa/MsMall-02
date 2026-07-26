-- Lock down PostgREST exposure for exporter_ingest_contracts.
-- This table stores ingest contract configuration by mall/local and is not
-- currently consumed directly by the frontend.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code

ALTER TABLE IF EXISTS public.exporter_ingest_contracts
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.exporter_ingest_contracts
FORCE ROW LEVEL SECURITY;
