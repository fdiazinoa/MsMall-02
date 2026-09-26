-- Restore per-local traceability for the six Santiago Center historical
-- WebService loads that were written directly to ventas without logs_carga.
-- These rows are explicitly marked as backfill: they are not new imports.

WITH target_locals AS (
    SELECT
        l.id AS local_id,
        l.mall_id,
        l.nombre AS local_nombre,
        m.nombre AS mall_nombre
    FROM public.locales AS l
    JOIN public.malls AS m ON m.id = l.mall_id
    WHERE trim(m.nombre) = 'Santiago Center'
      AND l.codigo_interno IN ('7', '13', '60', '106', '137', '139')
), historical_sales AS (
    SELECT
        t.local_id,
        t.mall_id,
        t.local_nombre,
        t.mall_nombre,
        count(*)::integer AS records_processed,
        min(v.fecha) AS sales_date_min,
        max(v.fecha) AS sales_date_max,
        max(v.created_at) AS latest_inserted_at
    FROM target_locals AS t
    JOIN public.ventas AS v
      ON v.mall_id = t.mall_id
     AND v.local_id = t.local_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM public.logs_carga AS existing
        WHERE existing.mall_id = t.mall_id
          AND existing.local_id = t.local_id
          AND coalesce(
              existing.records_processed,
              CASE
                  WHEN (existing.metadata ->> 'records_processed') ~ '^[0-9]+$'
                  THEN (existing.metadata ->> 'records_processed')::numeric
                  ELSE 0
              END
          ) > 0
    )
    GROUP BY t.local_id, t.mall_id, t.local_nombre, t.mall_nombre
)
INSERT INTO public.logs_carga (
    fecha_hora,
    local_nombre,
    archivo,
    estado,
    mensaje,
    batch_id,
    detalles,
    local_id,
    mall_id,
    mall_nombre,
    canal,
    records_processed,
    error_count,
    metadata
)
SELECT
    h.latest_inserted_at,
    h.local_nombre,
    'BACKFILL_HISTORICO',
    'exito',
    'Trazabilidad histórica reconstruida desde ventas existentes; no representa una nueva transmisión WebService.',
    'historical-webservice-backfill:' || h.local_id::text,
    '[]'::jsonb,
    h.local_id,
    h.mall_id,
    h.mall_nombre,
    'WebService',
    h.records_processed,
    0,
    jsonb_build_object(
        'source', 'historical_sales_backfill',
        'origin', 'ventas.created_at',
        'channel_family', 'ERP_WEBSERVICE',
        'backfill', true,
        'records_processed', h.records_processed,
        'sales_date_min', h.sales_date_min,
        'sales_date_max', h.sales_date_max,
        'latest_inserted_at', h.latest_inserted_at
    )
FROM historical_sales AS h;
