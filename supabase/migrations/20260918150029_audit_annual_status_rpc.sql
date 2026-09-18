CREATE OR REPLACE FUNCTION public.audit_annual_status(
    p_mall_id uuid, p_local_ids uuid[], p_start date, p_end date
)
RETURNS TABLE (local_id uuid, ultima_importacion_datos timestamptz, dias_reportados bigint)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public
AS $$
    WITH selected AS (
        SELECT id FROM public.locales
        WHERE mall_id = p_mall_id AND id = ANY(p_local_ids)
    ), sales AS (
        SELECT v.local_id, count(DISTINCT v.fecha) AS reported
        FROM public.ventas v
        JOIN selected s ON s.id = v.local_id
        WHERE v.mall_id = p_mall_id AND v.fecha >= p_start
          AND v.fecha <= least(p_end, (now() AT TIME ZONE 'America/Santo_Domingo')::date - 1)
        GROUP BY v.local_id
    )
    SELECT s.id,
        (SELECT l.fecha_hora FROM public.logs_carga l
         WHERE l.mall_id = p_mall_id AND l.local_id = s.id
           AND coalesce(l.records_processed,
               CASE WHEN (l.metadata ->> 'records_processed') ~ '^[0-9]+$'
                    THEN (l.metadata ->> 'records_processed')::numeric ELSE 0 END) > 0
         ORDER BY l.fecha_hora DESC LIMIT 1),
        coalesce(v.reported, 0)
    FROM selected s LEFT JOIN sales v ON v.local_id = s.id;
$$;
REVOKE ALL ON FUNCTION public.audit_annual_status(uuid, uuid[], date, date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.audit_annual_status(uuid, uuid[], date, date) TO service_role;
NOTIFY pgrst, 'reload schema';
