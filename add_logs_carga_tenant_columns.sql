-- Tenant hardening for logs_carga: add local_id + mall_id and backfill safely.

ALTER TABLE public.logs_carga
  ADD COLUMN IF NOT EXISTS local_id uuid,
  ADD COLUMN IF NOT EXISTS mall_id uuid;

-- Helpful indexes for monitor/cleanup queries.
CREATE INDEX IF NOT EXISTS idx_logs_carga_mall_fecha
  ON public.logs_carga (mall_id, fecha_hora DESC);

CREATE INDEX IF NOT EXISTS idx_logs_carga_local_fecha
  ON public.logs_carga (local_id, fecha_hora DESC);

-- 1) Backfill local_id/mall_id when local name maps unambiguously to exactly one local.
UPDATE public.logs_carga lc
SET
  local_id = l.id,
  mall_id = l.mall_id
FROM public.locales l
WHERE lc.local_id IS NULL
  AND lc.local_nombre = l.nombre
  AND NOT EXISTS (
    SELECT 1
    FROM public.locales l2
    WHERE l2.nombre = lc.local_nombre
      AND l2.id <> l.id
  );

-- 2) Ensure mall_id from local_id whenever local_id is present.
UPDATE public.logs_carga lc
SET mall_id = l.mall_id
FROM public.locales l
WHERE lc.local_id = l.id
  AND (lc.mall_id IS NULL OR lc.mall_id <> l.mall_id);

-- Optional sanity view for unresolved legacy rows (review manually).
-- SELECT id, fecha_hora, local_nombre, archivo
-- FROM public.logs_carga
-- WHERE mall_id IS NULL;
