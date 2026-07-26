-- Lock down PostgREST exposure for token_audit_log.
-- This table stores token usage/security audit data, including IP and user-agent.
-- Client roles should not access it directly through the Data API.
--
-- Access model:
-- - authenticated / anon: no direct SELECT/INSERT/UPDATE/DELETE policies
-- - backend service role: allowed to read/write through server-side code
-- - frontend should continue using backend endpoints that filter/sanitize access

ALTER TABLE IF EXISTS public.token_audit_log
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.token_audit_log
FORCE ROW LEVEL SECURITY;
