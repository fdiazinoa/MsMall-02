-- Evita duplicados de ventas por (local_id, fecha, factura_no)
-- y habilita upsert nativo con on_conflict="local_id,fecha,factura_no".

-- 1) Limpieza opcional de duplicados históricos (conserva el último registro físico por llave).
WITH ranked AS (
  SELECT
    ctid,
    ROW_NUMBER() OVER (
      PARTITION BY local_id, fecha, btrim(factura_no)
      ORDER BY ctid DESC
    ) AS rn
  FROM public.ventas
  WHERE factura_no IS NOT NULL
    AND btrim(factura_no) <> ''
)
DELETE FROM public.ventas v
USING ranked r
WHERE v.ctid = r.ctid
  AND r.rn > 1;

-- 2) Índice único parcial para permitir múltiples filas sin factura_no,
--    pero una sola fila por llave cuando factura_no está presente.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ventas_local_fecha_factura_no
  ON public.ventas (local_id, fecha, factura_no)
  WHERE factura_no IS NOT NULL
    AND btrim(factura_no) <> '';
