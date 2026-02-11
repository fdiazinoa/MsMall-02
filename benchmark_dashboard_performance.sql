-- Benchmark dashboard performance in Supabase/Postgres
-- Usage:
-- 1) Replace the placeholders below.
-- 2) Run each block in SQL Editor.
-- 3) Compare Execution Time / Buffers.

-- =========================
-- Parameters (EDIT THESE)
-- =========================
-- Example:
--   '11111111-2222-3333-4444-555555555555'::uuid
--   '2026-01-01'::date
--   '2026-01-31'::date

-- ---------------------------------------------------
-- A) Baseline: direct aggregation query (no RPC call)
-- ---------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH filtered_sales AS (
  SELECT
    v.local_id,
    v.fecha::date AS fecha,
    COALESCE(v.total_bruto, 0)::numeric AS total_bruto,
    COALESCE(v.total_neto, 0)::numeric AS total_neto
  FROM public.ventas v
  WHERE v.mall_id = 'REPLACE_MALL_ID'::uuid
    AND v.fecha >= 'REPLACE_START_DATE'::date
    AND v.fecha <= 'REPLACE_END_DATE'::date
),
store_totals AS (
  SELECT
    COALESCE(l.nombre, 'Desconocido') AS name,
    SUM(fs.total_bruto)::double precision AS total
  FROM filtered_sales fs
  LEFT JOIN public.locales l ON l.id = fs.local_id
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

-- --------------------------------------------
-- B) Target: RPC function call (current route)
-- --------------------------------------------
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT *
FROM public.get_dashboard_kpis(
  'REPLACE_MALL_ID'::uuid,
  'REPLACE_START_DATE'::date,
  'REPLACE_END_DATE'::date
);

-- ------------------------------------------------------
-- C) Optional: run N times to warm cache and compare p50
-- ------------------------------------------------------
-- SELECT * FROM public.get_dashboard_kpis('REPLACE_MALL_ID'::uuid, 'REPLACE_START_DATE'::date, 'REPLACE_END_DATE'::date);
