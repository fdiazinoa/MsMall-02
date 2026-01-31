-- Script para crear y poblar la tabla de locales

-- 1. Crear la tabla si no existe
CREATE TABLE IF NOT EXISTS public.locales (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  mall_id UUID DEFAULT gen_random_uuid(), -- Mock ID for now
  codigo_interno TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  rubro TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  responsable TEXT,
  contrato_no TEXT,
  piso TEXT,
  tipo_negocio TEXT,
  mts TEXT,
  porciento_renta TEXT,
  mall_nombre TEXT DEFAULT 'Mall Principal'
);

-- 2. Habilitar RLS (si no estaba ya)
ALTER TABLE public.locales ENABLE ROW LEVEL SECURITY;

-- 3. Políticas de lectura (públicas para autenticados)
DROP POLICY IF EXISTS "Lectura de locales" ON public.locales;
CREATE POLICY "Lectura de locales" ON public.locales FOR SELECT TO authenticated USING (true);

-- 4. Insertar datos de prueba (L001, L002, L003)
INSERT INTO public.locales (codigo_interno, nombre, rubro, responsable, contrato_no, piso, tipo_negocio, mts, porciento_renta)
VALUES 
  ('L001', 'Nike Store', 'Deportes', 'Juan Perez', 'C-001', '1', 'Retail', '120', '8.5'),
  ('L002', 'Adidas', 'Deportes', 'Maria Rodriguez', 'C-002', '1', 'Retail', '110', '8.5'),
  ('L003', 'Zara', 'Moda', 'Carlos Lopez', 'C-003', '2', 'Retail', '200', '9.0')
ON CONFLICT (codigo_interno) DO NOTHING;
