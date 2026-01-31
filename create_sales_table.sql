-- Script para crear la tabla de ventas (sales)

CREATE TABLE IF NOT EXISTS public.sales (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  factura_numero TEXT NOT NULL,
  fecha_venta DATE NOT NULL,
  local_codigo TEXT NOT NULL,
  total_bruto NUMERIC(12, 2) NOT NULL,
  total_impuestos NUMERIC(12, 2) NOT NULL,
  total_neto NUMERIC(12, 2) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Habilitar RLS
ALTER TABLE public.sales ENABLE ROW LEVEL SECURITY;

-- Políticas de seguridad
-- 1. Permitir insertar a usuarios autenticados (Auditores, TIC, Admin)
DROP POLICY IF EXISTS "Usuarios autenticados pueden insertar ventas" ON public.sales;
CREATE POLICY "Usuarios autenticados pueden insertar ventas"
ON public.sales FOR INSERT
TO authenticated
WITH CHECK (true);

-- 2. Permitir leer a usuarios autenticados
DROP POLICY IF EXISTS "Usuarios autenticados pueden ver ventas" ON public.sales;
CREATE POLICY "Usuarios autenticados pueden ver ventas"
ON public.sales FOR SELECT
TO authenticated
USING (true);

-- Índices para mejorar rendimiento de consultas
CREATE INDEX IF NOT EXISTS idx_sales_fecha_venta ON public.sales(fecha_venta);
CREATE INDEX IF NOT EXISTS idx_sales_local_codigo ON public.sales(local_codigo);
