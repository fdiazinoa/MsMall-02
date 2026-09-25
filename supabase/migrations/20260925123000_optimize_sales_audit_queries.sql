-- Keep sales-audit work inside Postgres and return only aggregates to the API.
-- All objects are schema-qualified so these SECURITY INVOKER functions can be
-- inlined and planned with the concrete mall/date arguments from each call.

CREATE OR REPLACE FUNCTION public.audit_sales_dates(
    p_mall_id uuid,
    p_local_ids uuid[],
    p_start date,
    p_end date
)
RETURNS TABLE(local_id uuid, fecha date)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT v.local_id, v.fecha
    FROM public.ventas AS v
    WHERE v.mall_id = p_mall_id
      AND v.local_id = ANY(p_local_ids)
      AND v.fecha BETWEEN p_start AND p_end
    GROUP BY v.local_id, v.fecha
    ORDER BY v.local_id, v.fecha;
$$;

REVOKE ALL ON FUNCTION public.audit_sales_dates(uuid, uuid[], date, date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.audit_sales_dates(uuid, uuid[], date, date)
    TO service_role;

CREATE OR REPLACE FUNCTION public.audit_sales_summary(
    p_mall_id uuid,
    p_start date,
    p_end date,
    p_local_id uuid DEFAULT NULL
)
RETURNS TABLE(
    local_id uuid,
    local_nombre text,
    mall_nombre text,
    total_bruto numeric,
    total_impuestos numeric,
    total_neto numeric
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    WITH totals AS (
        SELECT
            v.local_id,
            sum(
                CASE
                    WHEN abs(coalesce(v.total_bruto, 0)::numeric -
                             (coalesce(v.total_neto, 0)::numeric + coalesce(v.total_impuestos, 0)::numeric)) + 0.05
                         < abs(coalesce(v.total_neto, 0)::numeric -
                               (coalesce(v.total_bruto, 0)::numeric + coalesce(v.total_impuestos, 0)::numeric))
                    THEN coalesce(v.total_neto, 0)::numeric
                    ELSE coalesce(v.total_bruto, 0)::numeric
                END
            ) AS bruto,
            sum(coalesce(v.total_impuestos, 0)::numeric) AS impuestos,
            sum(
                CASE
                    WHEN abs(coalesce(v.total_bruto, 0)::numeric -
                             (coalesce(v.total_neto, 0)::numeric + coalesce(v.total_impuestos, 0)::numeric)) + 0.05
                         < abs(coalesce(v.total_neto, 0)::numeric -
                               (coalesce(v.total_bruto, 0)::numeric + coalesce(v.total_impuestos, 0)::numeric))
                    THEN coalesce(v.total_bruto, 0)::numeric
                    ELSE coalesce(v.total_neto, 0)::numeric
                END
            ) AS neto
        FROM public.ventas AS v
        WHERE v.mall_id = p_mall_id
          AND v.fecha BETWEEN p_start AND p_end
          AND (p_local_id IS NULL OR v.local_id = p_local_id)
        GROUP BY v.local_id
    )
    SELECT
        l.id,
        l.nombre::text,
        m.nombre::text,
        coalesce(t.bruto, 0),
        coalesce(t.impuestos, 0),
        coalesce(t.neto, 0)
    FROM public.locales AS l
    JOIN public.malls AS m ON m.id = l.mall_id
    LEFT JOIN totals AS t ON t.local_id = l.id
    WHERE l.mall_id = p_mall_id
      AND (p_local_id IS NULL OR l.id = p_local_id)
    ORDER BY l.nombre, l.id;
$$;

REVOKE ALL ON FUNCTION public.audit_sales_summary(uuid, date, date, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.audit_sales_summary(uuid, date, date, uuid)
    TO service_role;

CREATE OR REPLACE FUNCTION public.audit_annual_status(
    p_mall_id uuid,
    p_local_ids uuid[],
    p_start date,
    p_end date
)
RETURNS TABLE(
    local_id uuid,
    ultima_importacion_datos timestamptz,
    dias_reportados bigint
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    WITH selected AS MATERIALIZED (
        SELECT l.id
        FROM public.locales AS l
        WHERE l.mall_id = p_mall_id
          AND l.id = ANY(p_local_ids)
    ),
    sales AS (
        SELECT v.local_id, count(DISTINCT v.fecha) AS reported
        FROM public.ventas AS v
        JOIN selected AS s ON s.id = v.local_id
        WHERE v.mall_id = p_mall_id
          AND v.fecha >= p_start
          AND v.fecha <= least(
              p_end,
              (now() AT TIME ZONE 'America/Santo_Domingo')::date - 1
          )
        GROUP BY v.local_id
    )
    SELECT
        s.id,
        latest.fecha_hora,
        coalesce(v.reported, 0)
    FROM selected AS s
    LEFT JOIN sales AS v ON v.local_id = s.id
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

REVOKE ALL ON FUNCTION public.audit_annual_status(uuid, uuid[], date, date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.audit_annual_status(uuid, uuid[], date, date)
    TO service_role;

NOTIFY pgrst, 'reload schema';
