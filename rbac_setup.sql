-- PASO 1: Base de Datos (Script SQL para Supabase) - Versión Idempotente

-- 1. Crear el tipo ENUM si no existe
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'app_role') THEN
        CREATE TYPE public.app_role AS ENUM ('admin', 'tic', 'auditor');
    END IF;
END$$;

-- 2. Crear o actualizar la tabla profiles
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL PRIMARY KEY,
  nombre_completo TEXT,
  role public.app_role DEFAULT 'auditor' NOT NULL,
  mall_id UUID,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Asegurar que la columna 'role' existe con el tipo correcto si la tabla ya existía
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='profiles' AND column_name='role') THEN
        ALTER TABLE public.profiles ADD COLUMN role public.app_role DEFAULT 'auditor' NOT NULL;
    END IF;
END$$;

-- Habilitar RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 3. Función y Trigger (CREATE OR REPLACE para que sea seguro re-ejecutar)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, nombre_completo, role)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', 'auditor')
  ON CONFLICT (id) DO NOTHING; -- Evita errores si el perfil ya existe
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Eliminar el trigger si ya existe para evitar duplicados al re-ejecutar
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 4. Políticas RLS (Usamos DROP IF EXISTS para poder re-ejecutar el script)
DROP POLICY IF EXISTS "Los usuarios pueden leer sus propios datos" ON public.profiles;
CREATE POLICY "Los usuarios pueden leer sus propios datos"
  ON public.profiles FOR SELECT
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Los admins pueden leer todos los perfiles" ON public.profiles;
CREATE POLICY "Los admins pueden leer todos los perfiles"
  ON public.profiles FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role = 'admin'
    )
  );

-- Políticas para 'locales'
ALTER TABLE public.locales ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Cualquier usuario autenticado puede leer locales" ON public.locales;
CREATE POLICY "Cualquier usuario autenticado puede leer locales"
  ON public.locales FOR SELECT
  TO authenticated
  USING (true);

DROP POLICY IF EXISTS "Solo admin y tic pueden insertar locales" ON public.locales;
CREATE POLICY "Solo admin y tic pueden insertar locales"
  ON public.locales FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'tic')
    )
  );

DROP POLICY IF EXISTS "Solo admin y tic pueden actualizar locales" ON public.locales;
CREATE POLICY "Solo admin y tic pueden actualizar locales"
  ON public.locales FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'tic')
    )
  );
