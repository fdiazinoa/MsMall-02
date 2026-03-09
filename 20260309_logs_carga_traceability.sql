ALTER TABLE public.logs_carga
  ADD COLUMN IF NOT EXISTS mall_id uuid,
  ADD COLUMN IF NOT EXISTS mall_nombre varchar(255),
  ADD COLUMN IF NOT EXISTS local_id uuid,
  ADD COLUMN IF NOT EXISTS canal varchar(50),
  ADD COLUMN IF NOT EXISTS records_processed integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS error_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb;

ALTER TABLE public.logs_carga
  ALTER COLUMN batch_id TYPE text USING batch_id::text;

UPDATE public.logs_carga
SET error_count = COALESCE(error_count, jsonb_array_length(COALESCE(detalles, '[]'::jsonb)));

UPDATE public.logs_carga
SET records_processed = COALESCE(records_processed, 0)
WHERE records_processed IS NULL;

UPDATE public.logs_carga
SET metadata = '{}'::jsonb
WHERE metadata IS NULL;

CREATE INDEX IF NOT EXISTS idx_logs_carga_mall_fecha
  ON public.logs_carga (mall_id, fecha_hora DESC);

CREATE INDEX IF NOT EXISTS idx_logs_carga_local_fecha
  ON public.logs_carga (local_id, fecha_hora DESC);
