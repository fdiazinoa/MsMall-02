-- SQL para habilitar eliminación de locales en Supabase
-- Ejecutar en el Editor SQL de Supabase Dashboard

DROP POLICY IF EXISTS "Solo admin y tic pueden eliminar locales" ON public.locales;

CREATE POLICY "Solo admin y tic pueden eliminar locales"
  ON public.locales FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'tic')
    )
  );
