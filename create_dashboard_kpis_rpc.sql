-- Aggregated KPI function for dashboard performance at scale.
-- Execute in Supabase SQL Editor.

CREATE OR REPLACE FUNCTION public.get_dashboard_kpis(
  mall_id_param uuid,
  start_date_param date,
  end_date_param date
)
RETURNS TABLE (
  ventas_totales_bruto double precision,
  ventas_totales_neto double precision,
  transacciones integer,
  ticket_promedio double precision,
  variacion_ventas double precision,
  top_locales jsonb,
  ventas_por_dia jsonb,
  ventas_por_rubro jsonb,
  ventas_por_tienda_completo jsonb
)
LANGUAGE sql
STABLE
AS $$
WITH allowed_locales AS (
  SELECT
    l.id,
    l.nombre
  FROM public.locales l
  WHERE l.mall_id = mall_id_param
),
filtered_sales AS (
  SELECT
    v.local_id,
    v.fecha::date AS fecha,
    COALESCE(v.total_bruto, 0)::numeric AS total_bruto,
    COALESCE(v.total_neto, 0)::numeric AS total_neto
  FROM public.ventas v
  INNER JOIN allowed_locales al ON al.id = v.local_id
  WHERE v.fecha >= start_date_param
    AND v.fecha <= end_date_param
),
store_totals AS (
  SELECT
    al.nombre AS name,
    SUM(fs.total_bruto)::double precision AS total
  FROM filtered_sales fs
  INNER JOIN allowed_locales al ON al.id = fs.local_id
  GROUP BY 1
),
day_totals AS (
  SELECT
    fs.fecha,
    SUM(fs.total_bruto)::double precision AS total
  FROM filtered_sales fs
  GROUP BY fs.fecha
),
kpis AS (
  SELECT
    COALESCE(SUM(fs.total_bruto), 0)::double precision AS total_bruto,
    COALESCE(SUM(fs.total_neto), 0)::double precision AS total_neto,
    COUNT(*)::integer AS transacciones
  FROM filtered_sales fs
)
SELECT
  k.total_bruto AS ventas_totales_bruto,
  k.total_neto AS ventas_totales_neto,
  k.transacciones,
  COALESCE(k.total_bruto / NULLIF(k.transacciones, 0), 0)::double precision AS ticket_promedio,
  0::double precision AS variacion_ventas,
  COALESCE(
    (
      SELECT jsonb_agg(
        jsonb_build_object('name', ranked.name, 'total', ranked.total)
        ORDER BY ranked.total DESC
      )
      FROM (
        SELECT st.name, st.total
        FROM store_totals st
        ORDER BY st.total DESC
        LIMIT 5
      ) ranked
    ),
    '[]'::jsonb
  ) AS top_locales,
  COALESCE(
    (
      SELECT jsonb_agg(
        jsonb_build_object('fecha', to_char(dt.fecha, 'YYYY-MM-DD'), 'total', dt.total)
        ORDER BY dt.fecha ASC
      )
      FROM day_totals dt
    ),
    '[]'::jsonb
  ) AS ventas_por_dia,
  '[]'::jsonb AS ventas_por_rubro,
  COALESCE(
    (
      SELECT jsonb_object_agg(st.name, st.total)
      FROM store_totals st
    ),
    '{}'::jsonb
  ) AS ventas_por_tienda_completo
FROM kpis k;
$$;
