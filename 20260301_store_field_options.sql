-- Catalogo editable por mall para Tipo de Negocio y Rubro General.
-- Ejecutar en Supabase SQL Editor antes de usar la gestion persistente desde la UI.

CREATE OR REPLACE FUNCTION public.set_store_field_options_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS public.store_field_options (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id UUID NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  field_name TEXT NOT NULL CHECK (field_name IN ('tipo_negocio', 'rubro')),
  value TEXT NOT NULL,
  value_key TEXT GENERATED ALWAYS AS (lower(btrim(value))) STORED,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT store_field_options_value_not_empty CHECK (length(btrim(value)) > 0),
  CONSTRAINT store_field_options_unique_value UNIQUE (mall_id, field_name, value_key)
);

CREATE INDEX IF NOT EXISTS idx_store_field_options_lookup
  ON public.store_field_options (mall_id, field_name, sort_order, value);

DROP TRIGGER IF EXISTS trg_store_field_options_updated_at ON public.store_field_options;
CREATE TRIGGER trg_store_field_options_updated_at
BEFORE UPDATE ON public.store_field_options
FOR EACH ROW
EXECUTE FUNCTION public.set_store_field_options_updated_at();

ALTER TABLE public.store_field_options ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Cualquier usuario autenticado puede leer catalogos de locales" ON public.store_field_options;
CREATE POLICY "Cualquier usuario autenticado puede leer catalogos de locales"
  ON public.store_field_options FOR SELECT
  TO authenticated
  USING (true);

DROP POLICY IF EXISTS "Solo admin y tic pueden insertar catalogos de locales" ON public.store_field_options;
CREATE POLICY "Solo admin y tic pueden insertar catalogos de locales"
  ON public.store_field_options FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'tic')
    )
  );

DROP POLICY IF EXISTS "Solo admin y tic pueden actualizar catalogos de locales" ON public.store_field_options;
CREATE POLICY "Solo admin y tic pueden actualizar catalogos de locales"
  ON public.store_field_options FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'tic')
    )
  );

DROP POLICY IF EXISTS "Solo admin y tic pueden eliminar catalogos de locales" ON public.store_field_options;
CREATE POLICY "Solo admin y tic pueden eliminar catalogos de locales"
  ON public.store_field_options FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'tic')
    )
  );

DO $$
BEGIN
  IF to_regclass('public.malls') IS NULL THEN
    RAISE NOTICE 'Tabla public.malls no encontrada. Se omite seed del catalogo.';
  ELSE
    INSERT INTO public.store_field_options (mall_id, field_name, value, sort_order)
    SELECT
      malls.id,
      defaults.field_name,
      defaults.value,
      defaults.sort_order
    FROM public.malls AS malls
    CROSS JOIN (
      VALUES
        ('tipo_negocio', 'RETAIL', 1),
        ('tipo_negocio', 'GASTRONOMIA', 2),
        ('tipo_negocio', 'SERVICIOS', 3),
        ('tipo_negocio', 'ENTRETENIMIENTO', 4),
        ('tipo_negocio', 'SALUD', 5),
        ('tipo_negocio', 'BELLEZA', 6),
        ('tipo_negocio', 'HOGAR', 7),
        ('tipo_negocio', 'TECNOLOGIA', 8),
        ('tipo_negocio', 'SUPERMERCADO', 9),
        ('tipo_negocio', 'DEPARTAMENTAL', 10),
        ('tipo_negocio', 'FINANCIERO', 11),
        ('tipo_negocio', 'EDUCACION', 12),
        ('tipo_negocio', 'AUTOMOTRIZ', 13),
        ('tipo_negocio', 'DEPORTES', 14),
        ('tipo_negocio', 'OTROS', 15),
        ('rubro', 'MODA', 1),
        ('rubro', 'ZAPATERIA', 2),
        ('rubro', 'DEPORTES', 3),
        ('rubro', 'FAST FOOD', 4),
        ('rubro', 'RESTAURANTE', 5),
        ('rubro', 'CAFETERIA', 6),
        ('rubro', 'HELADERIA', 7),
        ('rubro', 'JOYERIA', 8),
        ('rubro', 'TECNOLOGIA', 9),
        ('rubro', 'HOGAR Y DECORACION', 10),
        ('rubro', 'SALUD Y FARMACIA', 11),
        ('rubro', 'BELLEZA Y COSMETICA', 12),
        ('rubro', 'SERVICIOS FINANCIEROS', 13),
        ('rubro', 'ENTRETENIMIENTO', 14),
        ('rubro', 'LIBRERIA', 15),
        ('rubro', 'INFANTIL', 16),
        ('rubro', 'SUPERMERCADO', 17),
        ('rubro', 'TELECOMUNICACIONES', 18),
        ('rubro', 'OPTICA', 19),
        ('rubro', 'OTROS', 20)
    ) AS defaults(field_name, value, sort_order)
    ON CONFLICT (mall_id, field_name, value_key) DO NOTHING;
  END IF;
END;
$$;
