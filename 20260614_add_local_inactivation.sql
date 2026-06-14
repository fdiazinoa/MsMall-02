ALTER TABLE public.locales
ADD COLUMN IF NOT EXISTS activo boolean NOT NULL DEFAULT true,
ADD COLUMN IF NOT EXISTS fecha_inactivacion date,
ADD COLUMN IF NOT EXISTS motivo_inactivacion text;

COMMENT ON COLUMN public.locales.activo IS
'Indica si el local participa en listados operativos, estadisticas futuras e importaciones automaticas.';

COMMENT ON COLUMN public.locales.fecha_inactivacion IS
'Fecha efectiva de salida/inactivacion del local.';

COMMENT ON COLUMN public.locales.motivo_inactivacion IS
'Motivo operativo de la inactivacion del local.';

CREATE INDEX IF NOT EXISTS idx_locales_mall_activo
ON public.locales (mall_id, activo);
