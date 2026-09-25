-- Return only the latest non-empty import per requested store so exports can
-- include this fact without scanning historical sales.

CREATE OR REPLACE FUNCTION public.audit_latest_imports(
    p_mall_id uuid,
    p_local_ids uuid[]
)
RETURNS TABLE(local_id uuid, ultima_importacion_datos timestamptz)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    WITH selected AS MATERIALIZED (
        SELECT l.id
        FROM public.locales AS l
        WHERE l.mall_id = p_mall_id
          AND l.id = ANY(p_local_ids)
    )
    SELECT s.id, latest.fecha_hora
    FROM selected AS s
    LEFT JOIN LATERAL (
        SELECT l.fecha_hora
        FROM public.logs_carga AS l
        WHERE l.mall_id = p_mall_id
          AND l.local_id = s.id
          AND coalesce(
              l.records_processed,
              CASE
                  WHEN (l.metadata ->> 'records_processed') ~ '^[0-9]+$'
                  THEN (l.metadata ->> 'records_processed')::numeric
                  ELSE 0
              END
          ) > 0
        ORDER BY l.fecha_hora DESC
        LIMIT 1
    ) AS latest ON true;
$$;

REVOKE ALL ON FUNCTION public.audit_latest_imports(uuid, uuid[])
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.audit_latest_imports(uuid, uuid[])
    TO service_role;

NOTIFY pgrst, 'reload schema';
