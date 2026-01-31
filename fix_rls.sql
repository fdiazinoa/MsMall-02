-- FIX: Corregir error de recursión infinita en RLS (Error 500)

-- 1. Crear función segura para verificar si es admin (bypassea RLS)
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND role = 'admin'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Eliminar políticas anteriores conflictivas
DROP POLICY IF EXISTS "Los admins pueden leer todos los perfiles" ON public.profiles;
DROP POLICY IF EXISTS "Los usuarios pueden leer sus propios datos" ON public.profiles;

-- 3. Re-crear políticas usando la función segura
CREATE POLICY "Los usuarios pueden leer sus propios datos"
  ON public.profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Los admins pueden leer todos los perfiles"
  ON public.profiles FOR SELECT
  USING ( public.is_admin() );

-- 4. Asegurar que el usuario actual sea admin (por si acaso)
INSERT INTO public.profiles (id, nombre_completo, role)
VALUES ('f04a21ff-725d-4837-8fd1-b6c717ad044e', 'Felix Diaz', 'admin')
ON CONFLICT (id) DO UPDATE
SET role = 'admin';
