ALTER TABLE public.locales
ADD COLUMN IF NOT EXISTS fecha_corte_importacion DATE;

COMMENT ON COLUMN public.locales.fecha_corte_importacion IS
'Fecha de cierre inclusiva para importaciones de ventas. No se permiten registros con fecha menor o igual a este valor.';
