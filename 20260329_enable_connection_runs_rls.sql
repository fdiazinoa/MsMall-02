-- Lock down PostgREST exposure for connection_runs.
-- Ownership/scope model:
-- - mall_id: primary tenant scope
-- - local_id: optional narrower store scope
-- - created_by: audit field only, not the main access boundary
--
-- Client access model:
-- - SELECT: allowed only to authenticated users that can access the row mall
-- - INSERT/UPDATE/DELETE: no direct client access; backend/service role owns writes

ALTER TABLE IF EXISTS public.connection_runs
ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS public.connection_runs
FORCE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.can_read_connection_run(target_mall_id uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.profiles p
    WHERE p.id = auth.uid()
      AND (
        COALESCE(p.role::text, p.rol::text) = 'admin'
        OR p.mall_assigned_id = target_mall_id
      )
  );
$$;

DROP POLICY IF EXISTS "connection_runs_select_by_mall" ON public.connection_runs;

CREATE POLICY "connection_runs_select_by_mall"
ON public.connection_runs
FOR SELECT
TO authenticated
USING (public.can_read_connection_run(mall_id));
