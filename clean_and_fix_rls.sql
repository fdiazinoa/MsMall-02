-- SOLUCIÓN DEFINITIVA PARA ERROR 500 (RLS RECURSIVO)

-- 1. Desactivar RLS momentáneamente para asegurar acceso inmediato
ALTER TABLE public.profiles DISABLE ROW LEVEL SECURITY;

-- 2. Borrar TODAS las políticas existentes en 'profiles' para limpiar conflictos
-- Este bloque recorre y borra cualquier política que exista en la tabla
DO $$
DECLARE pol record;
BEGIN
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'profiles' LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.profiles', pol.policyname);
    END LOOP;
END $$;

-- 3. Crear (o reemplazar) la función segura para verificar admin
-- SECURITY DEFINER hace que esta función se ejecute con permisos de superusuario,
-- evitando que se active la política RLS de nuevo (rompiendo el bucle).
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND role = 'admin'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Crear las nuevas políticas limpias
CREATE POLICY "Lectura propia"
  ON public.profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Lectura admin"
  ON public.profiles FOR SELECT
  USING ( public.is_admin() );

-- 5. Reactivar RLS ahora que las políticas son seguras
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
