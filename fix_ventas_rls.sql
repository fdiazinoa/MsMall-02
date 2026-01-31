-- Script para corregir permisos RLS en la tabla 'ventas'

-- 1. Habilitar RLS en ventas
ALTER TABLE public.ventas ENABLE ROW LEVEL SECURITY;

-- 2. Permitir INSERT a usuarios autenticados
DROP POLICY IF EXISTS "Permitir insertar ventas a autenticados" ON public.ventas;
CREATE POLICY "Permitir insertar ventas a autenticados"
ON public.ventas FOR INSERT
TO authenticated
WITH CHECK (true);

-- 3. Permitir SELECT a usuarios autenticados
DROP POLICY IF EXISTS "Permitir ver ventas a autenticados" ON public.ventas;
CREATE POLICY "Permitir ver ventas a autenticados"
ON public.ventas FOR SELECT
TO authenticated
USING (true);

-- 4. Permitir UPDATE/DELETE si es necesario (opcional, por ahora solo lectura/escritura básica)
-- DROP POLICY IF EXISTS "Permitir modificar ventas a autenticados" ON public.ventas;
-- CREATE POLICY "Permitir modificar ventas a autenticados" ON public.ventas FOR ALL TO authenticated USING (true);
