-- Lock down PostgREST exposure for exporter_sales_ingest.
-- This is a staging table for WebService sales ingestion and it stores raw_row
-- and raw_meta payloads. Client roles must not access it directly through the
-- Data API.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code

ALTER TABLE IF EXISTS public.exporter_sales_ingest
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.exporter_sales_ingest
FORCE ROW LEVEL SECURITY;
