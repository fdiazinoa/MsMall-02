-- RPC functions for insights performance at scale.
-- Execute in Supabase SQL Editor.

-- =========================================================
-- 1) Ranking RPC
-- =========================================================
CREATE OR REPLACE FUNCTION public.get_insights_ranking(
  metric_param text,
  mall_id_param uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  nombre text,
  valor double precision,
  extra text
)
LANGUAGE sql
STABLE
AS $$
WITH stores AS (
  SELECT
    l.id,
    l.nombre,
    COALESCE(NULLIF(regexp_replace(COALESCE(l.mts::text, ''), '[^0-9.-]', '', 'g'), '')::numeric, 1) AS mts,
    COALESCE(l.rubro, 'General') AS rubro,
    COALESCE(NULLIF(regexp_replace(COALESCE(l.renta_fija::text, ''), '[^0-9.-]', '', 'g'), '')::numeric, 0) AS renta_fija,
    COALESCE(
      NULLIF(regexp_replace(COALESCE(NULLIF(l.porcentaje_variable, 0)::text, ''), '[^0-9.-]', '', 'g'), '')::numeric,
      NULLIF(regexp_replace(COALESCE(l.porciento_renta::text, ''), '[^0-9.-]', '', 'g'), '')::numeric,
      0
    ) AS pct_variable
  FROM public.locales l
  WHERE mall_id_param IS NULL OR l.mall_id = mall_id_param
),
sales AS (
  SELECT
    v.local_id,
    COALESCE(SUM(v.total_bruto), 0)::numeric AS bruto,
    COALESCE(SUM(v.total_neto), 0)::numeric AS neto
  FROM public.ventas v
  INNER JOIN stores s ON s.id = v.local_id
  GROUP BY v.local_id
),
scored AS (
  SELECT
    s.id,
    s.nombre,
    s.mts,
    s.rubro,
    COALESCE(sa.neto, 0)::numeric AS neto,
    CASE
      WHEN s.renta_fija > 0 THEN s.renta_fija
      WHEN s.pct_variable > 0 AND COALESCE(sa.neto, 0) > 0 THEN (COALESCE(sa.neto, 0) * s.pct_variable) / 100
      ELSE 0
    END AS occupancy_cost,
    CASE
      WHEN s.renta_fija > 0 THEN 'renta_fija'
      WHEN s.pct_variable > 0 THEN 'porcentaje_variable'
      ELSE 'sin_configuracion'
    END AS cost_source
  FROM stores s
  LEFT JOIN sales sa ON sa.local_id = s.id
)
SELECT
  sc.id,
  sc.nombre,
  CASE
    WHEN metric_param = 'sales_per_m2' THEN (sc.neto / NULLIF(sc.mts, 0))::double precision
    WHEN metric_param = 'occupancy_cost' THEN (CASE WHEN sc.neto > 0 THEN (sc.occupancy_cost / sc.neto) * 100 ELSE 0 END)::double precision
    ELSE 0::double precision
  END AS valor,
  CASE
    WHEN metric_param = 'sales_per_m2' THEN (sc.mts::text || ' m²')
    WHEN metric_param = 'occupancy_cost' THEN
      CASE
        WHEN sc.neto = 0 THEN 'Sin Ventas'
        WHEN sc.cost_source = 'sin_configuracion' THEN 'Sin Config'
        WHEN (sc.occupancy_cost / sc.neto) * 100 < 15 THEN 'Saludable'
        ELSE 'Riesgo'
      END
    ELSE sc.rubro
  END AS extra
FROM scored sc
ORDER BY valor DESC;
$$;

-- =========================================================
-- 2) Heatmap RPC
-- =========================================================
CREATE OR REPLACE FUNCTION public.get_insights_heatmap(
  local_id_param uuid
)
RETURNS TABLE (
  dia text,
  hora text,
  valor double precision
)
LANGUAGE sql
STABLE
AS $$
WITH sampled AS (
  SELECT
    v.fecha::date AS fecha,
    COALESCE(v.hora_transaccion, '12:00:00'::time) AS hora_tx
  FROM public.ventas v
  WHERE v.local_id = local_id_param
  ORDER BY v.fecha DESC
  LIMIT 2000
),
bucketed AS (
  SELECT
    CASE EXTRACT(ISODOW FROM s.fecha)
      WHEN 1 THEN 'Lunes'
      WHEN 2 THEN 'Martes'
      WHEN 3 THEN 'Miércoles'
      WHEN 4 THEN 'Jueves'
      WHEN 5 THEN 'Viernes'
      WHEN 6 THEN 'Sábado'
      WHEN 7 THEN 'Domingo'
    END AS dia,
    LPAD(
      GREATEST(
        10,
        LEAST(
          22,
          (FLOOR(EXTRACT(HOUR FROM s.hora_tx) / 2) * 2)::int
        )
      )::text,
      2,
      '0'
    ) || ':00' AS hora,
    COUNT(*)::numeric AS cnt
  FROM sampled s
  GROUP BY 1, 2
),
max_cnt AS (
  SELECT GREATEST(COALESCE(MAX(b.cnt), 0), 1) AS max_value
  FROM bucketed b
),
days AS (
  SELECT * FROM (VALUES
    ('Lunes', 1), ('Martes', 2), ('Miércoles', 3), ('Jueves', 4),
    ('Viernes', 5), ('Sábado', 6), ('Domingo', 7)
  ) AS d(name, ord)
),
hours AS (
  SELECT * FROM (VALUES
    ('10:00', 1), ('12:00', 2), ('14:00', 3), ('16:00', 4),
    ('18:00', 5), ('20:00', 6), ('22:00', 7)
  ) AS h(slot, ord)
)
SELECT
  d.name AS dia,
  h.slot AS hora,
  ROUND((COALESCE(b.cnt, 0) / m.max_value) * 100.0, 2)::double precision AS valor
FROM days d
CROSS JOIN hours h
CROSS JOIN max_cnt m
LEFT JOIN bucketed b ON b.dia = d.name AND b.hora = h.slot
ORDER BY d.ord, h.ord;
$$;
